"""
Isolation service — orchestrates WorkspaceManager + DockerManager + ProjectRepository.

This service owns the full Phase 3 lifecycle:
  pending → building → ready → running → stopped
  any     → import_failed  (on any unrecoverable error)

SECURITY invariants:
  - Original source_path is never modified.
  - Only the scan_workspace/ copy is given to Docker.
  - No host environment variables flow into the container.
  - Cleanup is always called on failure.
"""
from __future__ import annotations

import asyncio
import logging
import time

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging import set_log_context
from app.core.validators import validate_project_id
from app.database.models import IsolationStatus, ProjectRecord
from app.database.repositories import ProjectRepository
from app.isolation.docker_manager import DockerManager
from app.isolation.errors import IsolationError
from app.isolation.sqlite_adapter import adapt_workspace_for_sqlite
from app.isolation.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class IsolationService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        docker_manager: DockerManager | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self._repo = ProjectRepository(db)
        self._workspace = workspace_manager or WorkspaceManager()
        self._docker_instance = docker_manager

    @property
    def _docker(self) -> DockerManager:
        if self._docker_instance is None:
            self._docker_instance = DockerManager()
        return self._docker_instance

    async def get_project(self, project_id: str) -> ProjectRecord | None:
        validate_project_id(project_id)
        return await self._repo.get_by_id(project_id)

    async def start_isolation(self, project_id: str) -> ProjectRecord:
        """
        Full isolation lifecycle for a validated project:
          1. Verify project is valid and has an entry point.
          2. Create scan workspace (copy of original source).
          3. Build Docker image (with timeout).
          4. Start container (with resource limits, no host env, isolated network).
          5. Health check (with startup timeout).
          6. Mark ready.

        On any failure: cleanup Docker + workspace, mark import_failed with reason.

        Returns the updated ProjectRecord.
        """
        validate_project_id(project_id)
        set_log_context(project_id=project_id, stage="isolation")
        start_time = time.monotonic()
        logger.info(
            "Starting isolation for project %s",
            project_id[:8],
            extra={"event": "pipeline.stage.started", "stage": "isolation"},
        )
        record = await self._repo.get_by_id(project_id)
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

        container_id: str | None = None
        workspace_path_str: str | None = None
        image_tag: str | None = None

        try:
            # ── Step 1: Create scan workspace ─────────────────────────────
            set_log_context(stage="workspace")
            record.isolation_status = IsolationStatus.BUILDING
            record = await self._repo.update(record)

            # Re-isolating a project must be idempotent: a workspace left over
            # from a previous run (successful or failed) is cleaned up first,
            # rather than failing with "workspace already exists". Without this,
            # clicking Isolate twice permanently wedges the project into
            # import_failed.
            existing_workspace = self._workspace.get_project_root(project_id)
            if existing_workspace.exists():
                logger.info(
                    "Existing workspace found for project %s — cleaning up before re-isolation.",
                    project_id[:8],
                    extra={"event": "workspace.cleanup.re_isolation"},
                )
                await asyncio.to_thread(self._workspace.cleanup_workspace, project_id)

            workspace_path = await asyncio.to_thread(
                self._workspace.create_scan_workspace, project_id, record.source_path
            )
            workspace_path_str = str(workspace_path)
            record.workspace_path = workspace_path_str
            record = await self._repo.update(record)

            # Adapt workspace for isolated SQLite storage if needed
            set_log_context(stage="sqlite_adapter")
            sqlite_result = await asyncio.to_thread(
                adapt_workspace_for_sqlite, workspace_path
            )
            if not sqlite_result.compatible:
                raise IsolationError(
                    f"Incompatible SQLite configuration for project {project_id}: "
                    f"{sqlite_result.incompatibility_reason}"
                )

            # ── Step 2: Build Docker image ────────────────────────────────
            set_log_context(stage="docker_build")
            image_tag = self._docker.image_tag(project_id)
            self._docker.build_image(
                project_id=project_id,
                workspace_path=workspace_path,
                entry_point=record.entry_point,
                dependency_file=record.dependency_file,
            )

            # ── Step 3: Start container ───────────────────────────────────
            set_log_context(stage="docker_container")
            container_id, container_name = self._docker.start_container(
                project_id,
                image_tag,
                environment=sqlite_result.env_vars,
            )
            record.container_id = container_id
            record.container_name = container_name
            record = await self._repo.update(record)

            # ── Step 4: Start scanner proxy service (C3.3) ────────────────
            set_log_context(stage="docker_proxy")
            proxy_container_id, proxy_port = self._docker.start_proxy(
                project_id, container_name
            )
            record.proxy_container_id = proxy_container_id
            record.proxy_port = proxy_port
            record = await self._repo.update(record)

            # ── Step 5: Health check via proxy ────────────────────────────
            set_log_context(stage="health_check")
            healthy = self._docker.wait_for_healthy(proxy_port)
            if not healthy:
                diag = self._docker.get_last_health_diagnostics()
                diag_parts = []
                if diag.get("probed_paths"):
                    diag_parts.append(f"probed {', '.join(diag['probed_paths'])}")
                if diag.get("last_status_code") is not None:
                    diag_parts.append(f"HTTP {diag['last_status_code']}")
                if diag.get("last_error"):
                    diag_parts.append(f"error: {diag['last_error']}")
                diag_summary = f" ({'; '.join(diag_parts)})" if diag_parts else ""

                raise IsolationError(
                    f"Container {container_name} failed health check via proxy within "
                    f"the startup timeout{diag_summary}."
                )

            # ── Step 6: Mark ready ────────────────────────────────────────
            set_log_context(stage="ready")
            record.isolation_status = IsolationStatus.READY
            record.isolation_error = None
            record = await self._repo.update(record)

            elapsed = time.monotonic() - start_time
            logger.info(
                "Project %s isolation complete in %.2fs. Container: %s, Proxy port: %s",
                project_id[:8],
                elapsed,
                container_name,
                proxy_port,
                extra={
                    "event": "pipeline.stage.succeeded",
                    "stage": "isolation",
                    "elapsed_sec": round(elapsed, 3),
                    "container_name": container_name,
                    "proxy_port": proxy_port,
                },
            )
            return record

        except (IsolationError, Exception) as exc:  # noqa: BLE001
            elapsed = time.monotonic() - start_time
            error_msg = str(exc)
            logger.error(
                "Isolation failed for project %s after %.2fs: %s",
                project_id[:8],
                elapsed,
                error_msg,
                exc_info=True,
                extra={
                    "event": "pipeline.stage.failed",
                    "stage": "isolation",
                    "elapsed_sec": round(elapsed, 3),
                    "error": error_msg,
                },
            )

            # Capture target and proxy logs BEFORE cleanup
            target_logs: str | None = None
            proxy_logs: str | None = None
            if container_id:
                try:
                    target_logs = self._docker.get_logs(container_id)
                    if target_logs and target_logs.strip():
                        logger.info(
                            "Captured target container logs before cleanup for %s:\n%s",
                            container_id[:12],
                            target_logs[-2000:],
                            extra={"event": "docker.target.logs", "container_id": container_id[:12]},
                        )
                except Exception as log_err:
                    logger.warning("Could not retrieve target logs before cleanup: %s", log_err)
            if record.proxy_container_id:
                try:
                    proxy_logs = self._docker.get_logs(record.proxy_container_id)
                    if proxy_logs and proxy_logs.strip():
                        logger.info(
                            "Captured proxy container logs before cleanup for %s:\n%s",
                            record.proxy_container_id[:12],
                            proxy_logs[-2000:],
                            extra={"event": "docker.proxy.logs", "container_id": record.proxy_container_id[:12]},
                        )
                except Exception as log_err:
                    logger.warning("Could not retrieve proxy logs before cleanup: %s", log_err)

            full_error_msg = error_msg
            if target_logs and target_logs.strip() and not target_logs.startswith("Container "):
                tail = "\n".join(target_logs.strip().splitlines()[-15:])
                full_error_msg = f"{error_msg}\n\nTarget container logs:\n{tail}"
            elif proxy_logs and "bad gateway" in error_msg.lower():
                tail = "\n".join(proxy_logs.strip().splitlines()[-10:])
                full_error_msg = f"{error_msg}\n\nProxy container logs:\n{tail}"

            # Best-effort cleanup — never skip even if partial
            set_log_context(stage="cleanup")
            try:
                self._docker.cleanup_all(project_id, container_id=container_id)
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.error(
                    "Cleanup also failed for project %s: %s",
                    project_id[:8],
                    cleanup_exc,
                    exc_info=True,
                    extra={"event": "docker.cleanup.failed"},
                )
            try:
                self._workspace.cleanup_workspace(project_id)
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.error(
                    "Workspace cleanup failed for project %s: %s",
                    project_id[:8],
                    cleanup_exc,
                    exc_info=True,
                    extra={"event": "workspace.cleanup.failed"},
                )

            # Mark import_failed in DB (truncate error msg to prevent unbounded storage)
            record.isolation_status = IsolationStatus.IMPORT_FAILED
            record.isolation_error = full_error_msg[:2000]
            record.container_id = None
            record.container_name = None
            record.proxy_container_id = None
            record.proxy_port = None
            record = await self._repo.update(record)
            return record

    async def stop_isolation(self, project_id: str) -> ProjectRecord:
        """Stop the container and proxy for a project and mark it stopped."""
        validate_project_id(project_id)
        set_log_context(project_id=project_id, stage="isolation_stop")
        logger.info(
            "Stopping isolation for project %s",
            project_id[:8],
            extra={"event": "isolation.stop.started", "stage": "isolation_stop"},
        )
        record = await self._repo.get_by_id(project_id)
        if record is None:
            raise IsolationError(f"Project {project_id} not found")

        if record.container_id:
            self._docker.stop_container(record.container_id)
        self._docker.stop_proxy(project_id)

        record.isolation_status = IsolationStatus.STOPPED
        record.container_id = None
        record.proxy_container_id = None
        record.proxy_port = None
        rec = await self._repo.update(record)
        logger.info(
            "Stopped isolation for project %s",
            project_id[:8],
            extra={"event": "isolation.stop.succeeded", "stage": "isolation_stop"},
        )
        return rec

    async def cleanup_isolation(self, project_id: str) -> ProjectRecord:
        """Full cleanup: stop container, proxy, remove image, remove workspace, update DB."""
        validate_project_id(project_id)
        set_log_context(project_id=project_id, stage="isolation_cleanup")
        logger.info(
            "Cleaning up isolation for project %s",
            project_id[:8],
            extra={"event": "isolation.cleanup.started", "stage": "isolation_cleanup"},
        )
        record = await self._repo.get_by_id(project_id)
        if record is None:
            raise IsolationError(f"Project {project_id} not found")

        self._docker.cleanup_all(project_id, container_id=record.container_id)
        self._workspace.cleanup_workspace(project_id)

        record.isolation_status = IsolationStatus.PENDING
        record.container_id = None
        record.container_name = None
        record.proxy_container_id = None
        record.proxy_port = None
        record.workspace_path = None
        record.isolation_error = None
        rec = await self._repo.update(record)
        logger.info(
            "Cleaned up isolation for project %s",
            project_id[:8],
            extra={"event": "isolation.cleanup.succeeded", "stage": "isolation_cleanup"},
        )
        return rec

    def get_logs(self, container_id: str) -> str:
        """Return size-limited container logs. Logs are treated as untrusted text."""
        return self._docker.get_logs(container_id)
