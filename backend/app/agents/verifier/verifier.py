"""
Verifier Agent (PHASES.md Phase 8, METHODOLOGY.md §5, DATA_MODEL.md §3 verification_results).

Responsibilities:
1. Target rebuild/restart from modified_workspace/.
2. Re-test original candidate exploit with platform oracles.
3. Enforce Dual Criterion:
   - Exploit blocked AND functional suite passes -> FIXED
   - Exploit blocked BUT functional suite fails -> REGRESSED
   - Exploit still succeeds -> UNRESOLVED
   - Rebuild/restart failed -> UNVERIFIED
4. Adapted variant attack execution (RESEARCH.md §5 post-fix robustness rate).
5. Persist complete VerificationRecord to verification_results collection.
"""
from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any

from app.agents.attacker.repository import TestCaseRepository
from app.agents.evaluator.schemas import EvaluatedFinding
from app.agents.fixer.schemas import PatchRecord
from app.agents.verifier.functional_runner import FunctionalSuiteRunner
from app.agents.verifier.repository import VerificationRepository
from app.agents.verifier.retester import OriginalExploitRetester
from app.agents.verifier.schemas import (
    FunctionalSuiteResult,
    OriginalExploitResult,
    VariantAttackResult,
    VerificationOutcome,
    VerificationRecord,
    VerificationScanSummary,
)
from app.agents.verifier.variant_runner import VariantAttackRunner
from app.isolation.workspace import WorkspaceManager
from app.targets.handle import LocalWorkspaceTargetHandle, TargetHandle

logger = logging.getLogger(__name__)


class VerifierAgent:
    """
    Orchestrates target restart, original exploit re-testing, functional test validation,
    and variant attack execution.
    """

    def __init__(
        self,
        *,
        verification_repo: VerificationRepository | None = None,
        test_case_repo: TestCaseRepository | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self._verification_repo = verification_repo or VerificationRepository()
        self._test_case_repo = test_case_repo or TestCaseRepository()
        self._workspace_manager = workspace_manager or WorkspaceManager()
        self._retester = OriginalExploitRetester(test_case_repo=self._test_case_repo)
        self._functional_runner = FunctionalSuiteRunner()
        self._variant_runner = VariantAttackRunner()

    async def verify_finding(
        self,
        *,
        finding: EvaluatedFinding,
        patch: PatchRecord,
        scan_id: str,
        target_handle: TargetHandle | None = None,
        modified_workspace: Path | None = None,
    ) -> VerificationRecord:
        """
        Verify a single patched finding against the rebuilt target:
        1. Ensure running target handle pointing to modified_workspace/.
        2. Re-run original candidate exploit.
        3. Run project's functional test suite (Dual Criterion).
        4. Run adapted variant attack.
        5. Persist and return VerificationRecord.
        """
        t0 = time.perf_counter()
        own_handle = False
        handle: TargetHandle | None = target_handle

        try:
            # Step 1: Rebuild / restart target from modified_workspace if handle not supplied
            if handle is None:
                if modified_workspace is None:
                    modified_workspace = self._workspace_manager.get_modified_workspace_path(patch.project_id)

                handle = LocalWorkspaceTargetHandle(workspace_dir=modified_workspace)
                own_handle = True
                try:
                    await handle.start()
                except Exception as exc:
                    duration_s = time.perf_counter() - t0
                    record = VerificationRecord(
                        finding_id=finding.id,
                        patch_id=patch.id,
                        scan_id=scan_id,
                        rebuild_ok=False,
                        original_exploit=OriginalExploitResult(ran=False, exploited=False, rationale="Rebuild failed"),
                        functional_suite=FunctionalSuiteResult(ran=False, total=0),
                        variant_attack=VariantAttackResult(ran=False, exploited=False),
                        outcome=VerificationOutcome.UNVERIFIED,
                        outcome_reason=f"rebuild_restart_failed: {exc}",
                        duration_s=duration_s,
                    )
                    return await self._verification_repo.create(record)

            # Step 2: Re-run original candidate exploit
            orig_exploit_res = await self._retester.retest(
                finding=finding,
                target_handle=handle,
            )

            # If the patch failed to stop the exploit, state is UNRESOLVED
            if orig_exploit_res.exploited:
                duration_s = time.perf_counter() - t0
                record = VerificationRecord(
                    finding_id=finding.id,
                    patch_id=patch.id,
                    scan_id=scan_id,
                    rebuild_ok=True,
                    original_exploit=orig_exploit_res,
                    functional_suite=FunctionalSuiteResult(ran=False, total=0),
                    variant_attack=VariantAttackResult(ran=False, exploited=False, rationale="Skipped: original exploit not blocked"),
                    outcome=VerificationOutcome.UNRESOLVED,
                    outcome_reason=f"exploit_still_succeeded: {orig_exploit_res.rationale}",
                    duration_s=duration_s,
                )
                return await self._verification_repo.create(record)

            # Step 3: Dual Criterion Evaluation — Run Functional Test Suite
            func_res = await self._functional_runner.run_functional_suite(
                target_handle=handle,
            )

            # If functional test suite fails, state is REGRESSED (broke legitimate functionality)
            if func_res.failed > 0:
                duration_s = time.perf_counter() - t0
                failed_str = ", ".join(func_res.newly_failing)
                record = VerificationRecord(
                    finding_id=finding.id,
                    patch_id=patch.id,
                    scan_id=scan_id,
                    rebuild_ok=True,
                    original_exploit=orig_exploit_res,
                    functional_suite=func_res,
                    variant_attack=VariantAttackResult(ran=False, exploited=False, rationale="Skipped: functional regression detected"),
                    outcome=VerificationOutcome.REGRESSED,
                    outcome_reason=f"functional_regression: {func_res.failed} test(s) failed: {failed_str}",
                    duration_s=duration_s,
                )
                return await self._verification_repo.create(record)

            # Step 4: Run Adapted Variant Attack (Post-fix Robustness Rate)
            variant_res = await self._variant_runner.run_variant_attack(
                finding=finding,
                target_handle=handle,
            )

            # Step 5: Both criteria satisfied — state is FIXED
            duration_s = time.perf_counter() - t0
            record = VerificationRecord(
                finding_id=finding.id,
                patch_id=patch.id,
                scan_id=scan_id,
                rebuild_ok=True,
                original_exploit=orig_exploit_res,
                functional_suite=func_res,
                variant_attack=variant_res,
                outcome=VerificationOutcome.FIXED,
                outcome_reason=(
                    f"dual_criterion_satisfied: original exploit blocked and all {func_res.passed} "
                    f"functional tests passed; variant {variant_res.variant_kind} exploited={variant_res.exploited}"
                ),
                duration_s=duration_s,
            )
            return await self._verification_repo.create(record)

        finally:
            if own_handle and handle is not None:
                await handle.stop()

    async def verify_scan(
        self,
        *,
        findings: list[EvaluatedFinding],
        patches: list[PatchRecord],
        scan_id: str,
        target_handle: TargetHandle | None = None,
        modified_workspace: Path | None = None,
    ) -> VerificationScanSummary:
        """
        Verify all findings and patches in a scan run.
        """
        records: list[VerificationRecord] = []
        fixed_count = 0
        regressed_count = 0
        unresolved_count = 0
        unverified_count = 0

        # Map patches by finding_id
        patch_map = {p.finding_id: p for p in patches}

        # Start a shared target handle for the modified workspace if not provided
        own_handle = False
        handle = target_handle

        if handle is None:
            if modified_workspace is None and patches:
                modified_workspace = self._workspace_manager.get_modified_workspace_path(patches[0].project_id)

            if modified_workspace is not None:
                handle = LocalWorkspaceTargetHandle(workspace_dir=modified_workspace)
                own_handle = True
                try:
                    await handle.start()
                except Exception as exc:
                    logger.error("Failed to start modified workspace target for scan: %s", exc)
                    handle = None

        try:
            for finding in findings:
                patch = patch_map.get(finding.id)
                if not patch or not patch.applied:
                    # No applied patch exists for finding
                    record = VerificationRecord(
                        finding_id=finding.id,
                        patch_id=patch.id if patch else "none",
                        scan_id=scan_id,
                        rebuild_ok=False,
                        original_exploit=OriginalExploitResult(ran=False, exploited=True, rationale="No patch applied"),
                        functional_suite=FunctionalSuiteResult(ran=False),
                        variant_attack=VariantAttackResult(ran=False, exploited=False),
                        outcome=VerificationOutcome.UNRESOLVED,
                        outcome_reason="no_applied_patch",
                        duration_s=0.0,
                    )
                    saved = await self._verification_repo.create(record)
                    records.append(saved)
                    unresolved_count += 1
                    continue

                record = await self.verify_finding(
                    finding=finding,
                    patch=patch,
                    scan_id=scan_id,
                    target_handle=handle,
                    modified_workspace=modified_workspace,
                )
                records.append(record)

                if record.outcome == VerificationOutcome.FIXED:
                    fixed_count += 1
                elif record.outcome == VerificationOutcome.REGRESSED:
                    regressed_count += 1
                elif record.outcome == VerificationOutcome.UNRESOLVED:
                    unresolved_count += 1
                elif record.outcome == VerificationOutcome.UNVERIFIED:
                    unverified_count += 1

            return VerificationScanSummary(
                scan_id=scan_id,
                records=records,
                fixed_count=fixed_count,
                regressed_count=regressed_count,
                unresolved_count=unresolved_count,
                unverified_count=unverified_count,
            )

        finally:
            if own_handle and handle is not None:
                await handle.stop()
