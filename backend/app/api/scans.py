"""
Scans API — create scans, run Builder, retrieve results.

Per docs/ARCHITECTURE.md §4:
  POST /api/scans                    — create a scan
  GET  /api/scans                    — list scans
  GET  /api/scans/{id}               — get scan status
  POST /api/scans/{id}/run-builder   — trigger Builder agent
  GET  /api/scans/{id}/context       — retrieve Builder output (agent_context)
  GET  /api/scans/{id}/events        — retrieve agent events
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database.client import get_database
from app.database.models import AgentContextRecord, AgentEvent, ScanRecord, ScanStatus
from app.database.scan_repositories import (
    AgentContextRepository,
    AgentEventRepository,
    ScanRepository,
)
from app.database.repositories import ProjectRepository
from app.llm.provider import get_provider

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────


class ScanResponse(BaseModel):
    scan_id: str
    project_id: str
    status: str
    llm_provider: str
    llm_model: str
    prompt_version: str
    error: str | None

    @classmethod
    def from_record(cls, r: ScanRecord) -> "ScanResponse":
        return cls(
            scan_id=r.id,
            project_id=r.project_id,
            status=r.status.value,
            llm_provider=r.llm_provider,
            llm_model=r.llm_model,
            prompt_version=r.prompt_version,
            error=r.error,
        )


class CreateScanRequest(BaseModel):
    project_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/scans",
    response_model=ScanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new scan for a project",
)
async def create_scan(
    body: CreateScanRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ScanResponse:
    """Create a scan record for the given project_id."""
    project_repo = ProjectRepository(db)
    project = await project_repo.get_by_id(body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{body.project_id}' not found.")

    scan = ScanRecord(project_id=body.project_id)
    scan_repo = ScanRepository(db)
    await scan_repo.create(scan)
    return ScanResponse.from_record(scan)


@router.get(
    "/scans",
    response_model=list[ScanResponse],
    summary="List all scans",
)
async def list_scans(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[ScanResponse]:
    scan_repo = ScanRepository(db)
    scans = await scan_repo._col.find({}).to_list(length=200)
    result = []
    for d in scans:
        d.pop("_id", None)
        result.append(ScanResponse.from_record(ScanRecord.model_validate(d)))
    return result


@router.get(
    "/scans/{scan_id}",
    response_model=ScanResponse,
    summary="Get a scan by ID",
)
async def get_scan(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ScanResponse:
    scan_repo = ScanRepository(db)
    scan = await scan_repo.get_by_id(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")
    return ScanResponse.from_record(scan)


@router.post(
    "/scans/{scan_id}/run-builder",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger the Builder agent for this scan",
)
async def run_builder(
    scan_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ScanResponse:
    """
    Trigger the Builder agent asynchronously.

    The scan status transitions to ANALYZING immediately; the Builder runs
    in the background. Poll GET /api/scans/{id} or GET /api/scans/{id}/events
    to track progress.
    """
    scan_repo = ScanRepository(db)
    scan = await scan_repo.get_by_id(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found.")

    if scan.status not in (ScanStatus.PENDING, ScanStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Scan is in status '{scan.status}' — cannot re-run Builder."
        )

    background_tasks.add_task(_run_builder_task, scan_id, scan.project_id, db)
    return ScanResponse.from_record(scan)


async def _run_builder_task(
    scan_id: str, project_id: str, db: AsyncIOMotorDatabase
) -> None:
    """Background task: instantiate and run BuilderAgent."""
    from app.agents.builder import BuilderAgent
    try:
        provider = get_provider()
        agent = BuilderAgent(db=db, llm_provider=provider)
        await agent.run(scan_id=scan_id, project_id=project_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Builder background task failed for scan %s: %s", scan_id, exc)
        # Best-effort: mark scan failed
        try:
            scan_repo = ScanRepository(db)
            scan = await scan_repo.get_by_id(scan_id)
            if scan:
                scan.status = ScanStatus.FAILED
                scan.error = str(exc)[:500]
                await scan_repo.update(scan)
        except Exception as inner:
            logger.error("Could not mark scan %s failed: %s", scan_id, inner)


@router.get(
    "/scans/{scan_id}/context",
    summary="Retrieve the Builder's structured output (agent_context)",
)
async def get_scan_context(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    """
    Returns the Builder's structured BuilderAnalysis as persisted to agent_context.
    """
    ctx_repo = AgentContextRepository(db)
    record = await ctx_repo.get_by_scan_and_agent(scan_id, "builder")
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="No Builder context found for this scan. Has the Builder run yet?"
        )
    return {
        "scan_id": scan_id,
        "agent": record.agent,
        "llm_provider": record.llm_provider,
        "llm_model": record.llm_model,
        "prompt_version": record.prompt_version,
        "created_at": record.created_at.isoformat(),
        "context": record.context,
    }


@router.get(
    "/scans/{scan_id}/events",
    summary="Retrieve all agent events for a scan",
)
async def get_scan_events(
    scan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[dict]:
    """
    Returns all structured agent events for the scan in chronological order.
    These are the same events that Phase 9 will stream over WebSocket.
    """
    event_repo = AgentEventRepository(db)
    events = await event_repo.list_by_scan(scan_id)
    return [
        {
            "id": e.id,
            "scan_id": e.scan_id,
            "agent": e.agent,
            "event_type": e.event_type,
            "status": e.status,
            "message": e.message,
            "data": e.data,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]
