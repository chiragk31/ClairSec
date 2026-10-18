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
        Full isolation lifecycle for a validated project using reusable async runner (A2, RULES §5a).
        All blocking Docker and workspace operations run in worker threads via anyio.to_thread.run_sync.
        """
        from app.services.isolation_runner import execute_isolation_steps

        return await execute_isolation_steps(
            project_id=project_id,
            project_repo=self._repo,
            docker_manager=self._docker,
            workspace_manager=self._workspace,
        )

    async def stop_isolation(self, project_id: str) -> ProjectRecord:
        """Stop the container and proxy for a project and mark it stopped."""
        import anyio

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
            await anyio.to_thread.run_sync(self._docker.stop_container, record.container_id)
        await anyio.to_thread.run_sync(self._docker.stop_proxy, project_id)

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
        import anyio

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

        await anyio.to_thread.run_sync(
            self._docker.cleanup_all, project_id, record.container_id
        )
        await anyio.to_thread.run_sync(self._workspace.cleanup_workspace, project_id)

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

