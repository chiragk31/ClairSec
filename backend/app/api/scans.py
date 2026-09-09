"""
Scans API — trigger scans, list scans, check scan status, get findings.
(ARCHITECTURE.md §4, RULES.md §5a, DATA_MODEL.md §3).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import validate_project_id
from app.database.client import get_database
from app.database.models import ScanRecord
from app.services.scan_service import ScanService

router = APIRouter()


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class CreateScanRequest(BaseModel):
    project_id: str = Field(alias="projectId", default=None)

    model_config = ConfigDict(populate_by_name=True)


class CreateScanResponse(BaseModel):
    scan_id: str
    scanId: str
    status: str = "accepted"
    message: str = "Scan pipeline queued in background."


class ScanSummaryResponse(BaseModel):
    id: str
    project_id: str
    projectId: str
    project_name: str
    projectName: str
    state: str
    stage: str
    created_at: str
    createdAt: str
    started_at: str | None = None
    startedAt: str | None = None
    ended_at: str | None = None
    endedAt: str | None = None
    findings_confirmed: int = 0
    findingsConfirmed: int = 0
    counters: dict[str, int] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, r: ScanRecord) -> "ScanSummaryResponse":
        c_at = r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at)
        s_at = r.started_at.isoformat() if r.started_at and hasattr(r.started_at, "isoformat") else (c_at if r.started_at else None)
        e_at = r.ended_at.isoformat() if r.ended_at and hasattr(r.ended_at, "isoformat") else None

        return cls(
            id=r.id,
            project_id=r.project_id,
            projectId=r.project_id,
            project_name=r.project_name,
            projectName=r.project_name,
            state=r.state,
            stage=r.stage,
            created_at=c_at,
            createdAt=c_at,
            started_at=s_at,
            startedAt=s_at,
            ended_at=e_at,
            endedAt=e_at,
            findings_confirmed=r.findings_confirmed,
            findingsConfirmed=r.findings_confirmed,
            counters=r.counters or {},
        )


class ScanDetailResponse(ScanSummaryResponse):
    arm: str = "multi_agent"
    error: str | None = None
    terminal_reason: str | None = None

    @classmethod
    def from_record(cls, r: ScanRecord) -> "ScanDetailResponse":
        c_at = r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at)
        s_at = r.started_at.isoformat() if r.started_at and hasattr(r.started_at, "isoformat") else (c_at if r.started_at else None)
        e_at = r.ended_at.isoformat() if r.ended_at and hasattr(r.ended_at, "isoformat") else None

        return cls(
            id=r.id,
            project_id=r.project_id,
            projectId=r.project_id,
            project_name=r.project_name,
            projectName=r.project_name,
            state=r.state,
            stage=r.stage,
            created_at=c_at,
            createdAt=c_at,
            started_at=s_at,
            startedAt=s_at,
            ended_at=e_at,
            endedAt=e_at,
            findings_confirmed=r.findings_confirmed,
            findingsConfirmed=r.findings_confirmed,
            counters=r.counters or {},
            arm=r.arm,
            error=r.error,
            terminal_reason=r.terminal_reason,
        )


# ---------------------------------------------------------------------------
# Dependency Helper
# ---------------------------------------------------------------------------

def get_scan_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ScanService:
    return ScanService(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/scans",
    response_model=CreateScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger full autonomous security scan pipeline against an isolated project",
)
async def create_scan(
    payload: CreateScanRequest,
    service: ScanService = Depends(get_scan_service),
) -> CreateScanResponse:
    """
    Triggers Builder -> Attacker -> Evaluator -> Fixer -> Verifier in the background.
    Returns 202 Accepted + scan_id immediately per RULES.md §5a.
    """
    if not payload.project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field 'project_id' or 'projectId' is required in request body.",
        )

    try:
        validate_project_id(payload.project_id)
        scan = await service.submit_scan(payload.project_id)
        return CreateScanResponse(
            scan_id=scan.id,
            scanId=scan.id,
            status="accepted",
            message="Scan pipeline queued in background.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/scans",
    response_model=list[ScanSummaryResponse],
    summary="List all scans",
)
async def list_scans(
    project_id: str | None = None,
    service: ScanService = Depends(get_scan_service),
) -> list[ScanSummaryResponse]:
    scans = await service.list_scans(project_id=project_id)
    return [ScanSummaryResponse.from_record(s) for s in scans]


@router.get(
    "/scans/{scan_id}",
    response_model=ScanDetailResponse,
    summary="Get status and details for a scan",
)
async def get_scan(
    scan_id: str,
    service: ScanService = Depends(get_scan_service),
) -> ScanDetailResponse:
    scan = await service.get_scan(scan_id)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )
    return ScanDetailResponse.from_record(scan)


@router.get(
    "/scans/{scan_id}/findings",
    summary="Get findings for a scan in Finding model shape",
)
async def get_scan_findings(
    scan_id: str,
    service: ScanService = Depends(get_scan_service),
) -> list[dict[str, Any]]:
    """
    Returns findings matching the Finding model in desktop/lib/models/finding.dart.
    """
    scan = await service.get_scan(scan_id)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )
    return await service.get_scan_findings_formatted(scan_id)


@router.get(
    "/scans/{scan_id}/patches",
    summary="Get generated patches (unified diffs) for a scan",
)
async def get_scan_patches(
    scan_id: str,
    service: ScanService = Depends(get_scan_service),
) -> list[dict[str, Any]]:
    """
    Returns the unified diffs the Fixer generated, for the Fix Review screen
    (DESIGN.md §8). Diffs are shown to the user before any promotion out of
    the isolated workspace.
    """
    scan = await service.get_scan(scan_id)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan '{scan_id}' not found.",
        )
    return await service.get_scan_patches_formatted(scan_id)
