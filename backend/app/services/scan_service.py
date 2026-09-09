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
import re
from pathlib import Path
from typing import Any
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase

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
from app.core.validators import validate_project_id
from app.database.models import IsolationStatus, ProjectRecord, ScanRecord
from app.database.repositories import ProjectRepository, ScanRepository
from app.isolation.docker_manager import DockerManager
from app.isolation.workspace import WorkspaceManager
from app.targets.handle import (
    ContainerTargetHandle,
    LocalFixtureTargetHandle,
    LocalWorkspaceTargetHandle,
    TargetHandle,
)

logger = logging.getLogger(__name__)

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
    def _docker(self) -> DockerManager:
        if self._docker_instance is None:
            self._docker_instance = DockerManager()
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

        # Create scan record in queued state
        scan = ScanRecord(
            project_id=project_id,
            project_name=project.name,
            state="running",
            stage="queued",
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
        )
        scan = await self._scan_repo.create(scan)

        # Spawn background task
        task = asyncio.create_task(
            self._run_scan_pipeline(scan.id, project_id)
        )
        self._active_tasks[scan.id] = task
        return scan

    async def _run_scan_pipeline(self, scan_id: str, project_id: str) -> None:
        """
        Execute the full autonomous scan pipeline:
        Builder -> Attacker -> Evaluator -> Fixer -> Verifier.
        """
        scan = await self._scan_repo.get_by_id(scan_id)
        project = await self.get_project(project_id)
        if not scan or not project:
            return

        target_handle: TargetHandle | None = None
        own_handle = False

        try:
            logger.info("Starting scan %s for project %s (%s)", scan_id[:8], project_id[:8], project.name)

            # ── 1. Acquire Target Handle ──────────────────────────────────────
            if project.container_id and project.proxy_port:
                target_handle = ContainerTargetHandle(
                    proxy_port=project.proxy_port,
                    container_id=project.container_id,
                    docker_manager=self._docker,
                )
            else:
                source_p = Path(project.source_path).resolve()
                if "tests" in source_p.parts and "fixtures" in source_p.parts:
                    target_handle = LocalFixtureTargetHandle(fixture_dir=source_p)
                elif project.workspace_path and Path(project.workspace_path).exists():
                    target_handle = LocalWorkspaceTargetHandle(workspace_dir=project.workspace_path)
                else:
                    scan_ws = self._workspace.get_scan_workspace_path(project.id)
                    if not scan_ws.exists():
                        scan_ws = self._workspace.create_scan_workspace(project.id, project.source_path)
                    target_handle = LocalWorkspaceTargetHandle(workspace_dir=scan_ws)

                await target_handle.start()
                own_handle = True

            # ── 2. Stage: Builder ─────────────────────────────────────────────
            scan.state = "running"
            scan.stage = "builder"
            await self._scan_repo.update(scan)

            builder = BuilderAgent()
            project_dir = Path(project.workspace_path) if (project.workspace_path and Path(project.workspace_path).exists()) else Path(project.source_path)
            context = await builder.build_context(
                project_id=project.id,
                scan_id=scan.id,
                project_dir=project_dir,
                target_handle=target_handle,
            )

            # ── 3. Stage: Attacker ────────────────────────────────────────────
            scan.stage = "attacker"
            await self._scan_repo.update(scan)

            test_case_repo = TestCaseRepository(self._db)
            attacker = AttackerAgent(test_case_repo=test_case_repo)
            attacker_res = await attacker.run_scan(
                context=context,
                target_handle=target_handle,
            )

            # ── 4. Stage: Evaluator ───────────────────────────────────────────
            scan.stage = "evaluator"
            await self._scan_repo.update(scan)

            evaluator = EvaluatorAgent(
                test_case_repo=test_case_repo,
                finding_repo=self._finding_repo,
            )
            eval_res = await evaluator.evaluate_scan(
                candidates=attacker_res.findings,
                target_handle=target_handle,
                scan_id=scan.id,
            )

            # ── 5. Stage: Fixer ───────────────────────────────────────────────
            scan.stage = "fixer"
            await self._scan_repo.update(scan)

            # Ensure scan_workspace exists before creating modified_workspace
            scan_ws = self._workspace.get_scan_workspace_path(project.id)
            if not scan_ws.exists():
                self._workspace.create_scan_workspace(project.id, project.source_path)

            mod_ws = self._workspace.create_modified_workspace(project.id)
            fixer = FixerAgent(
                patch_repo=self._patch_repo,
                workspace_manager=self._workspace,
            )
            fix_res = await fixer.fix_scan(
                findings=eval_res.findings,
                context=context,
                project_id=project.id,
                scan_id=scan.id,
                modified_workspace_root=mod_ws,
            )

            # ── 6. Stage: Verifier ────────────────────────────────────────────
            scan.stage = "verifier"
            await self._scan_repo.update(scan)

            verifier = VerifierAgent(
                verification_repo=self._verification_repo,
                test_case_repo=test_case_repo,
                workspace_manager=self._workspace,
            )
            ver_summary = await verifier.verify_scan(
                findings=eval_res.findings,
                patches=fix_res.patches,
                scan_id=scan.id,
                modified_workspace=mod_ws,
            )

            # ── 7. Complete Scan Record ───────────────────────────────────────
            scan.state = "completed"
            scan.stage = "completed"
            scan.ended_at = datetime.now(timezone.utc)
            scan.findings_confirmed = eval_res.confirmed_count
            scan.counters = {
                "tests_executed": len(attacker_res.findings),
                "candidates": len(attacker_res.findings),
                "confirmed": eval_res.confirmed_count,
                "rejected": eval_res.rejected_count,
                "inconclusive": eval_res.inconclusive_count,
                "fixes_proposed": len(fix_res.patches),
                "fixes_applied": fix_res.applied_count,
                "fixes_verified": ver_summary.fixed_count,
            }
            await self._scan_repo.update(scan)
            logger.info(
                "Scan %s completed successfully: %d confirmed, %d fixes verified",
                scan_id[:8],
                eval_res.confirmed_count,
                ver_summary.fixed_count,
            )

        except Exception as exc:
            logger.exception("Scan %s pipeline failed: %s", scan_id[:8], exc)
            scan.state = "failed"
            scan.stage = "failed"
            scan.error = str(exc)
            scan.ended_at = datetime.now(timezone.utc)
            await self._scan_repo.update(scan)

        finally:
            if own_handle and target_handle:
                try:
                    await target_handle.stop()
                except Exception as stop_exc:
                    logger.warning("Error stopping target handle for scan %s: %s", scan_id[:8], stop_exc)
            self._active_tasks.pop(scan_id, None)

    async def get_scan_patches_formatted(self, scan_id: str) -> list[dict[str, Any]]:
        """
        Return patches for a scan in the shape the Patch model in
        desktop/lib/models/patch.dart expects (Fix Review screen, DESIGN.md §8).
        """
        patches = await self._patch_repo.list_by_scan(scan_id)
        findings = await self._finding_repo.list_by_scan(scan_id)
        finding_by_id = {f.id: f for f in findings}

        results: list[dict[str, Any]] = []
        for p in patches:
            finding = finding_by_id.get(p.finding_id)
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
