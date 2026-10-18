"""
Scan supervisor and async pipeline orchestrator (ARCHITECTURE §4, §5, RULES §5a).

Rules enforced:
  - POST /api/scans returns 202 with scan_id immediately; runs pipeline in background.
  - Background task executes Builder -> Attacker -> Evaluator -> Fixer -> Verifier.
  - Scan, findings, patches, and verification results are persisted to Mongo.
  - Enforces scope-locked HTTP traffic and workspace isolation throughout.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.verifier import smoke_suite
from app.llm.factory import build_provider, provider_name_for_scan
from app.agents.attacker.attacker import AttackerAgent
from app.agents.attacker.repository import TestCaseRepository
from app.agents.builder.builder import BuilderAgent
from app.agents.evaluator.evaluator import EvaluatorAgent
from app.agents.evaluator.repository import FindingRepository
from app.agents.fixer.fixer import FixerAgent
from app.agents.fixer.repository import PatchRepository
from app.agents.verifier.repository import VerificationRepository
from app.agents.verifier.schemas import VerificationOutcome
from app.agents.verifier.verifier import VerifierAgent
from app.core.config import settings
from app.core.logging import set_log_context
from app.core.validators import validate_project_id
from app.database.models import ProjectRecord, ScanRecord
from app.database.repositories import ProjectRepository, ScanRepository
from app.isolation.docker_manager import DockerManager
from app.isolation.workspace import WorkspaceManager
from app.services.event_bus import event_bus
from app.services.task_registry import task_registry
import anyio
from app.targets.handle import (
    ContainerTargetHandle,
    LocalFixtureTargetHandle,
    TargetHandle,
    TrustedFixtureTargetHandle,
    is_trusted_fixture_path,
)

logger = logging.getLogger(__name__)


def _prompt_digest() -> str | None:
    try:
        from app.llm.prompts.registry import PromptRegistry

        return PromptRegistry().digest
    except Exception:  # noqa: BLE001 — metadata only; never fail a scan over it
        return None


class ScanNotCancellableError(Exception):
    """Raised when cancelling a scan that has already finished."""

# Unified diff hunk header, e.g. "@@ -126,6 +126,8 @@"
_HUNK_RE = re.compile(r"^@@\s*-(\d+)(?:,(\d+))?\s+\+\d+(?:,\d+)?\s*@@")


def _locations_from_patch(patch: Any) -> list[dict[str, Any]]:
    """
    Derive source locations from a patch's diff hunk headers.

    Findings are produced from runtime evidence and carry no source position.
    The Fixer's diff, however, states exactly which original lines were
    touched, so the first hunk of each file gives a usable location to show
    in the UI. Returns an empty list if nothing can be parsed — never raises,
    since a missing location must not break the findings response.
    """
    locations: list[dict[str, Any]] = []
    try:
        for file_diff in getattr(patch, "files", []) or []:
            path = getattr(file_diff, "path", "") or ""
            diff_text = getattr(file_diff, "diff", "") or ""
            for line in diff_text.splitlines():
                match = _HUNK_RE.match(line.strip())
                if not match:
                    continue
                start = int(match.group(1))
                span = int(match.group(2)) if match.group(2) else 1
                locations.append(
                    {
                        "file": str(path),
                        "lineStart": start,
                        "lineEnd": start + max(span - 1, 0),
                    }
                )
                break  # first hunk per file is enough to locate the change
    except Exception:  # noqa: BLE001 - display detail only, never fatal
        logger.debug("Could not derive source locations from patch", exc_info=True)
        return []
    return locations


class ScanService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase | None = None,
        workspace_manager: WorkspaceManager | None = None,
        docker_manager: DockerManager | None = None,
    ) -> None:
        self._db = db
        self._project_repo = ProjectRepository(db)
        self._scan_repo = ScanRepository(db)
        self._finding_repo = FindingRepository(db)
        self._patch_repo = PatchRepository(db)
        self._verification_repo = VerificationRepository(db)
        self._workspace = workspace_manager or WorkspaceManager()
        self._docker_instance = docker_manager
        self._active_tasks: dict[str, asyncio.Task] = {}

    @property
    def _docker(self) -> DockerManager | None:
        if self._docker_instance is None:
            try:
                self._docker_instance = DockerManager()
            except Exception:
                return None
        return self._docker_instance

    async def get_project(self, project_id: str) -> ProjectRecord | None:
        return await self._project_repo.get_by_id(project_id)

    async def get_scan(self, scan_id: str) -> ScanRecord | None:
        return await self._scan_repo.get_by_id(scan_id)

    async def list_scans(self, project_id: str | None = None) -> list[ScanRecord]:
        if project_id:
            validate_project_id(project_id)
            return await self._scan_repo.list_by_project(project_id)
        return await self._scan_repo.list_all()

    async def submit_scan(self, project_id: str) -> ScanRecord:
        """
        Validate project and start scan pipeline as a background job (RULES §5a).
        Returns the queued ScanRecord immediately (202 Accepted).
        """
        validate_project_id(project_id)
        project = await self.get_project(project_id)
        if project is None:
            raise ValueError(f"Project '{project_id}' not found.")

        if project.validation_status.value != "valid":
            raise ValueError(
                f"Project '{project_id}' cannot be scanned: validation_status="
                f"{project.validation_status}. Only valid projects can be scanned."
            )

        origin = getattr(project, "origin", "user_project")
        # Create scan record in queued state
        scan = ScanRecord(
            project_id=project_id,
            project_name=project.name,
            state="running",
            stage="queued",
            mode="demo" if origin == "demo_fixture" else "live",
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
        )
        scan = await self._scan_repo.create(scan)

        set_log_context(project_id=project_id, scan_id=scan.id, stage="queued")
        logger.info(
            "Scan job queued for project %s (%s)",
            project_id[:8],
            project.name,
            extra={
                "event": "scan.job.queued",
                "scan_id": scan.id,
                "project_id": project_id,
                "stage": "queued",
            },
        )

        # Spawn background task
        task = asyncio.create_task(
            self._run_scan_pipeline(scan.id, project_id)
        )
        self._active_tasks[scan.id] = task
        task_registry.register(scan.id, task)
        return scan

    TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted"})

    async def cancel_scan(self, scan_id: str) -> ScanRecord | None:
        """
        Cancel an in-flight scan (C1, C2, D4).

        Cancelling the registered task raises CancelledError inside the pipeline;
        the verifier's ``finally`` tears down any patched container/proxy/network it
        started. The project's own isolation container is a project resource and is
        left running (the user stops it from the Projects screen).

        Raises ScanNotCancellableError for scans already in a terminal state.
        """
        scan = await self._scan_repo.get_by_id(scan_id)
        if scan is None:
            return None
        if scan.state in self.TERMINAL_STATES:
            raise ScanNotCancellableError(f"Scan '{scan_id}' is already {scan.state}.")

        task_registry.request_cancellation(scan_id)

        scan.state = "cancelled"
        scan.terminal_reason = "user_cancelled"
        scan.ended_at = datetime.now(timezone.utc)
        await self._scan_repo.update(scan)

        await event_bus.emit(
            scan_id=scan_id,
            agent="system",
            kind="error",
            title="Scan cancelled",
            plain="Scan was cancelled by user request.",
        )
        return scan

    async def _run_scan_pipeline(self, scan_id: str, project_id: str) -> None:
        """
        Execute the full autonomous scan pipeline:
        Builder -> Attacker -> Evaluator -> Fixer -> Verifier.
        """
        set_log_context(scan_id=scan_id, project_id=project_id, stage="pipeline_start")
        pipeline_start_time = time.monotonic()
        scan = await self._scan_repo.get_by_id(scan_id)
        project = await self.get_project(project_id)
        if not scan or not project:
            logger.error(
                "Scan pipeline aborted: scan or project not found for scan_id=%s, project_id=%s",
                scan_id,
                project_id,
                extra={"event": "scan.pipeline.aborted"},
            )
            return

        target_handle: TargetHandle | None = None
        own_handle = False

        try:
            logger.info(
                "Starting scan pipeline for project %s (%s)",
                project_id[:8],
                project.name,
                extra={"event": "scan.pipeline.started", "stage": "starting"},
            )

            # ── 1. Acquire Target Handle ──────────────────────────────────────
            set_log_context(stage="target_handle")
            logger.info(
                "Acquiring target handle for scan %s",
                scan_id[:8],
                extra={"event": "target.handle.acquiring"},
            )
            # Provider is chosen per scan; Demo fixtures always use the offline
            # provider so no model-written code can reach the host (F4).
            provider_name = provider_name_for_scan(getattr(project, "origin", "user_project"))
            if getattr(project, "origin", "user_project") == "demo_fixture":
                scan.mode = "demo"
            else:
                # The mode badge must say which AI actually ran (FEATURES.md F4).
                scan.mode = {"mock": "live_offline_ai", "replay": "live_offline_ai",
                             "ollama": "live_local_ai"}.get(provider_name, "live")
            llm = build_provider(provider_name)
            scan.llm = {
                "provider": llm.descriptor.provider,
                "model_id": llm.descriptor.model_id,
                "prompt_registry_digest": _prompt_digest(),
            }

            if project.container_id and project.proxy_port:
                target_handle = ContainerTargetHandle(
                    proxy_port=project.proxy_port,
                    container_id=project.container_id,
                    docker_manager=self._docker,
                )
                logger.info(
                    "Using container target handle (container=%s, proxy_port=%s)",
                    project.container_id[:12],
                    project.proxy_port,
                    extra={
                        "event": "target.handle.acquired",
                        "handle_type": "container",
                        "container_id": project.container_id[:12],
                        "proxy_port": project.proxy_port,
                    },
                )
            else:
                source_p = Path(project.source_path).resolve()
                origin = getattr(project, "origin", None)
                if origin is None:
                    origin = "demo_fixture" if is_trusted_fixture_path(source_p) else "user_project"
                if is_trusted_fixture_path(source_p) and origin == "demo_fixture":
                    target_handle = TrustedFixtureTargetHandle(
                        workspace_dir=source_p,
                        entry_point=project.entry_point,
                    )
                    logger.info(
                        "Using trusted fixture target handle: %s",
                        source_p,
                        extra={"event": "target.handle.acquired", "handle_type": "fixture"},
                    )
                    await target_handle.start()
                    own_handle = True
                else:
                    # Non-fixture projects MUST run in hardened container isolation (F0, C3).
                    # Auto-run isolation as the first step of the scan (F0, Autopilot F3).
                    logger.info(
                        "No running container for non-fixture project %s; auto-running isolation",
                        project.id[:8],
                        extra={"event": "scan.isolation.auto_start"},
                    )
                    from app.services.isolation_service import IsolationService
                    from app.isolation.errors import IsolationError

                    docker_mgr = self._docker
                    if docker_mgr is None:
                        raise IsolationError(
                            f"isolation_required: Docker daemon is not available to isolate project {project.id}"
                        )

                    isolation_svc = IsolationService(
                        db=self._db,
                        docker_manager=docker_mgr,
                        workspace_manager=self._workspace,
                    )
                    try:
                        await event_bus.emit(scan.id, "system", "stage_started", "Container Isolation", "Auto-starting Docker isolation")
                        project = await isolation_svc.start_isolation(project.id)
                        await event_bus.emit(scan.id, "system", "stage_finished", "Container Isolation", "Container isolation established")
                    except Exception as exc:
                        await event_bus.emit(scan.id, "system", "error", f"Isolation failed: {exc}", detail=str(exc))
                        logger.error(
                            "Auto-isolation failed for project %s: %s",
                            project.id[:8],
                            exc,
                            extra={"event": "scan.isolation.auto_failed", "error": str(exc)},
                        )
                        raise IsolationError(
                            f"isolation_required: Project {project.id} cannot be scanned without container isolation: {exc}"
                        ) from exc

                    if not (project.container_id and project.proxy_port):
                        raise IsolationError(
                            f"isolation_required: Project {project.id} isolation completed without container/proxy."
                        )

                    target_handle = ContainerTargetHandle(
                        proxy_port=project.proxy_port,
                        container_id=project.container_id,
                        docker_manager=docker_mgr,
                    )
                    logger.info(
                        "Using container target handle after auto-isolation (container=%s, proxy_port=%s)",
                        project.container_id[:12],
                        project.proxy_port,
                        extra={
                            "event": "target.handle.acquired",
                            "handle_type": "container",
                            "container_id": project.container_id[:12],
                            "proxy_port": project.proxy_port,
                        },
                    )

            # ── 2. Stage: Builder ─────────────────────────────────────────────
            set_log_context(stage="builder")
            stage_start = time.monotonic()
            scan.state = "running"
            scan.stage = "builder"
            await self._scan_repo.update(scan)
            await event_bus.emit(scan.id, "builder", "stage_started", "Builder Agent", "Extracting API routes, auth schemes and principals")
            logger.info(
                "Scan stage transitioned to 'builder'",
                extra={"event": "scan.transition", "stage": "builder", "state": "running"},
            )
            logger.info("BuilderAgent starting context extraction", extra={"event": "scan.builder.started"})

            builder = BuilderAgent(llm_provider=llm, emitter=event_bus.emit)
            project_dir = Path(project.workspace_path) if (project.workspace_path and Path(project.workspace_path).exists()) else Path(project.source_path)
            context = await builder.build_context(
                project_id=project.id,
                scan_id=scan.id,
                project_dir=project_dir,
                target_handle=target_handle,
            )
            builder_elapsed = time.monotonic() - stage_start
            routes_count = len(getattr(context, "routes", []) or getattr(context, "endpoints", []) or [])
            scan.counters["endpoints_discovered"] = routes_count
            scan.stage_durations["builder"] = round(builder_elapsed, 3)
            auth_schemes = getattr(context, "auth_schemes", [])
            principals = getattr(context, "principals", [])
            auth_desc = ", ".join(auth_schemes) if auth_schemes else "none"
            principals_count = len(principals)

            await event_bus.emit(scan.id, "builder", "stage_finished", "Builder Agent", f"Discovered {routes_count} endpoints")
            logger.info(
                "BuilderAgent completed in %.2fs (routes=%d, auth_schemes=%s, principals=%d)",
                builder_elapsed,
                routes_count,
                auth_desc,
                principals_count,
                extra={
                    "event": "scan.builder.succeeded",
                    "elapsed_sec": round(builder_elapsed, 3),
                    "endpoints_discovered": routes_count,
                    "auth_schemes": auth_schemes,
                    "principals_count": principals_count,
                },
            )

            # ── 3. Stage: Attacker ────────────────────────────────────
            set_log_context(stage="attacker")
            stage_start = time.monotonic()
            scan.stage = "attacker"
            await self._scan_repo.update(scan)
            await event_bus.emit(scan.id, "attacker", "stage_started", "Attacker Agent", "Generating and executing targeted adversarial tests")
            logger.info(
                "Scan stage transitioned to 'attacker'",
                extra={"event": "scan.transition", "stage": "attacker", "state": "running"},
            )
            logger.info("AttackerAgent starting test execution", extra={"event": "scan.attacker.started"})

            test_case_repo = TestCaseRepository(self._db)
            token = task_registry.get_cancellation_token(scan.id)
            attacker = AttackerAgent(test_case_repo=test_case_repo, llm_provider=llm, emitter=event_bus.emit)
            attacker_res = await attacker.run_scan(
                context=context,
                target_handle=target_handle,
                cancellation_token=token,
            )
            attacker_elapsed = time.monotonic() - stage_start
            executed_count = len([tc for tc in attacker_res.test_cases if getattr(tc, "status", "executed") == "executed"])
            skipped_policy_count = len([tc for tc in attacker_res.test_cases if getattr(tc, "status", "executed") == "skipped_policy"])
            failed_error_count = len([tc for tc in attacker_res.test_cases if getattr(tc, "status", "executed") == "failed_error"])
            generated_count = len(attacker_res.test_cases)

            scan.counters["tests_generated"] = generated_count
            scan.counters["tests_executed"] = executed_count
            scan.counters["tests_skipped_policy"] = skipped_policy_count
            scan.counters["tests_failed_error"] = failed_error_count
            scan.counters["candidates"] = len(attacker_res.findings)
            scan.stage_durations["attacker"] = round(attacker_elapsed, 3)

            await event_bus.emit(scan.id, "attacker", "stage_finished", "Attacker Agent", f"Executed {executed_count} tests ({len(attacker_res.findings)} candidates)")
            logger.info(
                "AttackerAgent completed in %.2fs (generated=%d, executed=%d, skipped_policy=%d, failed_error=%d, candidate_findings=%d)",
                attacker_elapsed,
                generated_count,
                executed_count,
                skipped_policy_count,
                failed_error_count,
                len(attacker_res.findings),
                extra={
                    "event": "scan.attacker.succeeded",
                    "elapsed_sec": round(attacker_elapsed, 3),
                    "tests_generated": generated_count,
                    "tests_executed": executed_count,
                    "tests_skipped_policy": skipped_policy_count,
                    "tests_failed_error": failed_error_count,
                    "candidates_count": len(attacker_res.findings),
                },
            )

            # ── 4. Stage: Evaluator ───────────────────────────────────
            set_log_context(stage="evaluator")
            stage_start = time.monotonic()
            scan.stage = "evaluator"
            await self._scan_repo.update(scan)
            await event_bus.emit(scan.id, "evaluator", "stage_started", "Evaluator Agent", "Adjudicating candidates with deterministic verification oracles")
            logger.info(
                "Scan stage transitioned to 'evaluator'",
                extra={"event": "scan.transition", "stage": "evaluator", "state": "running"},
            )
            logger.info(
                "EvaluatorAgent evaluating %d candidates",
                len(attacker_res.findings),
                extra={"event": "scan.evaluator.started", "candidates_count": len(attacker_res.findings)},
            )

            evaluator = EvaluatorAgent(
                provider=llm,
                test_case_repo=test_case_repo,
                finding_repo=self._finding_repo,
                emitter=event_bus.emit,
            )
            eval_res = await evaluator.evaluate_scan(
                candidates=attacker_res.findings,
                target_handle=target_handle,
                scan_id=scan.id,
                context=context,
            )
            evaluator_elapsed = time.monotonic() - stage_start
            scan.counters["confirmed"] = eval_res.confirmed_count
            scan.counters["rejected"] = eval_res.rejected_count
            scan.counters["inconclusive"] = eval_res.inconclusive_count
            scan.findings_confirmed = eval_res.confirmed_count
            scan.stage_durations["evaluator"] = round(evaluator_elapsed, 3)

            confirmed_findings = eval_res.confirmed_findings
            confirmed_ids = [f.id for f in confirmed_findings]
            rejected_ids = [f.id for f in eval_res.rejected_findings]
            inconclusive_ids = [f.id for f in eval_res.inconclusive_findings]

            await event_bus.emit(scan.id, "evaluator", "stage_finished", "Evaluator Agent", f"Confirmed {eval_res.confirmed_count} vulnerabilities")
            logger.info(
                "EvaluatorAgent completed in %.2fs (confirmed=%d, rejected=%d, inconclusive=%d)",
                evaluator_elapsed,
                eval_res.confirmed_count,
                eval_res.rejected_count,
                eval_res.inconclusive_count,
                extra={
                    "event": "scan.evaluator.succeeded",
                    "elapsed_sec": round(evaluator_elapsed, 3),
                    "confirmed": eval_res.confirmed_count,
                    "confirmed_ids": confirmed_ids,
                    "rejected": eval_res.rejected_count,
                    "rejected_ids": rejected_ids,
                    "inconclusive": eval_res.inconclusive_count,
                    "inconclusive_ids": inconclusive_ids,
                },
            )

            # Compute initial security posture score (F6)
            from app.scoring.posture import compute_posture
            raw_findings = [f.model_dump() if hasattr(f, "model_dump") else dict(f) for f in eval_res.findings]
            raw_tests = [tc.model_dump() if hasattr(tc, "model_dump") else dict(tc) for tc in attacker_res.test_cases]
            scan.posture = compute_posture(findings=raw_findings, test_cases=raw_tests)

            # Functional baseline for projects without their own suite (F9): read-only
            # smoke checks from the app's OpenAPI schema, observed on the ORIGINAL target.
            functional_baseline = None
            if not is_trusted_fixture_path(project.source_path) and confirmed_findings:
                functional_baseline = await smoke_suite.record_baseline(target_handle.base_url)
                logger.info(
                    "Recorded functional smoke baseline: %s case(s)",
                    len(functional_baseline.cases) if functional_baseline else 0,
                    extra={"event": "scan.functional_baseline"},
                )

            # ── 5. Stage: Fixer ───────────────────────────────────────
            set_log_context(stage="fixer")
            stage_start = time.monotonic()
            scan.stage = "fixer"
            await self._scan_repo.update(scan)
            await event_bus.emit(scan.id, "fixer", "stage_started", "Fixer Agent", "Synthesizing AST remediation code patches")
            logger.info(
                "Scan stage transitioned to 'fixer' (confirmed=%d, rejected=%d, inconclusive=%d)",
                len(confirmed_findings),
                len(rejected_ids),
                len(inconclusive_ids),
                extra={
                    "event": "scan.transition",
                    "stage": "fixer",
                    "state": "running",
                    "confirmed_count": len(confirmed_findings),
                    "confirmed_ids": confirmed_ids,
                    "rejected_count": len(rejected_ids),
                    "rejected_ids": rejected_ids,
                    "inconclusive_count": len(inconclusive_ids),
                    "inconclusive_ids": inconclusive_ids,
                },
            )
            logger.info(
                "FixerAgent starting for %d confirmed findings (ids=%s)",
                len(confirmed_findings),
                confirmed_ids,
                extra={
                    "event": "scan.fixer.started",
                    "confirmed_count": len(confirmed_findings),
                    "confirmed_ids": confirmed_ids,
                },
            )

            # Ensure scan_workspace exists before creating modified_workspace
            scan_ws = self._workspace.get_scan_workspace_path(project.id)
            if not scan_ws.exists():
                self._workspace.create_scan_workspace(project.id, project.source_path)

            mod_ws = self._workspace.create_modified_workspace(project.id)
            fixer = FixerAgent(
                provider=llm,
                patch_repo=self._patch_repo,
                workspace_manager=self._workspace,
                emitter=event_bus.emit,
            )
            fix_res = await fixer.fix_scan(
                findings=confirmed_findings,
                context=context,
                project_id=project.id,
                scan_id=scan.id,
                modified_workspace_root=mod_ws,
            )
            fixer_elapsed = time.monotonic() - stage_start
            scan.counters["fixes_proposed"] = len(fix_res.patches)
            scan.counters["fixes_applied"] = fix_res.applied_count
            scan.stage_durations["fixer"] = round(fixer_elapsed, 3)

            await event_bus.emit(scan.id, "fixer", "stage_finished", "Fixer Agent", f"Synthesized {len(fix_res.patches)} code patches")
            logger.info(
                "FixerAgent completed in %.2fs (patches proposed=%d, applied=%d)",
                fixer_elapsed,
                len(fix_res.patches),
                fix_res.applied_count,
                extra={
                    "event": "scan.fixer.succeeded",
                    "elapsed_sec": round(fixer_elapsed, 3),
                    "patches_proposed": len(fix_res.patches),
                    "fixes_applied": fix_res.applied_count,
                },
            )

            # ── 6. Stage: Verifier ────────────────────────────────────
            set_log_context(stage="verifier")
            stage_start = time.monotonic()
            scan.stage = "verifier"
            await self._scan_repo.update(scan)
            await event_bus.emit(scan.id, "verifier", "stage_started", "Verifier Agent", "Re-executing exploits against patched target")
            logger.info(
                "Scan stage transitioned to 'verifier' (findings=%d, patches=%d)",
                len(confirmed_findings),
                len(fix_res.patches),
                extra={
                    "event": "scan.transition",
                    "stage": "verifier",
                    "state": "running",
                    "confirmed_findings_count": len(confirmed_findings),
                    "confirmed_ids": confirmed_ids,
                    "patches_proposed": len(fix_res.patches),
                    "patches_applied": fix_res.applied_count,
                },
            )
            logger.info(
                "VerifierAgent starting verification of %d patches for %d confirmed findings",
                len(fix_res.patches),
                len(confirmed_findings),
                extra={
                    "event": "scan.verifier.started",
                    "patch_count": len(fix_res.patches),
                    "confirmed_count": len(confirmed_findings),
                },
            )

            token = task_registry.get_cancellation_token(scan.id)
            verifier = VerifierAgent(
                verification_repo=self._verification_repo,
                test_case_repo=test_case_repo,
                workspace_manager=self._workspace,
                docker_manager=self._docker,
                emitter=event_bus.emit,
                provider_name=provider_name,
            )
            ver_summary = await verifier.verify_scan(
                findings=confirmed_findings,
                patches=fix_res.patches,
                scan_id=scan.id,
                modified_workspace=mod_ws,
                entry_point=project.entry_point,
                project=project,
                functional_baseline=functional_baseline,
                cancellation_token=token,
            )
            verifier_elapsed = time.monotonic() - stage_start
            scan.counters["fixes_verified"] = ver_summary.fixed_count
            scan.stage_durations["verifier"] = round(verifier_elapsed, 3)

            await event_bus.emit(scan.id, "verifier", "stage_finished", "Verifier Agent", f"Remediation verified: {ver_summary.fixed_count} fixed")
            logger.info(
                "VerifierAgent completed in %.2fs (fixed=%d, unresolved=%d, regressed=%d, unverified=%d, unfixed=%d)",
                verifier_elapsed,
                ver_summary.fixed_count,
                ver_summary.unresolved_count,
                ver_summary.regressed_count,
                ver_summary.unverified_count,
                ver_summary.unfixed_count,
                extra={
                    "event": "scan.verifier.succeeded",
                    "elapsed_sec": round(verifier_elapsed, 3),
                    "fixed": ver_summary.fixed_count,
                    "unresolved": ver_summary.unresolved_count,
                    "regressed": ver_summary.regressed_count,
                    "unverified": ver_summary.unverified_count,
                    "unfixed": ver_summary.unfixed_count,
                },
            )

            # Recompute posture after verification (F6)
            ver_records_map = {
                r.finding_id: r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome)
                for r in ver_summary.records
            }
            for rf in raw_findings:
                if rf.get("id") in ver_records_map:
                    rf["verification_outcome"] = ver_records_map[rf["id"]]
            scan.posture = compute_posture(findings=raw_findings, test_cases=raw_tests)

            # ── 7. Complete Scan Record ───────────────────────────────
            set_log_context(stage="completed")
            scan.state = "completed"
            scan.stage = "completed"
            scan.ended_at = datetime.now(timezone.utc)
            scan.findings_confirmed = eval_res.confirmed_count
            scan.counters.update({
                "endpoints_discovered": len(context.routes),
                "tests_generated": generated_count,
                "tests_executed": executed_count,
                "tests_skipped_policy": skipped_policy_count,
                "tests_failed_error": failed_error_count,
                "candidates": len(attacker_res.findings),
                "confirmed": eval_res.confirmed_count,
                "rejected": eval_res.rejected_count,
                "inconclusive": eval_res.inconclusive_count,
                "fixes_proposed": len(fix_res.patches),
                "fixes_applied": fix_res.applied_count,
                "fixes_verified": ver_summary.fixed_count,
            })
            await self._scan_repo.update(scan)
            total_elapsed = time.monotonic() - pipeline_start_time

            # Emit budget and completion events
            await event_bus.emit(
                scan.id,
                "system",
                "budget",
                "Resource budget summary",
                budget={
                    "tests_executed": executed_count,
                    "fixes_verified": ver_summary.fixed_count,
                    "elapsed_s": round(total_elapsed, 2),
                },
            )
            await event_bus.emit(scan.id, "system", "stage_finished", "Scan Completed", f"Scan finished in {total_elapsed:.1f}s")
            logger.info(
                "Scan %s completed successfully in %.2fs: %d confirmed, %d fixes verified",
                scan_id[:8],
                total_elapsed,
                eval_res.confirmed_count,
                ver_summary.fixed_count,
                extra={
                    "event": "scan.pipeline.completed",
                    "stage": "completed",
                    "state": "completed",
                    "elapsed_sec": round(total_elapsed, 3),
                    "confirmed": eval_res.confirmed_count,
                    "fixed": ver_summary.fixed_count,
                },
            )

        except asyncio.CancelledError:
            total_elapsed = time.monotonic() - pipeline_start_time
            logger.info("Scan %s was cancelled after %.2fs", scan_id[:8], total_elapsed)
            try:
                cur_scan = await self._scan_repo.get_by_id(scan_id)
                if cur_scan:
                    cur_scan.state = "cancelled"
                    cur_scan.terminal_reason = "user_cancelled"
                    cur_scan.ended_at = datetime.now(timezone.utc)
                    await self._scan_repo.update(cur_scan)
            except Exception as repo_err:
                logger.error("Failed to persist cancelled status for scan %s: %s", scan_id[:8], repo_err)
            await event_bus.emit(scan_id, "system", "error", "Scan cancelled", plain="Scan was cancelled.")
            raise

        except Exception as exc:  # noqa: BLE001
            total_elapsed = time.monotonic() - pipeline_start_time
            failed_stage = scan.stage
            await event_bus.emit(scan.id, "system", "error", f"Scan pipeline failed: {exc}", detail=str(exc))
            logger.exception(
                "Scan %s pipeline failed in stage '%s' after %.2fs: %s",
                scan_id[:8],
                failed_stage,
                total_elapsed,
                exc,
                extra={
                    "event": "scan.pipeline.failed",
                    "stage": failed_stage,
                    "state": "failed",
                    "elapsed_sec": round(total_elapsed, 3),
                    "error": str(exc),
                },
            )
            scan.state = "failed"
            scan.stage = "failed"
            scan.error = str(exc)
            scan.terminal_reason = f"pipeline_failed_{failed_stage}"
            scan.ended_at = datetime.now(timezone.utc)
            try:
                await self._scan_repo.update(scan)
            except Exception as repo_err:  # noqa: BLE001
                logger.error(
                    "Failed to persist terminal failure status for scan %s: %s",
                    scan_id[:8],
                    repo_err,
                    exc_info=True,
                )

        finally:
            if own_handle and target_handle:
                try:
                    await target_handle.stop()
                    logger.info(
                        "Stopped target handle for scan %s",
                        scan_id[:8],
                        extra={"event": "target.handle.stopped"},
                    )
                except Exception as stop_exc:  # noqa: BLE001
                    logger.warning(
                        "Error stopping target handle for scan %s: %s",
                        scan_id[:8],
                        stop_exc,
                        extra={"event": "target.handle.stop_failed"},
                    )
            self._active_tasks.pop(scan_id, None)
            task_registry.unregister(scan_id)

    async def get_scan_patches_formatted(self, scan_id: str) -> list[dict[str, Any]]:
        """
        Return patches for a scan in the shape the Patch model in
        desktop/lib/models/patch.dart expects (Fix Review screen, DESIGN.md §8).
        """
        patches = await self._patch_repo.list_by_scan(scan_id)
        findings = await self._finding_repo.list_by_scan(scan_id)
        verifications = await self._verification_repo.list_by_scan(scan_id)
        finding_by_id = {f.id: f for f in findings}
        ver_by_finding = {v.finding_id: v for v in verifications}

        results: list[dict[str, Any]] = []
        for p in patches:
            finding = finding_by_id.get(p.finding_id)
            ver = ver_by_finding.get(p.finding_id)

            # Surface the full verification proof, not just a collapsed status.
            # "Exploit blocked AND functional suite still passing" is the
            # platform's central claim (METHODOLOGY.md §5) and it is only
            # credible if the individual results are visible.
            verification: dict[str, Any] | None = None
            if ver:
                outcome = (
                    ver.outcome.value
                    if hasattr(ver.outcome, "value")
                    else str(ver.outcome)
                )
                verification = {
                    "outcome": outcome,
                    "outcomeReason": ver.outcome_reason,
                    "rebuildOk": ver.rebuild_ok,
                    "originalExploit": {
                        "ran": ver.original_exploit.ran,
                        "exploited": ver.original_exploit.exploited,
                        "rationale": ver.original_exploit.rationale,
                    },
                    "functionalSuite": {
                        "ran": ver.functional_suite.ran,
                        "passed": ver.functional_suite.passed,
                        "failed": ver.functional_suite.failed,
                        "total": ver.functional_suite.total,
                        "newlyFailing": list(ver.functional_suite.newly_failing),
                        "source": ver.functional_suite.source,
                        "detail": ver.functional_suite.detail,
                    },
                    "endpointPreserved": {
                        "ran": ver.endpoint_preserved.ran,
                        "preserved": ver.endpoint_preserved.preserved,
                        "route": ver.endpoint_preserved.route,
                        "method": ver.endpoint_preserved.method,
                        "detail": ver.endpoint_preserved.detail,
                    },
                    "variantAttack": {
                        "ran": ver.variant_attack.ran,
                        "exploited": ver.variant_attack.exploited,
                        "variantKind": ver.variant_attack.variant_kind,
                        "rationale": ver.variant_attack.rationale,
                    },
                    "durationSeconds": ver.duration_s,
                }
            results.append(
                {
                    "id": p.id,
                    "findingId": p.finding_id,
                    "finding_id": p.finding_id,
                    "scanId": p.scan_id,
                    "scan_id": p.scan_id,
                    "findingTitle": finding.title if finding else "",
                    "finding_title": finding.title if finding else "",
                    "rootCause": p.root_cause,
                    "root_cause": p.root_cause,
                    "rationale": p.rationale,
                    "applied": p.applied,
                    "applyError": p.apply_error,
                    "apply_error": p.apply_error,
                    "files": [
                        {"path": f.path, "diff": f.diff} for f in p.files
                    ],
                    "diffStats": {
                        "files": p.diff_stats.files,
                        "added": p.diff_stats.added,
                        "removed": p.diff_stats.removed,
                    },
                    "diff_stats": {
                        "files": p.diff_stats.files,
                        "added": p.diff_stats.added,
                        "removed": p.diff_stats.removed,
                    },
                    "validation": {
                        "astParsed": p.validation.ast_parsed,
                        "pathCheckPassed": p.validation.path_check_passed,
                        "sizeOk": p.validation.size_ok,
                    },
                    "verification": verification,
                }
            )
        return results

    async def get_scan_findings_formatted(self, scan_id: str) -> list[dict[str, Any]]:
        """
        Return findings for a scan in the exact shape the Finding model
        in desktop/lib/models/finding.dart expects.
        """
        findings = await self._finding_repo.list_by_scan(scan_id)
        patches = await self._patch_repo.list_by_scan(scan_id)
        verifications = await self._verification_repo.list_by_scan(scan_id)

        patch_by_finding = {p.finding_id: p for p in patches}
        ver_by_finding = {v.finding_id: v for v in verifications}

        results: list[dict[str, Any]] = []

        for f in findings:
            patch = patch_by_finding.get(f.id)
            ver = ver_by_finding.get(f.id)

            if not patch:
                remediation_status = "notStarted"
            elif not patch.applied:
                remediation_status = "fixFailed"
            elif not ver:
                remediation_status = "fixApplied"
            elif ver.outcome == VerificationOutcome.FIXED or ver.outcome.value == "fixed":
                remediation_status = "fixVerified"
            elif ver.outcome == VerificationOutcome.REGRESSED or ver.outcome.value == "regressed":
                remediation_status = "regressed"
            elif ver.outcome == VerificationOutcome.UNRESOLVED or ver.outcome.value == "unresolved":
                remediation_status = "fixFailed"
            elif ver.outcome == VerificationOutcome.UNVERIFIED or ver.outcome.value == "unverified":
                remediation_status = "verificationUnavailable"
            else:
                remediation_status = "notStarted"

            # Parse source locations into list of {file, lineStart, lineEnd}
            locations = []
            for loc in f.source_locations:
                file_name = loc.get("file") or loc.get("path") or ""
                line_start = loc.get("line_start") or loc.get("lineStart") or 1
                line_end = loc.get("line_end") or loc.get("lineEnd") or line_start
                locations.append({
                    "file": str(file_name),
                    "lineStart": int(line_start),
                    "lineEnd": int(line_end),
                })

            # The Attacker/Evaluator work from runtime evidence and therefore do
            # not know source positions. Where the Fixer produced a patch, the
            # diff hunk headers tell us exactly which lines were involved, so
            # derive the location from there rather than showing nothing.
            if not locations and patch:
                locations = _locations_from_patch(patch)

            cwe_str = f.cwe[0] if f.cwe else ""
            severity_str = f.cvss.severity.value.lower() if hasattr(f.cvss.severity, "value") else str(f.cvss.severity).lower()
            confidence_str = f.confidence.band.value.lower() if hasattr(f.confidence.band, "value") else str(f.confidence.band).lower()
            status_str = f.status.value.lower() if hasattr(f.status, "value") else str(f.status).lower()

            results.append({
                "id": f.id,
                "scanId": f.scan_id,
                "scan_id": f.scan_id,
                "title": f.title,
                "category": f.category,
                "cwe": cwe_str,
                "severity": severity_str,
                "confidence": confidence_str,
                "routeTemplate": f.route_template,
                "route_template": f.route_template,
                "method": f.method,
                "description": f.description,
                "impact": f.impact,
                "runtimeConfirmed": f.runtime_confirmed,
                "runtime_confirmed": f.runtime_confirmed,
                "status": status_str,
                "statusReason": f.status_reason or None,
                "status_reason": f.status_reason or None,
                "evidenceSummary": f.reproduction_summary or None,
                "evidence_summary": f.reproduction_summary or None,
                "reproductionSummary": f.reproduction_summary or None,
                "reproduction_summary": f.reproduction_summary or None,
                "sourceLocations": locations,
                "source_locations": locations,
                "remediationStatus": remediation_status,
                "remediation_status": remediation_status,
                "createdAt": f.created_at,
                "created_at": f.created_at,
            })

        return results
