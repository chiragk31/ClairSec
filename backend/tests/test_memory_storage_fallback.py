"""
D3: the backend must start and be useful without MongoDB and without Docker.

Boots the real app (real lifespan, real routes, real scan pipeline) against an
unreachable MongoDB URL with Docker unavailable, then runs the Demo flow purely
over HTTP. Only the Docker daemon is faked (process boundary).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture()
def memory_app(monkeypatch):
    monkeypatch.setattr(settings, "mongodb_url", "mongodb://127.0.0.1:9")  # nothing listens here
    monkeypatch.setattr(settings, "memory_storage_fallback", True)
    from app.main import create_app

    return create_app()


def test_backend_starts_on_memory_storage_and_runs_demo_scan(memory_app):
    from app.core.auth import get_launch_token

    docker_down = Exception("Docker daemon not available")
    with patch("app.services.scan_service.DockerManager", side_effect=docker_down), \
         patch("app.agents.verifier.verifier.DockerManager", side_effect=docker_down), \
         patch("app.api.system.DockerManager", side_effect=docker_down):
        with TestClient(memory_app) as client:
            client.headers["Authorization"] = f"Bearer {get_launch_token()}"

            pre = client.get("/api/system/preflight").json()
            assert pre["storage"] == "memory"
            assert pre["mongodb"]["fallback"] == "memory"
            assert pre["mode"]["id"] == "demo"

            project = client.post("/api/projects/demo", json={"fixture": "vulnerable"}).json()
            assert project.get("origin", "demo_fixture") == "demo_fixture"
            pid = project["id"]

            scan = client.post("/api/scans", json={"project_id": pid}).json()
            sid = scan.get("scan_id") or scan.get("scanId") or scan.get("id")

            state = None
            for _ in range(240):
                state = client.get(f"/api/scans/{sid}").json()
                if state.get("state") in ("completed", "failed", "cancelled"):
                    break
                time.sleep(0.5)
            assert state and state.get("state") == "completed", state

            findings = client.get(f"/api/scans/{sid}/findings").json()
            confirmed = [f for f in findings if str(f.get("status", "")).lower() == "confirmed"]
            assert len(confirmed) >= 1, findings

            # The Demo flow fixes and VERIFIES at least one finding (dual criterion) on the host
            # fixture handle — allowed only because origin=demo_fixture and the provider is mock.
            counters = state.get("counters") or {}
            verified = state.get("fixesVerified") or state.get("fixes_verified") or counters.get("fixes_verified", 0)
            assert verified >= 1, state
            assert (state.get("posture") or {}).get("after", 0) > (state.get("posture") or {}).get("before", 100), state

            # Data persisted across requests (shared in-memory DB, not per-request stores).
            listed = client.get("/api/projects").json()
            assert any(p["id"] == pid for p in listed)


def _run_demo_scan(client) -> tuple[str, list[dict]]:
    pid = client.post("/api/projects/demo", json={"fixture": "vulnerable"}).json()["id"]
    scan = client.post("/api/scans", json={"project_id": pid}).json()
    sid = scan.get("scan_id") or scan.get("scanId") or scan.get("id")
    for _ in range(240):
        st = client.get(f"/api/scans/{sid}").json()
        if st.get("state") in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert st.get("state") == "completed", st
    return sid, client.get(f"/api/scans/{sid}/findings").json()


def _await_replay(client, replay_id: str) -> dict:
    for _ in range(240):
        r = client.get(f"/api/replays/{replay_id}").json()
        if r.get("state") in ("completed", "failed"):
            return r
        time.sleep(0.25)
    raise AssertionError("replay did not finish")


def test_replay_original_fires_and_patched_is_blocked(memory_app):
    """F8: the same stored attack works on the original app and is blocked on the patched app."""
    from app.core.auth import get_launch_token
    from app.database.client import get_database

    docker_down = Exception("Docker daemon not available")
    with patch("app.services.scan_service.DockerManager", side_effect=docker_down), \
         patch("app.agents.verifier.verifier.DockerManager", side_effect=docker_down), \
         patch("app.api.system.DockerManager", side_effect=docker_down):
        with TestClient(memory_app) as client:
            client.headers["Authorization"] = f"Bearer {get_launch_token()}"
            sid, findings = _run_demo_scan(client)
            bola = next(f for f in findings if f.get("category") == "BOLA"
                        and str(f.get("status", "")).lower() == "confirmed")

            orig = _await_replay(client, client.post(f"/api/findings/{bola['id']}/replay",
                                                     json={"target": "original"}).json()["id"])
            assert orig["state"] == "completed", orig
            assert orig["oracle_fired"] is True, orig
            assert orig["exchange"]["response"]["status"] == 200

            patched = _await_replay(client, client.post(f"/api/findings/{bola['id']}/replay",
                                                        json={"target": "patched"}).json()["id"])
            assert patched["state"] == "completed", patched
            assert patched["oracle_fired"] is False, patched

            listed = client.get(f"/api/findings/{bola['id']}/replays").json()
            assert {r["target"] for r in listed} == {"original", "patched"}

            # Append-only: replays are new test_cases with kind=replay; originals untouched.
            async def count():
                db = get_database()
                replays = await db["test_cases"].count_documents({"kind": "replay", "scan_id": sid})
                originals = await db["test_cases"].count_documents({"scan_id": sid, "kind": {"$ne": "replay"}})
                return replays, originals
            replays, originals = client.portal.call(count)
            assert replays == 2 and originals >= 3
