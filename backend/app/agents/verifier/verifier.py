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

import asyncio
import logging
import time
from pathlib import Path

from app.agents.verifier import smoke_suite
from app.agents.verifier.endpoint_check import check_endpoint_preserved
from app.agents.verifier.smoke_suite import SmokeBaseline
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
import anyio

from app.agents.verifier.variant_runner import VariantAttackRunner
from app.core.config import settings
from app.isolation.docker_manager import DockerManager
from app.isolation.workspace import WorkspaceManager
from app.targets.handle import (
    ContainerTargetHandle,
    TargetHandle,
    TrustedFixtureTargetHandle,
    is_trusted_fixture_path,
)

logger = logging.getLogger(__name__)


class VerificationUnavailableError(Exception):
    """Raised when patched code verification cannot proceed safely without Docker isolation."""


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
        docker_manager: DockerManager | None = None,
        emitter: Any = None,
        provider_name: str | None = None,
    ) -> None:
        self._verification_repo = verification_repo or VerificationRepository()
        self._test_case_repo = test_case_repo or TestCaseRepository()
        self._workspace_manager = workspace_manager or WorkspaceManager()
        self._docker_manager = docker_manager
        self._emitter = emitter
        # Which LLM wrote the patches being verified (decides the Demo host-execution rule).
        self._provider_name = (provider_name or settings.llm_provider or "mock").lower()
        self._retester = OriginalExploitRetester(test_case_repo=self._test_case_repo)
        self._functional_runner = FunctionalSuiteRunner()
        self._variant_runner = VariantAttackRunner()

    async def _acquire_patched_handle(
        self,
        project_id: str,
        patch_id: str,
        modified_workspace: Path,
        entry_point: str | None = None,
        project: Any | None = None,
    ) -> tuple[TargetHandle, bool, bool]:
        """
        Acquire target handle for modified workspace (F0, C3).
        Returns (handle, is_local_handle, is_docker_patched).
        Fixtures use TrustedFixtureTargetHandle only when Docker is unavailable (Demo mode).
        When Docker IS available, patched code of fixtures also runs in a container (A6).
        """
        from app.isolation.errors import IsolationError
        from app.isolation.sqlite_adapter import adapt_workspace_for_sqlite

        docker_available = False
        docker_mgr = self._docker_manager
        if docker_mgr is not None:
            if hasattr(docker_mgr, "preflight"):
                try:
                    rep = await anyio.to_thread.run_sync(docker_mgr.preflight)
                    docker_available = bool(rep.get("ready"))
                except Exception:
                    docker_available = False
            else:
                docker_available = True
        else:
            try:
                docker_mgr = await anyio.to_thread.run_sync(DockerManager)
                rep = await anyio.to_thread.run_sync(docker_mgr.preflight)
                docker_available = bool(rep.get("ready"))
            except Exception:
                docker_available = False

        # Host-execution trust comes only from the project's database record (D5).
        source_path = getattr(project, "source_path", None) if project else None
        is_fixture = bool(source_path and is_trusted_fixture_path(source_path)) or (
            is_trusted_fixture_path(modified_workspace)
        )

        raw_entry = getattr(project, "entry_point", None) or entry_point or "main.py"
        if ":" in str(raw_entry):
            file_part = str(raw_entry).split(":")[0]
            resolved_entry = f"{file_part}.py" if not file_part.endswith(".py") else file_part
        elif not str(raw_entry).endswith(".py"):
            resolved_entry = f"{raw_entry}.py"
        else:
            resolved_entry = str(raw_entry)

        if not docker_available:
            origin = getattr(project, "origin", None)
            if origin is None:
                origin = "demo_fixture" if is_fixture else "user_project"
            is_mock_or_replay = self._provider_name in ("mock", "replay")

            if is_fixture and origin == "demo_fixture":
                if is_mock_or_replay:
                    handle = TrustedFixtureTargetHandle(
                        workspace_dir=modified_workspace,
                        entry_point=resolved_entry,
                        trusted_source_path=source_path,
                        project_workspace_root=self._workspace_manager.get_project_root(project_id),
                    )
                    await handle.start()
                    return handle, True, False
                else:
                    raise VerificationUnavailableError(
                        "Verification unavailable: Docker isolation is required to verify code written by cloud or external LLM models on this system."
                    )
            raise IsolationError(
                f"isolation_required: Docker daemon required to verify patched image for project {project_id}"
            )

        # Adapt workspace for isolated SQLite storage if needed (A5)
        sqlite_result = await anyio.to_thread.run_sync(
            adapt_workspace_for_sqlite,
            modified_workspace,
        )

        dependency_file = getattr(project, "dependency_file", None) if project else None
        if not dependency_file and (Path(modified_workspace) / "requirements.txt").is_file():
            # Record without a dependency file: use the workspace's requirements.txt
            # rather than the `pip install .` template, which needs a pyproject/setup.py.
            dependency_file = "requirements.txt"

        tag = docker_mgr.patched_image_tag(project_id, patch_id)
        # Any failure or cancellation between build and healthy (D4) must not leak
        # the patched image, target, proxy or network.
        try:
            await anyio.to_thread.run_sync(
                docker_mgr.build_image,
                project_id,
                modified_workspace,
                resolved_entry,
                dependency_file,
                tag,
            )
            target_id, proxy_id, proxy_port = await anyio.to_thread.run_sync(
                docker_mgr.start_patched_target,
                project_id,
                patch_id,
                tag,
                sqlite_result.env_vars,
            )

            # Wait for health through proxy (A3)
            healthy = await anyio.to_thread.run_sync(
                docker_mgr.wait_for_healthy,
                proxy_port,
                settings.docker_startup_timeout,
            )
            if not healthy:
                diag = (
                    docker_mgr.get_last_health_diagnostics()
                    if hasattr(docker_mgr, "get_last_health_diagnostics")
                    else {}
                )
                raise IsolationError(
                    f"Patched container failed health check via proxy within "
                    f"{settings.docker_startup_timeout}s timeout. Diagnostics: {diag}"
                )
        except BaseException:
            try:
                await asyncio.shield(
                    asyncio.to_thread(docker_mgr.cleanup_patched_target, project_id, patch_id)
                )
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.warning("Patched target cleanup failed for %s: %s", patch_id[:8], cleanup_exc)
            raise

        handle = ContainerTargetHandle(
            proxy_port=proxy_port,
            container_id=target_id,
            docker_manager=docker_mgr,
        )
        return handle, False, True

    async def _release_patched_handle(
        self,
        handle: TargetHandle | None,
        project_id: str,
        patch_id: str,
        is_local_handle: bool,
        is_docker_patched: bool,
    ) -> None:
        if is_docker_patched:
            docker_mgr = self._docker_manager
            if docker_mgr is None:
                try:
                    docker_mgr = DockerManager()
                except Exception:
                    docker_mgr = None
            if docker_mgr:
                await anyio.to_thread.run_sync(
                    docker_mgr.cleanup_patched_target,
                    project_id,
                    patch_id,
                )
        elif is_local_handle and handle is not None and hasattr(handle, "stop"):
            await handle.stop()

    async def _run_functional_check(
        self,
        *,
        handle: TargetHandle,
        finding: EvaluatedFinding,
        project: Any | None,
        functional_baseline: SmokeBaseline | None,
        scan_fixed_routes: list[tuple[str, str]] | None = None,
    ) -> FunctionalSuiteResult:
        """
        Pick the functional suite honestly (F9 "App still works"):
        - the demo fixtures ship their own hand-written suite;
        - every other project is checked with auto-generated read-only smoke cases
          compared against the pre-fix baseline;
        - with neither, report that no suite ran (the outcome can then never be "fixed").
        """
        source_path = getattr(project, "source_path", None) if project else None
        if source_path and is_trusted_fixture_path(source_path):
            return await self._functional_runner.run_functional_suite(target_handle=handle)
        if functional_baseline is not None:
            return await smoke_suite.run_against(
                handle.base_url, functional_baseline, (finding.route_template, finding.method),
                scan_fixed_routes,
            )
        return FunctionalSuiteResult(
            ran=False, total=0, source="none",
            detail="This project has no runnable test suite and no OpenAPI baseline was recorded.",
        )

    async def verify_finding(
        self,
        *,
        finding: EvaluatedFinding,
        patch: PatchRecord,
        scan_id: str,
        target_handle: TargetHandle | None = None,
        modified_workspace: Path | None = None,
        entry_point: str | None = None,
        project: Any | None = None,
        functional_baseline: SmokeBaseline | None = None,
        scan_fixed_routes: list[tuple[str, str]] | None = None,
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
        own_local_handle = False
        own_docker_patched = False
        target_project_id = patch.project_id if patch else (getattr(project, "id", "project") if project else "project")
        target_patch_id = patch.id if patch else "patch"
        handle: TargetHandle | None = target_handle

        try:
            # Step 1: Rebuild / restart target from modified_workspace if handle not supplied
            if handle is None:
                if modified_workspace is None:
                    modified_workspace = self._workspace_manager.get_modified_workspace_path(target_project_id)

                try:
                    handle, own_local_handle, own_docker_patched = await self._acquire_patched_handle(
                        project_id=target_project_id,
                        patch_id=target_patch_id,
                        modified_workspace=modified_workspace,
                        entry_point=entry_point,
                        project=project,
                    )
                except VerificationUnavailableError as exc:
                    duration_s = time.perf_counter() - t0
                    record = VerificationRecord(
                        finding_id=finding.id,
                        patch_id=patch.id,
                        scan_id=scan_id,
                        rebuild_ok=False,
                        original_exploit=OriginalExploitResult(ran=False, exploited=False, rationale="Verification unavailable"),
                        functional_suite=FunctionalSuiteResult(ran=False, total=0),
                        variant_attack=VariantAttackResult(ran=False, exploited=False),
                        outcome=VerificationOutcome.VERIFICATION_UNAVAILABLE,
                        outcome_reason=str(exc),
                        duration_s=duration_s,
                    )
                    return await self._verification_repo.create(record)
                except Exception as exc:  # noqa: BLE001
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
            func_res = await self._run_functional_check(
                handle=handle,
                finding=finding,
                project=project,
                functional_baseline=functional_baseline,
                scan_fixed_routes=scan_fixed_routes,
            )
            ws_for_routes = modified_workspace or self._workspace_manager.get_modified_workspace_path(target_project_id)
            endpoint_res = await anyio.to_thread.run_sync(
                check_endpoint_preserved, Path(ws_for_routes), finding.route_template, finding.method,
            )

            # No functional evidence at all: we cannot say the app still works, so never "fixed".
            if not func_res.ran or func_res.total == 0:
                duration_s = time.perf_counter() - t0
                record = VerificationRecord(
                    finding_id=finding.id,
                    patch_id=patch.id,
                    scan_id=scan_id,
                    rebuild_ok=True,
                    original_exploit=orig_exploit_res,
                    functional_suite=func_res,
                    variant_attack=VariantAttackResult(ran=False, exploited=False, rationale="Skipped: no functional baseline"),
                    endpoint_preserved=endpoint_res,
                    outcome=VerificationOutcome.UNVERIFIED,
                    outcome_reason=(
                        "functional_baseline_unavailable: the exploit is blocked, but there was no "
                        f"way to check the app still works ({func_res.detail or 'no suite ran'})"
                    ),
                    duration_s=duration_s,
                )
                return await self._verification_repo.create(record)

            # The fix removed the vulnerable endpoint: blocking by deletion is not a fix.
            if endpoint_res.ran and not endpoint_res.preserved:
                duration_s = time.perf_counter() - t0
                record = VerificationRecord(
                    finding_id=finding.id,
                    patch_id=patch.id,
                    scan_id=scan_id,
                    rebuild_ok=True,
                    original_exploit=orig_exploit_res,
                    functional_suite=func_res,
                    variant_attack=VariantAttackResult(ran=False, exploited=False, rationale="Skipped: endpoint removed"),
                    endpoint_preserved=endpoint_res,
                    outcome=VerificationOutcome.REGRESSED,
                    outcome_reason=f"endpoint_removed: {endpoint_res.detail}",
                    duration_s=duration_s,
                )
                return await self._verification_repo.create(record)

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
                    endpoint_preserved=endpoint_res,
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
                endpoint_preserved=endpoint_res,
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
            await self._release_patched_handle(
                handle=handle,
                project_id=target_project_id,
                patch_id=target_patch_id,
                is_local_handle=own_local_handle,
                is_docker_patched=own_docker_patched,
            )

    async def verify_scan(
        self,
        *,
        findings: list[EvaluatedFinding],
        patches: list[PatchRecord],
        scan_id: str,
        target_handle: TargetHandle | None = None,
        modified_workspace: Path | None = None,
        entry_point: str | None = None,
        project: Any | None = None,
        emitter: Any = None,
        cancellation_token: asyncio.Event | None = None,
        functional_baseline: SmokeBaseline | None = None,
    ) -> VerificationScanSummary:
        """
        Verify all findings and patches in a scan run.
        """
        active_emitter = emitter or self._emitter
        t0 = time.perf_counter()
        records: list[VerificationRecord] = []
        fixed_count = 0
        regressed_count = 0
        unresolved_count = 0
        unverified_count = 0

        # Filter to confirmed findings only
        confirmed_findings = [
            f for f in findings
            if getattr(getattr(f, "status", None), "value", str(getattr(f, "status", ""))) == "confirmed"
        ]

        # Map patches by finding_id
        patch_map = {p.finding_id: p for p in patches}
        applied_patches = [p for p in patches if p.applied]

        # If there are zero confirmed findings to verify, return clean empty summary
        if not confirmed_findings:
            logger.info(
                "Verification: zero confirmed findings to verify for scan %s (patches=%d). Skipping verification.",
                scan_id[:8],
                len(patches),
                extra={
                    "event": "scan.verifier.no_findings",
                    "findings_count": 0,
                    "patches_count": len(patches),
                },
            )
            return VerificationScanSummary(
                scan_id=scan_id,
                records=[],
                fixed_count=0,
                regressed_count=0,
                unresolved_count=0,
                unverified_count=0,
            )

        # If there are zero applied patches, skip target startup cleanly and mark confirmed findings as unresolved
        if not applied_patches:
            logger.info(
                "Verification: zero applied patches to verify for scan %s (findings=%d, patches=%d). Skipping target startup.",
                scan_id[:8],
                len(confirmed_findings),
                len(patches),
                extra={
                    "event": "scan.verifier.no_patches",
                    "findings_count": len(confirmed_findings),
                    "patches_count": len(patches),
                },
            )
            for finding in confirmed_findings:
                patch = patch_map.get(finding.id)
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

            return VerificationScanSummary(
                scan_id=scan_id,
                records=records,
                fixed_count=0,
                regressed_count=0,
                unresolved_count=unresolved_count,
                unverified_count=0,
            )

        # Start a shared target handle for the modified workspace if not provided
        own_local_handle = False
        own_docker_patched = False
        target_project_id = applied_patches[0].project_id if applied_patches else (getattr(project, "id", "project") if project else "project")
        target_patch_id = applied_patches[0].id if applied_patches else "all"
        handle = target_handle

        if handle is None:
            if modified_workspace is None and applied_patches:
                modified_workspace = self._workspace_manager.get_modified_workspace_path(target_project_id)

            if modified_workspace is not None:
                try:
                    handle, own_local_handle, own_docker_patched = await self._acquire_patched_handle(
                        project_id=target_project_id,
                        patch_id=target_patch_id,
                        modified_workspace=modified_workspace,
                        entry_point=entry_point,
                        project=project,
                    )
                except Exception as exc:
                    if isinstance(exc, FileNotFoundError):
                        raise
                    for finding in confirmed_findings:
                        patch = patch_map.get(finding.id)
                        record = VerificationRecord(
                            finding_id=finding.id,
                            patch_id=patch.id if patch else "none",
                            scan_id=scan_id,
                            rebuild_ok=False,
                            original_exploit=OriginalExploitResult(ran=False, exploited=False, rationale="Rebuild failed"),
                            functional_suite=FunctionalSuiteResult(ran=False, total=0),
                            variant_attack=VariantAttackResult(ran=False, exploited=False),
                            outcome=VerificationOutcome.UNVERIFIED,
                            outcome_reason=f"rebuild_restart_failed: {exc}",
                            duration_s=time.perf_counter() - t0,
                        )
                        persisted = await self._verification_repo.create(record)
                        records.append(persisted)
                    return VerificationScanSummary(
                        scan_id=scan_id,
                        records=records,
                        total_findings=len(confirmed_findings),
                        total_fixed=0,
                        total_regressed=0,
                        total_unresolved=0,
                        total_unverified=len(records),
                        duration_s=time.perf_counter() - t0,
                    )

        try:
            for finding in confirmed_findings:
                if cancellation_token and cancellation_token.is_set():
                    raise asyncio.CancelledError("Verifier execution cancelled")
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

                if active_emitter:
                    await active_emitter(
                        scan_id,
                        "verifier",
                        "verification_started",
                        f"Testing patch for {finding.id}",
                        refs={"finding_id": finding.id},
                    )

                record = await self.verify_finding(
                    finding=finding,
                    patch=patch,
                    scan_id=scan_id,
                    target_handle=handle,
                    modified_workspace=modified_workspace,
                    entry_point=entry_point,
                    project=project,
                    functional_baseline=functional_baseline,
                    scan_fixed_routes=[(f.route_template, f.method) for f in findings],
                )
                records.append(record)

                if active_emitter:
                    outcome_str = record.outcome.value if hasattr(record.outcome, "value") else str(record.outcome)
                    await active_emitter(
                        scan_id,
                        "verifier",
                        "verification_result",
                        f"Outcome: {outcome_str}",
                        detail=record.outcome_reason or "",
                        refs={"finding_id": finding.id},
                    )

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
            await self._release_patched_handle(
                handle=handle,
                project_id=target_project_id,
                patch_id=target_patch_id,
                is_local_handle=own_local_handle,
                is_docker_patched=own_docker_patched,
            )
