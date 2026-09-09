"""
Projects API — POST/GET /api/projects, GET /api/projects/{id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.validators import validate_project_id
from app.database.client import get_database
from app.database.models import ProjectRecord
from app.services.project_service import ProjectService

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ImportProjectRequest(BaseModel):
    path: str
    """Absolute path to the local project directory on the host filesystem."""
    name: str | None = None
    """Optional user-supplied name; defaults to directory name."""


class ProjectResponse(BaseModel):
    """API-facing representation of a project record."""
    id: str
    name: str
    source_path: str
    validation_status: str
    validation_errors: list[str]
    entry_point: str | None
    dependency_file: str | None
    dependencies: list[str]
    isolation_ready: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: ProjectRecord) -> "ProjectResponse":
        return cls(
            id=record.id,
            name=record.name,
            source_path=record.source_path,
            validation_status=record.validation_status.value,
            validation_errors=record.validation_errors,
            entry_point=record.entry_point,
            dependency_file=record.dependency_file,
            dependencies=record.dependencies,
            isolation_ready=record.isolation_ready,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def get_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ProjectService:
    return ProjectService(db)


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a local FastAPI project",
)
async def import_project(
    body: ImportProjectRequest,
    service: ProjectService = Depends(get_service),
) -> ProjectResponse:
    """
    Inspect and import a local FastAPI project.

    The project directory is inspected statically (no code execution).
    Returns the validated project record regardless of validation outcome —
    callers must check validation_status to determine if the import succeeded.
    """
    record = await service.import_project(body.path, body.name)
    return ProjectResponse.from_record(record)


@router.get(
    "/projects",
    response_model=list[ProjectResponse],
    summary="List all imported projects",
)
async def list_projects(
    service: ProjectService = Depends(get_service),
) -> list[ProjectResponse]:
    records = await service.list_projects()
    return [ProjectResponse.from_record(r) for r in records]


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Get a single project by ID",
)
async def get_project(
    project_id: str = Depends(validate_project_id),
    service: ProjectService = Depends(get_service),
) -> ProjectResponse:
    record = await service.get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    return ProjectResponse.from_record(record)
