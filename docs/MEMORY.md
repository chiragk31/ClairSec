# Project Memory

> This file is a living state document for AI coding agents.
> Update it after meaningful implementation progress.
> Do not turn it into a dump of every source file or every conversation.

## Current status

- Project stage: Builder agent
- Current phase: Phase 4
- Overall status: Phase 4 implemented and verified

## Product

Working name: Adversarial FastAPI Security Platform

Core workflow:

```text
Import FastAPI project
→ isolate
→ Builder
→ Attacker
→ Evaluator
→ Fixer
→ verify
→ report
```

## Technology decisions

### Desktop

- Flutter
- Dart
- Riverpod
- REST + WebSocket

### Backend

- Python
- FastAPI
- Pydantic
- asyncio

### Data

- MongoDB
- Local scan workspace/filesystem

### Isolation

- Docker

### AI

- Provider-agnostic LLM abstraction

## Current architecture decisions

- Flutter is presentation/client layer.
- Python owns orchestration, agents, security testing, Docker, and patching.
- MongoDB stores structured shared scan context.
- Imported source is treated as immutable input.
- Fixes are applied to a controlled workspace.
- Every fix should be re-tested.
- LLM output is never trusted blindly.

## Implemented features

- Scaffolded Flutter desktop app with placeholder directories (`desktop/lib/features/`, `core/`, `models/`, `providers/`, `services/`).
- Scaffolded Python FastAPI backend with placeholder directories and standard structure.
- Implemented backend health check endpoint (`/api/health`) and basic environment configuration using `pydantic-settings`.
- Added basic test runner commands (`pytest` for backend and `flutter test` for desktop).
- [Phase 1] Installed `flutter_riverpod 3.4.3`, `go_router 18.0.1`, `google_fonts 8.2.1`.
- [Phase 1] Implemented dark desktop theme (`core/theme/app_theme.dart`) with high-contrast palette, restrained accent, and semantic severity colours (Critical/High/Medium/Low/Informational/Success/Warning/Error), each paired with icon+label per DESIGN.md.
- [Phase 1] Monospace font (`JetBrainsMono`) declared via `AppTheme.monoStyle()` for future code/log display.
- [Phase 1] Implemented `AppShell` persistent left navigation rail with 8 destinations (Dashboard, Projects, Scans, Vulnerabilities, Agents, Reports, Research, Settings), hover/active states, and a backend connectivity indicator.
- [Phase 1] Implemented `go_router` router via Riverpod `routerProvider` with `ShellRoute` and `NoTransitionPage` for all 8 routes.
- [Phase 1] Built all 8 feature screens: Dashboard (stat cards + recent scans + high-priority findings sections, all honest empty states), Projects, Scans (pipeline legend), Vulnerabilities (severity legend), Agents (role cards for all 4 agents), Reports, Research, Settings (grouped read-only settings).
- [Phase 1] Shared widgets: `PageHeader`, `StatCard`, `EmptyState` in `features/shared/`.
- [Phase 1] Updated `main.dart` to use `ProviderScope` + `MaterialApp.router`.
- [Phase 2] Added `motor` for async MongoDB connection, `tomli` for Python <3.11 TOML parsing.
- [Phase 2] Implemented pure-static file inspection `fastapi_validator.py` (uses AST parsing, no code execution) to detect FastAPI entry points and parse dependency manifests.
- [Phase 2] Added `ProjectRecord` Pydantic model and `ProjectRepository` for MongoDB persistence.
- [Phase 2] Implemented `/api/projects` endpoints (POST, GET list, GET single).
- [Phase 2] Added Flutter dependencies: `dio`, `file_picker`.
- [Phase 2] Rewrote Flutter `ProjectsScreen` to use native folder picker and call backend import API. Displays detailed project cards (entry point, dependencies, isolation-ready badge) or honest error list.
- [Phase 2] Wired the shell's backend connectivity indicator to the actual `/api/health` endpoint via Riverpod.
- [Phase 3] Extended `ProjectRecord` with `IsolationStatus` enum (`pending/building/ready/running/stopped/import_failed`), `workspace_path`, `container_id`, `container_name`, `isolation_error` fields.
- [Phase 3] Added `update()` to `ProjectRepository` for in-place status transitions.
- [Phase 3] Implemented `WorkspaceManager` (`isolation/workspace.py`): copy-on-import into `{workspace_root}/{project_id}/scan_workspace/`, no symlink following, safe cleanup. The `modified_workspace/` convention is established but not yet populated (Phase 7).
- [Phase 3] Implemented `DockerManager` (`isolation/docker_manager.py`): generates a Dockerfile, builds image (120s timeout), starts container (no host env vars, isolated bridge network, 256m/0.5cpu limits), health-checks by polling `GET /health` then `GET /` until `status<400` (30s timeout), captures size-limited logs (100KB cap), stops/removes containers, removes images, `cleanup_all()` safe on every failure path.
- [Phase 3] Implemented `IsolationService` (`services/isolation_service.py`): orchestrates the full lifecycle; on any failure calls cleanup and marks `import_failed` with a truncated (2KB) reason string in `isolation_error`; no automatic retry (1 attempt by design).
- [Phase 3] Added isolation REST API (`api/isolation.py`): `POST /isolate`, `POST /stop`, `POST /cleanup`, `GET /status`, `GET /logs`.
- [Phase 3] Added Docker integration test fixture (`broken_fastapi_app/`) with an invalid pip package to trigger build failure → `import_failed`.
- [Phase 3] Added `pytest.ini` with `docker` marker so Docker integration tests can be skipped in CI.
- [Phase 3] 32 tests pass (26 unit + 6 Docker integration).
- [Phase 4] Added `BaseLLMProvider` abstract interface (`llm/provider.py`) with `generate(prompt, prompt_version) -> LLMResponse`. Concrete impls: `GeminiProvider` (google-generativeai SDK), `MockProvider` (test-only, no network). Factory: `get_provider()` reads `settings.llm_provider`.
- [Phase 4] Added LLM config to `core/config.py`: `llm_provider`, `llm_model`, `gemini_api_key`, `openai_api_key`, `anthropic_api_key`, `llm_max_retries=3`, `llm_request_timeout=60`.
- [Phase 4] Added versioned prompt templates (`llm/prompts.py`): `BUILDER_ANALYSIS_VERSION='builder_v1.0'`. System preamble enforces prompt injection defense (target content cannot override Builder role). Source truncated to 150 lines before sending to LLM.
- [Phase 4] Added Pydantic output schemas (`llm/schemas.py`): `BuilderAnalysis`, `RouteInfo`, `AuthMechanism`, `DependencyInfo`, `DatabaseAccessInfo`. `BuilderAnalysis` has explicit `gaps` field for honest representation of analysis limits.
- [Phase 4] Added `AgentState` enum and `BaseAgent` abstract class (`agents/base.py`) covering the full pipeline state machine (CREATED→COMPLETED + FAILED/CANCELLED/PARTIAL).
- [Phase 4] Added Phase 4 MongoDB models: `ScanRecord`, `AgentEvent`, `AgentContextRecord` (`database/models.py`).
- [Phase 4] Added `ScanRepository`, `AgentEventRepository` (10KB payload cap), `AgentContextRepository` (`database/scan_repositories.py`).
- [Phase 4] Implemented `BuilderAgent` (`agents/builder.py`): fetches live OpenAPI from running container via `DockerManager.get_host_port()`, reads entry source from workspace (not original), calls LLM with bounded retries, validates response against `BuilderAnalysis` schema (handles JSON, markdown-fenced JSON, refusals, empty responses, schema mismatches), persists to `agent_context`, emits structured `AgentEvent` records throughout.
- [Phase 4] Added `ScanRepository.list_by_project`, scans REST API (`api/scans.py`): `POST /api/scans`, `GET /api/scans`, `GET /api/scans/{id}`, `POST /api/scans/{id}/run-builder` (background task), `GET /api/scans/{id}/context`, `GET /api/scans/{id}/events`.
- [Phase 4] 57 tests pass: 50 unit (no Docker/LLM/Mongo), 7 Docker integration.

## In-progress work

None.

## Known issues

None.

## Important decisions log

### Initial decision

The product will focus on existing FastAPI projects as input rather than generating an application from scratch.

### Initial decision

The four agents have distinct responsibilities:

- Builder = understand
- Attacker = challenge
- Evaluator = verify
- Fixer = remediate

### Initial decision

Research data must be structured enough to compare multi-agent, single-agent, and traditional approaches.

## Agent handoff notes

When changing phases, add:

```text
Date: 2026-09-09
Phase: Phase 0
What was implemented: Repository scaffolding for both Flutter desktop frontend and Python FastAPI backend, including health check endpoint and configuration module.
Files/modules changed: Added `desktop/` and `backend/` directories with their internal structures.
Tests/checks run: Executed `pytest` in `backend/` which passed successfully. Executed `flutter test` in `desktop/`.
Known limitations: No UI exists yet. The backend only has a health endpoint.
Next recommended task: Begin Phase 1 (Flutter shell) to start building the desktop UI layout and navigation.
```

```text
Date: 2026-09-09
Phase: Phase 1
What was implemented: Full Flutter shell — dark theme, left nav rail, go_router routing via Riverpod, all 8 screens with real placeholder layouts (not blank/stub). Shared widgets: PageHeader, StatCard, EmptyState.
Files/modules changed:
  desktop/lib/main.dart (rewritten)
  desktop/lib/core/theme/app_theme.dart (new)
  desktop/lib/core/routing/app_router.dart (new)
  desktop/lib/core/shell/app_shell.dart (new)
  desktop/lib/features/dashboard/dashboard_screen.dart (new)
  desktop/lib/features/projects/projects_screen.dart (new)
  desktop/lib/features/scans/scans_screen.dart (new)
  desktop/lib/features/vulnerabilities/vulnerabilities_screen.dart (new)
  desktop/lib/features/agents/agents_screen.dart (new)
  desktop/lib/features/reports/reports_screen.dart (new)
  desktop/lib/features/settings/settings_screen.dart (new)
  desktop/lib/features/shared/ (new: page_header.dart, stat_card.dart, empty_state.dart)
  desktop/test/widget_test.dart (updated)
  desktop/pubspec.yaml (flutter_riverpod, go_router, google_fonts added)
Tests/checks run: `flutter analyze` — no issues. `flutter test` — 1 test passed.
Known limitations:
  - App does not launch on Windows without Visual Studio Developer environment in PATH (MSBuild issue, pre-existing).
  - `flutter test` passes but `flutter run -d windows` requires Developer shell.
  - No backend connectivity yet — status indicator hardcoded to "not connected".
  - Assumption: "Research" nav item and screen included even though not explicitly listed in PHASES.md Phase 1 because DESIGN.md §3 lists it in Main navigation; recorded as assumption.
Next recommended task: Begin Phase 2 (Project import) — backend project API, folder picker in Flutter, FastAPI validation, persistence.
```

```text
Date: 2026-09-09
Phase: Phase 2
What was implemented: 
- Backend: Async MongoDB connection (`motor`), FastAPI static validator (`ast.parse`, no execution), `ProjectRecord` model, `/api/projects` endpoints.
- Flutter: `dio` API client, native folder selection (`file_picker`), Riverpod state providers, functional Projects screen with validation rendering, live backend health indicator in shell.
Files/modules changed:
  backend/requirements.txt (added motor, tomli, pytest-asyncio)
  backend/app/core/config.py (mongodb settings)
  backend/app/database/client.py, models.py, repositories.py (new)
  backend/app/services/project_service.py, fastapi_validator.py (new)
  backend/app/api/projects.py (new)
  backend/app/main.py (added lifespan and router)
  backend/tests/test_projects.py (new)
  desktop/pubspec.yaml (added file_picker, dio)
  desktop/lib/models/project.dart (new)
  desktop/lib/services/api_client.dart, projects_service.dart, health_service.dart (new)
  desktop/lib/providers/projects_provider.dart (new)
  desktop/lib/features/projects/projects_screen.dart (rewritten)
  desktop/lib/core/shell/app_shell.dart (updated health indicator)
Tests/checks run: `pytest` passed (15 tests, mocked Mongo). `flutter test` passed.
Known limitations:
  - MSBuild issue on Windows still requires Developer PowerShell for `flutter run` (pre-existing).
  - Validation requires `requirements.txt` or `pyproject.toml` to consider a project "ready for isolation", but this is by design.
Next recommended task: Begin Phase 3 (Isolation and target lifecycle) — Docker workspace creation, container lifecycle, and resource limits.
```

```text
Date: 2026-09-09
Phase: Phase 3
What was implemented:
- WorkspaceManager: copy-on-import to scan_workspace/, symlinks not followed, cleanup safe.
- DockerManager: Dockerfile generation, image build (120s timeout), container start (no host env, 256m/0.5cpu, bridge network), health check polling with httpx (30s timeout, catches all httpx.HTTPError), size-limited log retrieval (100KB), stop/remove, cleanup_all.
- IsolationService: full lifecycle orchestration; import_failed fallback on any error; cleanup always called on failure path.
- REST API: POST /isolate, POST /stop, POST /cleanup, GET /status, GET /logs.
- broken_fastapi_app/ fixture for build-failure testing.
- pytest.ini with docker marker.
Files/modules changed:
  backend/requirements.txt (added docker>=6.1.0)
  backend/pytest.ini (new: docker marker)
  backend/app/core/config.py (added workspace/docker settings)
  backend/app/database/models.py (added IsolationStatus enum, 4 new fields)
  backend/app/database/repositories.py (added update())
  backend/app/isolation/errors.py (new)
  backend/app/isolation/workspace.py (new)
  backend/app/isolation/docker_manager.py (new)
  backend/app/services/isolation_service.py (new)
  backend/app/api/isolation.py (new)
  backend/app/main.py (registered isolation router)
  backend/tests/fixtures/valid_fastapi_app/main.py (added / endpoint)
  backend/tests/fixtures/valid_fastapi_app/Dockerfile (new)
  backend/tests/fixtures/broken_fastapi_app/ (new)
  backend/tests/test_isolation.py (new: 18 tests)
Tests/checks run: pytest — 32 passed (26 unit, 6 Docker integration).
Architecture decisions this phase:
  - Resource limits: 256m RAM, 0.5 CPU (nano_cpus=500_000_000). Documented assumption.
  - Build timeout: 120s. Startup timeout: 30s. Log cap: 100KB. Documented assumptions.
  - internal=True removed from Docker network: bridge network already isolates from LAN;
    internal=True blocked host→container health-check traffic. Documented in docker_manager.py.
  - No automatic retry on import failure: 1 attempt, then import_failed. Documented assumption.
  - Error strings truncated to 2KB before storing in isolation_error (prevents unbounded DB growth).
Known limitations:
  - MSBuild/flutter run caveat from Phase 1 still present (pre-existing).
  - Isolation tests require Docker Desktop running; skippable with -m "not docker".
  - Target containers can reach the internet during runtime (bridge network, no outbound firewall).
    Outbound internet restriction can be added via iptables rules or a custom Docker network with
    specific routing — deferred as hardening to Phase 12 per docs/SECURITY.md.
Next recommended task: Begin Phase 4 (Builder agent) — static analysis of the isolated target's
API surface, route discovery, OpenAPI parsing, and producing structured target context.
```

```text
Date: 2026-09-09
Phase: Phase 4
What was implemented:
- LLM provider abstraction (BaseLLMProvider, MockProvider, GeminiProvider, get_provider factory).
- Versioned prompt templates (builder_v1.0) with prompt injection defense in system preamble.
- Pydantic output schemas for BuilderAnalysis with explicit 'gaps' field.
- AgentState enum + BaseAgent abstract class covering full 8-state pipeline machine.
- Phase 4 MongoDB models: ScanRecord, AgentEvent, AgentContextRecord.
- ScanRepository, AgentEventRepository (10KB payload cap), AgentContextRepository.
- BuilderAgent: live OpenAPI fetch from container, bounded retries, full schema validation,
  structured event emission, agent_context persistence.
- Scans REST API: POST /scans, GET /scans, GET /scans/{id}, POST /{id}/run-builder,
  GET /{id}/context, GET /{id}/events.
Files/modules changed:
  backend/requirements.txt (added google-generativeai>=0.8.0)
  backend/app/core/config.py (added LLM provider settings)
  backend/app/llm/provider.py (new)
  backend/app/llm/prompts.py (new)
  backend/app/llm/schemas.py (new)
  backend/app/agents/base.py (new)
  backend/app/agents/builder.py (new)
  backend/app/database/models.py (extended: ScanRecord, AgentEvent, AgentContextRecord)
  backend/app/database/scan_repositories.py (new)
  backend/app/api/scans.py (new)
  backend/app/main.py (registered scans router)
  backend/tests/test_builder.py (new: 25 unit + 1 Docker integration test)
Tests/checks run: pytest -m "not docker" — 50 passed. pytest -m docker — 7 passed. Total: 57.
Architecture decisions this phase:
  - First concrete LLM provider: Google Gemini (gemini-2.0-flash). Assumption: most accessible
    for this dev environment. Swappable via LLM_PROVIDER env var without code changes.
  - Provider interface: generate(prompt, prompt_version) -> LLMResponse. Prompt version stored
    alongside every output for research reproducibility (docs/RESEARCH.md §8).
  - Source truncated to 150 lines before sending to LLM to limit token usage and avoid sending
    large untrusted payloads to an external provider.
  - OpenAPI schema bounded to 8000 chars before inclusion in prompt.
  - AgentEvent.data payload capped at 10KB in AgentEventRepository before MongoDB write.
  - Builder does not produce security judgments — only structured inventory with explicit gaps.
  - Prompt injection defense: system preamble explicitly instructs model to ignore any
    instructions embedded in target project content.
Known limitations:
  - GEMINI_API_KEY must be set in .env for real (non-mock) LLM calls.
  - Scans run-builder uses FastAPI BackgroundTasks (single-process). For Phase 9+, consider
    a proper task queue (Celery/ARQ) for parallel scan support.
  - No Flutter UI for scans yet — accessible via /api/scans and /docs only.
Next recommended task: Begin Phase 5 (Attacker agent) — test-case abstraction, controlled
request execution against the isolated container, evidence capture, candidate finding generation.
```

## Do not record here

- secrets
- API keys
- passwords
- huge logs
- complete source files
- private user data
- raw LLM chain-of-thought

Keep this file concise enough that a new coding agent can understand the project quickly.