"""
Job supervisor and async execution service (OPERATIONS §5, RULES §5a).

Rules enforced:
  - No blocking I/O in coroutines: wrapped in anyio.to_thread.run_sync.
  - POST /isolate returns 202 with a job_id immediately; runs in background.
  - Cancellation token checked at phase boundaries and between poll cycles.
  - Reconciles orphaned containers and workspaces on backend startup.
"""
from __future__ import annotations

import asyncio
import logging
import time
from motor.motor_asyncio import AsyncIOMotorDatabase
import anyio

from app.core.validators import validate_project_id
from app.database.models import IsolationStatus, JobRecord, JobStatus, ProjectRecord
from app.database.repositories import JobRepository, ProjectRepository
from app.isolation.docker_manager import DockerManager
from app.isolation.errors import IsolationError
from app.isolation.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        docker_manager: DockerManager | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self._db = db
        self._job_repo = JobRepository(db)
        self._project_repo = ProjectRepository(db)
        self._workspace = workspace_manager or WorkspaceManager()
        self._docker_instance = docker_manager
        self._active_tasks: dict[str, asyncio.Task] = {}

    @property
    def _docker(self) -> DockerManager:
        if self._docker_instance is None:
            self._docker_instance = DockerManager()
        return self._docker_instance

    async def get_job(self, job_id: str) -> JobRecord | None:
        return await self._job_repo.get_by_id(job_id)

    async def cancel_job(self, job_id: str) -> JobRecord | None:
        """
        Request cancellation for an in-flight or queued job.
        Sets cancel_requested=True in DB and in memory.
        """
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            return None

        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.INTERRUPTED):
            return job

        job.cancel_requested = True
        job = await self._job_repo.update(job)
        logger.info("Cancellation requested for job %s (project %s)", job_id, job.project_id[:8])
        return job

    async def submit_isolation_job(self, project_id: str) -> JobRecord:
        """
        Validate project and queue isolation as a background job.
        Returns the created JobRecord immediately (202 Accepted).
        """
        validate_project_id(project_id)
        record = await self._project_repo.get_by_id(project_id)
        if record is None:
            raise IsolationError(f"Project {project_id} not found")

        if record.validation_status.value != "valid":
            raise IsolationError(
                f"Project {project_id} cannot be isolated: validation_status="
                f"{record.validation_status}. Only valid projects can be isolated."
            )

        if not record.entry_point:
            raise IsolationError(
                f"Project {project_id} has no detected entry point. Cannot generate Dockerfile."
            )

        # Create job record
        job = JobRecord(
            project_id=project_id,
            status=JobStatus.PENDING,
            stage="queued",
        )
        job = await self._job_repo.create(job)

        # Spawn background task
        task = asyncio.create_task(
            self._run_isolation_job(job.id, project_id)
        )
        self._active_tasks[job.id] = task

        logger.info("Queued isolation job %s for project %s", job.id, project_id[:8])
        return job

    async def _run_isolation_job(self, job_id: str, project_id: str) -> None:
        """
        Execute the isolation lifecycle in the background with async discipline:
          - Blocking Docker and filesystem work wrapped in anyio.to_thread.run_sync
          - Cancellation token checked at phase boundaries
        """
        job = await self._job_repo.get_by_id(job_id)
        if not job:
            return

        record = await self._project_repo.get_by_id(project_id)
        if not record:
            return

        container_id: str | None = None
        image_tag: str | None = None

        try:
            job.status = JobStatus.RUNNING
            job.stage = "starting"
            await self._job_repo.update(job)

            if await self._is_cancelled(job_id):
                await self._handle_cancelled(job_id, project_id)
                return

            # ── Phase 1: Workspace creation (run in thread pool) ────────────
            job.stage = "creating_workspace"
            await self._job_repo.update(job)

            record.isolation_status = IsolationStatus.BUILDING
            await self._project_repo.update(record)

            # Re-isolating must be idempotent: clean up any workspace left from
            # a previous run (successful or failed) instead of failing with
            # "workspace already exists". Without this, pressing Isolate a
            # second time permanently wedges the project into import_failed.
            if self._workspace.get_project_root(project_id).exists():
                logger.info(
                    "Existing workspace for project %s — cleaning up before re-isolation.",
                    project_id[:8],
                )
                await anyio.to_thread.run_sync(
                    self._workspace.cleanup_workspace, project_id
                )

            workspace_path = await anyio.to_thread.run_sync(
                self._workspace.create_scan_workspace, project_id, record.source_path
            )
            record.workspace_path = str(workspace_path)
            await self._project_repo.update(record)

            if await self._is_cancelled(job_id):
                await self._handle_cancelled(job_id, project_id)
                return

            # ── Phase 2: Build Docker image (run in thread pool) ────────────
            job.stage = "building_image"
            await self._job_repo.update(job)

            image_tag = self._docker.image_tag(project_id)
            await anyio.to_thread.run_sync(
                self._docker.build_image,
                project_id,
                workspace_path,
                record.entry_point,
                record.dependency_file,
            )

            # Cancellation check after image build:
            # Per OPERATIONS §5: Cancel means mark cancelled, clean up image, do not start container
            if await self._is_cancelled(job_id):
                await self._handle_cancelled(job_id, project_id, image_tag=image_tag)
                return

            # ── Phase 3: Start target container (run in thread pool) ────────
            job.stage = "starting_target"
            await self._job_repo.update(job)

            container_id, container_name = await anyio.to_thread.run_sync(
                self._docker.start_container, project_id, image_tag
            )
            record.container_id = container_id
            record.container_name = container_name
            await self._project_repo.update(record)

            if await self._is_cancelled(job_id):
                await self._handle_cancelled(job_id, project_id, container_id=container_id, image_tag=image_tag)
                return

            # ── Phase 4: Start scanner proxy service (run in thread pool) ───
            job.stage = "starting_proxy"
            await self._job_repo.update(job)

            proxy_id, proxy_port = await anyio.to_thread.run_sync(
                self._docker.start_proxy, project_id, container_name
            )
            record.proxy_container_id = proxy_id
            record.proxy_port = proxy_port
            await self._project_repo.update(record)

            if await self._is_cancelled(job_id):
                await self._handle_cancelled(job_id, project_id, container_id=container_id, image_tag=image_tag)
                return

            # ── Phase 5: Health check via proxy (async polling with cancel checks)
            job.stage = "health_checking"
            await self._job_repo.update(job)

            healthy = await self._poll_health_with_cancel(job_id, proxy_port)
            if not healthy:
                if await self._is_cancelled(job_id):
                    await self._handle_cancelled(job_id, project_id, container_id=container_id, image_tag=image_tag)
                    return
                raise IsolationError(
                    f"Container {container_name} failed health check via proxy within startup timeout."
                )

            # ── Phase 6: Ready ──────────────────────────────────────────────
            record.isolation_status = IsolationStatus.READY
            record.isolation_error = None
            await self._project_repo.update(record)

            job.status = JobStatus.COMPLETED
            job.stage = "ready"
            await self._job_repo.update(job)

            logger.info("Isolation job %s completed for project %s", job_id, project_id[:8])

        except Exception as exc:  # noqa: BLE001
            if await self._is_cancelled(job_id):
                await self._handle_cancelled(job_id, project_id, container_id=container_id, image_tag=image_tag)
            else:
                error_msg = str(exc)
                logger.error("Isolation job %s failed: %s", job_id, error_msg)

                job = await self._job_repo.get_by_id(job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error = error_msg[:1000]
                    await self._job_repo.update(job)

                record = await self._project_repo.get_by_id(project_id)
                if record:
                    record.isolation_status = IsolationStatus.IMPORT_FAILED
                    record.isolation_error = error_msg[:2000]
                    record.container_id = None
                    record.container_name = None
                    record.proxy_container_id = None
                    record.proxy_port = None
                    await self._project_repo.update(record)

                try:
                    await anyio.to_thread.run_sync(
                        self._docker.cleanup_all, project_id, container_id
                    )
                except Exception as cleanup_exc:  # noqa: BLE001
                    logger.debug("Docker cleanup error: %s", cleanup_exc)
                try:
                    await anyio.to_thread.run_sync(
                        self._workspace.cleanup_workspace, project_id
                    )
                except Exception as cleanup_exc:  # noqa: BLE001
                    logger.debug("Workspace cleanup error: %s", cleanup_exc)

        finally:
            self._active_tasks.pop(job_id, None)

    async def _is_cancelled(self, job_id: str) -> bool:
        job = await self._job_repo.get_by_id(job_id)
        return bool(job and job.cancel_requested)

    async def _handle_cancelled(
        self,
        job_id: str,
        project_id: str,
        container_id: str | None = None,
        image_tag: str | None = None,
    ) -> None:
        """Teardown on cancellation: prune container, image, and workspace."""
        logger.info("Processing cancellation for job %s (project %s)", job_id, project_id[:8])
        job = await self._job_repo.get_by_id(job_id)
        if job:
            job.status = JobStatus.CANCELLED
            job.stage = "cancelled"
            await self._job_repo.update(job)

        record = await self._project_repo.get_by_id(project_id)
        if record:
            record.isolation_status = IsolationStatus.STOPPED
            record.container_id = None
            record.container_name = None
            record.proxy_container_id = None
            record.proxy_port = None
            await self._project_repo.update(record)

        try:
            await anyio.to_thread.run_sync(self._docker.cleanup_all, project_id, container_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cleanup on cancel error: %s", exc)

        try:
            await anyio.to_thread.run_sync(self._workspace.cleanup_workspace, project_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Workspace cleanup on cancel error: %s", exc)

    async def _poll_health_with_cancel(self, job_id: str, proxy_port: int, timeout_sec: int = 30) -> bool:
        """Poll health endpoint asynchronously, checking for cancellation on each iteration."""
        import httpx
        base_url = f"http://127.0.0.1:{proxy_port}"
        deadline = time.monotonic() + timeout_sec

        async with httpx.AsyncClient(timeout=2.0) as client:
            while time.monotonic() < deadline:
                if await self._is_cancelled(job_id):
                    return False
                for path in ("/health", "/"):
                    try:
                        resp = await client.get(f"{base_url}{path}")
                        if resp.status_code < 400:
                            return True
                    except (httpx.HTTPError, OSError):
                        pass
                await asyncio.sleep(1.0)
        return False

    async def reconcile_startup(self) -> int:
        """
        Reconcile in-flight jobs and containers from a previous backend run (OPERATIONS §5).
        Finds all jobs in 'pending' or 'running' state, marks them 'interrupted',
        and cleans up any orphaned workspaces or containers.
        """
        active_jobs = await self._job_repo.get_active_jobs()
        reconciled_count = 0
        for job in active_jobs:
            job.status = JobStatus.INTERRUPTED
            job.error = "Backend restarted while job was in-flight."
            await self._job_repo.update(job)

            project = await self._project_repo.get_by_id(job.project_id)
            if project:
                if project.isolation_status in (IsolationStatus.BUILDING, IsolationStatus.PENDING):
                    project.isolation_status = IsolationStatus.IMPORT_FAILED
                    project.isolation_error = "Isolation interrupted by backend restart."
                    project.container_id = None
                    project.container_name = None
                    project.proxy_container_id = None
                    project.proxy_port = None
                    await self._project_repo.update(project)

                try:
                    await anyio.to_thread.run_sync(
                        self._docker.cleanup_all, project.id, project.container_id
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Reconcile docker cleanup: %s", exc)

                try:
                    await anyio.to_thread.run_sync(
                        self._workspace.cleanup_workspace, project.id
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Reconcile workspace cleanup: %s", exc)

            reconciled_count += 1

        if reconciled_count:
            logger.info("Startup reconciliation: cleaned up %d interrupted job(s)", reconciled_count)
        return reconciled_count
