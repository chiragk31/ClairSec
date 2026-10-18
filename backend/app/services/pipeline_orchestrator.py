"""
Pipeline orchestrator service for Autopilot (FEATURES.md F3, UI_SYSTEM.md §9).

Chains:
  Import -> Isolate (build + start container) -> Scan (Builder -> Attacker -> Evaluator -> Fixer -> Verifier) -> Report

Enforces:
  - Resuming from failed stage
  - Cancellation of in-flight jobs
  - Emitting F5 events at each stage transition
  - Honest reporting (Report stage notes arrival in V7 without faking)
"""
from __future__ import annotations

import asyncio

import anyio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.models import (
    IsolationStatus,
    JobStatus,
    PipelineRecord,
    PipelineStage,
    PipelineStageInfo,
    PipelineStatus,
    ProjectRecord,
)
from app.database.repositories import (
    JobRepository,
    PipelineRepository,
    ProjectRepository,
    ScanRepository,
)
from app.isolation.docker_manager import _diagnose_build_failure
from app.services.isolation_runner import execute_isolation_steps
from app.services.event_bus import event_bus
from app.services.git_import_service import GitImportService
from app.services.scan_service import ScanService
from app.services.task_registry import task_registry

logger = logging.getLogger(__name__)

_STAGE_LINES = {
    PipelineStage.IMPORT: "Cloning and reading repository structure",
    PipelineStage.ISOLATE: "Building sealed container sandbox for safe testing",
    PipelineStage.SCAN: "Autonomous security scan: Builder -> Attacker -> Evaluator -> Fixer -> Verifier",
    PipelineStage.REPORT: "Write an executive + technical report (HTML, Markdown, JSON, SARIF)",
}


class PipelineOrchestrator:
    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._pipeline_repo = PipelineRepository(db)
        self._project_repo = ProjectRepository(db)
        self._job_repo = JobRepository(db)
        self._scan_repo = ScanRepository(db)
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def create_pipeline(
        self,
        project_id: str | None = None,
        git_import_data: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> PipelineRecord:
        """Create and persist a new pipeline record."""
        if not project_id and not git_import_data:
            raise ValueError("Either project_id or git_import must be provided.")

        stages = {
            stage.value: PipelineStageInfo(
                status="pending",
                line=_STAGE_LINES[stage],
            )
            for stage in PipelineStage
        }

        # If project is already imported, import stage starts completed
        if project_id and not git_import_data:
            stages[PipelineStage.IMPORT.value].status = "completed"
            stages[PipelineStage.IMPORT.value].line = "Project already imported"

        pipeline = PipelineRecord(
            project_id=project_id,
            status=PipelineStatus.PENDING,
            current_stage=PipelineStage.ISOLATE if (project_id and not git_import_data) else PipelineStage.IMPORT,
            stages=stages,
        )

        created = await self._pipeline_repo.create(pipeline)
        return created

    async def start_pipeline(
        self,
        pipeline_id: str,
        git_import_data: dict[str, Any] | None = None,
    ) -> None:
        """Start pipeline execution as a background asyncio task."""
        task = asyncio.create_task(self._run_pipeline(pipeline_id, git_import_data))
        self._active_tasks[pipeline_id] = task
        task_registry.register(pipeline_id, task)

    async def get_pipeline(self, pipeline_id: str) -> PipelineRecord | None:
        return await self._pipeline_repo.get_by_id(pipeline_id)

    async def cancel_pipeline(self, pipeline_id: str) -> PipelineRecord | None:
        """Cancel an in-flight pipeline and its active sub-job."""
        pipeline = await self._pipeline_repo.get_by_id(pipeline_id)
        if not pipeline:
            return None

        pipeline.status = PipelineStatus.CANCELLED
        stage_key = pipeline.current_stage.value
        if stage_key in pipeline.stages and pipeline.stages[stage_key].status == "running":
            pipeline.stages[stage_key].status = "cancelled"

        await self._pipeline_repo.update(pipeline)

        # Cancel background task via task registry and local dict
        task_registry.request_cancellation(pipeline_id)
        task = self._active_tasks.get(pipeline_id)
        if task and not task.done():
            task.cancel()

        # Cancel any active scan
        if pipeline.scan_id:
            try:
                scan_svc = ScanService(self._db)
                await scan_svc.cancel_scan(pipeline.scan_id)
            except Exception as exc:
                logger.warning(
                    "Error cancelling scan %s for pipeline %s: %s",
                    pipeline.scan_id,
                    pipeline_id,
                    exc,
                )

        await event_bus.emit(
            scan_id=pipeline.scan_id or f"pipe-{pipeline_id}",
            agent="orchestrator",
            kind="error",
            title="Autopilot pipeline cancelled",
            refs={"pipeline_id": pipeline_id},
        )

        return pipeline

    async def resume_pipeline(self, pipeline_id: str) -> PipelineRecord | None:
        """Resume a failed pipeline from the failed stage."""
        pipeline = await self._pipeline_repo.get_by_id(pipeline_id)
        if not pipeline:
            return None

        # Reset failed stage
        for stage in [PipelineStage.IMPORT, PipelineStage.ISOLATE, PipelineStage.SCAN, PipelineStage.REPORT]:
            info = pipeline.stages.get(stage.value)
            if info and info.status in ("failed", "cancelled"):
                info.status = "pending"
                info.error = None
                info.fix_hint = None
                pipeline.current_stage = stage
                break

        pipeline.status = PipelineStatus.PENDING
        pipeline.error = None
        pipeline.fix_hint = None
        await self._pipeline_repo.update(pipeline)

        await self.start_pipeline(pipeline_id)
        return pipeline

    async def _run_pipeline(
        self,
        pipeline_id: str,
        git_import_data: dict[str, Any] | None = None,
    ) -> None:
        """Main pipeline state-machine runner."""
        pipeline = await self._pipeline_repo.get_by_id(pipeline_id)
        if not pipeline:
            return

        pipeline.status = PipelineStatus.RUNNING
        await self._pipeline_repo.update(pipeline)

        try:
            # ── 1. IMPORT STAGE ──────────────────────────────────────────────
            if pipeline.stages[PipelineStage.IMPORT.value].status != "completed":
                pipeline.current_stage = PipelineStage.IMPORT
                success = await self._execute_import_stage(pipeline, git_import_data)
                if not success:
                    return

            # ── 2. ISOLATE STAGE ─────────────────────────────────────────────
            if pipeline.stages[PipelineStage.ISOLATE.value].status != "completed":
                pipeline.current_stage = PipelineStage.ISOLATE
                success = await self._execute_isolate_stage(pipeline)
                if not success:
                    return

            # ── 3. SCAN STAGE ────────────────────────────────────────────────
            if pipeline.stages[PipelineStage.SCAN.value].status != "completed":
                pipeline.current_stage = PipelineStage.SCAN
                success = await self._execute_scan_stage(pipeline)
                if not success:
                    return

            # ── 4. REPORT STAGE ──────────────────────────────────────────────
            if pipeline.stages[PipelineStage.REPORT.value].status != "completed":
                pipeline.current_stage = PipelineStage.REPORT
                await self._execute_report_stage(pipeline)

            pipeline.status = PipelineStatus.COMPLETED
            await self._pipeline_repo.update(pipeline)

            await event_bus.emit(
                scan_id=pipeline.scan_id or f"pipe-{pipeline_id}",
                agent="orchestrator",
                kind="stage_finished",
                title="Autopilot pipeline completed successfully",
                refs={"pipeline_id": pipeline_id},
            )

        except asyncio.CancelledError:
            pipeline.status = PipelineStatus.CANCELLED
            await self._pipeline_repo.update(pipeline)
        except Exception as exc:
            logger.exception("Pipeline %s failed: %s", pipeline_id, exc)
            pipeline.status = PipelineStatus.FAILED
            pipeline.error = str(exc)
            await self._pipeline_repo.update(pipeline)

    async def _execute_import_stage(
        self,
        pipeline: PipelineRecord,
        git_import_data: dict[str, Any] | None,
    ) -> bool:
        """Run or resume the Git import stage."""
        stage_info = pipeline.stages[PipelineStage.IMPORT.value]
        stage_info.status = "running"
        stage_info.started_at = datetime.now(timezone.utc)
        start_t = time.time()
        await self._pipeline_repo.update(pipeline)

        await event_bus.emit(
            scan_id=f"pipe-{pipeline.id}",
            agent="orchestrator",
            kind="stage_started",
            title="Importing repository",
            refs={"pipeline_id": pipeline.id},
        )

        try:
            if not git_import_data:
                raise ValueError("No git import configuration supplied.")

            git_service = GitImportService(self._db)
            job, project = await git_service.start_import(
                url=git_import_data["url"],
                ref=git_import_data.get("ref"),
                subdir=git_import_data.get("subdir"),
                name=git_import_data.get("name"),
                authorization_affirmed=git_import_data.get("authorization_affirmed", False),
            )
            pipeline.import_job_id = job.id
            pipeline.project_id = project.id
            await self._pipeline_repo.update(pipeline)

            # Wait for import completion
            while True:
                j = await self._job_repo.get_by_id(job.id)
                if not j or j.status == JobStatus.FAILED:
                    raise ValueError(j.error if j else "Import job failed")
                if j.status == JobStatus.COMPLETED:
                    break
                if j.status == JobStatus.CANCELLED:
                    stage_info.status = "cancelled"
                    pipeline.status = PipelineStatus.CANCELLED
                    await self._pipeline_repo.update(pipeline)
                    return False
                await asyncio.sleep(0.5)

            stage_info.status = "completed"
            stage_info.finished_at = datetime.now(timezone.utc)
            stage_info.elapsed_s = round(time.time() - start_t, 1)
            await self._pipeline_repo.update(pipeline)
            return True

        except Exception as exc:
            stage_info.status = "failed"
            stage_info.error = str(exc)
            stage_info.finished_at = datetime.now(timezone.utc)
            stage_info.elapsed_s = round(time.time() - start_t, 1)
            pipeline.status = PipelineStatus.FAILED
            pipeline.error = str(exc)
            await self._pipeline_repo.update(pipeline)
            return False

    async def _execute_isolate_stage(self, pipeline: PipelineRecord) -> bool:
        """Run or resume the container isolation stage."""
        stage_info = pipeline.stages[PipelineStage.ISOLATE.value]
        stage_info.status = "running"
        stage_info.started_at = datetime.now(timezone.utc)
        start_t = time.time()
        await self._pipeline_repo.update(pipeline)

        await event_bus.emit(
            scan_id=f"pipe-{pipeline.id}",
            agent="orchestrator",
            kind="stage_started",
            title="Building and starting isolated container",
            refs={"pipeline_id": pipeline.id, "project_id": pipeline.project_id},
        )

        try:
            project = await self._project_repo.get_by_id(pipeline.project_id or "")
            if not project:
                raise ValueError(f"Project '{pipeline.project_id}' not found.")

            # The demo apps are ClairSec's own code: the scan runs them on the trusted
            # fixture runner, so no container is built for them (FEATURES.md F4).
            if getattr(project, "origin", "user_project") == "demo_fixture":
                stage_info.line = (
                    "Demo app: runs on ClairSec's built-in test runner, so no container is needed."
                )
                stage_info.status = "completed"
                stage_info.finished_at = datetime.now(timezone.utc)
                stage_info.elapsed_s = round(time.time() - start_t, 1)
                await self._pipeline_repo.update(pipeline)
                return True

            # If project is already isolated and container is ready, skip build
            if project.isolation_status == IsolationStatus.READY and project.proxy_port:
                stage_info.status = "completed"
                stage_info.finished_at = datetime.now(timezone.utc)
                stage_info.elapsed_s = round(time.time() - start_t, 1)
                await self._pipeline_repo.update(pipeline)
                return True

            # Run threaded isolation steps
            from app.isolation.docker_manager import DockerManager
            from app.isolation.workspace import WorkspaceManager

            try:
                docker_mgr = await anyio.to_thread.run_sync(DockerManager)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    "Docker is not running, so this project cannot be isolated. "
                    "Start Docker Desktop, or try the Demo app instead."
                ) from exc
            await execute_isolation_steps(
                project.id,
                self._project_repo,
                docker_mgr,
                WorkspaceManager(),
                scan_id=pipeline.scan_id,
            )

            # Re-fetch project to check isolation outcome
            updated_proj = await self._project_repo.get_by_id(project.id)
            if not updated_proj or updated_proj.isolation_status != IsolationStatus.READY:
                err_msg = updated_proj.isolation_error if updated_proj else "Isolation failed"
                hint = _diagnose_build_failure([err_msg or ""])
                pipeline.fix_hint = hint
                stage_info.fix_hint = hint
                raise ValueError(f"{err_msg}. Hint: {hint}" if hint else err_msg)

            stage_info.status = "completed"
            stage_info.finished_at = datetime.now(timezone.utc)
            stage_info.elapsed_s = round(time.time() - start_t, 1)
            await self._pipeline_repo.update(pipeline)
            return True

        except Exception as exc:
            stage_info.status = "failed"
            stage_info.error = str(exc)
            stage_info.fix_hint = stage_info.fix_hint or _diagnose_build_failure([str(exc)])
            stage_info.finished_at = datetime.now(timezone.utc)
            stage_info.elapsed_s = round(time.time() - start_t, 1)
            pipeline.status = PipelineStatus.FAILED
            pipeline.error = str(exc)
            pipeline.fix_hint = stage_info.fix_hint
            await self._pipeline_repo.update(pipeline)
            return False

    async def _execute_scan_stage(self, pipeline: PipelineRecord) -> bool:
        """Run or resume the autonomous security scan stage."""
        stage_info = pipeline.stages[PipelineStage.SCAN.value]
        stage_info.status = "running"
        stage_info.started_at = datetime.now(timezone.utc)
        start_t = time.time()
        await self._pipeline_repo.update(pipeline)

        await event_bus.emit(
            scan_id=f"pipe-{pipeline.id}",
            agent="orchestrator",
            kind="stage_started",
            title="Starting autonomous security scan",
            refs={"pipeline_id": pipeline.id, "project_id": pipeline.project_id},
        )

        try:
            scan_service = ScanService(self._db)
            scan = await scan_service.submit_scan(pipeline.project_id or "")
            pipeline.scan_id = scan.id
            await self._pipeline_repo.update(pipeline)

            # Poll scan state until finished
            while True:
                s = await self._scan_repo.get_by_id(scan.id)
                if not s:
                    raise ValueError("Scan record lost during scan execution.")
                if s.state in ("completed", "finished"):
                    break
                if s.state in ("failed", "error", "interrupted"):
                    raise ValueError(f"Scan failed at stage '{s.stage}': {s.error or 'no error recorded'}")
                if s.state == "cancelled":
                    stage_info.status = "cancelled"
                    pipeline.status = PipelineStatus.CANCELLED
                    await self._pipeline_repo.update(pipeline)
                    return False
                await asyncio.sleep(0.5)

            stage_info.status = "completed"
            stage_info.finished_at = datetime.now(timezone.utc)
            stage_info.elapsed_s = round(time.time() - start_t, 1)
            await self._pipeline_repo.update(pipeline)
            return True

        except Exception as exc:
            stage_info.status = "failed"
            stage_info.error = str(exc)
            stage_info.finished_at = datetime.now(timezone.utc)
            stage_info.elapsed_s = round(time.time() - start_t, 1)
            pipeline.status = PipelineStatus.FAILED
            pipeline.error = str(exc)
            await self._pipeline_repo.update(pipeline)
            return False

    async def _execute_report_stage(self, pipeline: PipelineRecord) -> None:
        """Generate the real report for the pipeline's scan (FEATURES.md F12)."""
        from app.database.client import get_database
        from app.reporting.service import generate_report

        stage_info = pipeline.stages[PipelineStage.REPORT.value]
        stage_info.status = "running"
        stage_info.started_at = datetime.now(timezone.utc)
        start_t = time.time()
        await self._pipeline_repo.update(pipeline)

        db = self._db if self._db is not None else get_database()
        record = await generate_report(db, pipeline.scan_id)
        stage_info.line = (
            f"Report ready: {record['confirmed_count']} confirmed finding(s); "
            f"HTML, Markdown, JSON and SARIF saved."
        )
        stage_info.status = "completed"
        stage_info.finished_at = datetime.now(timezone.utc)
        stage_info.elapsed_s = round(time.time() - start_t, 1)
        pipeline.report_id = record["id"]
        await self._pipeline_repo.update(pipeline)
