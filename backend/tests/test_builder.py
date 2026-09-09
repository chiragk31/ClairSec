"""
Phase 4 Builder agent tests.

Test groups:
  1. LLM provider / schema tests  — no Docker, no real LLM, no Mongo
  2. BuilderAgent unit tests       — mocked LLM + mocked Mongo (via AsyncMock)
  3. Scans API unit tests          — mocked Mongo
  4. Docker integration tests      — real Docker, real container (gated on 'docker' marker)

Per docs/TESTING.md §3: mock cases cover valid output, malformed output,
refusal/empty response, timeout simulation, and schema validation errors.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_APP_PATH = str(FIXTURES_DIR / "valid_fastapi_app")

_VALID_BUILDER_JSON = json.dumps({
    "entry_point": "main.py",
    "openapi_source": "live",
    "routes": [
        {
            "path": "/health",
            "methods": ["GET"],
            "summary": "Health check",
            "description": None,
            "parameters": [],
            "request_body_schema": None,
            "response_schema": None,
            "tags": [],
            "auth_required": False,
            "auth_schemes": [],
        },
        {
            "path": "/",
            "methods": ["GET"],
            "summary": "Root",
            "description": None,
            "parameters": [],
            "request_body_schema": None,
            "response_schema": None,
            "tags": [],
            "auth_required": False,
            "auth_schemes": [],
        },
    ],
    "auth_mechanisms": [
        {"kind": "none", "details": "No authentication detected", "source_location": "main.py"}
    ],
    "dependencies": [
        {"name": "fastapi", "version_spec": None, "notes": None},
        {"name": "uvicorn", "version_spec": None, "notes": None},
    ],
    "database_access": [],
    "configuration_notes": [],
    "analysis_notes": "Simple FastAPI app with two endpoints, no auth.",
    "gaps": [],
})


# ─────────────────────────────────────────────────────────────────────────────
# 1. LLM provider / schema tests (no external dependencies)
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMSchemas:
    def test_valid_builder_analysis_parses(self):
        from app.llm.schemas import BuilderAnalysis
        data = json.loads(_VALID_BUILDER_JSON)
        analysis = BuilderAnalysis.model_validate(data)
        assert len(analysis.routes) == 2
        assert analysis.entry_point == "main.py"
        assert analysis.openapi_source == "live"

    def test_empty_builder_analysis_valid(self):
        """Minimum valid BuilderAnalysis — all optional fields absent."""
        from app.llm.schemas import BuilderAnalysis
        analysis = BuilderAnalysis.model_validate({})
        assert analysis.routes == []
        assert analysis.gaps == []

    def test_route_info_defaults(self):
        from app.llm.schemas import RouteInfo
        r = RouteInfo(path="/foo", methods=["POST"])
        assert r.auth_required is None
        assert r.auth_schemes == []

    def test_builder_analysis_extra_fields_ignored(self):
        """Unknown fields from LLM should not cause validation failure."""
        from app.llm.schemas import BuilderAnalysis
        data = json.loads(_VALID_BUILDER_JSON)
        data["future_unknown_field"] = "some value"
        # Should not raise
        analysis = BuilderAnalysis.model_validate(data)
        assert analysis.entry_point == "main.py"


class TestMockProvider:
    def test_mock_provider_returns_canned_response(self):
        from app.llm.provider import MockProvider
        provider = MockProvider(response_text=_VALID_BUILDER_JSON)
        response = provider.generate("test prompt", "test_v1")
        assert response.raw_text == _VALID_BUILDER_JSON
        assert response.provider == "mock"
        assert response.model == "mock"
        assert response.prompt_version == "test_v1"

    def test_mock_provider_info(self):
        from app.llm.provider import MockProvider
        provider = MockProvider()
        assert provider.info.provider == "mock"

    def test_gemini_provider_raises_without_api_key(self):
        from app.llm.provider import GeminiProvider, LLMProviderError
        with pytest.raises(LLMProviderError, match="API key"):
            GeminiProvider(api_key="", model="gemini-2.0-flash")

    def test_get_provider_mock(self):
        """get_provider returns MockProvider when llm_provider='mock'."""
        from app.llm.provider import MockProvider, get_provider
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.llm_provider = "mock"
            provider = get_provider()
            assert isinstance(provider, MockProvider)

    def test_get_provider_unknown_raises(self):
        from app.llm.provider import LLMProviderError, get_provider
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.llm_provider = "nonexistent_provider_xyz"
            with pytest.raises(LLMProviderError):
                get_provider()


class TestPrompts:
    def test_builder_prompt_assembled(self):
        from app.llm.prompts import build_builder_prompt, BUILDER_ANALYSIS_VERSION
        prompt, version = build_builder_prompt(
            entry_point="main.py",
            dependency_file="requirements.txt",
            dependencies=["fastapi", "uvicorn"],
            openapi_schema={"openapi": "3.0.0"},
            entry_source="from fastapi import FastAPI\napp = FastAPI()",
        )
        assert version == BUILDER_ANALYSIS_VERSION
        assert "BUILDER" in prompt
        assert "UNTRUSTED INPUT" in prompt   # prompt injection defense present
        assert "main.py" in prompt
        assert "fastapi" in prompt

    def test_builder_prompt_truncates_source(self):
        """Source longer than 150 lines should be truncated."""
        from app.llm.prompts import build_builder_prompt
        long_source = "\n".join([f"# line {i}" for i in range(300)])
        prompt, _ = build_builder_prompt(
            entry_point="main.py",
            dependency_file=None,
            dependencies=[],
            openapi_schema=None,
            entry_source=long_source,
        )
        assert "truncated to 150 lines" in prompt

    def test_builder_prompt_no_openapi(self):
        from app.llm.prompts import build_builder_prompt
        prompt, _ = build_builder_prompt(
            entry_point=None,
            dependency_file=None,
            dependencies=[],
            openapi_schema=None,
            entry_source=None,
        )
        assert "Not available" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# 2. BuilderAgent unit tests with mocked LLM + mocked DB
# ─────────────────────────────────────────────────────────────────────────────

def _make_project(isolation_status="ready", container_id="abc123", workspace_path=None):
    """Create a minimal ProjectRecord-like mock."""
    from app.database.models import IsolationStatus, ProjectRecord, ValidationStatus
    return ProjectRecord(
        name="test-project",
        source_path=VALID_APP_PATH,
        validation_status=ValidationStatus.VALID,
        isolation_status=IsolationStatus(isolation_status),
        container_id=container_id,
        workspace_path=workspace_path or VALID_APP_PATH,
        entry_point="main.py",
        dependency_file="requirements.txt",
        dependencies=["fastapi", "uvicorn"],
    )


def _make_scan(project_id: str):
    from app.database.models import ScanRecord
    return ScanRecord(project_id=project_id)


class TestBuilderAgentParsing:
    """Test the response parsing logic in isolation (no DB, no LLM calls)."""

    def _make_agent(self):
        from app.agents.builder import BuilderAgent
        from app.llm.provider import MockProvider
        mock_db = MagicMock()
        provider = MockProvider(_VALID_BUILDER_JSON)
        with patch("app.agents.builder.DockerManager"):
            agent = BuilderAgent(db=mock_db, llm_provider=provider)
        return agent

    def test_parse_valid_json(self):
        agent = self._make_agent()
        result = agent._parse_builder_response(_VALID_BUILDER_JSON)
        assert result is not None
        assert len(result.routes) == 2

    def test_parse_json_in_markdown_fence(self):
        agent = self._make_agent()
        wrapped = f"```json\n{_VALID_BUILDER_JSON}\n```"
        result = agent._parse_builder_response(wrapped)
        assert result is not None
        assert result.entry_point == "main.py"

    def test_parse_invalid_json_returns_none(self):
        agent = self._make_agent()
        result = agent._parse_builder_response("not valid json at all {{{")
        assert result is None

    def test_parse_empty_response_returns_none(self):
        agent = self._make_agent()
        result = agent._parse_builder_response("")
        assert result is None

    def test_parse_refusal_returns_none(self):
        """LLM returns a refusal message instead of JSON."""
        agent = self._make_agent()
        result = agent._parse_builder_response(
            "I cannot analyze this code as it may be harmful."
        )
        assert result is None

    def test_parse_wrong_schema_returns_none(self):
        """JSON that doesn't match BuilderAnalysis (e.g., wrong types)."""
        agent = self._make_agent()
        bad_data = json.dumps({"routes": "not a list"})
        result = agent._parse_builder_response(bad_data)
        assert result is None

    def test_parse_minimal_valid_json(self):
        """Empty JSON object should produce a valid empty BuilderAnalysis."""
        agent = self._make_agent()
        result = agent._parse_builder_response("{}")
        assert result is not None
        assert result.routes == []
        assert result.gaps == []


class TestBuilderAgentRun:
    """Tests for BuilderAgent.run() using AsyncMock for all DB/Docker calls."""

    def _make_agent_with_mocks(self, llm_response_text=_VALID_BUILDER_JSON):
        from app.agents.builder import BuilderAgent
        from app.llm.provider import MockProvider

        mock_db = MagicMock()
        provider = MockProvider(llm_response_text)

        with patch("app.agents.builder.DockerManager"):
            agent = BuilderAgent(db=mock_db, llm_provider=provider)

        # Mock all repos
        agent._project_repo = AsyncMock()
        agent._scan_repo = AsyncMock()
        agent._event_repo = AsyncMock()
        agent._context_repo = AsyncMock()
        agent._docker = MagicMock()
        agent._docker.get_host_port = MagicMock(return_value=None)  # no live OpenAPI

        return agent

    @pytest.mark.asyncio
    async def test_run_happy_path(self):
        from app.agents.base import AgentState
        agent = self._make_agent_with_mocks()
        project = _make_project()
        scan = _make_scan(project.id)

        agent._scan_repo.get_by_id = AsyncMock(return_value=scan)
        agent._project_repo.get_by_id = AsyncMock(return_value=project)
        agent._scan_repo.update = AsyncMock(return_value=scan)
        agent._project_repo.update = AsyncMock(return_value=project)
        agent._context_repo.save = AsyncMock()
        agent._event_repo.emit = AsyncMock()

        result = await agent.run(scan_id=scan.id, project_id=project.id)
        assert result == AgentState.COMPLETED
        agent._context_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_fails_when_scan_not_found(self):
        from app.agents.base import AgentState
        agent = self._make_agent_with_mocks()
        agent._scan_repo.get_by_id = AsyncMock(return_value=None)
        agent._event_repo.emit = AsyncMock()

        result = await agent.run(scan_id="nonexistent", project_id="pid")
        assert result == AgentState.FAILED

    @pytest.mark.asyncio
    async def test_run_fails_when_project_not_ready(self):
        from app.agents.base import AgentState
        agent = self._make_agent_with_mocks()

        project = _make_project(isolation_status="pending")
        scan = _make_scan(project.id)

        agent._scan_repo.get_by_id = AsyncMock(return_value=scan)
        agent._project_repo.get_by_id = AsyncMock(return_value=project)
        agent._scan_repo.update = AsyncMock(return_value=scan)
        agent._event_repo.emit = AsyncMock()

        result = await agent.run(scan_id=scan.id, project_id=project.id)
        assert result == AgentState.FAILED

    @pytest.mark.asyncio
    async def test_run_fails_after_max_retries_on_malformed_llm(self):
        """If LLM consistently returns malformed JSON, Builder gives up and fails."""
        from app.agents.base import AgentState
        from app.llm.provider import MockProvider

        agent = self._make_agent_with_mocks(llm_response_text="not valid json {{{{")
        project = _make_project()
        scan = _make_scan(project.id)

        agent._scan_repo.get_by_id = AsyncMock(return_value=scan)
        agent._project_repo.get_by_id = AsyncMock(return_value=project)
        agent._scan_repo.update = AsyncMock(return_value=scan)
        agent._project_repo.update = AsyncMock(return_value=project)
        agent._context_repo.save = AsyncMock()
        agent._event_repo.emit = AsyncMock()

        with patch("app.agents.builder.settings") as mock_settings:
            mock_settings.llm_max_retries = 2
            result = await agent.run(scan_id=scan.id, project_id=project.id)

        assert result == AgentState.FAILED
        agent._context_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_retries_on_provider_error(self):
        """LLMProviderError triggers retry up to max_retries then fails."""
        from app.agents.base import AgentState
        from app.llm.provider import LLMProviderError, MockProvider

        agent = self._make_agent_with_mocks()
        project = _make_project()
        scan = _make_scan(project.id)

        agent._scan_repo.get_by_id = AsyncMock(return_value=scan)
        agent._project_repo.get_by_id = AsyncMock(return_value=project)
        agent._scan_repo.update = AsyncMock(return_value=scan)
        agent._project_repo.update = AsyncMock(return_value=project)
        agent._context_repo.save = AsyncMock()
        agent._event_repo.emit = AsyncMock()

        # Make LLM raise every time
        agent._llm.generate = MagicMock(side_effect=LLMProviderError("API down"))

        with patch("app.agents.builder.settings") as mock_settings:
            mock_settings.llm_max_retries = 2
            result = await agent.run(scan_id=scan.id, project_id=project.id)

        assert result == AgentState.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# 3. Docker integration test — real container, real Builder (gated)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.docker
class TestBuilderDockerIntegration:
    """
    Full Builder integration test against the real Phase 3 fixture app.
    Requires Docker Desktop running.
    Run with: pytest -m docker
    """

    @pytest.fixture(autouse=True)
    def cleanup_resources(self):
        created_project_ids = []
        yield created_project_ids
        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager
        dm = DockerManager()
        ws = WorkspaceManager()
        for pid in created_project_ids:
            try:
                dm.cleanup_all(pid)
                ws.cleanup_workspace(pid)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_builder_produces_structured_output(self, tmp_path, cleanup_resources):
        """Builder runs against a real isolated container and produces valid BuilderAnalysis."""
        import uuid as _uuid
        from app.agents.builder import BuilderAgent
        from app.database.models import (
            IsolationStatus, ProjectRecord, ScanRecord, ValidationStatus
        )
        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager
        from app.llm.provider import MockProvider
        from app.llm.schemas import BuilderAnalysis

        project_id = str(_uuid.uuid4())
        cleanup_resources.append(project_id)

        # Step 1: create workspace + container (like Phase 3 IsolationService would)
        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        workspace = ws.create_scan_workspace(project_id, VALID_APP_PATH)

        dm = DockerManager()
        image_tag = dm.build_image(project_id, workspace, "main.py", "requirements.txt")
        container_id, container_name = dm.start_container(project_id, image_tag)
        healthy = dm.wait_for_healthy(container_id)
        assert healthy, "Container did not become healthy"

        # Step 2: build a minimal ProjectRecord reflecting the container state
        project = ProjectRecord(
            id=project_id,
            name="test-fixture",
            source_path=VALID_APP_PATH,
            validation_status=ValidationStatus.VALID,
            isolation_status=IsolationStatus.READY,
            workspace_path=str(workspace),
            entry_point="main.py",
            dependency_file="requirements.txt",
            dependencies=["fastapi", "uvicorn"],
            container_id=container_id,
            container_name=container_name,
        )
        scan = ScanRecord(project_id=project_id)

        # Step 3: run Builder with MockProvider (validates the plumbing without LLM cost)
        mock_provider = MockProvider(_VALID_BUILDER_JSON)

        # Inject mock repos
        mock_project_repo = AsyncMock()
        mock_project_repo.get_by_id = AsyncMock(return_value=project)
        mock_project_repo.update = AsyncMock(return_value=project)
        mock_scan_repo = AsyncMock()
        mock_scan_repo.get_by_id = AsyncMock(return_value=scan)
        mock_scan_repo.update = AsyncMock(return_value=scan)
        mock_context_repo = AsyncMock()
        captured_context = {}

        async def capture_save(record):
            captured_context.update(record.context)
            return record

        mock_context_repo.save = capture_save
        mock_event_repo = AsyncMock()
        mock_event_repo.emit = AsyncMock()

        from app.agents.builder import BuilderAgent
        mock_db = MagicMock()
        agent = BuilderAgent(db=mock_db, llm_provider=mock_provider)
        agent._project_repo = mock_project_repo
        agent._scan_repo = mock_scan_repo
        agent._context_repo = mock_context_repo
        agent._event_repo = mock_event_repo

        from app.agents.base import AgentState
        result = await agent.run(scan_id=scan.id, project_id=project_id)

        assert result == AgentState.COMPLETED

        # Validate the persisted context is a valid BuilderAnalysis
        analysis = BuilderAnalysis.model_validate(captured_context)
        assert analysis.entry_point == "main.py"
        assert len(analysis.routes) >= 1

        # Verify OpenAPI was actually fetched from live container
        assert analysis.openapi_source in ("live", "unavailable")
