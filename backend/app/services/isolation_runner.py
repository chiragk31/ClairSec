"""
Reusable async isolation steps runner (A2, RULES §5a).

All blocking DockerManager and WorkspaceManager calls are executed off the event
loop in worker threads via anyio.to_thread.run_sync.
"""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable
import anyio

from app.core.logging import set_log_context
from app.core.validators import validate_project_id
from app.database.models import IsolationStatus, ProjectRecord
from app.database.repositories import ProjectRepository
from app.isolation.docker_manager import DockerManager
from app.isolation.errors import IsolationError
from app.isolation.sqlite_adapter import adapt_workspace_for_sqlite
from app.isolation.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


async def execute_isolation_steps(
    project_id: str,
    project_repo: ProjectRepository,
    docker_manager: DockerManager,
    workspace_manager: WorkspaceManager,
    *,
    is_cancelled_fn: Callable[[], Awaitable[bool]] | None = None,
    on_stage_fn: Callable[[str], Awaitable[None]] | None = None,
    scan_id: str | None = None,
) -> ProjectRecord:
    """
    Execute full isolation lifecycle with async discipline:
      1. Workspace creation & SQLite adaptation (off event loop)
      2. Docker image build (off event loop)
      3. Container startup (off event loop)
      4. Proxy startup (off event loop)
      5. Health checking (off event loop)
      6. Error handling & teardown (off event loop)
    """
    validate_project_id(project_id)
    set_log_context(project_id=project_id, stage="isolation")
    start_time = time.monotonic()
    logger.info(
        "Starting isolation steps for project %s",
        project_id[:8],
        extra={"event": "pipeline.stage.started", "stage": "isolation"},
    )

    record = await project_repo.get_by_id(project_id)
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

    async def _transition(stage_name: str) -> None:
        set_log_context(stage=stage_name)
        if on_stage_fn:
            await on_stage_fn(stage_name)

    try:
        # ── Step 1: Create scan workspace ─────────────────────────────
        await _transition("workspace")
        record.isolation_status = IsolationStatus.BUILDING
        record = await project_repo.update(record)

        existing_workspace = await anyio.to_thread.run_sync(
            workspace_manager.get_project_root, project_id
        )
        if existing_workspace.exists():
            logger.info(
                "Existing workspace found for project %s — cleaning up before re-isolation.",
                project_id[:8],
                extra={"event": "workspace.cleanup.re_isolation"},
            )
            await anyio.to_thread.run_sync(workspace_manager.cleanup_workspace, project_id)

        workspace_path = await anyio.to_thread.run_sync(
            workspace_manager.create_scan_workspace, project_id, record.source_path
        )
        workspace_path_str = str(workspace_path)
        record.workspace_path = workspace_path_str
        record = await project_repo.update(record)

        # Adapt workspace for isolated SQLite storage if needed
        await _transition("sqlite_adapter")
        sqlite_result = await anyio.to_thread.run_sync(
            adapt_workspace_for_sqlite, workspace_path
        )
        if not sqlite_result.compatible:
            raise IsolationError(
                f"Incompatible SQLite configuration for project {project_id}: "
                f"{sqlite_result.incompatibility_reason}"
            )

        if is_cancelled_fn and await is_cancelled_fn():
            return record

        # ── Step 2: Build Docker image ────────────────────────────────
        await _transition("docker_build")
        image_tag = docker_manager.image_tag(project_id)
        await anyio.to_thread.run_sync(
            docker_manager.build_image,
            project_id,
            workspace_path,
            record.entry_point,
            record.dependency_file,
        )

        if is_cancelled_fn and await is_cancelled_fn():
            return record

        # ── Step 3: Start container ───────────────────────────────────
        await _transition("docker_container")
        container_id, container_name = await anyio.to_thread.run_sync(
            docker_manager.start_container,
            project_id,
            image_tag,
            None,
            sqlite_result.env_vars,
        )
        record.container_id = container_id
        record.container_name = container_name
        record = await project_repo.update(record)

        if is_cancelled_fn and await is_cancelled_fn():
            return record

        # ── Step 4: Start scanner proxy service (C3.3) ────────────────
        await _transition("docker_proxy")
        proxy_container_id, proxy_port = await anyio.to_thread.run_sync(
            docker_manager.start_proxy,
            project_id,
            container_name,
        )
        record.proxy_container_id = proxy_container_id
        record.proxy_port = proxy_port
        record = await project_repo.update(record)

        if is_cancelled_fn and await is_cancelled_fn():
            return record

        # ── Step 5: Health check via proxy ────────────────────────────
        await _transition("health_check")
        healthy = await anyio.to_thread.run_sync(
            docker_manager.wait_for_healthy, proxy_port
        )
        if not healthy:
            diag = docker_manager.get_last_health_diagnostics()
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
        await _transition("ready")
        record.isolation_status = IsolationStatus.READY
        record.isolation_error = None
        record = await project_repo.update(record)

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

        target_logs: str | None = None
        proxy_logs: str | None = None
        if container_id:
            try:
                target_logs = await anyio.to_thread.run_sync(
                    docker_manager.get_logs, container_id
                )
                if target_logs and target_logs.strip():
                    logger.info(
                        "Captured target container logs before cleanup for %s:\n%s",
                        container_id[:12],
                        target_logs[-2000:],
                        extra={"event": "docker.target.logs", "container_id": container_id[:12]},
                    )
            except Exception as log_err:
                logger.warning("Could not retrieve target logs before cleanup: %s", log_err)
        if record and record.proxy_container_id:
            try:
                proxy_logs = await anyio.to_thread.run_sync(
                    docker_manager.get_logs, record.proxy_container_id
                )
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

        # Best-effort cleanup off the event loop
        set_log_context(stage="cleanup")
        try:
            await anyio.to_thread.run_sync(
                docker_manager.cleanup_all, project_id, container_id
            )
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.error(
                "Cleanup also failed for project %s: %s",
                project_id[:8],
                cleanup_exc,
                exc_info=True,
                extra={"event": "docker.cleanup.failed"},
            )
        try:
            await anyio.to_thread.run_sync(
                workspace_manager.cleanup_workspace, project_id
            )
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.error(
                "Workspace cleanup failed for project %s: %s",
                project_id[:8],
                cleanup_exc,
                exc_info=True,
                extra={"event": "workspace.cleanup.failed"},
            )

        if record:
            record.isolation_status = IsolationStatus.IMPORT_FAILED
            record.isolation_error = full_error_msg[:2000]
            record.container_id = None
            record.container_name = None
            record.proxy_container_id = None
            record.proxy_port = None
            record = await project_repo.update(record)
            return record
        raise
