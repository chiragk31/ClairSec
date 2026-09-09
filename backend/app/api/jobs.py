"""
Jobs API — query status and request cancellation for background jobs (OPERATIONS §5).
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database.client import get_database
from app.database.models import JobRecord
from app.services.job_service import JobService

router = APIRouter()


class JobResponse(BaseModel):
    id: str
    project_id: str
    status: str
    stage: str
    cancel_requested: bool
    error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: JobRecord) -> "JobResponse":
        return cls(
            id=record.id,
            project_id=record.project_id,
            status=record.status.value,
            stage=record.stage,
            cancel_requested=record.cancel_requested,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def get_job_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> JobService:
    return JobService(db)


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get background job status",
)
async def get_job_status(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobResponse.from_record(job)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    summary="Request job cancellation",
)
async def cancel_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = await service.cancel_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobResponse.from_record(job)
