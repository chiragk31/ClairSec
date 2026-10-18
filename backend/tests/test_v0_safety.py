"""
Tests for Phase V0 Safety & Stability Foundation (FEATURES.md F0, F1, F4).

Exit gates verified here:
1. Canary test: proves a non-fixture project without a container is never imported by the backend.
2. Verifier test: asserts patched-image build + hardened run (mocked Docker).
3. Preflight and mode: verifies all diagnostic fields and ensures secret keys are never exposed.
4. TrustedFixtureTargetHandle: verifies strict path gating.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from app.agents.evaluator.schemas import EvaluatedFinding, EvaluationStatus
from app.agents.fixer.schemas import PatchRecord
from app.agents.verifier.schemas import (
    FunctionalSuiteResult,
    OriginalExploitResult,
    VariantAttackResult,
    VerificationOutcome,
)
from app.agents.verifier.verifier import VerifierAgent
from app.api.system import _resolve_experience_mode
from app.core.config import settings
from app.database.models import ProjectRecord, ScanRecord, ValidationStatus
from app.isolation.errors import IsolationError
from app.services.scan_service import ScanService
from app.targets.handle import (
    TargetAccessForbiddenError,
    TrustedFixtureTargetHandle,
    is_trusted_fixture_path,
)


# -----------------------------------------------------------------------------
# 1. Canary Test (Exit Gate 1)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_canary_proves_non_fixture_project_never_imported_by_backend(tmp_path: Path):
    """
    Canary test: a non-fixture project without a running container must NEVER be
    imported by the backend process on the host.

    If imported, main.py writes a canary file. This test asserts that running a scan
    on such a project refuses host execution, attempts isolation, and never creates the canary.
    """
    # Create an untrusted project outside tests/fixtures/
    untrusted_dir = tmp_path / "untrusted_external_project"
    untrusted_dir.mkdir(parents=True)

    canary_file = untrusted_dir / "HOST_IMPORTED_CANARY.txt"
    app_file = untrusted_dir / "main.py"

    # Python code that writes a canary file immediately upon module execution/import
    app_file.write_text(
        f"""
from pathlib import Path
Path(r"{canary_file}").write_text("VULNERABILITY: host execution occurred!")
from fastapi import FastAPI
app = FastAPI()
@app.get("/")
def root(): return {{"status": "ok"}}
"""
    )

    project_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())

    project = ProjectRecord(
        id=project_id,
        name="Untrusted User Project",
        source_path=str(untrusted_dir),
        entry_point="main.py",
        validation_status=ValidationStatus.VALID,
        container_id=None,  # No running container
        proxy_port=None,
    )
    scan = ScanRecord(
        id=scan_id,
        project_id=project_id,
        state="pending",
    )

    mock_db = MagicMock()
    mock_docker = MagicMock()
    # Mock isolation failure to verify the scan aborts safely without host fallback
    mock_docker.build_image.side_effect = IsolationError("Docker daemon simulated offline")

    scan_service = ScanService(
        db=mock_db,
        docker_manager=mock_docker,
    )
    scan_service._project_repo.get_by_id = AsyncMock(return_value=project)
    scan_service._scan_repo.get_by_id = AsyncMock(return_value=scan)
    scan_service._scan_repo.update = AsyncMock(return_value=scan)

    # Run the scan pipeline
    await scan_service._run_scan_pipeline(scan_id, project_id)

    # CRITICAL INVARIANT: The canary file must NOT exist on disk!
    assert not canary_file.exists(), (
        "SECURITY VIOLATION: Non-fixture project code was executed on the host!"
    )
    # The scan state should be failed due to isolation failure, never completed on host
    assert scan.state == "failed"
    assert "isolation_required" in (scan.error or "")


# -----------------------------------------------------------------------------
# 2. TrustedFixtureTargetHandle Gating
# -----------------------------------------------------------------------------

def test_trusted_fixture_target_handle_refuses_non_fixture_path(tmp_path: Path):
    """Verify that TrustedFixtureTargetHandle refuses arbitrary non-fixture paths."""
    untrusted_dir = tmp_path / "some_random_app"
    untrusted_dir.mkdir(parents=True)

    with pytest.raises(TargetAccessForbiddenError) as exc_info:
        TrustedFixtureTargetHandle(workspace_dir=untrusted_dir)

    assert "refused non-fixture path" in str(exc_info.value)


def test_is_trusted_fixture_path():
    """Verify trusted fixture path detection."""
    assert is_trusted_fixture_path(Path(__file__).parent / "fixtures" / "vulnerable_fastapi_app")
    assert is_trusted_fixture_path(Path(__file__).parent / "fixtures" / "valid_fastapi_app")
    assert not is_trusted_fixture_path("C:/Users/someone/my_app")
    assert not is_trusted_fixture_path("/home/user/projects/fastapi_app")


# -----------------------------------------------------------------------------
# 3. Verifier Patched Image Build & Hardened Run (Exit Gate 2)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verifier_builds_patched_image_and_runs_hardened_container(tmp_path: Path):
    """
    Exit Gate 2: Verifier test asserts a patched image build + hardened run (mocked Docker).
    """
    project_id = str(uuid.uuid4())
    patch_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())
    finding_id = str(uuid.uuid4())

    mod_ws = tmp_path / "workspaces" / project_id / "modified_workspace"
    mod_ws.mkdir(parents=True)
    (mod_ws / "main.py").write_text("app = None")

    from app.agents.evaluator.schemas import (
        CvssResult,
        CvssInputs,
        ConfidenceResult,
        ConfidenceInputs,
        SeverityBand,
        ConfidenceLevel,
    )

    cvss = CvssResult(
        inputs=CvssInputs(),
        vector_string="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        base_score=7.5,
        severity=SeverityBand.HIGH,
    )
    confidence = ConfidenceResult(
        inputs=ConfidenceInputs(
            runtime_confirmed=True,
            oracle_fired=True,
            reproduced_n_times=1,
            evidence_complete=True,
        ),
        band=ConfidenceLevel.HIGH,
        score=0.9,
    )
    finding = EvaluatedFinding(
        id=finding_id,
        scan_id=scan_id,
        project_id=project_id,
        title="BOLA Finding",
        category="BOLA",
        cwe=["CWE-639"],
        route_template="/users/{user_id}",
        method="GET",
        description="BOLA vulnerability",
        impact="Unauthorized data access",
        status=EvaluationStatus.CONFIRMED,
        runtime_confirmed=True,
        oracle_rule_id="ORACLE-BOLA-01",
        cvss=cvss,
        confidence=confidence,
    )
    patch_record = PatchRecord(
        id=patch_id,
        scan_id=scan_id,
        project_id=project_id,
        finding_id=finding_id,
        applied=True,
    )
    project = ProjectRecord(
        id=project_id,
        name="External App",
        source_path=str(tmp_path / "external_source"),
        entry_point="main.py",
        dependency_file="requirements.txt",
        validation_status=ValidationStatus.VALID,
    )

    mock_docker = MagicMock()
    expected_tag = f"clairsec-image-{project_id[:8]}-patched:{patch_id[:8]}"
    mock_docker.patched_image_tag.return_value = expected_tag
    mock_docker.build_image.return_value = expected_tag
    mock_docker.start_patched_target.return_value = ("target_cid_123", "proxy_cid_456", 49152)
    mock_docker.cleanup_patched_target.return_value = None

    mock_ver_repo = MagicMock()
    mock_ver_repo.create = AsyncMock(side_effect=lambda r: r)

    verifier = VerifierAgent(
        verification_repo=mock_ver_repo,
        docker_manager=mock_docker,
    )

    # Mock retester and functional runner to avoid network calls against mock port
    verifier._retester.retest = AsyncMock(
        return_value=OriginalExploitResult(ran=True, exploited=False, rationale="Blocked")
    )
    # User project: "App still works" comes from the auto-generated smoke suite against a
    # pre-fix baseline (F9). The baseline itself is out of scope for this container test.
    verifier._run_functional_check = AsyncMock(
        return_value=FunctionalSuiteResult(ran=True, passed=5, failed=0, total=5, source="auto_smoke")
    )
    verifier._variant_runner.run_variant_attack = AsyncMock(
        return_value=VariantAttackResult(ran=True, exploited=False, variant_kind="bypass_header")
    )

    summary = await verifier.verify_scan(
        findings=[finding],
        patches=[patch_record],
        scan_id=scan_id,
        modified_workspace=mod_ws,
        entry_point="main.py",
        project=project,
    )

    # Assert patched image was built with the exact tag format
    mock_docker.build_image.assert_called_once_with(
        project_id,
        mod_ws,
        "main.py",
        "requirements.txt",
        expected_tag,
    )

    # Assert hardened patched target + proxy container were started with sqlite env
    mock_docker.start_patched_target.assert_called_once_with(
        project_id,
        patch_id,
        expected_tag,
        {},
    )

    # Assert patched target was torn down in cleanup
    mock_docker.cleanup_patched_target.assert_called_once_with(
        project_id,
        patch_id,
    )

    assert summary.fixed_count == 1


# -----------------------------------------------------------------------------
# 4. Preflight & Experience Mode Endpoints
# -----------------------------------------------------------------------------

def test_preflight_diagnostics_structure_and_secret_redaction(authed_client: TestClient):
    """
    Asserts GET /api/system/preflight returns all required diagnostic fields
    and NEVER leaks the API key string.
    """
    resp = authed_client.get("/api/system/preflight")
    assert resp.status_code == 200
    data = resp.json()

    # Required top-level keys
    assert "ready" in data
    assert "mongodb" in data
    assert "docker" in data
    assert "llm" in data
    assert "ollama" in data
    assert "git" in data
    assert "disk" in data
    assert "mode" in data

    # LLM diagnostic fields
    llm = data["llm"]
    assert "provider" in llm
    assert "key_configured" in llm
    assert isinstance(llm["key_configured"], bool)
    # CRITICAL: API key must NEVER appear in response
    resp_text = resp.text
    if settings.llm_api_key:
        assert settings.llm_api_key not in resp_text

    # Ollama diagnostic fields
    ollama = data["ollama"]
    assert "reachable" in ollama
    assert "url" in ollama
    assert isinstance(ollama["reachable"], bool)

    # Git diagnostic fields
    git = data["git"]
    assert "available" in git
    assert isinstance(git["available"], bool)

    # Disk diagnostic fields
    disk = data["disk"]
    assert "workspace_root" in disk
    assert "free_bytes" in disk
    assert "free_gb" in disk
    assert isinstance(disk["free_bytes"], (int, float))

    # Mode diagnostic fields
    mode = data["mode"]
    assert mode["id"] in ("live", "live_local_ai", "live_offline_ai", "demo")
    assert "label" in mode
    assert "reason" in mode


def test_system_mode_endpoint(authed_client: TestClient):
    """Asserts GET /api/system/mode returns the active experience mode."""
    resp = authed_client.get("/api/system/mode")
    assert resp.status_code == 200
    mode = resp.json()
    assert mode["id"] in ("live", "live_local_ai", "live_offline_ai", "demo")
    assert mode["label"] in ("LIVE", "LIVE · LOCAL AI", "LIVE · OFFLINE AI", "DEMO APP")
    assert isinstance(mode["reason"], str)


def test_experience_mode_resolution_matrix():
    """Verify experience mode decision matrix across all dependency permutations (FEATURES.md F4)."""
    # 1. Docker + LLM key -> live
    m1 = _resolve_experience_mode(
        docker_ready=True,
        key_configured=True,
        ollama_reachable=False,
        provider="anthropic",
    )
    assert m1["id"] == "live"
    assert m1["label"] == "LIVE"

    # 2. Docker + Ollama -> live_local_ai
    m2 = _resolve_experience_mode(
        docker_ready=True,
        key_configured=False,
        ollama_reachable=True,
        provider="mock",
    )
    assert m2["id"] == "live_local_ai"
    assert m2["label"] == "LIVE · LOCAL AI"

    # 3. Docker only -> live_offline_ai
    m3 = _resolve_experience_mode(
        docker_ready=True,
        key_configured=False,
        ollama_reachable=False,
        provider="mock",
    )
    assert m3["id"] == "live_offline_ai"
    assert m3["label"] == "LIVE · OFFLINE AI"

    # 4. No Docker -> demo
    m4 = _resolve_experience_mode(
        docker_ready=False,
        key_configured=True,
        ollama_reachable=True,
        provider="anthropic",
    )
    assert m4["id"] == "demo"
    assert m4["label"] == "DEMO APP"
