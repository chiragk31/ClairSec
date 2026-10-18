"""
Projects API — POST/GET /api/projects, GET /api/projects/{id}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.validators import validate_project_id
from app.database.client import get_database
from app.database.models import ProjectRecord
from app.services.git_import_service import GitImportService, build_project_file_tree
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


class GitImportRequest(BaseModel):
    url: str
    ref: str | None = None
    subdir: str | None = None
    name: str | None = None
    authorization_affirmed: bool = False


class DemoProjectRequest(BaseModel):
    fixture: str = "vulnerable"  # "vulnerable" | "secure"


class GitImportResponse(BaseModel):
    job_id: str
    project_id: str


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
    origin: str = "user_project"
    import_source: str = "local"
    commit_sha: str | None = None
    import_notes: list[str] = []
    exposed_secrets: list[dict] = []
    monorepo_candidates: list[dict] = []
    file_count: int = 0
    repo_size_bytes: int = 0
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
            origin=getattr(record, "origin", "user_project"),
            import_source=record.import_source,
            commit_sha=record.commit_sha,
            import_notes=record.import_notes,
            exposed_secrets=record.exposed_secrets,
            monorepo_candidates=record.monorepo_candidates,
            file_count=record.file_count,
            repo_size_bytes=record.repo_size_bytes,
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


@router.post(
    "/projects/demo",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a demo fixture project (FEATURES.md F4)",
)
async def import_demo_project(
    body: DemoProjectRequest = DemoProjectRequest(),
    service: ProjectService = Depends(get_service),
) -> ProjectResponse:
    """
    Registers the bundled demo fixture project (vulnerable_fastapi_app or secure_fastapi_app)
    with origin: 'demo_fixture' pointing to the trusted fixture root.
    """
    record = await service.import_demo_project(body.fixture)
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


@router.post(
    "/projects/import/git",
    response_model=GitImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import a public GitHub repository",
)
async def import_git_project(
    body: GitImportRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> GitImportResponse:
    if not body.authorization_affirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Authorization must be affirmed to test this code (ETHICS.md §1).",
        )
    git_service = GitImportService(db)
    try:
        job, project = await git_service.start_import(
            url=body.url,
            ref=body.ref,
            subdir=body.subdir,
            name=body.name,
            authorization_affirmed=body.authorization_affirmed,
        )
        return GitImportResponse(job_id=job.id, project_id=project.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/projects/{project_id}/tree",
    summary="Get read-only file tree structure for preview",
)
async def get_project_tree(
    project_id: str = Depends(validate_project_id),
    depth: int = 3,
    service: ProjectService = Depends(get_service),
) -> dict[str, Any]:
    project = await service.get_project(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    source = Path(project.source_path)
    if not source.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project source directory does not exist or has not finished downloading.",
        )
    return build_project_file_tree(source, max_depth=min(depth, 5))

