"""
Read-only facts for the assistant (FEATURES.md F11).

Every function here only READS platform records. There is deliberately no write
tool: the assistant explains, it never acts. `READ_TOOLS` is asserted by tests to
contain only these readers.
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.glossary import GLOSSARY_ENTRIES
from app.isolation.docker_manager import _diagnose_build_failure
from app.llm.redaction import redact_secrets
from app.services.provenance_service import assemble_finding_provenance


def _v(x: Any) -> Any:
    return getattr(x, "value", x)


def _clean(doc: dict | None) -> dict | None:
    if doc is not None:
        doc.pop("_id", None)
    return doc


async def get_scan(db: AsyncIOMotorDatabase, scan_id: str) -> dict | None:
    return _clean(await db["scans"].find_one({"id": scan_id}))


async def get_project(db: AsyncIOMotorDatabase, project_id: str) -> dict | None:
    return _clean(await db["projects"].find_one({"id": project_id}))


async def list_findings(db: AsyncIOMotorDatabase, scan_id: str) -> list[dict]:
    return [_clean(f) async for f in db["findings"].find({"scan_id": scan_id})]


async def get_finding(db: AsyncIOMotorDatabase, finding_id: str) -> dict | None:
    return _clean(await db["findings"].find_one({"id": finding_id}))


async def get_verification(db: AsyncIOMotorDatabase, finding_id: str) -> dict | None:
    return _clean(await db["verification_results"].find_one({"finding_id": finding_id}))


async def get_patch(db: AsyncIOMotorDatabase, finding_id: str) -> dict | None:
    return _clean(await db["patches"].find_one({"finding_id": finding_id}))


async def get_recent_events(db: AsyncIOMotorDatabase, scan_id: str, limit: int = 12) -> list[dict]:
    cursor = db["agent_events"].find({"scan_id": scan_id}).sort("seq", -1).limit(limit)
    events = [_clean(e) async for e in cursor]
    return list(reversed(events))


async def get_provenance(db: AsyncIOMotorDatabase, finding_id: str) -> dict | None:
    try:
        return await assemble_finding_provenance(finding_id, db)
    except ValueError:
        return None


async def get_latest_scan_for_project(db: AsyncIOMotorDatabase, project_id: str) -> dict | None:
    cursor = db["scans"].find({"project_id": project_id}).sort("created_at", -1).limit(1)
    docs = [_clean(d) async for d in cursor]
    return docs[0] if docs else None


async def get_latest_scan(db: AsyncIOMotorDatabase) -> dict | None:
    cursor = db["scans"].find({}).sort("created_at", -1).limit(1)
    docs = [_clean(d) async for d in cursor]
    return docs[0] if docs else None


def explain_category(category: str) -> str | None:
    entry = GLOSSARY_ENTRIES.get(str(category or "").upper())
    return entry["plain"] if entry else None


def diagnose_failure(message: str | None) -> str | None:
    if not message:
        return None
    return _diagnose_build_failure([message])


def redact(text: Any) -> str:
    return redact_secrets(str(text or ""))


READ_TOOLS = {
    "get_scan": get_scan,
    "get_project": get_project,
    "list_findings": list_findings,
    "get_finding": get_finding,
    "get_verification": get_verification,
    "get_patch": get_patch,
    "get_recent_events": get_recent_events,
    "get_provenance": get_provenance,
    "get_latest_scan_for_project": get_latest_scan_for_project,
    "get_latest_scan": get_latest_scan,
    "explain_category": explain_category,
    "diagnose_failure": diagnose_failure,
}
