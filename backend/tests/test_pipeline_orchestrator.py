"""
Tests for PipelineOrchestrator and Autopilot state machine (FEATURES.md F3 exit gate).

Tests:
- Happy path (import -> isolate -> scan -> report)
- Failure at each stage (import, isolate, scan)
- Resume from failed stage (does not re-run completed stages)
- Cancellation
- API endpoints (POST /api/pipelines, GET, cancel, resume, 422 on missing authorization)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_launch_token, initialize_auth
from app.database.models import (
    IsolationStatus,
    JobRecord,
    JobStatus,
    PipelineRecord,
    PipelineStage,
    PipelineStatus,
    ProjectRecord,
    ScanRecord,
    ValidationStatus,
)
from app.main import create_app
from app.services.pipeline_orchestrator import PipelineOrchestrator


@pytest.fixture
def orchestrator():
    # A real in-memory database, so the Report stage generates a real report (V7).
    from mongomock_motor import AsyncMongoMockClient

    return PipelineOrchestrator(AsyncMongoMockClient()["pipeline_tests"])


@pytest.fixture
def auth_headers():
    initialize_auth()
    token = get_launch_token()
    return {"Authorization": f"Bearer {token}", "Host": "testserver"}


@pytest.mark.asyncio
async def test_pipeline_happy_path(orchestrator, monkeypatch):
    """Happy path: import -> isolate -> scan -> report all complete."""
    project = ProjectRecord(
        name="test_proj",
        source_path="/tmp/test",
        validation_status=ValidationStatus.VALID,
        isolation_status=IsolationStatus.READY,
        proxy_port=8001,
    )
    await orchestrator._project_repo.create(project)

    pipeline = await orchestrator.create_pipeline(project_id=project.id)
    assert pipeline.stages[PipelineStage.IMPORT.value].status == "completed"

    # Mock ScanService
    mock_scan = ScanRecord(project_id=project.id, state="completed")
    await orchestrator._scan_repo.create(mock_scan)

    with patch("app.services.pipeline_orchestrator.ScanService") as mock_scan_svc_cls:
        mock_scan_svc = mock_scan_svc_cls.return_value
        mock_scan_svc.submit_scan = AsyncMock(return_value=mock_scan)

        await orchestrator._run_pipeline(pipeline.id)

    updated = await orchestrator.get_pipeline(pipeline.id)
    assert updated.status == PipelineStatus.COMPLETED
    assert updated.stages[PipelineStage.IMPORT.value].status == "completed"
    assert updated.stages[PipelineStage.ISOLATE.value].status == "completed"
    assert updated.stages[PipelineStage.SCAN.value].status == "completed"
    assert updated.stages[PipelineStage.REPORT.value].status == "completed"
    assert updated.stages[PipelineStage.REPORT.value].line.startswith("Report ready")
    assert updated.report_id, "Autopilot must produce a real report"


@pytest.mark.asyncio
async def test_pipeline_failure_at_import(orchestrator):
    """Failure at import stage halts pipeline before isolate and scan."""
    git_data = {
        "url": "https://github.com/owner/badrepo",
        "authorization_affirmed": True,
    }
    pipeline = await orchestrator.create_pipeline(git_import_data=git_data)

    with patch("app.services.pipeline_orchestrator.GitImportService") as mock_git_cls:
        mock_git = mock_git_cls.return_value
        # Start import returns job that immediately fails
        job = JobRecord(project_id="p1", status=JobStatus.FAILED, error="Connection refused")
        project = ProjectRecord(name="badrepo", source_path="")
        await orchestrator._job_repo.create(job)
        mock_git.start_import = AsyncMock(return_value=(job, project))

        await orchestrator._run_pipeline(pipeline.id, git_import_data=git_data)

    updated = await orchestrator.get_pipeline(pipeline.id)
    assert updated.status == PipelineStatus.FAILED
    assert updated.current_stage == PipelineStage.IMPORT
    assert updated.stages[PipelineStage.IMPORT.value].status == "failed"
    assert "Connection refused" in updated.stages[PipelineStage.IMPORT.value].error
    # Later stages must remain pending
    assert updated.stages[PipelineStage.ISOLATE.value].status == "pending"
    assert updated.stages[PipelineStage.SCAN.value].status == "pending"


@pytest.mark.asyncio
async def test_pipeline_failure_at_isolate(orchestrator):
    """Failure at isolate stage captures error, fix hint, and stops before scan."""
    project = ProjectRecord(
        name="test_proj",
        source_path="/tmp/test",
        validation_status=ValidationStatus.VALID,
        isolation_status=IsolationStatus.IMPORT_FAILED,
        isolation_error="pip install failed: No matching distribution found for imaginary-pkg",
    )
    await orchestrator._project_repo.create(project)
    pipeline = await orchestrator.create_pipeline(project_id=project.id)

    # Docker daemon faked at the process boundary; the isolation runner leaves the project failed.
    with patch("app.isolation.docker_manager.DockerManager", MagicMock()),          patch("app.services.pipeline_orchestrator.execute_isolation_steps", new_callable=AsyncMock) as mock_iso:
        mock_iso.return_value = None  # project remains IMPORT_FAILED

        await orchestrator._run_pipeline(pipeline.id)

    updated = await orchestrator.get_pipeline(pipeline.id)
    assert updated.status == PipelineStatus.FAILED
    assert updated.current_stage == PipelineStage.ISOLATE
    assert updated.stages[PipelineStage.ISOLATE.value].status == "failed"
    assert updated.stages[PipelineStage.SCAN.value].status == "pending"
    assert updated.fix_hint is not None


@pytest.mark.asyncio
async def test_pipeline_resume_from_failed_stage(orchestrator):
    """Resuming a pipeline restarts from the failed stage without repeating completed stages."""
    project = ProjectRecord(
        name="test_proj",
        source_path="/tmp/test",
        validation_status=ValidationStatus.VALID,
        isolation_status=IsolationStatus.READY,
        proxy_port=8000,
    )
    await orchestrator._project_repo.create(project)

    pipeline = await orchestrator.create_pipeline(project_id=project.id)
    # Mark isolate as failed
    pipeline.status = PipelineStatus.FAILED
    pipeline.current_stage = PipelineStage.ISOLATE
    pipeline.stages[PipelineStage.ISOLATE.value].status = "failed"
    pipeline.stages[PipelineStage.ISOLATE.value].error = "Docker daemon unreachable"
    await orchestrator._pipeline_repo.update(pipeline)

    with patch.object(orchestrator, "start_pipeline", new_callable=AsyncMock) as mock_start:
        resumed = await orchestrator.resume_pipeline(pipeline.id)

    assert resumed.status == PipelineStatus.PENDING
    assert resumed.current_stage == PipelineStage.ISOLATE
    assert resumed.stages[PipelineStage.IMPORT.value].status == "completed"  # Preserved!
    assert resumed.stages[PipelineStage.ISOLATE.value].status == "pending"  # Reset for retry
    assert resumed.stages[PipelineStage.ISOLATE.value].error is None
    mock_start.assert_called_once_with(pipeline.id)


@pytest.mark.asyncio
async def test_pipeline_cancellation(orchestrator):
    """Cancelling a running pipeline cancels active task and updates state."""
    project = ProjectRecord(
        name="test_proj",
        source_path="/tmp/test",
        validation_status=ValidationStatus.VALID,
    )
    await orchestrator._project_repo.create(project)
    pipeline = await orchestrator.create_pipeline(project_id=project.id)
    pipeline.status = PipelineStatus.RUNNING
    pipeline.current_stage = PipelineStage.SCAN
    pipeline.stages[PipelineStage.SCAN.value].status = "running"
    await orchestrator._pipeline_repo.update(pipeline)

    cancelled = await orchestrator.cancel_pipeline(pipeline.id)
    assert cancelled.status == PipelineStatus.CANCELLED
    assert cancelled.stages[PipelineStage.SCAN.value].status == "cancelled"


def test_pipeline_api_routes(auth_headers):
    """Test REST API routes for pipelines."""
    from app.database.client import get_database

    app = create_app()
    app.dependency_overrides[get_database] = lambda: None
    client = TestClient(app)

    # 1. Reject without authorization affirmation (422)
    resp = client.post(
        "/api/pipelines",
        json={"git_import": {"url": "https://github.com/owner/repo", "authorization_affirmed": False}},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # 2. Reject if neither project_id nor git_import is provided
    resp = client.post(
        "/api/pipelines",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # 3. Create pipeline with project_id
    with patch("app.services.pipeline_orchestrator.PipelineOrchestrator.start_pipeline", new_callable=AsyncMock):
        resp = client.post(
            "/api/pipelines",
            json={"project_id": "proj_123"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "pipeline_id" in data
        pipeline_id = data["pipeline_id"]

        # 4. Get pipeline details
        get_resp = client.get(f"/api/pipelines/{pipeline_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        p_data = get_resp.json()
        assert p_data["id"] == pipeline_id
        assert "stages" in p_data
        assert PipelineStage.IMPORT.value in p_data["stages"]
        assert PipelineStage.REPORT.value in p_data["stages"]

        # 5. Cancel pipeline
        cancel_resp = client.post(f"/api/pipelines/{pipeline_id}/cancel", headers=auth_headers)
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # 6. Resume pipeline
        resume_resp = client.post(f"/api/pipelines/{pipeline_id}/resume", headers=auth_headers)
        assert resume_resp.status_code == 200



@pytest.mark.asyncio
async def test_autopilot_runs_real_scan_and_report_for_demo_project():
    """No ScanService mock: the scan stage must call a method that really exists
    (the mocked test above hid a call to a non-existent `start_scan`)."""
    from pathlib import Path
    from unittest.mock import patch as _patch

    from mongomock_motor import AsyncMongoMockClient

    from app.core.config import settings

    db = AsyncMongoMockClient()["autopilot_real"]
    orch = PipelineOrchestrator(db)
    project = ProjectRecord(
        name="Demo", source_path=str(Path(settings.trusted_fixtures_root) / "vulnerable_fastapi_app"),
        entry_point="main.py", validation_status=ValidationStatus.VALID, origin="demo_fixture",
    )
    await orch._project_repo.create(project)
    pipeline = await orch.create_pipeline(project_id=project.id)
    down = Exception("Docker daemon not available")
    with _patch("app.services.scan_service.DockerManager", side_effect=down),          _patch("app.agents.verifier.verifier.DockerManager", side_effect=down):
        await asyncio.wait_for(orch._run_pipeline(pipeline.id), timeout=240)
    done = await orch.get_pipeline(pipeline.id)
    assert done.status == PipelineStatus.COMPLETED, {k: (v.status, v.error) for k, v in done.stages.items()}
    assert done.scan_id and done.report_id
