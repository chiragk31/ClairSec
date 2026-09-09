"""
Integration and exit gate tests for Phase 7 Fixer Agent.
(PHASES.md Phase 7, THREAT_MODEL.md C2.1, C2.2, C2.4, T8, DATA_MODEL.md §2 & §3).

EXIT GATE CRITERIA:
1. Each of the 3 confirmed findings in vulnerable_fastapi_app produces a reviewable
   unified diff written to modified_workspace/.
2. A patch that targets a path outside modified_workspace/ is refused and recorded
   (explicit test pointing mock patch at ../../../etc/passwd-style path asserts rejection).
3. The ORIGINAL imported project (scan_workspace/ and upstream fixture source) is
   BYTE-IDENTICAL after the full run (SHA-256 directory tree checksum equality test).
4. Pre-apply validation persisted as DATA on the patch record: ast_parsed, path_check_passed, size_ok.
5. Oversized patch exceeding 256 KB is rejected and recorded as patch_too_large, never truncated silently.
6. Patched file must parse as valid Python AST; unparseable patch is rejected and recorded.
7. Hallucinated path not in workspace inventory is recorded as unattempted hallucination.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import uuid
import pytest

from app.agents.attacker.attacker import AttackerAgent
from app.agents.attacker.repository import TestCaseRepository
from app.agents.builder.builder import BuilderAgent
from app.agents.evaluator.evaluator import EvaluatorAgent
from app.agents.evaluator.repository import FindingRepository
from app.agents.fixer.fixer import FixerAgent
from app.agents.fixer.patch_engine import (
    DIFF_SIZE_CAP_BYTES,
    PatchEngine,
    apply_hunks_to_content,
    validate_path_containment,
)
from app.agents.fixer.repository import PatchRepository
from app.agents.fixer.schemas import PatchRecord
from app.isolation.workspace import WorkspaceManager
from app.targets.handle import LocalFixtureTargetHandle

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VULN_FIXTURE = FIXTURES_DIR / "vulnerable_fastapi_app"


def calculate_tree_sha256(directory: Path) -> str:
    """Compute a deterministic recursive SHA-256 digest of a directory tree."""
    hasher = hashlib.sha256()
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file():
            # Include relative path and file contents
            rel_path = file_path.relative_to(directory).as_posix()
            hasher.update(rel_path.encode("utf-8"))
            hasher.update(file_path.read_bytes())
    return hasher.hexdigest()


@pytest.mark.asyncio
async def test_fixer_produces_and_applies_unified_diffs_for_seeded_vulns(tmp_path: Path):
    """
    Phase 7 Exit Gate 1: Fixer produces and applies reviewable unified diffs
    for all 3 confirmed findings in vulnerable_fastapi_app inside modified_workspace/.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        # Step 1: Builder extracts context
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id=project_id,
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        # Step 2: Attacker generates candidates
        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_result = await attacker.run_scan(context=context, target_handle=handle)
        assert len(attacker_result.findings) == 3

        # Step 3: Evaluator confirms findings
        finding_repo = FindingRepository()
        evaluator = EvaluatorAgent(test_case_repo=test_case_repo, finding_repo=finding_repo)
        eval_result = await evaluator.evaluate_scan(
            candidates=attacker_result.findings,
            target_handle=handle,
            scan_id=scan_id,
        )
        assert eval_result.confirmed_count == 3

        # Step 4: Workspace Manager creates scan_workspace and modified_workspace
        ws_manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        scan_ws = ws_manager.create_scan_workspace(project_id, str(VULN_FIXTURE))
        mod_ws = ws_manager.create_modified_workspace(project_id)

        # Step 5: Fixer Agent generates and applies patches to modified_workspace
        patch_repo = PatchRepository()
        fixer = FixerAgent(
            patch_repo=patch_repo,
            workspace_manager=ws_manager,
        )
        fix_result = await fixer.fix_scan(
            findings=eval_result.findings,
            context=context,
            project_id=project_id,
            scan_id=scan_id,
            modified_workspace_root=mod_ws,
        )

        # Assertions
        assert fix_result.applied_count == 3, f"Expected 3 applied patches, got {fix_result.applied_count}"
        assert fix_result.rejected_count == 0, f"Expected 0 rejected patches, got {fix_result.rejected_count}"
        assert len(fix_result.patches) == 3

        # Verify each patch record data model and validation
        for p in fix_result.patches:
            assert p.applied is True
            assert p.applied_at is not None
            assert p.apply_error is None
            assert p.workspace == "modified"
            assert p.validation.ast_parsed is True
            assert p.validation.path_check_passed is True
            assert p.validation.size_ok is True
            assert p.diff_stats.files == 1
            assert p.diff_stats.added > 0
            assert len(p.files) == 1
            assert "--- " in p.files[0].diff and "+++ " in p.files[0].diff
            assert "@@ " in p.files[0].diff

        # Check that modified_workspace/main.py actually changed and is valid Python
        mod_main = mod_ws / "main.py"
        scan_main = scan_ws / "main.py"
        assert mod_main.read_text(encoding="utf-8") != scan_main.read_text(encoding="utf-8")

        # Verify modified file parses cleanly as Python AST
        import ast
        ast.parse(mod_main.read_text(encoding="utf-8"), filename="main.py")

    finally:
        await handle.stop()


def test_path_containment_refuses_traversal_paths_c2_1(tmp_path: Path):
    """
    Phase 7 Exit Gate 2: Path containment (THREAT_MODEL C2.1, C2.2, C2.4).
    A patch targeting a path outside modified_workspace/ (e.g. ../../../etc/passwd)
    is strictly refused and recorded with path_check_passed=False.
    """
    mod_root = tmp_path / "workspaces" / "proj_123" / "modified_workspace"
    mod_root.mkdir(parents=True, exist_ok=True)
    (mod_root / "main.py").write_text("print('hello')", encoding="utf-8")

    engine = PatchEngine(modified_root=mod_root, inventory_files={"main.py"})

    traversal_patch = """--- a/../../../etc/passwd
+++ b/../../../etc/passwd
@@ -1,1 +1,1 @@
-root:x:0:0:root:/root:/bin/bash
+root:x:0:0:root:/root:/bin/sh
"""

    applied, validation, stats, _, apply_error = engine.evaluate_and_apply(
        rel_path="../../../etc/passwd",
        diff_text=traversal_patch,
    )

    assert applied is False
    assert validation.path_check_passed is False
    assert "path_outside_workspace" in (apply_error or "")


def test_path_containment_refuses_symlinks_c2_2(tmp_path: Path):
    """
    Phase 7 Control C2.2: Symlinks inside workspace are not followed during patch application.
    """
    mod_root = tmp_path / "workspaces" / "proj_123" / "modified_workspace"
    mod_root.mkdir(parents=True, exist_ok=True)

    secret_target = tmp_path / "host_secret.txt"
    secret_target.write_text("SUPER_SECRET", encoding="utf-8")

    symlink_file = mod_root / "symlink_file.py"
    try:
        symlink_file.symlink_to(secret_target)
    except OSError:
        pytest.skip("Symlink creation requires elevated privileges on this Windows environment")

    engine = PatchEngine(modified_root=mod_root, inventory_files={"symlink_file.py"})
    applied, validation, _, _, apply_error = engine.evaluate_and_apply(
        rel_path="symlink_file.py",
        diff_text="--- a/symlink_file.py\n+++ b/symlink_file.py\n@@ -1 +1 @@\n-SUPER_SECRET\n+OVERWRITTEN\n",
    )

    assert applied is False
    assert validation.path_check_passed is False
    assert "symlink_detected" in (apply_error or "")


def test_patch_engine_rejects_oversized_diff_t8(tmp_path: Path):
    """
    Phase 7 Exit Gate 4 (T8 / DATA_MODEL.md §2):
    Patch diff exceeding 256 KB is rejected and recorded as patch_too_large.
    Must NOT be truncated silently.
    """
    mod_root = tmp_path / "workspaces" / "proj_123" / "modified_workspace"
    mod_root.mkdir(parents=True, exist_ok=True)
    (mod_root / "main.py").write_text("x = 1\n", encoding="utf-8")

    engine = PatchEngine(modified_root=mod_root, inventory_files={"main.py"})

    # Generate oversized diff (> 256 KB)
    huge_comment = "# " + ("A" * 100) + "\n"
    huge_lines = huge_comment * 3000  # ~300 KB
    oversized_diff = f"""--- a/main.py
+++ b/main.py
@@ -1,1 +1,3001 @@
-x = 1
+x = 1
{huge_lines}"""

    assert len(oversized_diff.encode("utf-8")) > DIFF_SIZE_CAP_BYTES

    applied, validation, stats, _, apply_error = engine.evaluate_and_apply(
        rel_path="main.py",
        diff_text=oversized_diff,
    )

    assert applied is False
    assert validation.size_ok is False
    assert "patch_too_large" in (apply_error or "")
    assert "256 KB" in (apply_error or "")


def test_patch_engine_rejects_unparseable_python_syntax_t8(tmp_path: Path):
    """
    Phase 7 Exit Gate 5 (T8):
    Patched file must parse as Python (ast.parse).
    Malformed syntax introduced by diff must be rejected and recorded as data.
    """
    mod_root = tmp_path / "workspaces" / "proj_123" / "modified_workspace"
    mod_root.mkdir(parents=True, exist_ok=True)
    (mod_root / "main.py").write_text("def valid():\n    return 42\n", encoding="utf-8")

    engine = PatchEngine(modified_root=mod_root, inventory_files={"main.py"})

    # Diff that introduces blatant syntax error
    syntax_error_diff = """--- a/main.py
+++ b/main.py
@@ -1,2 +1,2 @@
 def valid():
-    return 42
+    return def invalid syntax syntax !!!
"""

    applied, validation, stats, _, apply_error = engine.evaluate_and_apply(
        rel_path="main.py",
        diff_text=syntax_error_diff,
    )

    assert applied is False
    assert validation.ast_parsed is False
    assert "syntax_error" in (apply_error or "")
    # Verify disk was untouched due to validation failure
    assert (mod_root / "main.py").read_text(encoding="utf-8") == "def valid():\n    return 42\n"


@pytest.mark.asyncio
async def test_fixer_records_hallucinated_path_without_crashing(tmp_path: Path):
    """
    Phase 7 Requirement: The Fixer must not invent files. Every target path must exist
    in the workspace inventory. A hallucinated path is a recorded outcome, never attempted.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    mod_root = tmp_path / "workspaces" / project_id / "modified_workspace"
    mod_root.mkdir(parents=True, exist_ok=True)
    (mod_root / "main.py").write_text("print('hello')", encoding="utf-8")

    # Create dummy AgentContext with only main.py
    from app.agents.builder.schemas import AgentContext, RouteItem
    from app.agents.evaluator.schemas import EvaluatedFinding

    context = AgentContext(
        project_id=project_id,
        scan_id=scan_id,
        routes=[],
    )

    # Finding referencing non-existent file
    hallucinated_finding = EvaluatedFinding(
        scan_id=scan_id,
        project_id=project_id,
        title="Hallucinated Finding",
        category="BOLA",
        cwe=["CWE-639"],
        route_template="/ghost/endpoint",
        method="GET",
        description="Ghost endpoint",
        impact="None",
        runtime_confirmed=True,
        oracle_rule_id="RULE_001",
        cvss={
            "inputs": {},
            "vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N",
            "base_score": 0.0,
            "severity": "NONE",
        },
        confidence={"inputs": {"runtime_confirmed": True, "oracle_fired": True, "reproduced_n_times": 1, "evidence_complete": True}, "band": "HIGH", "score": 1.0},
        source_locations=[{"file": "non_existent_auth_module.py", "line_start": 1, "line_end": 10}],
        status="confirmed",
    )

    patch_repo = PatchRepository()
    fixer = FixerAgent(patch_repo=patch_repo)
    patch_record = await fixer.fix_finding(
        finding=hallucinated_finding,
        context=context,
        project_id=project_id,
        scan_id=scan_id,
        modified_workspace_root=mod_root,
    )

    # Must be recorded as rejected hallucination without crashing
    assert patch_record.applied is False
    assert patch_record.validation.path_check_passed is False
    assert "hallucinated_path" in (patch_record.apply_error or "")


@pytest.mark.asyncio
async def test_full_pipeline_original_project_byte_identical_checksum(tmp_path: Path):
    """
    Phase 7 Exit Gate 3 (RULES.md §4, SECURITY.md §7):
    The ORIGINAL imported project source and scan_workspace/ remain 100% BYTE-IDENTICAL
    after a full Builder -> Attacker -> Evaluator -> Fixer run.
    Verified with SHA-256 recursive checksums before and after.
    """
    # Upstream reference fixture (original imported project source)
    original_source = VULN_FIXTURE

    # Checksum BEFORE run
    checksum_before_upstream = calculate_tree_sha256(original_source)

    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=original_source)
    await handle.start()

    try:
        # Full Pipeline Run
        # 1. Builder
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id=project_id,
            scan_id=scan_id,
            project_dir=original_source,
            target_handle=handle,
        )

        # 2. Attacker
        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_res = await attacker.run_scan(context=context, target_handle=handle)
        assert len(attacker_res.findings) == 3

        # 3. Evaluator
        evaluator = EvaluatorAgent(test_case_repo=test_case_repo)
        eval_res = await evaluator.evaluate_scan(
            candidates=attacker_res.findings,
            target_handle=handle,
            scan_id=scan_id,
        )
        assert eval_res.confirmed_count == 3

        # 4. Workspace setup
        ws_manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        scan_ws = ws_manager.create_scan_workspace(project_id, str(original_source))
        checksum_before_scan_ws = calculate_tree_sha256(scan_ws)

        # 5. Fixer
        fixer = FixerAgent(workspace_manager=ws_manager)
        fix_res = await fixer.fix_scan(
            findings=eval_res.findings,
            context=context,
            project_id=project_id,
            scan_id=scan_id,
        )
        assert fix_res.applied_count == 3

        # Checksum AFTER run
        checksum_after_upstream = calculate_tree_sha256(original_source)
        checksum_after_scan_ws = calculate_tree_sha256(scan_ws)

        # PROOF OF BYTE-IDENTITY:
        assert checksum_before_upstream == checksum_after_upstream, (
            "FATAL: Original upstream project source was modified during pipeline execution!"
        )
        assert checksum_before_scan_ws == checksum_after_scan_ws, (
            "FATAL: scan_workspace/ was modified during patch execution! Only modified_workspace/ may be written to."
        )

        # Verify modified_workspace actually received writes
        mod_ws = ws_manager.get_modified_workspace_path(project_id)
        checksum_mod_ws = calculate_tree_sha256(mod_ws)
        assert checksum_mod_ws != checksum_after_scan_ws, (
            "modified_workspace was not modified despite applied patches"
        )

    finally:
        await handle.stop()
