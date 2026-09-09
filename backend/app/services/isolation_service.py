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

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.validators import validate_project_id
from app.database.models import IsolationStatus, ProjectRecord
from app.database.repositories import ProjectRepository
from app.isolation.docker_manager import DockerManager
from app.isolation.errors import IsolationError
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
                )
                await asyncio.to_thread(self._workspace.cleanup_workspace, project_id)

            workspace_path = await asyncio.to_thread(
                self._workspace.create_scan_workspace, project_id, record.source_path
            )
            workspace_path_str = str(workspace_path)
            record.workspace_path = workspace_path_str
            record = await self._repo.update(record)

            # ── Step 2: Build Docker image ────────────────────────────────
            image_tag = self._docker.image_tag(project_id)
            self._docker.build_image(
                project_id=project_id,
                workspace_path=workspace_path,
                entry_point=record.entry_point,
                dependency_file=record.dependency_file,
            )

            # ── Step 3: Start container ───────────────────────────────────
            container_id, container_name = self._docker.start_container(
                project_id, image_tag
            )
            record.container_id = container_id
            record.container_name = container_name
            record = await self._repo.update(record)

            # ── Step 4: Start scanner proxy service (C3.3) ────────────────
            proxy_container_id, proxy_port = self._docker.start_proxy(
                project_id, container_name
            )
            record.proxy_container_id = proxy_container_id
            record.proxy_port = proxy_port
            record = await self._repo.update(record)

            # ── Step 5: Health check via proxy ────────────────────────────
            healthy = self._docker.wait_for_healthy(proxy_port)
            if not healthy:
                raise IsolationError(
                    f"Container {container_name} failed health check via proxy within "
                    f"the startup timeout."
                )

            # ── Step 6: Mark ready ────────────────────────────────────────
            record.isolation_status = IsolationStatus.READY
            record.isolation_error = None
            record = await self._repo.update(record)

            logger.info(
                "Project %s isolation complete. Container: %s, Proxy port: %s",
                project_id[:8],
                container_name,
                proxy_port,
            )
            return record

        except (IsolationError, Exception) as exc:  # noqa: BLE001
            error_msg = str(exc)
            logger.error(
                "Isolation failed for project %s: %s", project_id[:8], error_msg
            )

            # Best-effort cleanup — never skip even if partial
            try:
                self._docker.cleanup_all(project_id, container_id=container_id)
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.error(
                    "Cleanup also failed for project %s: %s",
                    project_id[:8],
                    cleanup_exc,
                )
            try:
                self._workspace.cleanup_workspace(project_id)
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.error(
                    "Workspace cleanup failed for project %s: %s",
                    project_id[:8],
                    cleanup_exc,
                )

            # Mark import_failed in DB (truncate error msg to prevent unbounded storage)
            record.isolation_status = IsolationStatus.IMPORT_FAILED
            record.isolation_error = error_msg[:2000]
            record.container_id = None
            record.container_name = None
            record.proxy_container_id = None
            record.proxy_port = None
            record = await self._repo.update(record)
            return record

    async def stop_isolation(self, project_id: str) -> ProjectRecord:
        """Stop the container and proxy for a project and mark it stopped."""
        validate_project_id(project_id)
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
        return await self._repo.update(record)

    async def cleanup_isolation(self, project_id: str) -> ProjectRecord:
        """Full cleanup: stop container, proxy, remove image, remove workspace, update DB."""
        validate_project_id(project_id)
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
        return await self._repo.update(record)

    def get_logs(self, container_id: str) -> str:
        """Return size-limited container logs. Logs are treated as untrusted text."""
        return self._docker.get_logs(container_id)
