"""
Builder agent — Phase 4.

Per docs/PRD.md §7:
  - Inspect project structure and identify FastAPI entry points.
  - Identify routes and HTTP methods.
  - Parse OpenAPI information — prefer live endpoint, fall back to static analysis.
  - Identify authentication and authorization mechanisms.
  - Identify models, dependencies, configuration, and database access.
  - Produce structured target context.

The Builder does NOT decide that a vulnerability is confirmed.
It produces context only — no security findings or judgments.

SECURITY:
  - Project source is treated as untrusted input to the LLM (prompt injection defense
    enforced by the system preamble in prompts.py).
  - Source excerpts are truncated before being sent to the LLM provider.
  - LLM output is validated against BuilderAnalysis Pydantic schema.
  - Malformed LLM responses trigger bounded retries (settings.llm_max_retries).
  - The OpenAPI fetch is from the running container via the mapped host port —
    this is controlled traffic from our backend to our own container, not from
    the target to the LLM.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.agents.base import AgentRole, AgentState, BaseAgent
from app.core.config import settings
from app.database.models import (
    AgentContextRecord,
    AgentEvent,
    ScanRecord,
    ScanStatus,
)
from app.database.scan_repositories import (
    AgentContextRepository,
    AgentEventRepository,
    ScanRepository,
)
from app.database.repositories import ProjectRepository
from app.isolation.docker_manager import DockerManager
from app.llm.prompts import build_builder_prompt
from app.llm.provider import BaseLLMProvider, LLMProviderError
from app.llm.schemas import BuilderAnalysis

logger = logging.getLogger(__name__)


class BuilderAgent(BaseAgent):
    """
    Builder agent: analyzes an isolated, running FastAPI target and produces
    a structured BuilderAnalysis persisted to MongoDB.
    """

    def __init__(
        self,
        db,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self._project_repo = ProjectRepository(db)
        self._scan_repo = ScanRepository(db)
        self._event_repo = AgentEventRepository(db)
        self._context_repo = AgentContextRepository(db)
        self._docker = DockerManager()
        self._llm = llm_provider

    @property
    def role(self) -> AgentRole:
        return AgentRole.BUILDER

    # ─────────────────────────────────────────────────────────────────────────
    # Public entrypoint
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self, scan_id: str, project_id: str, **kwargs) -> AgentState:
        """
        Execute the Builder analysis for this scan.

        Prerequisites: project must be in IsolationStatus.READY or RUNNING
        (container is up and health-checked).

        Returns AgentState.COMPLETED on success, AgentState.FAILED on error.
        """
        await self._emit(scan_id, "agent.status", status="running",
                         message="Builder starting analysis")

        scan = await self._scan_repo.get_by_id(scan_id)
        if scan is None:
            logger.error("Builder: scan %s not found", scan_id)
            return AgentState.FAILED

        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            await self._fail(scan, "Project not found")
            return AgentState.FAILED

        from app.database.models import IsolationStatus
        if project.isolation_status not in (
            IsolationStatus.READY, IsolationStatus.RUNNING
        ):
            await self._fail(
                scan,
                f"Project is not isolated (status={project.isolation_status}). "
                "Run POST /api/projects/{id}/isolate first."
            )
            return AgentState.FAILED

        # ── Update scan to ANALYZING ──────────────────────────────────────
        scan.status = ScanStatus.ANALYZING
        await self._scan_repo.update(scan)
        await self._emit(scan_id, "agent.progress", status="analyzing",
                         message="Fetching OpenAPI schema from live container")

        # ── Step 1: Fetch OpenAPI from live container ─────────────────────
        openapi_schema, openapi_source = await self._fetch_openapi(project)

        # ── Step 2: Read entry point source (truncated, untrusted) ────────
        entry_source = self._read_entry_source(project)

        await self._emit(scan_id, "agent.progress", status="analyzing",
                         message="Sending project inventory to LLM for analysis")

        # ── Step 3: Assemble prompt and call LLM with retries ─────────────
        prompt, prompt_version = build_builder_prompt(
            entry_point=project.entry_point,
            dependency_file=project.dependency_file,
            dependencies=project.dependencies,
            openapi_schema=openapi_schema,
            entry_source=entry_source,
        )

        analysis = await self._call_llm_with_retries(
            scan_id=scan_id,
            prompt=prompt,
            prompt_version=prompt_version,
            openapi_source=openapi_source,
        )

        if analysis is None:
            await self._fail(scan, "LLM analysis failed after maximum retries")
            return AgentState.FAILED

        # Ensure openapi_source from actual fetch is reflected in analysis
        analysis = analysis.model_copy(update={"openapi_source": openapi_source})

        # ── Step 4: Persist to agent_context ──────────────────────────────
        context_record = AgentContextRecord(
            scan_id=scan_id,
            project_id=project_id,
            agent=AgentRole.BUILDER.value,
            llm_provider=self._llm.info.provider,
            llm_model=self._llm.info.model,
            prompt_version=prompt_version,
            context=analysis.model_dump(),
        )
        await self._context_repo.save(context_record)

        # ── Step 5: Update scan and project status ────────────────────────
        scan.status = ScanStatus.TARGET_READY
        scan.llm_provider = self._llm.info.provider
        scan.llm_model = self._llm.info.model
        scan.prompt_version = prompt_version
        await self._scan_repo.update(scan)

        # Mark project as RUNNING now that a scan is actively using it
        from app.database.models import IsolationStatus
        project.isolation_status = IsolationStatus.RUNNING
        await self._project_repo.update(project)

        route_count = len(analysis.routes)
        gap_count = len(analysis.gaps)
        await self._emit(
            scan_id, "agent.result", status="completed",
            message=f"Builder completed: {route_count} routes, {gap_count} gaps",
            data={"route_count": route_count, "gap_count": gap_count,
                  "openapi_source": openapi_source},
        )
        logger.info(
            "Builder completed for scan %s: %d routes, openapi_source=%s",
            scan_id, route_count, openapi_source
        )
        return AgentState.COMPLETED

    # ─────────────────────────────────────────────────────────────────────────
    # OpenAPI fetch from live container
    # ─────────────────────────────────────────────────────────────────────────

    async def _fetch_openapi(
        self, project
    ) -> tuple[dict | None, str]:
        """
        Try to fetch /openapi.json from the running container.

        Returns (schema_dict, source_string):
          - source = 'live' if fetched successfully
          - source = 'static_fallback' or 'unavailable' if not
        """
        if not project.container_id:
            logger.debug("Builder: no container_id on project, skipping OpenAPI fetch")
            return None, "unavailable"

        host_port = self._docker.get_host_port(project.container_id)
        if host_port is None:
            logger.warning("Builder: could not determine container port")
            return None, "unavailable"

        url = f"http://127.0.0.1:{host_port}/openapi.json"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    schema = response.json()
                    logger.info("Builder: fetched OpenAPI schema from %s", url)
                    return schema, "live"
                else:
                    logger.info(
                        "Builder: %s returned HTTP %d — no OpenAPI available",
                        url, response.status_code
                    )
                    return None, "unavailable"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Builder: failed to fetch OpenAPI from %s: %s", url, exc)
            return None, "unavailable"

    # ─────────────────────────────────────────────────────────────────────────
    # Entry point source reader
    # ─────────────────────────────────────────────────────────────────────────

    def _read_entry_source(self, project) -> str | None:
        """
        Read the entry point source from the scan workspace (not the original).
        Truncation to 150 lines is done in the prompt template.

        SECURITY: reads from workspace_path (our copy), never source_path (original).
        Treats content as untrusted — returned as a string for prompt assembly.
        """
        if not project.workspace_path or not project.entry_point:
            return None
        try:
            workspace = Path(project.workspace_path)
            entry_file = workspace / project.entry_point
            if entry_file.exists() and entry_file.stat().st_size < 500_000:
                return entry_file.read_text(encoding="utf-8", errors="replace")
            return None
        except OSError as exc:
            logger.debug("Builder: could not read entry source: %s", exc)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # LLM call with bounded retries
    # ─────────────────────────────────────────────────────────────────────────

    async def _call_llm_with_retries(
        self,
        *,
        scan_id: str,
        prompt: str,
        prompt_version: str,
        openapi_source: str,
    ) -> BuilderAnalysis | None:
        """
        Call the LLM and validate the response against BuilderAnalysis.
        Retries on malformed output up to settings.llm_max_retries times.
        Returns None if all attempts fail.
        """
        max_retries = settings.llm_max_retries

        for attempt in range(1, max_retries + 1):
            try:
                response = self._llm.generate(prompt, prompt_version)
                analysis = self._parse_builder_response(response.raw_text)
                if analysis is not None:
                    return analysis
                # Malformed response — retry
                logger.warning(
                    "Builder: attempt %d/%d — malformed LLM response, retrying",
                    attempt, max_retries
                )
                await self._emit(
                    scan_id, "agent.progress", status="retrying",
                    message=f"Malformed LLM response (attempt {attempt}/{max_retries}), retrying"
                )

            except LLMProviderError as exc:
                logger.error(
                    "Builder: attempt %d/%d — LLM provider error: %s",
                    attempt, max_retries, exc
                )
                await self._emit(
                    scan_id, "agent.error",
                    message=f"LLM provider error (attempt {attempt}/{max_retries}): {str(exc)[:200]}"
                )
                if attempt >= max_retries:
                    return None

        return None

    def _parse_builder_response(self, raw_text: str) -> BuilderAnalysis | None:
        """
        Parse and validate the LLM's raw text response as BuilderAnalysis.

        Handles:
          - Valid JSON: parsed and validated against schema.
          - Markdown code fences: stripped before parsing.
          - Invalid JSON / schema mismatch: returns None (triggers retry).

        Returns None on any parse failure — never raises.
        """
        # Strip markdown code fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            inner = lines[1:] if lines[0].startswith("```") else lines
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            text = "\n".join(inner).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.debug("Builder: JSON parse error: %s", exc)
            return None

        try:
            return BuilderAnalysis.model_validate(data)
        except ValidationError as exc:
            logger.debug("Builder: schema validation error: %s", exc)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _emit(
        self,
        scan_id: str,
        event_type: str,
        *,
        status: str | None = None,
        message: str | None = None,
        data: dict | None = None,
    ) -> None:
        """Persist a structured agent event to agent_events collection."""
        event = AgentEvent(
            scan_id=scan_id,
            agent=AgentRole.BUILDER.value,
            event_type=event_type,
            status=status,
            message=message,
            data=data or {},
        )
        try:
            await self._event_repo.emit(event)
        except Exception as exc:  # noqa: BLE001
            logger.error("Builder: failed to emit event: %s", exc)

    async def _fail(self, scan: ScanRecord, reason: str) -> None:
        """Mark the scan as FAILED and emit an error event."""
        reason_truncated = reason[:500]
        scan.status = ScanStatus.FAILED
        scan.error = reason_truncated
        await self._scan_repo.update(scan)
        await self._emit(
            scan.id, "agent.error",
            status="failed",
            message=reason_truncated,
        )
        logger.error("Builder failed for scan %s: %s", scan.id, reason_truncated)
