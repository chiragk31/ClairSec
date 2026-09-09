# Project Memory

> This file is a living state document for AI coding agents.
> Update it after meaningful implementation progress.
> Do not turn it into a dump of every source file or every conversation.

## Current status

- Project stage: Project import
- Current phase: Phase 2
- Overall status: Phase 2 implemented and verified

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

## Do not record here

- secrets
- API keys
- passwords
- huge logs
- complete source files
- private user data
- raw LLM chain-of-thought

Keep this file concise enough that a new coding agent can understand the project quickly.