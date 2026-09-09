"""
Project service — orchestrates validation and persistence.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.models import ProjectRecord, ValidationStatus
from app.database.repositories import ProjectRepository
from app.services.fastapi_validator import validate_fastapi_project


class ProjectService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._repo = ProjectRepository(db)

    async def import_project(self, source_path: str, name: str | None) -> ProjectRecord:
        """
        Validate the project at source_path and persist the record.

        The source directory is inspected statically — no code is executed.
        """
        result = validate_fastapi_project(source_path)

        # Derive a name from the directory if not provided
        resolved_name = name or source_path.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

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

        return await self._repo.create(record)

    async def list_projects(self) -> list[ProjectRecord]:
        return await self._repo.list_all()

    async def get_project(self, project_id: str) -> ProjectRecord | None:
        return await self._repo.get_by_id(project_id)
