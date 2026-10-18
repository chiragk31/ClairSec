"""
Scan Bundle APIs: listing, retrieval, and replay ingestion (FEATURES.md F4).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database.client import get_database
from app.services.bundle_service import (
    DEFAULT_BUNDLES_DIR,
    import_bundle_as_scan,
    list_available_bundles,
    load_bundle,
)

router = APIRouter()


class BundleInfo(BaseModel):
    file_path: str
    file_name: str
    scan_id: str | None
    project_name: str | None
    recorded_at: str | None
    events_count: int
    findings_count: int
    bundle_size_bytes: int


class ReplayBundleResponse(BaseModel):
    scan_id: str
    project_id: str
    project_name: str
    mode: str
    state: str
    events_count: int
    findings_count: int


@router.get(
    "/bundles",
    response_model=list[BundleInfo],
    summary="List all recorded scan bundles",
)
async def list_bundles() -> list[BundleInfo]:
    """List available recorded scan bundles stored in demo/bundles/."""
    bundles = list_available_bundles()
    return [BundleInfo(**b) for b in bundles]


@router.get(
    "/bundles/{bundle_name}",
    response_model=dict[str, Any],
    summary="Fetch a scan bundle by filename or scan ID",
)
async def get_bundle(bundle_name: str) -> dict[str, Any]:
    """Retrieve full bundle payload for client-side replay playback."""
    if not bundle_name.endswith(".clairsec.json"):
        bundle_name = f"{bundle_name}.clairsec.json"

    # Only plain file names inside the bundles directory (no traversal, no absolute paths).
    if "/" in bundle_name or "\\" in bundle_name or ".." in bundle_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid bundle name.")
    bundle_path = (DEFAULT_BUNDLES_DIR / bundle_name).resolve()
    if not bundle_path.is_relative_to(DEFAULT_BUNDLES_DIR.resolve()) or not bundle_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bundle '{bundle_name}' not found.",
        )

    try:
        return load_bundle(bundle_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to load bundle: {exc}",
        )


@router.post(
    "/bundles/{bundle_name}/replay",
    response_model=ReplayBundleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest bundle as a recorded scan run",
)
async def replay_bundle(
    bundle_name: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ReplayBundleResponse:
    """Import a bundle into MongoDB so UI can inspect the recorded run."""
    if not bundle_name.endswith(".clairsec.json"):
        bundle_name = f"{bundle_name}.clairsec.json"

    if "/" in bundle_name or "\\" in bundle_name or ".." in bundle_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid bundle name.")
    bundle_path = (DEFAULT_BUNDLES_DIR / bundle_name).resolve()
    if not bundle_path.is_relative_to(DEFAULT_BUNDLES_DIR.resolve()) or not bundle_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bundle '{bundle_name}' not found.",
        )

    try:
        data = load_bundle(bundle_path)
        scan = await import_bundle_as_scan(data, db)
        return ReplayBundleResponse(
            scan_id=scan.id,
            project_id=scan.project_id,
            project_name=scan.project_name,
            mode=scan.mode,
            state=scan.state,
            events_count=len(data.get("events", [])),
            findings_count=len(data.get("findings", [])),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to replay bundle: {exc}",
        )
