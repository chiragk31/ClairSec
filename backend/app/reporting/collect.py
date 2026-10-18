"""
Report data collection (FEATURES.md F12).

Gathers everything a report shows from stored records only, then passes every
string through the secret redactor BEFORE any renderer sees it
(THREAT_MODEL.md C5.2). Renderers never query the database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.glossary import GLOSSARY_ENTRIES
from app.llm.redaction import redact_secrets
from app.scoring.posture import IN_SCOPE_CATEGORIES, POSTURE_VERSION, _resolve_severity
from app.services.provenance_service import assemble_finding_provenance

# VULN_TAXONOMY.md section 2 - category -> (name, OWASP API Top 10 2023, primary CWE)
TAXONOMY: dict[str, tuple[str, str, str]] = {
    "BOLA": ("Broken Object Level Authorization", "API1:2023", "CWE-639"),
    "BROKEN_AUTH": ("Broken Authentication", "API2:2023", "CWE-287"),
    "BOPLA_MASS_ASSIGN": ("Mass assignment", "API3:2023", "CWE-915"),
    "BOPLA_DATA_EXPOSURE": ("Excessive data exposure", "API3:2023", "CWE-213"),
    "BFLA": ("Broken Function Level Authorization", "API5:2023", "CWE-285"),
    "RESOURCE_CONSUMPTION": ("Unrestricted resource consumption", "API4:2023", "CWE-770"),
    "INJECTION": ("Injection", "API8:2023 (adjacent)", "CWE-89"),
    "SECURITY_MISCONFIG": ("Security misconfiguration", "API8:2023", "CWE-16"),
}

# What each category means for the business, for the executive page.
IMPACT_SENTENCE: dict[str, str] = {
    "BOLA": "One customer can read or change another customer's records.",
    "BROKEN_AUTH": "Someone can act as a user without proving who they are.",
    "BOPLA_MASS_ASSIGN": "A user can give themselves powers they should not have, such as admin rights.",
    "BOPLA_DATA_EXPOSURE": "The app hands out private data that the screen never needed.",
    "BFLA": "Ordinary users can run actions meant only for administrators.",
    "RESOURCE_CONSUMPTION": "Anyone can overload the app or run up its costs.",
    "INJECTION": "Text typed by a visitor can be run as commands by the app.",
    "SECURITY_MISCONFIG": "An unsafe default setting exposes internal details to anyone.",
}


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _plain(category: str) -> str | None:
    entry = GLOSSARY_ENTRIES.get(category)
    return entry["plain"] if entry else None


async def _one(db: AsyncIOMotorDatabase, coll: str, query: dict) -> dict | None:
    doc = await db[coll].find_one(query)
    if doc:
        doc.pop("_id", None)
    return doc


async def _many(db: AsyncIOMotorDatabase, coll: str, query: dict, sort: str | None = None, limit: int = 0):
    cursor = db[coll].find(query)
    if sort:
        cursor = cursor.sort(sort, 1)
    if limit:
        cursor = cursor.limit(limit)
    out = []
    async for d in cursor:
        d.pop("_id", None)
        out.append(d)
    return out


def _status(value: Any) -> str:
    return str(getattr(value, "value", value) or "").lower()


async def collect_report_data(db: AsyncIOMotorDatabase, scan_id: str) -> dict[str, Any]:
    from app.database.client import storage_mode

    scan = await _one(db, "scans", {"id": scan_id})
    if scan is None:
        raise ValueError(f"Scan '{scan_id}' not found.")
    project = await _one(db, "projects", {"id": scan.get("project_id")}) or {}

    findings_raw = await _many(db, "findings", {"scan_id": scan_id})
    tests = [t for t in await _many(db, "test_cases", {"scan_id": scan_id}) if t.get("kind", "attack") != "replay"]
    patches = await _many(db, "patches", {"scan_id": scan_id})
    verifications = await _many(db, "verification_results", {"scan_id": scan_id})
    events = await _many(db, "agent_events", {"scan_id": scan_id}, sort="seq", limit=60)
    patch_by_f = {p.get("finding_id"): p for p in patches}
    ver_by_f = {v.get("finding_id"): v for v in verifications}

    confirmed, candidates = [], []
    for f in findings_raw:
        cat = str(f.get("category") or "").upper()
        name, owasp, cwe = TAXONOMY.get(cat, (cat.replace("_", " ").title(), "-", ", ".join(f.get("cwe") or [])))
        prov = await assemble_finding_provenance(f["id"], db)
        replays = await _many(db, "replays", {"finding_id": f["id"]})
        latest_replay = {r["target"]: r for r in sorted(replays, key=lambda r: r.get("created_at") or "")}
        ver = ver_by_f.get(f["id"])
        patch = patch_by_f.get(f["id"])
        cvss = f.get("cvss") or {}
        item = {
            "id": f["id"],
            "title": f.get("title") or name,
            "category": cat,
            "category_name": name,
            "owasp": owasp,
            "cwe": ", ".join(f.get("cwe") or []) or cwe,
            "method": f.get("method"),
            "route": f.get("route_template"),
            "severity": _resolve_severity(f),
            "cvss_score": cvss.get("base_score"),
            "cvss_vector": cvss.get("vector_string"),
            "description": f.get("description"),
            "impact": f.get("impact"),
            "plain": _plain(cat),
            "business_impact": IMPACT_SENTENCE.get(cat),
            "status": _status(f.get("status")),
            "status_reason": f.get("status_reason"),
            "reproduction_summary": f.get("reproduction_summary"),
            "source_locations": f.get("source_locations") or [],
            "provenance": prov,
            "patch": {
                "diff": "\n".join(x.get("diff", "") for x in (patch or {}).get("files") or []),
                "rationale": (patch or {}).get("rationale"),
                "root_cause": (patch or {}).get("root_cause"),
                "applied": (patch or {}).get("applied"),
            } if patch else None,
            "verification": {
                "outcome": _status(ver.get("outcome")),
                "reason": ver.get("outcome_reason"),
                "exploit_blocked": bool((ver.get("original_exploit") or {}).get("ran"))
                and not (ver.get("original_exploit") or {}).get("exploited"),
                "suite": ver.get("functional_suite") or {},
                "endpoint": ver.get("endpoint_preserved") or {},
            } if ver else None,
            "replays": latest_replay,
        }
        (confirmed if prov.get("lane") == "confirmed" else candidates).append(item)

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4, "unscored": 5}
    confirmed.sort(key=lambda x: (order.get(x["severity"], 9), x["title"]))

    posture = scan.get("posture") or {}
    tested_categories = sorted({str(t.get("category") or "").upper() for t in tests if t.get("category")})
    untested = [c for c in IN_SCOPE_CATEGORIES if c not in tested_categories]
    fixed = [c for c in confirmed if (c.get("verification") or {}).get("outcome") == "fixed"]
    needs_human = [c for c in confirmed if (c.get("verification") or {}).get("outcome") != "fixed"]

    llm = scan.get("llm") or {}
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scan": {
            "id": scan_id,
            "state": scan.get("state"),
            "mode": scan.get("mode", "live"),
            "started_at": str(scan.get("started_at") or scan.get("created_at") or ""),
            "ended_at": str(scan.get("ended_at") or ""),
            "counters": scan.get("counters") or {},
        },
        "project": {
            "name": project.get("name") or scan.get("project_name") or "Project",
            "origin": project.get("origin", "user_project"),
            "git_url": project.get("git_url"),
            "commit_sha": project.get("commit_sha"),
            # Already masked at import time; the raw values are never stored.
            "exposed_secrets": project.get("exposed_secrets") or [],
        },
        "posture": posture,
        "confirmed": confirmed,
        "candidates": candidates,
        "fixed": fixed,
        "needs_human": needs_human,
        "coverage": {
            "tested": tested_categories,
            "untested": [{"category": c, "reason": "No applicable endpoint or test was found for this category in this scan."}
                         for c in untested],
            # The scan's own counter (attacker tests); stored test cases also include the
            # Evaluator's independent re-runs, which are listed in the appendix.
            "tests_executed": int((scan.get("counters") or {}).get("tests_executed")
                                  or len([t for t in tests if t.get("status") == "executed"])),
            "tests_total": int((scan.get("counters") or {}).get("tests_generated") or len(tests)),
            "requests_recorded": len(tests),
        },
        "tests": [
            {"category": t.get("category"), "method": t.get("method"), "route": t.get("route_template"),
             "status": t.get("status"), "oracle_fired": bool((t.get("oracle_result") or {}).get("fired")),
             "http_status": (t.get("response") or {}).get("status")}
            for t in tests
        ],
        "timeline": [{"seq": e.get("seq"), "agent": e.get("agent"), "kind": e.get("kind"),
                      "title": e.get("title"), "plain": e.get("plain")} for e in events],
        "method": {
            "platform_version": settings.version,
            "llm_provider": llm.get("provider", "not recorded"),
            "model_id": llm.get("model_id", "not recorded"),
            "prompt_registry_digest": llm.get("prompt_registry_digest", "not recorded"),
            "posture_version": posture.get("version", POSTURE_VERSION),
            "experience_mode": scan.get("mode", "live"),
            "storage_mode": storage_mode(),
        },
    }
    data["summary"] = executive_summary(data)
    return _redact(data)


def executive_summary(d: dict[str, Any]) -> list[str]:
    """Three plain sentences built from data. Never claims the app is safe."""
    n_conf = len(d["confirmed"])
    n_fixed = len(d["fixed"])
    tests = d["coverage"]["tests_executed"]
    cats = len(d["coverage"]["tested"])
    p = d.get("posture") or {}
    if n_conf == 0:
        first = (f"ClairSec ran {tests} real attacks across {cats} categories and could not prove any "
                 "vulnerability. That is not a guarantee: untested categories and logic outside these "
                 "attacks may still hide problems.")
    else:
        first = (f"ClairSec ran {tests} real attacks against a sealed copy of {d['project']['name']} and "
                 f"proved {n_conf} vulnerabilit{'y' if n_conf == 1 else 'ies'} with captured evidence.")
    second = (f"{n_fixed} of {n_conf} were fixed and the fix was re-tested: the attack no longer works and "
              "the app still behaves as before." if n_conf else
              "No fixes were needed for the attacks that were run.")
    third = (f"Security score: {p.get('before')} ({p.get('grade_before')}) before fixes, "
             f"{p.get('after')} ({p.get('grade_after')}) after verified fixes."
             if p.get("before") is not None else "A security score was not computed for this scan.")
    return [first, second, third]
