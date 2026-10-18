"""F4 recorded runs: the shipped bundles come from real scans and replay into the app."""
from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.bundle_service import DEFAULT_BUNDLES_DIR, load_bundle


def test_shipped_bundles_are_valid_real_recordings():
    vuln = load_bundle(DEFAULT_BUNDLES_DIR / "demo-vulnerable.clairsec.json")
    assert vuln["recorded_from"].startswith("real Demo-mode scan")
    assert len(vuln["findings"]) >= 1 and len(vuln["events"]) >= 10
    seqs = [e["seq"] for e in vuln["events"]]
    assert seqs == sorted(seqs)
    secure = load_bundle(DEFAULT_BUNDLES_DIR / "demo-secure.clairsec.json")
    assert [f for f in secure["findings"] if str(f.get("status")).lower() == "confirmed"] == []


def test_watch_recorded_run_and_report_it(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mongodb_url", "mongodb://127.0.0.1:9")
    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    from app.core.auth import get_launch_token
    from app.main import create_app

    with patch("app.api.system.DockerManager", side_effect=Exception("down")):
        with TestClient(create_app()) as c:
            c.headers["Authorization"] = f"Bearer {get_launch_token()}"
            names = [b["file_name"] for b in c.get("/api/bundles").json()]
            assert "demo-vulnerable.clairsec.json" in names
            assert c.post("/api/bundles/..%5C..%5Csecret/replay").status_code in (400, 404)
            r = c.post("/api/bundles/demo-vulnerable/replay")
            assert r.status_code == 201, r.text
            sid = r.json()["scan_id"]
            scan = c.get(f"/api/scans/{sid}").json()
            assert scan["mode"] == "recorded" and scan["state"] == "completed"
            events = c.get(f"/api/scans/{sid}/events").json()
            assert len(events.get("events", events) if isinstance(events, dict) else events) >= 10
            rep = c.post(f"/api/scans/{sid}/reports", json={"formats": ["json"]}).json()
            data = json.loads(c.get(f"/api/reports/{rep['id']}/download", params={"format": "json"}).text)
            assert data["method"]["experience_mode"] == "recorded"
            assert len(data["confirmed"]) >= 1
