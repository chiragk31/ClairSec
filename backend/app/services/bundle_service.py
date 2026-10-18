"""
Scan Bundle Service: Export and Replay of Recorded Scans (FEATURES.md F4).
Schema version: clairsec.bundle/v1, <= 5 MB cap, redacted before export.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import redact_secrets as recursive_redact
from app.database.models import ScanRecord

logger = logging.getLogger(__name__)

BUNDLE_SCHEMA_VERSION = "clairsec.bundle/v1"
BUNDLE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB cap per F4
# <repo>/demo/bundles regardless of the backend's working directory.
DEFAULT_BUNDLES_DIR = Path(__file__).resolve().parents[3] / "demo" / "bundles"


def _sanitize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove MongoDB _id and redact sensitive secrets."""
    clean = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in clean.items():
        if isinstance(v, datetime):
            clean[k] = v.isoformat()
    return recursive_redact(clean)


async def record_scan_bundle(
    scan_id: str,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    """
    Export a completed scan as a versioned scan bundle (F4).
    Includes relative timings for events, findings, test cases, patches, and verification.
    """
    scans_col = db["scans"]
    projects_col = db["projects"]
    events_col = db["agent_events"]
    findings_col = db["findings"]
    test_cases_col = db["test_cases"]
    patches_col = db["patches"]
    verification_col = db["verification_results"]

    scan_doc = await scans_col.find_one({"id": scan_id})
    if not scan_doc:
        raise ValueError(f"Scan '{scan_id}' not found.")

    project_doc = await projects_col.find_one({"id": scan_doc.get("project_id")})

    # Fetch and order events
    events_cursor = events_col.find({"scan_id": scan_id}).sort("seq", 1)
    raw_events = await events_cursor.to_list(length=10000)

    # Compute relative timing offset_ms
    start_ts = None
    processed_events = []
    for ev in raw_events:
        clean_ev = _sanitize_doc(ev)
        ev_ts = clean_ev.get("timestamp")
        if ev_ts:
            try:
                if isinstance(ev_ts, str):
                    dt = datetime.fromisoformat(ev_ts.replace("Z", "+00:00"))
                else:
                    dt = ev_ts
                if start_ts is None:
                    start_ts = dt
                clean_ev["offset_ms"] = int((dt - start_ts).total_seconds() * 1000)
            except Exception:
                clean_ev["offset_ms"] = 0
        else:
            clean_ev["offset_ms"] = 0
        processed_events.append(clean_ev)

    # Fetch findings, test cases, patches, verification results
    findings = [_sanitize_doc(d) for d in await findings_col.find({"scan_id": scan_id}).to_list(1000)]
    test_cases = [_sanitize_doc(d) for d in await test_cases_col.find({"scan_id": scan_id}).to_list(5000)]
    patches = [_sanitize_doc(d) for d in await patches_col.find({"scan_id": scan_id}).to_list(1000)]
    verifications = [_sanitize_doc(d) for d in await verification_col.find({"scan_id": scan_id}).to_list(1000)]

    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "scan_id": scan_id,
        "project_id": scan_doc.get("project_id", "project-demo"),
        "project_name": project_doc.get("name") if project_doc else (scan_doc.get("project_name") or "Demo App"),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "mode": "demo",
        "posture": scan_doc.get("posture"),
        "counters": scan_doc.get("counters", {}),
        "stage_durations": scan_doc.get("stage_durations", {}),
        "events": processed_events,
        "findings": findings,
        "test_cases": test_cases,
        "patches": patches,
        "verification_results": verifications,
    }

    # Size check
    serialized = json.dumps(bundle, ensure_ascii=False)
    byte_len = len(serialized.encode("utf-8"))
    if byte_len > BUNDLE_MAX_BYTES:
        raise ValueError(
            f"Bundle size ({byte_len / (1024 * 1024):.2f} MB) exceeds maximum allowed cap of 5 MB."
        )

    bundle["bundle_size_bytes"] = byte_len
    return bundle


def save_bundle(bundle_data: dict[str, Any], output_path: str | Path | None = None) -> Path:
    """Save scan bundle to disk."""
    if output_path is not None:
        target = Path(output_path).resolve()
    else:
        DEFAULT_BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
        scan_id = bundle_data.get("scan_id", "scan")
        target = (DEFAULT_BUNDLES_DIR / f"{scan_id}.clairsec.json").resolve()

    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(bundle_data, indent=2, ensure_ascii=False)
    target.write_text(serialized, encoding="utf-8")
    logger.info("Saved scan bundle (%d bytes) to %s", len(serialized), target)
    return target


def load_bundle(bundle_path: str | Path) -> dict[str, Any]:
    """Load and validate a scan bundle from disk."""
    p = Path(bundle_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Scan bundle file not found: {p}")

    content = p.read_text(encoding="utf-8")
    if len(content.encode("utf-8")) > BUNDLE_MAX_BYTES:
        raise ValueError("Bundle file exceeds 5 MB cap.")

    data = json.loads(content)
    if data.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported bundle schema_version '{data.get('schema_version')}'; expected '{BUNDLE_SCHEMA_VERSION}'."
        )
    return data


def list_available_bundles(search_dir: Path | None = None) -> list[dict[str, Any]]:
    """List all available scan bundles on disk."""
    s_dir = search_dir or DEFAULT_BUNDLES_DIR
    if not s_dir.exists():
        return []

    bundles = []
    for file in sorted(s_dir.glob("*.clairsec.json")):
        try:
            data = load_bundle(file)
            bundles.append({
                "file_path": str(file),
                "file_name": file.name,
                "scan_id": data.get("scan_id"),
                "project_name": data.get("project_name"),
                "recorded_at": data.get("recorded_at"),
                "events_count": len(data.get("events", [])),
                "findings_count": len(data.get("findings", [])),
                "bundle_size_bytes": data.get("bundle_size_bytes", 0),
            })
        except Exception as exc:
            logger.debug("Skipping invalid bundle %s: %s", file, exc)
    return bundles


async def import_bundle_as_scan(
    bundle_data: dict[str, Any],
    db: AsyncIOMotorDatabase,
) -> ScanRecord:
    """Import a bundle into the database as a recorded scan run."""
    scan_id = bundle_data.get("scan_id") or "bundle-scan"
    scans_col = db["scans"]
    events_col = db["agent_events"]
    findings_col = db["findings"]
    test_cases_col = db["test_cases"]
    patches_col = db["patches"]
    verification_col = db["verification_results"]

    # Upsert scan
    scan_record = ScanRecord(
        id=scan_id,
        project_id=bundle_data.get("project_id", "project-demo"),
        project_name=bundle_data.get("project_name", "Demo App"),
        arm="multi_agent",
        mode="recorded",
        state="completed",
        stage="completed",
        posture=bundle_data.get("posture"),
        counters=bundle_data.get("counters", {}),
        findings_confirmed=len([f for f in bundle_data.get("findings", []) if f.get("status") == "confirmed"]),
    )

    doc = scan_record.model_dump()
    doc["_id"] = scan_id
    await scans_col.replace_one({"id": scan_id}, doc, upsert=True)

    # Ingest events
    for ev in bundle_data.get("events", []):
        ev_copy = dict(ev)
        ev_copy["_id"] = ev_copy.get("id") or f"{scan_id}-{ev_copy.get('seq')}"
        ev_copy["scan_id"] = scan_id
        await events_col.replace_one({"scan_id": scan_id, "seq": ev_copy["seq"]}, ev_copy, upsert=True)

    # Ingest findings
    for f in bundle_data.get("findings", []):
        f_copy = dict(f)
        f_copy["_id"] = f_copy.get("id")
        f_copy["scan_id"] = scan_id
        await findings_col.replace_one({"id": f_copy["id"]}, f_copy, upsert=True)

    # Ingest test cases
    for tc in bundle_data.get("test_cases", []):
        tc_copy = dict(tc)
        tc_copy["_id"] = tc_copy.get("id")
        tc_copy["scan_id"] = scan_id
        await test_cases_col.replace_one({"id": tc_copy["id"]}, tc_copy, upsert=True)

    # Ingest patches
    for p in bundle_data.get("patches", []):
        p_copy = dict(p)
        p_copy["_id"] = p_copy.get("id")
        p_copy["scan_id"] = scan_id
        await patches_col.replace_one({"id": p_copy["id"]}, p_copy, upsert=True)

    # Ingest verifications
    for v in bundle_data.get("verification_results", []):
        v_copy = dict(v)
        v_copy["_id"] = v_copy.get("id") or v_copy.get("finding_id")
        v_copy["scan_id"] = scan_id
        await verification_col.replace_one({"scan_id": scan_id, "finding_id": v_copy.get("finding_id")}, v_copy, upsert=True)

    return scan_record
