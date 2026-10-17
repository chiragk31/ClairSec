"""
Regression and unit tests for Verifier entrypoint resolution and scan error handling.

Covers:
1. Entrypoint resolution for root main.py.
2. Entrypoint resolution for nested and differently named Python files (e.g., app/main.py, src/server.py).
3. Missing entrypoint diagnostic reporting (bounded file listing, workspace root, attempted path).
4. Modified workspace handling for stale, incomplete, or corrupted directories.
5. Zero patches proposed/applied workflow (cleanly skipped target startup, unresolved outcome).
6. Verifier startup exception without secondary AttributeError.
7. VerificationScanSummary model fields (fixed_count, unresolved_count, unfixed_count property) and terminal scan status.
"""
from __future__ import annotations

import logging
import uuid
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
    VerificationOutcome,
    VerificationScanSummary,
)
from app.agents.verifier.verifier import VerifierAgent
from app.database.models import ProjectRecord, ScanRecord, ValidationStatus
from app.isolation.errors import IsolationError
from app.isolation.workspace import WorkspaceManager
from app.services.scan_service import ScanService
from app.targets.handle import resolve_workspace_entrypoint


def _make_dummy_finding(scan_id: str, project_id: str, finding_id: str | None = None) -> EvaluatedFinding:
    f_id = finding_id or str(uuid.uuid4())
    return EvaluatedFinding(
        id=f_id,
        scan_id=scan_id,
        project_id=project_id,
        title="BOLA on /users/{user_id}",
        category="BOLA",
        cwe=["CWE-639"],
        route_template="/users/{user_id}",
        method="GET",
        description="Unauthorized profile access",
        impact="Information disclosure",
        runtime_confirmed=True,
        oracle_rule_id="ORACLE-001",
        status=EvaluationStatus.CONFIRMED,
        cvss=CvssResult(
            vector_string="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
            base_score=6.5,
            severity=SeverityBand.MEDIUM,
            inputs=CvssInputs(
                attack_vector="N",
                attack_complexity="L",
                privileges_required="L",
                user_interaction="N",
                scope="U",
                confidentiality="H",
                integrity="N",
                availability="N",
            ),
        ),
        confidence=ConfidenceResult(
            band=ConfidenceLevel.HIGH,
            score=0.95,
            inputs=ConfidenceInputs(
                runtime_confirmed=True,
                oracle_fired=True,
                reproduced_n_times=2,
                evidence_complete=True,
            ),
        ),
        evidence_ids=[],
        reproduction_summary="Reproduced twice against isolated target container",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Entrypoint Resolution: root main.py
# ─────────────────────────────────────────────────────────────────────────────

def test_entrypoint_resolution_main_py(tmp_path: Path):
    ws = tmp_path / "workspaces" / "proj1" / "modified_workspace"
    ws.mkdir(parents=True)
    (ws / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

    # When no explicit entrypoint is given, main.py is resolved
    entry_path, mod_name, app_attr = resolve_workspace_entrypoint(ws)
    assert entry_path == (ws / "main.py").resolve()
    assert mod_name == "main"
    assert app_attr == "app"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Entrypoint Resolution: nested or differently named Python files
# ─────────────────────────────────────────────────────────────────────────────

def test_entrypoint_resolution_nested_and_differently_named(tmp_path: Path):
    ws = tmp_path / "workspaces" / "proj2" / "modified_workspace"
    ws.mkdir(parents=True)
    app_dir = ws / "app"
    app_dir.mkdir()
    (app_dir / "server.py").write_text("from fastapi import FastAPI\napi = FastAPI()\n", encoding="utf-8")

    # 1. Explicit relative path "app/server.py"
    entry_path, mod_name, app_attr = resolve_workspace_entrypoint(
        ws, entry_point="app/server.py:api"
    )
    assert entry_path == (app_dir / "server.py").resolve()
    assert mod_name == "app.server"
    assert app_attr == "api"

    # 2. Windows style path "app\\server.py"
    entry_path2, mod_name2, app_attr2 = resolve_workspace_entrypoint(
        ws, entry_point=r"app\server.py"
    )
    assert entry_path2 == (app_dir / "server.py").resolve()
    assert mod_name2 == "app.server"
    assert app_attr2 == "app"

    # 3. Module dot-notation "app.server:api"
    entry_path3, mod_name3, app_attr3 = resolve_workspace_entrypoint(
        ws, app_module="app.server:api"
    )
    assert entry_path3 == (app_dir / "server.py").resolve()
    assert mod_name3 == "app.server"
    assert app_attr3 == "api"


def test_entrypoint_resolution_autodiscovery(tmp_path: Path):
    ws = tmp_path / "workspaces" / "proj_auto" / "modified_workspace"
    ws.mkdir(parents=True)
    src_dir = ws / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")

    # Neither main.py nor explicit entrypoint provided: auto-discovery detects src/app.py
    entry_path, mod_name, app_attr = resolve_workspace_entrypoint(ws)
    assert entry_path == (src_dir / "app.py").resolve()
    assert mod_name == "src.app"
    assert app_attr == "app"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Missing Entrypoint Diagnostic Error
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_entrypoint_raises_clear_diagnostic_error(tmp_path: Path, caplog):
    caplog.set_level(logging.DEBUG)
    ws = tmp_path / "workspaces" / "proj_missing" / "modified_workspace"
    ws.mkdir(parents=True)
    (ws / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")
    (ws / "models.py").write_text("class User: pass\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_workspace_entrypoint(ws, entry_point="nonexistent/main.py")

    err_msg = str(exc_info.value)
    assert "Workspace entrypoint not found" in err_msg
    assert "nonexistent/main.py" in err_msg
    assert "utils.py" in err_msg or "models.py" in err_msg

    # Verify diagnostic log record was emitted with structured metadata
    records = [r for r in caplog.records if getattr(r, "event", None) == "workspace.entrypoint.not_found"]
    assert len(records) >= 1
    assert records[0].files == ["models.py", "utils.py"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Modified Workspace: Stale or Incomplete Handling & Validation
# ─────────────────────────────────────────────────────────────────────────────

def test_modified_workspace_stale_or_incomplete_handling(tmp_path: Path):
    ws_mgr = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    project_id = str(uuid.uuid4())

    # Create dummy source project
    src = tmp_path / "source_app"
    src.mkdir()
    (src / "main.py").write_text("app = 1\n", encoding="utf-8")
    (src / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    # Create scan workspace
    scan_ws = ws_mgr.create_scan_workspace(project_id, str(src))
    assert (scan_ws / "main.py").exists()

    # Create an initial modified workspace
    mod_ws = ws_mgr.create_modified_workspace(project_id)
    assert (mod_ws / "main.py").exists()

    # Simulate stale state: corrupt/delete main.py in modified workspace
    (mod_ws / "main.py").unlink()
    assert not (mod_ws / "main.py").exists()

    # Calling create_modified_workspace with reset=True refreshes from pristine scan_workspace
    refreshed_ws = ws_mgr.create_modified_workspace(project_id, reset=True)
    assert (refreshed_ws / "main.py").exists()
    assert (refreshed_ws / "requirements.txt").exists()


def test_modified_workspace_copy_validation_failure(tmp_path: Path, monkeypatch):
    ws_mgr = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    project_id = str(uuid.uuid4())

    src = tmp_path / "source_app2"
    src.mkdir()
    (src / "main.py").write_text("app = 1\n", encoding="utf-8")
    ws_mgr.create_scan_workspace(project_id, str(src))

    # Mock copytree to simulate an incomplete copy that drops files
    with (
        patch("shutil.copytree", side_effect=lambda src, dst, **kwargs: dst.mkdir(parents=True, exist_ok=True)),
        pytest.raises(IsolationError, match="incomplete"),
    ):
        ws_mgr.create_modified_workspace(project_id)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Zero Patches: Cleanly Skipped Startup & Unresolved Outcomes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zero_patches_verification_skips_startup(tmp_path: Path):
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    ws_mgr = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    src = tmp_path / "src3"
    src.mkdir()
    (src / "app.py").write_text("app = 1\n", encoding="utf-8")
    ws_mgr.create_scan_workspace(project_id, str(src))
    mod_ws = ws_mgr.create_modified_workspace(project_id)

    finding = _make_dummy_finding(scan_id, project_id)

    # Empty patches list (zero patches proposed/applied)
    verifier = VerifierAgent(workspace_manager=ws_mgr)
    summary = await verifier.verify_scan(
        findings=[finding],
        patches=[],
        scan_id=scan_id,
        modified_workspace=mod_ws,
        entry_point="nonexistent_main.py",  # Should NOT be touched or raise
    )

    assert summary.fixed_count == 0
    assert summary.unresolved_count == 1
    assert summary.unverified_count == 0
    assert summary.unfixed_count == 1
    assert len(summary.records) == 1
    assert summary.records[0].outcome == VerificationOutcome.UNRESOLVED
    assert summary.records[0].outcome_reason == "no_applied_patch"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Verifier Startup Exception without Secondary AttributeError
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verifier_startup_exception_without_secondary_attribute_error(tmp_path: Path):
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    ws_mgr = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    src = tmp_path / "src4"
    src.mkdir()
    (src / "server.py").write_text("app = 1\n", encoding="utf-8")
    ws_mgr.create_scan_workspace(project_id, str(src))
    mod_ws = ws_mgr.create_modified_workspace(project_id)

    finding = _make_dummy_finding(scan_id, project_id)
    patch = PatchRecord(
        id=str(uuid.uuid4()),
        finding_id=finding.id,
        scan_id=scan_id,
        project_id=project_id,
        applied=True,
    )

    verifier = VerifierAgent(workspace_manager=ws_mgr)

    # Missing entrypoint should raise FileNotFoundError cleanly out of verify_scan
    with pytest.raises(FileNotFoundError, match="Workspace entrypoint not found"):
        await verifier.verify_scan(
            findings=[finding],
            patches=[patch],
            scan_id=scan_id,
            modified_workspace=mod_ws,
            entry_point="missing_entrypoint.py",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. VerificationScanSummary Model Fields & Accurate Scan Terminal Status
# ─────────────────────────────────────────────────────────────────────────────

def test_verification_scan_summary_fields():
    summary = VerificationScanSummary(
        scan_id="test-scan",
        fixed_count=2,
        regressed_count=1,
        unresolved_count=3,
        unverified_count=1,
    )
    assert summary.fixed_count == 2
    assert summary.regressed_count == 1
    assert summary.unresolved_count == 3
    assert summary.unverified_count == 1
    # unfixed_count derived correctly
    assert summary.unfixed_count == 5


@pytest.mark.asyncio
async def test_scan_service_terminal_failure_on_verifier_error():
    """Verify that if Verifier fails, the scan pipeline transitions to failed without AttributeError."""
    project_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())

    mock_db = MagicMock()
    scan_service = ScanService(db=mock_db)

    # Mock get_project and get_scan
    project = ProjectRecord(
        id=project_id,
        name="test-project",
        source_path="/dummy",
        entry_point="missing_app.py",
        validation_status=ValidationStatus.VALID,
    )
    scan = ScanRecord(
        id=scan_id,
        project_id=project_id,
        state="running",
        stage="builder",
    )

    scan_service.get_project = AsyncMock(return_value=project)
    scan_service._scan_repo.get_by_id = AsyncMock(return_value=scan)
    scan_service._scan_repo.update = AsyncMock(return_value=scan)

    # Run pipeline with Verifier raising FileNotFoundError
    with (
        patch("app.services.scan_service.LocalWorkspaceTargetHandle") as mock_handle_cls,
        patch("app.agents.builder.builder.BuilderAgent.build_context", new_callable=AsyncMock) as mock_builder,
        patch("app.agents.attacker.attacker.AttackerAgent.run_scan", new_callable=AsyncMock) as mock_attacker,
        patch("app.agents.evaluator.evaluator.EvaluatorAgent.evaluate_scan", new_callable=AsyncMock) as mock_evaluator,
        patch("app.agents.fixer.fixer.FixerAgent.fix_scan", new_callable=AsyncMock) as mock_fixer,
        patch("app.agents.verifier.verifier.VerifierAgent.verify_scan", side_effect=FileNotFoundError("Workspace entrypoint not found")),
        patch.object(scan_service._workspace, "get_scan_workspace_path", return_value=Path("/dummy/scan_ws")),
        patch.object(scan_service._workspace, "create_modified_workspace", return_value=Path("/dummy/mod_ws")),
    ):
        mock_handle = MagicMock()
        mock_handle.start = AsyncMock()
        mock_handle.stop = AsyncMock()
        mock_handle_cls.return_value = mock_handle
        mock_builder.return_value = MagicMock(routes=[], auth_scheme="none")
        mock_attacker.return_value = MagicMock(findings=[])
        mock_evaluator.return_value = MagicMock(findings=[], confirmed_count=1, rejected_count=0, inconclusive_count=0)
        mock_fixer.return_value = MagicMock(patches=[MagicMock(applied=True)], applied_count=1)

        # Run pipeline
        await scan_service._run_scan_pipeline(scan_id, project_id)

    # Verify terminal status is failed and error message reflects the verifier failure
    assert scan.state == "failed"
    assert scan.stage == "failed"
    assert "Workspace entrypoint not found" in scan.error
    assert scan.terminal_reason == "pipeline_failed_verifier"
