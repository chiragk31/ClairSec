"""
Reports and regression-watch API (FEATURES.md F12, F13).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database.client import get_database
from app.reporting.render import MEDIA_TYPES
from app.reporting.service import (
    ReportError,
    generate_report,
    get_report,
    list_reports,
    safe_report_path,
)

router = APIRouter()


class ReportRequest(BaseModel):
    formats: list[str] | None = None  # default: html, md, json, sarif
    audience: str = "both"            # both | exec | technical


@router.post("/scans/{scan_id}/reports", status_code=status.HTTP_201_CREATED,
             summary="Generate a report for a scan (HTML, Markdown, JSON, SARIF)")
async def create_report(scan_id: str, body: ReportRequest,
                        db: AsyncIOMotorDatabase = Depends(get_database)) -> dict[str, Any]:
    try:
        return await generate_report(db, scan_id, body.formats, body.audience)
    except ReportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/scans/{scan_id}/reports", summary="List reports for a scan")
async def scan_reports(scan_id: str, db: AsyncIOMotorDatabase = Depends(get_database)) -> list[dict[str, Any]]:
    return await list_reports(db, scan_id)


@router.get("/reports", summary="List all reports, newest first")
async def all_reports(db: AsyncIOMotorDatabase = Depends(get_database)) -> list[dict[str, Any]]:
    return await list_reports(db)


@router.get("/reports/{report_id}/download", summary="Download one report format")
async def download_report(report_id: str, format: str = Query("html"),
                          db: AsyncIOMotorDatabase = Depends(get_database)) -> FileResponse:
    record = await get_report(db, report_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    try:
        path = safe_report_path(record, format)
    except ReportError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(path, media_type=MEDIA_TYPES.get(format, "application/octet-stream"),
                        filename=f"clairsec-{record['scan_id'][:8]}.{path.name.split('.', 1)[1]}")


@router.get("/projects/{project_id}/scan-diff", summary="Compare two scans of a project (F13)")
async def scan_diff(project_id: str, base: str | None = None, head: str | None = None,
                    db: AsyncIOMotorDatabase = Depends(get_database)) -> dict[str, Any]:
    from app.research.matching import diff_scans

    scans = []
    async for s in db["scans"].find({"project_id": project_id, "state": "completed"}).sort("created_at", -1):
        scans.append(s)
    if not base or not head:
        if len(scans) < 2:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Run at least two completed scans of this project to compare them.")
        head = head or scans[0]["id"]
        base = base or scans[1]["id"]

    async def confirmed(scan_id: str) -> list[dict[str, Any]]:
        outcomes = {v["finding_id"]: str(v.get("outcome", "")).lower()
                    async for v in db["verification_results"].find({"scan_id": scan_id})}
        out = []
        async for f in db["findings"].find({"scan_id": scan_id}):
            if str(getattr(f.get("status"), "value", f.get("status")) or "").lower() == "confirmed":
                f.pop("_id", None)
                f["verification_outcome"] = outcomes.get(f["id"])
                out.append(f)
        return out

    base_f, head_f = await confirmed(base), await confirmed(head)
    routes = sorted({f.get("route_template") for f in base_f + head_f if f.get("route_template")})
    d = diff_scans(base_f, head_f, routes)

    def brief(f: dict[str, Any]) -> dict[str, Any]:
        return {"id": f.get("id"), "title": f.get("title"), "category": f.get("category"),
                "method": f.get("method"), "route": f.get("route_template")}

    by_id = {s["id"]: s for s in scans}
    return {
        "base": {"scan_id": base, "posture": (by_id.get(base) or {}).get("posture")},
        "head": {"scan_id": head, "posture": (by_id.get(head) or {}).get("posture")},
        **{k: [brief(f) for f in v] for k, v in d.items()},
    }
