"""
V7 / F12: reports people can act on, without leaking secrets or overclaiming.

End-to-end tests run a real Demo scan on the in-memory database, then generate
reports through the HTTP API. Only the Docker daemon is faked.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

SARIF_SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"
# Source: https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json

# A verdict that the app is safe. Mentions such as the fixture name "secure_fastapi_app"
# or "Trust Check: Secure FastAPI App" are fine; claiming security is not.
SECURE_VERDICT = re.compile(
    r"\b(app|application|project|api|system|it|this)\s+is\s+(now\s+)?secure\b|status[:\s]+secure\b|>\s*secure\s*<",
    re.IGNORECASE,
)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mongodb_url", "mongodb://127.0.0.1:9")
    monkeypatch.setattr(settings, "workspace_root", str(tmp_path / "ws"))
    from app.core.auth import get_launch_token
    from app.main import create_app

    down = Exception("Docker daemon not available")
    with patch("app.services.scan_service.DockerManager", side_effect=down), \
         patch("app.agents.verifier.verifier.DockerManager", side_effect=down), \
         patch("app.api.system.DockerManager", side_effect=down):
        with TestClient(create_app()) as c:
            c.headers["Authorization"] = f"Bearer {get_launch_token()}"
            yield c


def _scan(client, fixture: str) -> str:
    pid = client.post("/api/projects/demo", json={"fixture": fixture}).json()["id"]
    sc = client.post("/api/scans", json={"project_id": pid}).json()
    sid = sc.get("scan_id") or sc.get("scanId") or sc.get("id")
    for _ in range(240):
        st = client.get(f"/api/scans/{sid}").json()
        if st.get("state") in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert st["state"] == "completed", st
    return sid


def _download(client, report_id: str, fmt: str) -> str:
    r = client.get(f"/api/reports/{report_id}/download", params={"format": fmt})
    assert r.status_code == 200, r.text
    return r.text


def test_demo_report_all_formats_and_sarif_is_valid(client):
    sid = _scan(client, "vulnerable")
    rec = client.post(f"/api/scans/{sid}/reports", json={}).json()
    assert {"html", "md", "json", "sarif"} <= set(rec["formats"])
    from app.reporting.pdf import find_browser
    if find_browser() is not None:
        assert "pdf" in rec["formats"], rec.get("pdf_note")
    assert rec["confirmed_count"] >= 1

    html = _download(client, rec["id"], "html")
    assert "Executive summary" in html and "Confirmed findings" in html
    assert "Fix verified" in html
    assert "No AI" in html or "AI models only proposed" in html
    assert not SECURE_VERDICT.search(html)

    sarif = json.loads(_download(client, rec["id"], "sarif"))
    jsonschema.validate(sarif, json.loads(SARIF_SCHEMA.read_text(encoding="utf-8")))
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "ClairSec"
    assert run["results"] and all(r["properties"]["cvss"]["score"] is not None for r in run["results"])

    md = _download(client, rec["id"], "md")
    assert "Security score" in md

    data = json.loads(_download(client, rec["id"], "json"))
    m = data["method"]
    assert m["platform_version"] == settings.version
    assert m["llm_provider"] == "mock" and m["model_id"]
    assert m["posture_version"] == "posture_v1"
    assert m["experience_mode"] == "demo"
    assert m["storage_mode"] == "memory"
    assert m["prompt_registry_digest"] not in (None, "", "not recorded")

    listed = client.get(f"/api/scans/{sid}/reports").json()
    assert listed and listed[0]["id"] == rec["id"]


def test_trust_check_report_never_claims_secure(client):
    sid = _scan(client, "secure")
    rec = client.post(f"/api/scans/{sid}/reports", json={}).json()
    assert rec["confirmed_count"] == 0
    for fmt in ("html", "md", "json"):
        text = _download(client, rec["id"], fmt)
        assert not SECURE_VERDICT.search(text), fmt
    assert "does not mean" in _download(client, rec["id"], "html")


@pytest.mark.asyncio
async def test_canary_secret_is_absent_from_every_format(tmp_path, monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    from app.reporting.service import generate_report

    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    canary = "CANARY_SECRET_REPORT_7F3A"
    db = AsyncMongoMockClient()["canary"]
    await db.projects.insert_one({"id": "p", "name": "Canary App", "origin": "user_project"})
    await db.scans.insert_one({"id": "s", "project_id": "p", "state": "completed", "mode": "live",
                               "posture": {"before": 82, "after": 82, "grade_before": "B", "grade_after": "B"}})
    await db.test_cases.insert_one({
        "id": "t", "scan_id": "s", "category": "BOPLA_DATA_EXPOSURE", "route_template": "/me", "method": "GET",
        "request": {"method": "GET", "url_path": "/me", "headers": {"X-Debug": canary}},
        "response": {"status": 200, "body": f'{{"api_key": "{canary}"}}'},
        "oracle_result": {"fired": True, "rule_id": "R", "rationale": f"leaked {canary}"},
        "status": "executed", "kind": "attack",
    })
    await db.findings.insert_one({
        "id": "f", "scan_id": "s", "project_id": "p", "title": "Data exposure", "category": "BOPLA_DATA_EXPOSURE",
        "cwe": ["CWE-213"], "route_template": "/me", "method": "GET", "status": "confirmed",
        "description": f"Response contained {canary}", "impact": "i", "runtime_confirmed": True,
        "oracle_rule_id": "R", "evidence_ids": ["t"],
        "cvss": {"base_score": 6.5, "severity": "medium", "vector_string": "CVSS:3.1/AV:N"},
        "confidence": {"inputs": {"oracle_fired": True, "reproduced_n_times": 2}, "score": 0.8},
        "reproduction_summary": f"Saw {canary} twice",
    })
    rec = await generate_report(db, "s")
    for fmt, path in rec["files"].items():
        assert canary.encode() not in Path(path).read_bytes(), fmt


@pytest.mark.asyncio
async def test_pdf_report_is_printed_from_html(tmp_path, monkeypatch):
    """F12 PDF: printed from the redacted HTML by a local Chromium browser (Edge on Windows)."""
    from mongomock_motor import AsyncMongoMockClient

    from app.reporting.pdf import find_browser
    from app.reporting.service import generate_report

    if find_browser() is None:
        pytest.skip("No Edge/Chrome/Chromium installed on this machine")
    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    db = AsyncMongoMockClient()["pdf"]
    await db.projects.insert_one({"id": "p", "name": "PDF App"})
    await db.scans.insert_one({"id": "s", "project_id": "p", "state": "completed", "mode": "demo",
                               "posture": {"before": 70, "after": 100, "grade_before": "C", "grade_after": "A"}})
    rec = await generate_report(db, "s", ["pdf"])
    pdf = Path(rec["files"]["pdf"])
    assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size > 1000, rec.get("pdf_note")
    assert "html" in rec["files"]
