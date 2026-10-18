"""
Tests for Verifier build arguments and SQLite environment passing (Audit defects A4, A5).

Exit gate:
- Pass project.dependency_file and project.entry_point (path format, e.g. main.py) to patched build.
- Run SQLite adaptation on modified_workspace and pass env_vars to start_patched_target.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
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
)
from app.agents.verifier.verifier import VerifierAgent
from app.database.models import ProjectRecord


@pytest.mark.asyncio
async def test_verifier_passes_dependency_file_entrypoint_and_sqlite_env(tmp_path: Path):
    """
    Audit A4/A5 test:
    Verifier must pass project.dependency_file, project.entry_point (path format),
    and SQLite adaptation env vars to docker manager.
    """
    project_id = "proj-test-123"
    patch_id = "patch-test-456"

    sample_project = ProjectRecord(
        id=project_id,
        name="test-project",
        source_path=str(tmp_path / "source"),
        validation_status="valid",
        entry_point="src/main.py",
        dependency_file="requirements.txt",
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
    sample_finding = EvaluatedFinding(
        id="finding-test-1",
        scan_id="scan-test-1",
        project_id=project_id,
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
    sample_patch = PatchRecord(
        id=patch_id,
        finding_id="finding-test-1",
        project_id=project_id,
        scan_id="scan-test-1",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-# fix",
        explanation="Sanitize inputs",
        target_file="src/main.py",
        applied=True,
    )

    mod_ws = tmp_path / "mod_ws"
    mod_ws.mkdir()
    # Create a dummy sqlite db file to trigger sqlite adaptation detection
    (mod_ws / "test.db").touch()

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
    verifier._functional_runner.run_functional_suite = AsyncMock(
        return_value=FunctionalSuiteResult(ran=True, total=2, passed=2, failed=0)
    )
    verifier._variant_runner.run_variant_attack = AsyncMock(
        return_value=VariantAttackResult(ran=True, exploited=False, variant_kind="header_bypass")
    )

    await verifier.verify_scan(
        findings=[sample_finding],
        patches=[sample_patch],
        scan_id="scan-test-1",
        modified_workspace=mod_ws,
        entry_point="src/main.py",
        project=sample_project,
    )

    # A4 assertion: build_image receives project.dependency_file ("requirements.txt")
    # and entry_point in path format ("src/main.py")
    mock_docker.build_image.assert_called_once()
    call_args = mock_docker.build_image.call_args[0]
    # args: (project_id, workspace_path, entry_point, dependency_file, tag)
    assert call_args[2] == "src/main.py"
    assert call_args[3] == "requirements.txt", f"Expected dependency_file 'requirements.txt', got {call_args[3]}"

    # A5 assertion: start_patched_target receives sqlite environment dict
    mock_docker.start_patched_target.assert_called_once()
    start_call_args = mock_docker.start_patched_target.call_args
    # Can be passed as 4th positional or keyword environment=
    env_passed = start_call_args.kwargs.get("environment") or (
        start_call_args.args[3] if len(start_call_args.args) > 3 else None
    )
    assert env_passed is not None, "SQLite environment variables were not passed to start_patched_target!"
    assert isinstance(env_passed, dict)
