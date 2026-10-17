"""
Project service — orchestrates validation and persistence.
"""
from __future__ import annotations

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
        # Derive a name from the directory if not provided
        resolved_name = name or source_path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        logger.info(
            "Starting import for project '%s' from '%s'",
            resolved_name,
            source_path,
            extra={"event": "project.import.started"},
        )

        result = validate_fastapi_project(source_path)

        record = ProjectRecord(
            name=resolved_name,
            source_path=source_path,
            validation_status=ValidationStatus.VALID if result.is_valid else ValidationStatus.INVALID,
            validation_errors=result.errors,
            entry_point=result.entry_point,
            dependency_file=result.dependency_file,
            dependencies=result.dependencies,
            isolation_ready=result.isolation_ready,
        )

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
