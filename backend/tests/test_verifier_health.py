"""
Tests for Verifier patched container health check (Audit defect A3).

Exit gate:
- After start_patched_target, wait for health through the proxy (DockerManager.wait_for_healthy).
- On timeout: outcome "unverified", rebuild_ok=False, reason includes health diagnostics, and teardown still runs.
- On success: proceeds with retest.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agents.evaluator.schemas import (
    ConfidenceInputs,
    ConfidenceLevel,
    ConfidenceResult,
    CvssInputs,
    CvssResult,
    EvaluatedFinding,
    EvaluationStatus,
    SeverityBand,
)
from app.agents.fixer.schemas import PatchRecord
from app.agents.verifier.schemas import (
    FunctionalSuiteResult,
    OriginalExploitResult,
    VariantAttackResult,
    VerificationOutcome,
)
from app.agents.verifier.verifier import VerifierAgent
from app.database.models import ProjectRecord


@pytest.fixture
def sample_finding():
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
    return EvaluatedFinding(
        id="finding-test-1",
        scan_id="scan-test-1",
        project_id="project-test-1",
        title="SQLi Finding",
        category="SQLI",
        cwe=["CWE-89"],
        route_template="/items",
        method="GET",
        description="SQL injection vulnerability",
        impact="Data leakage",
        status=EvaluationStatus.CONFIRMED,
        runtime_confirmed=True,
        oracle_rule_id="ORACLE-SQLI-01",
        cvss=cvss,
        confidence=confidence,
    )


@pytest.fixture
def sample_patch():
    return PatchRecord(
        id="patch-test-1",
        finding_id="finding-test-1",
        project_id="project-test-1",
        scan_id="scan-test-1",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-# fix",
        explanation="Sanitize inputs",
        target_file="main.py",
        applied=True,
    )


@pytest.fixture
def sample_project():
    return ProjectRecord(
        id="project-test-1",
        name="test-project",
        source_path="/tmp/untrusted/project",
        validation_status="valid",
        entry_point="main.py",
        dependency_file="requirements.txt",
    )


@pytest.mark.asyncio
async def test_verifier_health_timeout_marks_unverified_and_tears_down(
    sample_finding, sample_patch, sample_project, tmp_path: Path
):
    """
    Audit A3 test: If patched container fails health check through proxy,
    verification outcome must be UNVERIFIED, rebuild_ok=False, reason must
    include health diagnostics, and cleanup_patched_target must still run.
    """
    mock_docker = MagicMock()
    mock_docker.patched_image_tag.return_value = "patched:tag"
    mock_docker.start_patched_target.return_value = ("target_cid", "proxy_cid", 9999)
    # Simulate health check failure / timeout
    mock_docker.wait_for_healthy.return_value = False
    mock_docker.get_last_health_diagnostics.return_value = {
        "probed_paths": ["/health"],
        "last_status_code": 502,
        "last_error": "Connection refused",
    }

    mock_ver_repo = MagicMock()
    mock_ver_repo.create = AsyncMock(side_effect=lambda r: r)
    verifier = VerifierAgent(verification_repo=mock_ver_repo, docker_manager=mock_docker)

    mod_ws = tmp_path / "mod_ws"
    mod_ws.mkdir()

    summary = await verifier.verify_scan(
        findings=[sample_finding],
        patches=[sample_patch],
        scan_id="scan-test-1",
        modified_workspace=mod_ws,
        entry_point="main.py",
        project=sample_project,
    )

    # 1. Must call wait_for_healthy through the proxy port
    mock_docker.wait_for_healthy.assert_called_once()

    # 2. Must produce UNVERIFIED outcome with rebuild_ok=False
    assert len(summary.records) == 1
    rec = summary.records[0]
    assert rec.rebuild_ok is False
    assert rec.outcome == VerificationOutcome.UNVERIFIED
    assert "Diagnostics:" in rec.outcome_reason or "502" in rec.outcome_reason

    # 3. Teardown must still run
    mock_docker.cleanup_patched_target.assert_called()


@pytest.mark.asyncio
async def test_verifier_health_success_proceeds(
    sample_finding, sample_patch, sample_project, tmp_path: Path
):
    """
    Audit A3 test: When wait_for_healthy succeeds, verification proceeds to retest.
    """
    mock_docker = MagicMock()
    mock_docker.patched_image_tag.return_value = "patched:tag"
    mock_docker.start_patched_target.return_value = ("target_cid", "proxy_cid", 9999)
    mock_docker.wait_for_healthy.return_value = True

    mock_ver_repo = MagicMock()
    mock_ver_repo.create = AsyncMock(side_effect=lambda r: r)
    verifier = VerifierAgent(verification_repo=mock_ver_repo, docker_manager=mock_docker)

    verifier._retester.retest = AsyncMock(
        return_value=OriginalExploitResult(ran=True, exploited=False, rationale="Blocked")
    )
    # User project: "App still works" comes from the auto-generated smoke suite against a
    # pre-fix baseline (F9). The baseline itself is out of scope for this container test.
    verifier._run_functional_check = AsyncMock(
        return_value=FunctionalSuiteResult(ran=True, total=2, passed=2, failed=0, source="auto_smoke")
    )
    verifier._variant_runner.run_variant_attack = AsyncMock(
        return_value=VariantAttackResult(ran=True, exploited=False, variant_kind="header_bypass")
    )

    mod_ws = tmp_path / "mod_ws"
    mod_ws.mkdir()

    summary = await verifier.verify_scan(
        findings=[sample_finding],
        patches=[sample_patch],
        scan_id="scan-test-1",
        modified_workspace=mod_ws,
        entry_point="main.py",
        project=sample_project,
    )

    mock_docker.wait_for_healthy.assert_called_once()
    assert len(summary.records) == 1
    assert summary.records[0].rebuild_ok is True
    assert summary.records[0].outcome == VerificationOutcome.FIXED
