"""
Integration tests for Scans REST API:
  POST /api/scans
  GET  /api/scans
  GET  /api/scans/{id}
  GET  /api/scans/{id}/findings
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.auth import initialize_auth
from app.core.config import settings
from app.database.client import get_database
from app.database.models import IsolationStatus, ProjectRecord, ValidationStatus
from app.database.repositories import ProjectRepository
from app.main import create_app
from app.services.scan_service import ScanService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VULN_FIXTURE = FIXTURES_DIR / "vulnerable_fastapi_app"


def _scan_wait_budget() -> float:
    """With a Docker daemon the verifier builds one patched image per fix (minutes);
    without Docker the demo fixture runs on the trusted host runner (seconds)."""
    try:
        import docker

        docker.from_env(timeout=3).ping()
        return 900.0
    except Exception:
        return 120.0


@pytest.fixture
def api_client(tmp_path: Path):
    """Creates a TestClient configured with auth and in-memory scan service."""
    app = create_app()
    token = initialize_auth()

    # Shared repositories for test
    scan_service = ScanService()

    from app.api.scans import get_scan_service
    app.dependency_overrides[get_scan_service] = lambda: scan_service

    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {token}"},
    )
    return client, scan_service


def test_create_scan_rejects_missing_project_id(api_client):
    client, _ = api_client
    r = client.post("/api/scans", json={})
    assert r.status_code == 422


def test_create_scan_rejects_non_existent_project(api_client):
    client, _ = api_client
    fake_id = str(uuid.uuid4())
    r = client.post("/api/scans", json={"project_id": fake_id})
    assert r.status_code == 400
    assert "not found" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_scans_api_full_pipeline_against_vulnerable_app(tmp_path: Path):
    """
    Test: POST a scan against vulnerable_fastapi_app, poll until complete,
    GET the findings back, assert the 3 confirmed findings with their
    fix/verification status are all present with correct field shapes.
    """
    token = initialize_auth()
    app = create_app()

    scan_service = ScanService()
    from app.api.scans import get_scan_service
    app.dependency_overrides[get_scan_service] = lambda: scan_service

    # Create and register a ready project pointing to VULN_FIXTURE
    project_id = str(uuid.uuid4())
    project = ProjectRecord(
        id=project_id,
        name="Vulnerable Test App",
        source_path=str(VULN_FIXTURE),
        validation_status=ValidationStatus.VALID,
        entry_point="main.py",
        isolation_status=IsolationStatus.READY,
    )
    # Store project in service memory store
    await scan_service._project_repo.create(project)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        # 1. Trigger scan via POST /api/scans
        res = await client.post("/api/scans", json={"project_id": project_id})
        assert res.status_code == 202, res.text
        body = res.json()
        assert "scan_id" in body or "scanId" in body
        scan_id = body.get("scan_id") or body.get("scanId")
        assert scan_id is not None

        # 2. Check GET /api/scans (list)
        list_res = await client.get("/api/scans")
        assert list_res.status_code == 200
        scans_list = list_res.json()
        assert any(s["id"] == scan_id for s in scans_list)

        # 3. Poll GET /api/scans/{id} until completed (background task executes)
        max_wait = _scan_wait_budget()
        start_time = time.time()
        final_scan = None

        while time.time() - start_time < max_wait:
            status_res = await client.get(f"/api/scans/{scan_id}")
            assert status_res.status_code == 200
            scan_data = status_res.json()
            if scan_data["state"] in ("completed", "failed"):
                final_scan = scan_data
                break
            await asyncio.sleep(1.0)

        assert final_scan is not None, f"Scan timed out after {max_wait}s (last stage: {scan_data.get('stage')}, state: {scan_data.get('state')})"
        assert final_scan["state"] == "completed", f"Scan failed: {final_scan.get('error')}"
        assert final_scan["findings_confirmed"] == 3
        assert final_scan["findingsConfirmed"] == 3

        # UI contract metric assertions
        assert final_scan["endpoints_discovered"] > 0
        assert final_scan["endpointsDiscovered"] > 0
        assert final_scan["tests_executed"] >= 3
        assert final_scan["testsExecuted"] >= 3
        assert final_scan["fixes_generated"] == 3
        assert final_scan["fixesGenerated"] == 3
        assert final_scan["fixes_verified"] == 3
        assert final_scan["fixesVerified"] == 3
        assert "builder" in final_scan.get("stage_durations", {})
        assert "builder" in final_scan.get("stageDurations", {})

        # Check counters
        counters = final_scan["counters"]
        assert counters["confirmed"] == 3
        assert counters["fixes_applied"] == 3
        assert counters["fixes_verified"] == 3

        # 4. Fetch findings via GET /api/scans/{id}/findings
        findings_res = await client.get(f"/api/scans/{scan_id}/findings")
        assert findings_res.status_code == 200
        findings = findings_res.json()
        assert len(findings) == 3

    categories = {f["category"] for f in findings}
    assert categories == {"BOLA", "BOPLA_MASS_ASSIGN", "SECURITY_MISCONFIG"}

    # 5. Assert each finding conforms strictly to the Finding model in desktop/lib/models/finding.dart
    for f in findings:
        assert isinstance(f["id"], str)
        assert f["scanId"] == scan_id
        assert isinstance(f["title"], str)
        assert isinstance(f["category"], str)
        assert isinstance(f["cwe"], str)
        assert f["severity"] in ("critical", "high", "medium", "low", "informational")
        assert f["confidence"] in ("high", "medium", "low")
        assert isinstance(f["routeTemplate"], str)
        assert isinstance(f["method"], str)
        assert isinstance(f["description"], str)
        assert isinstance(f["impact"], str)
        assert f["runtimeConfirmed"] is True
        assert f["status"] == "confirmed"
        assert isinstance(f["sourceLocations"], list)
        for loc in f["sourceLocations"]:
            assert "file" in loc
            assert "lineStart" in loc
            assert "lineEnd" in loc

        # Post-fix & verification check: all 3 seeded findings should be verified
        assert f["remediationStatus"] == "fixVerified", f"Expected fixVerified, got {f['remediationStatus']}"
        assert f["createdAt"] is not None


@pytest.mark.asyncio
async def test_scans_api_pipeline_against_secure_app():
    """
    Test: POST a scan against secure_fastapi_app (negative reference fixture).
    Asserts:
    - Zero confirmed findings (false positive rate = 0).
    - Endpoints discovered > 0.
    - Tests executed > 0.
    - Zero fixes proposed or verified.
    - Scan state completed cleanly.
    - UI contract fields accurately reflect zero findings and genuine activity.
    """
    token = initialize_auth()
    app = create_app()

    scan_service = ScanService()
    from app.api.scans import get_scan_service
    app.dependency_overrides[get_scan_service] = lambda: scan_service

    project_id = str(uuid.uuid4())
    project = ProjectRecord(
        id=project_id,
        name="Secure Test App",
        source_path=str(FIXTURES_DIR / "secure_fastapi_app"),
        validation_status=ValidationStatus.VALID,
        entry_point="main.py",
        isolation_status=IsolationStatus.READY,
    )
    await scan_service._project_repo.create(project)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        res = await client.post("/api/scans", json={"project_id": project_id})
        assert res.status_code == 202
        body = res.json()
        scan_id = body.get("scan_id") or body.get("scanId")

        # Poll until complete
        max_wait = _scan_wait_budget()
        start_time = time.time()
        final_scan = None

        while time.time() - start_time < max_wait:
            status_res = await client.get(f"/api/scans/{scan_id}")
            assert status_res.status_code == 200
            scan_data = status_res.json()
            if scan_data["state"] in ("completed", "failed"):
                final_scan = scan_data
                break
            await asyncio.sleep(1.0)

        assert final_scan is not None
        assert final_scan["state"] == "completed", f"Scan failed: {final_scan.get('error')}"
        assert final_scan["findings_confirmed"] == 0
        assert final_scan["findingsConfirmed"] == 0
        assert final_scan["endpoints_discovered"] > 0
        assert final_scan["endpointsDiscovered"] > 0
        assert final_scan["tests_executed"] > 0
        assert final_scan["testsExecuted"] > 0
        assert final_scan["fixes_generated"] == 0
        assert final_scan["fixesGenerated"] == 0
        assert final_scan["fixes_verified"] == 0
        assert final_scan["fixesVerified"] == 0

        findings_res = await client.get(f"/api/scans/{scan_id}/findings")
        assert findings_res.status_code == 200
        assert len(findings_res.json()) == 0


@pytest.mark.asyncio
async def test_scans_api_pipeline_with_prohibited_delete_route(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "trusted_fixtures_root", tmp_path)
    """
    Integration test: Runs a complete scan pipeline against an app containing
    a prohibited DELETE route (/admin/users/{user_id}) alongside safe routes.
    Verifies that:
    1. The pipeline does not abort on NonDestructivePolicyViolationError.
    2. The prohibited DELETE route is recorded as skipped_policy.
    3. The safe routes are executed.
    4. Metrics reflect tests_skipped_policy >= 1 and tests_executed >= 1.
    5. The final scan state transitions to 'completed'.
    """
    token = initialize_auth()
    app_fastapi = create_app()

    scan_service = ScanService()
    from app.api.scans import get_scan_service
    app_fastapi.dependency_overrides[get_scan_service] = lambda: scan_service

    project_id = str(uuid.uuid4())
    # Create a small FastAPI project directory in tmp_path with workspaces in path
    proj_dir = tmp_path / "workspaces" / project_id / "scan_workspace"
    proj_dir.mkdir(parents=True)
    (proj_dir / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (proj_dir / "main.py").write_text('''
from fastapi import FastAPI

app = FastAPI(title="App With Delete")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/admin/users")
def list_admin_users():
    return [{"id": 1, "username": "admin"}]

@app.delete("/admin/users/{user_id}")
def delete_admin_user(user_id: int):
    return {"status": "deleted", "user_id": user_id}
''')
    project = ProjectRecord(
        id=project_id,
        name="App With Delete",
        source_path=str(proj_dir),
        workspace_path=str(proj_dir),
        validation_status=ValidationStatus.VALID,
        entry_point="main.py",
        isolation_status=IsolationStatus.READY,
    )
    await scan_service._project_repo.create(project)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_fastapi),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        # Trigger scan
        res = await client.post("/api/scans", json={"project_id": project_id})
        assert res.status_code == 202
        scan_id = res.json()["scan_id"]

        # Poll until complete
        max_wait = 60.0
        start_time = time.time()
        final_scan = None

        while time.time() - start_time < max_wait:
            status_res = await client.get(f"/api/scans/{scan_id}")
            assert status_res.status_code == 200
            scan_data = status_res.json()
            if scan_data["state"] in ("completed", "failed"):
                final_scan = scan_data
                break
            await asyncio.sleep(1.0)

        assert final_scan is not None, f"Scan timed out (last stage: {scan_data.get('stage')}, state: {scan_data.get('state')})"
        assert final_scan["state"] == "completed", f"Scan failed: {final_scan.get('error')}"
        assert final_scan["tests_skipped_policy"] >= 1
        assert final_scan["testsSkippedPolicy"] >= 1
        assert final_scan["tests_executed"] >= 1
        assert final_scan["testsExecuted"] >= 1
        assert final_scan["tests_generated"] >= final_scan["tests_executed"] + final_scan["tests_skipped_policy"]

