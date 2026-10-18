"""
Project service — orchestrates validation and persistence.
"""
from __future__ import annotations

import anyio

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

import logging

from app.core.logging import set_log_context
from app.database.models import ProjectRecord, ValidationStatus
from app.database.repositories import ProjectRepository
from app.services.fastapi_validator import validate_fastapi_project

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._repo = ProjectRepository(db)

    async def import_project(self, source_path: str, name: str | None) -> ProjectRecord:
        """
        Validate the project at source_path and persist the record.

        The source directory is inspected statically — no code is executed.
        """
        # An empty or relative path would resolve against the backend's own working
        # directory and silently "import" ClairSec itself. Require an absolute folder.
        import os.path as _osp

        if not source_path or not source_path.strip() or not _osp.isabs(source_path.strip()):
            raise ValueError("Choose the project folder: an absolute folder path is required.")
        source_path = source_path.strip()

        # Derive a name from the directory if not provided
        resolved_name = name or source_path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        logger.info(
            "Starting import for project '%s' from '%s'",
            resolved_name,
            source_path,
            extra={"event": "project.import.started"},
        )

        result = validate_fastapi_project(source_path)
        from app.targets.handle import is_trusted_fixture_path
        is_fixture = is_trusted_fixture_path(source_path)

        record = ProjectRecord(
            name=resolved_name,
            source_path=source_path,
            origin="demo_fixture" if is_fixture else "user_project",
            validation_status=ValidationStatus.VALID if result.is_valid else ValidationStatus.INVALID,
            validation_errors=result.errors,
            entry_point=result.entry_point,
            dependency_file=result.dependency_file,
            dependencies=result.dependencies,
            isolation_ready=result.isolation_ready,
        )
        if result.is_valid and not is_fixture:
            # Static, read-only scan for committed credentials (values masked).
            from pathlib import Path as _P

            from app.services.secret_scanner import scan_tree

            record.exposed_secrets = await anyio.to_thread.run_sync(scan_tree, _P(source_path))
            if record.exposed_secrets:
                record.import_notes.insert(
                    0, f"{len(record.exposed_secrets)} exposed secret(s) committed in this project "
                       "(values masked; rotate them).")

        created_record = await self._repo.create(record)
        set_log_context(project_id=created_record.id)

        if result.is_valid:
            logger.info(
                "Project '%s' successfully imported (project_id=%s, isolation_ready=%s, entry_point=%s)",
                created_record.name,
                created_record.id,
                created_record.isolation_ready,
                created_record.entry_point,
                extra={"event": "project.import.succeeded"},
            )
        else:
            logger.warning(
                "Project '%s' imported with validation errors (project_id=%s, errors=%s)",
                created_record.name,
                created_record.id,
                created_record.validation_errors,
                extra={"event": "project.import.failed"},
            )

        return created_record

    async def list_projects(self) -> list[ProjectRecord]:
        return await self._repo.list_all()

    async def get_project(self, project_id: str) -> ProjectRecord | None:
        from app.core.validators import validate_project_id
        validate_project_id(project_id)
        return await self._repo.get_by_id(project_id)

    async def import_demo_project(self, fixture: str = "vulnerable") -> ProjectRecord:
        """Register a demo project pointing directly to trusted fixture (origin: demo_fixture)."""
        from pathlib import Path
        from app.core.config import settings
        from app.targets.handle import is_trusted_fixture_path

        root = Path(settings.trusted_fixtures_root).resolve()
        if fixture == "secure":
            target_dir = (root / "secure_fastapi_app").resolve()
            name = "Trust Check: Secure FastAPI App"
        else:
            target_dir = (root / "vulnerable_fastapi_app").resolve()
            name = "Demo: Vulnerable FastAPI App"

        if not target_dir.exists():
            raise FileNotFoundError(f"Fixture directory not found: {target_dir}")

        if not is_trusted_fixture_path(target_dir):
            raise PermissionError(f"Fixture directory {target_dir} is not inside trusted root {settings.trusted_fixtures_root}")

        existing = await self._repo.find_by_source_path(str(target_dir))
        if existing:
            return existing

        return await self.import_project(str(target_dir), name)

