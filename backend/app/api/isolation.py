"""
Isolation API — start/stop/status/logs/cleanup for project containers.

All endpoints are project-scoped under /api/projects/{project_id}/.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.core.validators import validate_project_id
from app.database.client import get_database
from app.database.models import ProjectRecord
from app.isolation.errors import IsolationError
from app.services.isolation_service import IsolationService
from app.services.job_service import JobService

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class IsolationStatusResponse(BaseModel):
    project_id: str
    name: str
    isolation_status: str
    workspace_path: str | None
    container_id: str | None
    container_name: str | None
    isolation_error: str | None

    @classmethod
    def from_record(cls, record: ProjectRecord) -> "IsolationStatusResponse":
        return cls(
            project_id=record.id,
            name=record.name,
            isolation_status=record.isolation_status.value,
            workspace_path=record.workspace_path,
            container_id=record.container_id,
            container_name=record.container_name,
            isolation_error=record.isolation_error,
        )


class IsolationJobResponse(BaseModel):
    job_id: str
    project_id: str
    status: str
    message: str = "Isolation job queued."


class LogsResponse(BaseModel):
    project_id: str
    logs: str


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def get_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> IsolationService:
    return IsolationService(db)


def get_job_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> JobService:
    return JobService(db)


async def _get_record_or_404(project_id: str, service: IsolationService) -> ProjectRecord:
    validate_project_id(project_id)
    record = await service.get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    return record


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/isolate",
    response_model=IsolationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start isolation for a validated project as a background job",
)
async def start_isolation(
    project_id: str = Depends(validate_project_id),
    service: JobService = Depends(get_job_service),
) -> IsolationJobResponse:
    """
    Trigger the Docker isolation lifecycle as a background job (OPERATIONS §5).
    Returns 202 Accepted with job_id immediately.
    """
    try:
        job = await service.submit_isolation_job(project_id)
        return IsolationJobResponse(
            job_id=job.id,
            project_id=job.project_id,
            status=job.status.value,
        )
    except IsolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/projects/{project_id}/stop",
    response_model=IsolationStatusResponse,
    summary="Stop the running container for a project",
)
async def stop_isolation(
    project_id: str = Depends(validate_project_id),
    service: IsolationService = Depends(get_service),
) -> IsolationStatusResponse:
    """Stop the container for this project and mark it stopped."""
    try:
        record = await service.stop_isolation(project_id)
        return IsolationStatusResponse.from_record(record)
    except IsolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/cleanup",
    response_model=IsolationStatusResponse,
    summary="Full cleanup: stop container, remove image and workspace",
)
async def cleanup_isolation(
    project_id: str = Depends(validate_project_id),
    service: IsolationService = Depends(get_service),
) -> IsolationStatusResponse:
    """Remove all Docker and filesystem resources for this project."""
    try:
        record = await service.cleanup_isolation(project_id)
        return IsolationStatusResponse.from_record(record)
    except IsolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/status",
    response_model=IsolationStatusResponse,
    summary="Get current isolation status for a project",
)
async def get_isolation_status(
    project_id: str = Depends(validate_project_id),
    service: IsolationService = Depends(get_service),
) -> IsolationStatusResponse:
    record = await _get_record_or_404(project_id, service)
    return IsolationStatusResponse.from_record(record)


@router.get(
    "/projects/{project_id}/logs",
    response_model=LogsResponse,
    summary="Retrieve container logs (size-limited)",
)
async def get_logs(
    project_id: str = Depends(validate_project_id),
    service: IsolationService = Depends(get_service),
) -> LogsResponse:
    """
    Return the last ~100 KB of container stdout/stderr.
    Logs are treated as untrusted text from the target application.
    """
    record = await _get_record_or_404(project_id, service)
    if not record.container_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No container is associated with this project.",
        )
    logs = service.get_logs(record.container_id)
    return LogsResponse(project_id=project_id, logs=logs)
