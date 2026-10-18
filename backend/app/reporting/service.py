"""
Report generation service (FEATURES.md F12).

Writes report files under WORKSPACE_ROOT/reports/<scan_id>/ and records them in
the `reports` collection. Downloads are only ever served from that directory.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.reporting.collect import collect_report_data
from app.reporting.render import EXTENSIONS, FORMATS, RENDERERS

REPORTS = "reports"
AUDIENCES = ("both", "exec", "technical")


class ReportError(Exception):
    pass


def reports_root() -> Path:
    return (Path(settings.workspace_root).expanduser() / "reports").resolve()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def generate_report(
    db: AsyncIOMotorDatabase,
    scan_id: str,
    formats: list[str] | None = None,
    audience: str = "both",
) -> dict[str, Any]:
    formats = [f for f in (formats or [*FORMATS, "pdf"])]
    want_pdf = "pdf" in formats
    formats = [f for f in formats if f != "pdf"]
    if want_pdf and "html" not in formats:
        formats.append("html")  # the PDF is printed from the HTML report
    bad = [f for f in formats if f not in FORMATS]
    if bad:
        raise ReportError(f"Unknown format(s): {bad}. Allowed: {list(FORMATS)}")
    if audience not in AUDIENCES:
        raise ReportError(f"audience must be one of {AUDIENCES}")
    try:
        data = await collect_report_data(db, scan_id)
    except ValueError as exc:
        raise ReportError(str(exc)) from exc

    report_id = str(uuid.uuid4())
    folder = reports_root() / scan_id
    files: dict[str, str] = {}
    for fmt in formats:
        text = RENDERERS[fmt](data, audience)
        path = folder / f"{report_id}.{EXTENSIONS[fmt]}"
        await anyio.to_thread.run_sync(_write, path, text)
        files[fmt] = str(path)

    pdf_note = None
    if want_pdf:
        from app.reporting.pdf import PdfUnavailable, html_to_pdf

        pdf_path = folder / f"{report_id}.pdf"
        try:
            await anyio.to_thread.run_sync(html_to_pdf, Path(files["html"]), pdf_path)
            files["pdf"] = str(pdf_path)
        except (PdfUnavailable, OSError, Exception) as exc:  # noqa: BLE001 — HTML stays available
            pdf_note = str(exc)

    record = {
        "id": report_id,
        "scan_id": scan_id,
        "project_name": data["project"]["name"],
        "audience": audience,
        "formats": list(files.keys()),
        "pdf_note": pdf_note,
        "files": files,
        "summary": data["summary"],
        "posture": {k: data["posture"].get(k) for k in ("before", "after", "grade_before", "grade_after")}
        if data.get("posture") else None,
        "confirmed_count": len(data["confirmed"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
    }
    await db[REPORTS].insert_one(dict(record))
    return record


async def get_report(db: AsyncIOMotorDatabase, report_id: str) -> dict[str, Any] | None:
    doc = await db[REPORTS].find_one({"id": report_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def list_reports(db: AsyncIOMotorDatabase, scan_id: str | None = None) -> list[dict[str, Any]]:
    query = {"scan_id": scan_id} if scan_id else {}
    out = []
    async for doc in db[REPORTS].find(query).sort("created_at", -1):
        doc.pop("_id", None)
        out.append(doc)
    return out


def safe_report_path(record: dict[str, Any], fmt: str) -> Path:
    """Resolve a stored report path and refuse anything outside the reports directory."""
    raw = (record.get("files") or {}).get(fmt)
    if not raw:
        raise ReportError(f"This report has no '{fmt}' file.")
    path = Path(raw).resolve()
    if not path.is_relative_to(reports_root()) or not path.is_file():
        raise ReportError("Report file is missing or outside the reports directory.")
    return path
