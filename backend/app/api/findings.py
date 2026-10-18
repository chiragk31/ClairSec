"""
Findings API: retrieval and evidence chain of custody / provenance (FEATURES.md F7).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database.client import get_database
from app.services.provenance_service import assemble_finding_provenance

router = APIRouter()


class ProvenanceStep(BaseModel):
    step_number: int
    who: str
    action: str
    title: str
    status: str
    timestamp: str | None = None
    record_id: str | None = None
    record_type: str | None = None
    detail: str


class FindingProvenanceResponse(BaseModel):
    finding_id: str
    scan_id: str | None = None
    category: str | None = None
    status: str | None = None
    is_confirmed: bool
    has_oracle_evidence: bool
    lane: str
    badge: str
    steps: list[ProvenanceStep]


@router.get(
    "/findings/{finding_id}/provenance",
    response_model=FindingProvenanceResponse,
    summary="Get 6-step evidence chain of custody for a finding (FEATURES.md F7)",
)
async def get_finding_provenance(
    finding_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> FindingProvenanceResponse:
    """
    Assemble the complete evidence chain of custody for a finding from stored database records.
    Never fabricates; returns platform evidence and records.
    """
    try:
        data = await assemble_finding_provenance(finding_id, db)
        return FindingProvenanceResponse(**data)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error assembling provenance: {exc}",
        )


# ── Exploit replay (FEATURES.md F8) ───────────────────────────────────────────


class ReplayRequest(BaseModel):
    target: str = "original"  # "original" | "patched"


@router.post(
    "/findings/{finding_id}/replay",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-send the stored attack against the original or patched app (FEATURES.md F8)",
)
async def start_replay(
    finding_id: str,
    body: ReplayRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict[str, Any]:
    from app.services.replay_service import ReplayError, ReplayService

    try:
        return await ReplayService(db).start(finding_id, body.target)
    except ReplayError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/replays/{replay_id}", summary="Get one replay result")
async def get_replay(replay_id: str, db: AsyncIOMotorDatabase = Depends(get_database)) -> dict[str, Any]:
    from app.services.replay_service import ReplayService

    doc = await ReplayService(db).get(replay_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay not found.")
    return doc


@router.get("/findings/{finding_id}/replays", summary="List replays for a finding, newest first")
async def list_replays(finding_id: str, db: AsyncIOMotorDatabase = Depends(get_database)) -> list[dict[str, Any]]:
    from app.services.replay_service import ReplayService

    return await ReplayService(db).list_for_finding(finding_id)
