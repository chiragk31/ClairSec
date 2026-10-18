"""
Pipelines API for Autopilot (FEATURES.md F3).

Endpoints:
- POST /api/pipelines -> start full check pipeline
- GET /api/pipelines/{id} -> get status and stage history
- POST /api/pipelines/{id}/cancel -> cancel running pipeline
- POST /api/pipelines/{id}/resume -> resume from failed stage
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.api.projects import GitImportRequest
from app.database.client import get_database
from app.database.models import PipelineRecord, PipelineStage, PipelineStatus
from app.services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class CreatePipelineRequest(BaseModel):
    project_id: str | None = None
    git_import: GitImportRequest | None = None
    name: str | None = None


class CreatePipelineResponse(BaseModel):
    pipeline_id: str
    status: str
    current_stage: str


class PipelineResponse(BaseModel):
    id: str
    project_id: str | None
    status: str
    current_stage: str
    stages: dict[str, Any]
    import_job_id: str | None
    isolation_job_id: str | None
    scan_id: str | None
    report_id: str | None = None
    error: str | None
    fix_hint: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: PipelineRecord) -> "PipelineResponse":
        return cls(
            id=record.id,
            project_id=record.project_id,
            status=record.status.value,
            current_stage=record.current_stage.value,
            stages={k: v.model_dump() for k, v in record.stages.items()},
            import_job_id=record.import_job_id,
            isolation_job_id=record.isolation_job_id,
            scan_id=record.scan_id,
            report_id=getattr(record, "report_id", None),
            error=record.error,
            fix_hint=record.fix_hint,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


@router.post(
    "",
    response_model=CreatePipelineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start an Autopilot pipeline",
)
async def create_pipeline(
    body: CreatePipelineRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> CreatePipelineResponse:
    orchestrator = PipelineOrchestrator(db)
    git_data = body.git_import.model_dump() if body.git_import else None

    if git_data and not git_data.get("authorization_affirmed"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Authorization must be affirmed to test this code (ETHICS.md §1).",
        )

    try:
        pipeline = await orchestrator.create_pipeline(
            project_id=body.project_id,
            git_import_data=git_data,
            name=body.name,
        )
        await orchestrator.start_pipeline(pipeline.id, git_import_data=git_data)
        return CreatePipelineResponse(
            pipeline_id=pipeline.id,
            status=pipeline.status.value,
            current_stage=pipeline.current_stage.value,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{pipeline_id}",
    response_model=PipelineResponse,
    summary="Get pipeline status and stage details",
)
async def get_pipeline(
    pipeline_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PipelineResponse:
    orchestrator = PipelineOrchestrator(db)
    pipeline = await orchestrator.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found.",
        )
    return PipelineResponse.from_record(pipeline)


@router.post(
    "/{pipeline_id}/cancel",
    response_model=PipelineResponse,
    summary="Cancel an active pipeline",
)
async def cancel_pipeline(
    pipeline_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PipelineResponse:
    orchestrator = PipelineOrchestrator(db)
    pipeline = await orchestrator.cancel_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found.",
        )
    return PipelineResponse.from_record(pipeline)


@router.post(
    "/{pipeline_id}/resume",
    response_model=PipelineResponse,
    summary="Resume a failed pipeline from its failed stage",
)
async def resume_pipeline(
    pipeline_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PipelineResponse:
    orchestrator = PipelineOrchestrator(db)
    pipeline = await orchestrator.resume_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline '{pipeline_id}' not found.",
        )
    return PipelineResponse.from_record(pipeline)
