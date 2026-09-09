"""
Integration and exit gate tests for Phase 8 Re-test and Verification Agent.
(PHASES.md Phase 8, METHODOLOGY.md §5, DATA_MODEL.md §3 verification_results, RESEARCH.md §5).

EXIT GATE CRITERIA:
1. All 3 confirmed findings in vulnerable_fastapi_app go through re-test and land on
   one of the four states (fixed, regressed, unresolved, unverified) with recorded reasons.
2. DUAL CRITERION ENFORCEMENT: A fix counts as `fixed` only if original exploit is blocked
   AND project functional test suite passes.
3. ADVERSARIAL REGRESSION TEST: Hand-craft a patch that blocks the exploit by disabling/deleting
   the vulnerable endpoint, and confirm it lands on `regressed`, NOT `fixed`.
4. UNRESOLVED TEST: An ineffective patch where the exploit still fires lands on `unresolved`.
5. UNVERIFIED TEST: A target whose rebuild/startup fails lands on `unverified`.
6. VARIANT ATTACK: After original exploit is blocked, an adapted attack variant executes
   and is recorded as a distinct field on the verification record.
7. Verification records match DATA_MODEL.md §3 verification_results schema.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import uuid
import pytest

from app.agents.attacker.attacker import AttackerAgent
from app.agents.attacker.repository import TestCaseRepository
from app.agents.builder.builder import BuilderAgent
from app.agents.evaluator.evaluator import EvaluatorAgent
from app.agents.evaluator.repository import FindingRepository
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
from app.agents.fixer.fixer import FixerAgent
from app.agents.fixer.repository import PatchRepository
from app.agents.fixer.schemas import FileDiff, PatchRecord, PatchValidation
from app.agents.verifier.repository import VerificationRepository
from app.agents.verifier.schemas import (
    FunctionalSuiteResult,
    OriginalExploitResult,
    VariantAttackResult,
    VerificationOutcome,
    VerificationRecord,
)
from app.agents.verifier.verifier import VerifierAgent
from app.isolation.workspace import WorkspaceManager
from app.targets.handle import LocalFixtureTargetHandle, LocalWorkspaceTargetHandle

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VULN_FIXTURE = FIXTURES_DIR / "vulnerable_fastapi_app"


def _make_dummy_finding(
    scan_id: str,
    project_id: str,
    category: str,
    route_template: str,
    method: str,
    oracle_rule_id: str,
) -> EvaluatedFinding:
    return EvaluatedFinding(
        scan_id=scan_id,
        project_id=project_id,
        title=f"{category} finding",
        category=category,
        cwe=["CWE-639"] if category == "BOLA" else ["CWE-16"],
        route_template=route_template,
        method=method,
        description="Test finding",
        impact="High",
        runtime_confirmed=True,
        oracle_rule_id=oracle_rule_id,
        cvss=CvssResult(
            inputs=CvssInputs(),
            vector_string="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
            base_score=7.5,
            severity=SeverityBand.HIGH,
        ),
        confidence=ConfidenceResult(
            inputs=ConfidenceInputs(
                runtime_confirmed=True,
                oracle_fired=True,
                reproduced_n_times=1,
                evidence_complete=True,
            ),
            band=ConfidenceLevel.HIGH,
            score=1.0,
        ),
        status=EvaluationStatus.CONFIRMED,
    )


@pytest.mark.asyncio
async def test_verifier_confirms_dual_criterion_fixed_on_all_three_seeded_vulns(tmp_path: Path):
    """
    Phase 8 Exit Gate 1: Full pipeline Builder -> Attacker -> Evaluator -> Fixer -> Verifier.
    All 3 confirmed findings reach `fixed` status via the Dual Criterion:
    1. pov / original exploit re-run returns exploited=False.
    2. All 6 functional tests in vulnerable_fastapi_app still pass.
    3. Adapted variant attacks execute and are recorded distinctly.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fixture_handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await fixture_handle.start()

    try:
        # Step 1: Builder
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id=project_id,
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=fixture_handle,
        )

        # Step 2: Attacker
        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_res = await attacker.run_scan(context=context, target_handle=fixture_handle)
        assert len(attacker_res.findings) == 3

        # Step 3: Evaluator
        finding_repo = FindingRepository()
        evaluator = EvaluatorAgent(test_case_repo=test_case_repo, finding_repo=finding_repo)
        eval_res = await evaluator.evaluate_scan(
            candidates=attacker_res.findings,
            target_handle=fixture_handle,
            scan_id=scan_id,
        )
        assert eval_res.confirmed_count == 3

        # Step 4: Workspace setup
        ws_manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        scan_ws = ws_manager.create_scan_workspace(project_id, str(VULN_FIXTURE))
        mod_ws = ws_manager.create_modified_workspace(project_id)

        # Step 5: Fixer
        patch_repo = PatchRepository()
        fixer = FixerAgent(patch_repo=patch_repo, workspace_manager=ws_manager)
        fix_res = await fixer.fix_scan(
            findings=eval_res.findings,
            context=context,
            project_id=project_id,
            scan_id=scan_id,
            modified_workspace_root=mod_ws,
        )
        assert fix_res.applied_count == 3

        # Step 6: Verifier
        ver_repo = VerificationRepository()
        verifier = VerifierAgent(
            verification_repo=ver_repo,
            test_case_repo=test_case_repo,
            workspace_manager=ws_manager,
        )
        ver_summary = await verifier.verify_scan(
            findings=eval_res.findings,
            patches=fix_res.patches,
            scan_id=scan_id,
            modified_workspace=mod_ws,
        )

        # Four-way outcome assertions
        assert ver_summary.fixed_count == 3, f"Expected 3 fixed findings, got {ver_summary.fixed_count}"
        assert ver_summary.regressed_count == 0, f"Expected 0 regressions, got {ver_summary.regressed_count}"
        assert ver_summary.unresolved_count == 0, f"Expected 0 unresolved, got {ver_summary.unresolved_count}"
        assert ver_summary.unverified_count == 0, f"Expected 0 unverified, got {ver_summary.unverified_count}"
        assert len(ver_summary.records) == 3

        # Verify each record adheres to DATA_MODEL.md §3 verification_results schema
        for r in ver_summary.records:
            assert r.scan_id == scan_id
            assert r.rebuild_ok is True
            assert r.outcome == VerificationOutcome.FIXED
            assert "dual_criterion_satisfied" in r.outcome_reason

            # 1. Original exploit must be blocked
            assert r.original_exploit.ran is True
            assert r.original_exploit.exploited is False, f"Original exploit should be blocked: {r.original_exploit.rationale}"

            # 2. Functional test suite must have 100% pass rate
            assert r.functional_suite.ran is True
            assert r.functional_suite.failed == 0, f"Functional tests failed: {r.functional_suite.newly_failing}"
            assert r.functional_suite.passed == 6, f"Expected 6 passed tests, got {r.functional_suite.passed}"

            # 3. Variant attack executed and recorded separately
            assert r.variant_attack.ran is True
            assert r.variant_attack.variant_kind != ""
            assert isinstance(r.variant_attack.exploited, bool)

            # 4. Performance timing recorded
            assert r.duration_s > 0.0

    finally:
        await fixture_handle.stop()


@pytest.mark.asyncio
async def test_adversarial_regression_delete_endpoint_patch_lands_on_regressed(tmp_path: Path):
    """
    Phase 8 Adversarial Test: A patch that blocks the exploit by breaking/disabling the endpoint
    MUST land on `regressed`, NOT `fixed`, because the functional suite catches the broken endpoint.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    ws_manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    scan_ws = ws_manager.create_scan_workspace(project_id, str(VULN_FIXTURE))
    mod_ws = ws_manager.create_modified_workspace(project_id)

    # Malicious/destructive patch: disable /documents/{doc_id} by making it always return 404
    mod_main = mod_ws / "main.py"
    original_code = mod_main.read_text(encoding="utf-8")
    broken_code = original_code.replace(
        "return doc",
        "raise HTTPException(status_code=404, detail='Endpoint deleted')",
    )
    mod_main.write_text(broken_code, encoding="utf-8")

    # Synthetic BOLA finding and patch record
    finding_repo = FindingRepository()
    bola_finding = await finding_repo.create(
        _make_dummy_finding(
            scan_id=scan_id,
            project_id=project_id,
            category="BOLA",
            route_template="/documents/{doc_id}",
            method="GET",
            oracle_rule_id="ORACLE_BOLA_001",
        )
    )

    patch_record = PatchRecord(
        id=str(uuid.uuid4()),
        finding_id=bola_finding.id,
        scan_id=scan_id,
        project_id=project_id,
        files=[FileDiff(path="main.py", diff="--- broken diff")],
        applied=True,
        applied_at="2026-09-10T00:00:00Z",
        workspace="modified",
        validation=PatchValidation(ast_parsed=True, path_check_passed=True, size_ok=True),
    )

    verifier = VerifierAgent(workspace_manager=ws_manager)
    ver_record = await verifier.verify_finding(
        finding=bola_finding,
        patch=patch_record,
        scan_id=scan_id,
        modified_workspace=mod_ws,
    )

    # CRITICAL DUAL CRITERION ASSERTION:
    # 1. Exploit was technically blocked (it got 404, so Bob's data was not leaked)
    assert ver_record.original_exploit.exploited is False
    # 2. BUT legitimate functional test failed (Alice can't read her own document)
    assert ver_record.functional_suite.failed > 0
    assert "test_user_can_read_own_document" in ver_record.functional_suite.newly_failing
    # 3. MUST land on REGRESSED, never FIXED
    assert ver_record.outcome == VerificationOutcome.REGRESSED
    assert "functional_regression" in ver_record.outcome_reason


@pytest.mark.asyncio
async def test_verifier_ineffective_patch_lands_on_unresolved(tmp_path: Path):
    """
    Phase 8 Test: If the patch fails to remediate the vulnerability (exploit still fires),
    the outcome is UNRESOLVED.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    ws_manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    scan_ws = ws_manager.create_scan_workspace(project_id, str(VULN_FIXTURE))
    mod_ws = ws_manager.create_modified_workspace(project_id)
    # Leave mod_ws unmodified (vulnerable code remains active)

    finding_repo = FindingRepository()
    misconfig_finding = await finding_repo.create(
        _make_dummy_finding(
            scan_id=scan_id,
            project_id=project_id,
            category="SECURITY_MISCONFIG",
            route_template="/debug/config",
            method="GET",
            oracle_rule_id="ORACLE_MISCONFIG_001",
        )
    )

    patch_record = PatchRecord(
        id=str(uuid.uuid4()),
        finding_id=misconfig_finding.id,
        scan_id=scan_id,
        project_id=project_id,
        applied=True,
        applied_at="2026-09-10T00:00:00Z",
    )

    verifier = VerifierAgent(workspace_manager=ws_manager)
    ver_record = await verifier.verify_finding(
        finding=misconfig_finding,
        patch=patch_record,
        scan_id=scan_id,
        modified_workspace=mod_ws,
    )

    # Exploit still fires -> UNRESOLVED
    assert ver_record.original_exploit.exploited is True
    assert ver_record.outcome == VerificationOutcome.UNRESOLVED
    assert "exploit_still_succeeded" in ver_record.outcome_reason


@pytest.mark.asyncio
async def test_verifier_broken_rebuild_lands_on_unverified(tmp_path: Path):
    """
    Phase 8 Test: If target rebuild/restart fails to boot or become healthy,
    outcome is UNVERIFIED.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    ws_manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    scan_ws = ws_manager.create_scan_workspace(project_id, str(VULN_FIXTURE))
    mod_ws = ws_manager.create_modified_workspace(project_id)

    # Corrupt main.py so it cannot start
    (mod_ws / "main.py").write_text("raise SystemExit('Fatal boot failure')", encoding="utf-8")

    finding_repo = FindingRepository()
    finding = await finding_repo.create(
        _make_dummy_finding(
            scan_id=scan_id,
            project_id=project_id,
            category="BOLA",
            route_template="/documents/{doc_id}",
            method="GET",
            oracle_rule_id="ORACLE_BOLA_001",
        )
    )

    patch_record = PatchRecord(
        id=str(uuid.uuid4()),
        finding_id=finding.id,
        scan_id=scan_id,
        project_id=project_id,
        applied=True,
    )

    verifier = VerifierAgent(workspace_manager=ws_manager)
    ver_record = await verifier.verify_finding(
        finding=finding,
        patch=patch_record,
        scan_id=scan_id,
        modified_workspace=mod_ws,
    )

    # Rebuild failed -> UNVERIFIED
    assert ver_record.rebuild_ok is False
    assert ver_record.outcome == VerificationOutcome.UNVERIFIED
    assert "rebuild_restart_failed" in ver_record.outcome_reason
