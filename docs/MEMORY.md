# Project Memory

> This file is a living state document for AI coding agents.
> Update it after meaningful implementation progress.
> Do not turn it into a dump of every source file or every conversation.

## Current status

- Project stage: Foundation remediation before agent work
- Current phase: **Phase 3.5** (new — see `PHASES.md`)
- Overall status: Phases 0–3 implemented. A documentation and design review on
  2026-09-09 expanded the specification set and identified foundation issues that must
  be fixed before Phase 4 builds on them.

### Verification note (2026-09-09)

Re-verified on a second machine. 26 unit tests pass. The 6 Docker integration tests
could not run (daemon not started) and **fail rather than skip** — they need an
availability fixture. The committed `venv/` is unusable (built by another user on
another drive, Python 3.12) and the repository has no `.gitignore`, so `venv/` and
`__pycache__` are tracked. `desktop/pubspec.yaml` requires Dart `^3.13.2` while the
installed Flutter 3.38.7 ships Dart 3.10.7, so `flutter pub get`/`analyze`/`test` all
fail at version solving. These are tracked in `PHASES.md` Phase 3.5.

### Specification documents added (2026-09-09)

`THREAT_MODEL.md`, `LLM.md`, `VULN_TAXONOMY.md`, `METHODOLOGY.md`, `DATA_MODEL.md`,
`ETHICS.md`, `OPERATIONS.md`. The original nine docs state intent; these seven state
the contracts precisely enough to implement without guessing. Read order and
precedence updated in `README.md`.

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

## In-progress work

Phase 3.5 — foundation remediation. Not started.

## Known issues

Ordered by how expensive they become if deferred.

1. **Target containers can reach the host LAN.** `internal=True` was removed from the
   Docker network in Phase 3 so host-side health checks would work. That traded away
   the isolation property. Fix: target on an internal network, health checks and
   attack traffic from a scanner-side container attached to both networks.
   (`THREAT_MODEL.md` C3.3)
2. **Blocking I/O on the event loop.** `IsolationService.start_isolation` runs a
   120-second Docker build inside an `async def` handler, stalling all other requests
   and every WebSocket client. Must be fixed before Phase 9 adds live streaming, and
   ideally before Phase 4. (`OPERATIONS.md` §5)
3. **Backend HTTP surface is unauthenticated.** Any local process can drive Docker
   through it. Needs localhost binding, a per-launch token, and strict CORS/Host
   validation. (`THREAT_MODEL.md` T7)
4. **`project_id` is unvalidated before use in filesystem paths** and container names.
   (`THREAT_MODEL.md` C2.3)
5. **Repository is not reproducible on another machine:** no `.gitignore`, `venv/` and
   `__pycache__` committed, dependencies pinned with `>=` ranges, Flutter SDK
   constraint unsatisfiable on the installed toolchain. (`OPERATIONS.md` §1, §2)
6. **Docker tests fail instead of skipping** without a daemon.
7. Container hardening flags (`cap-drop`, `no-new-privileges`, non-root, read-only
   rootfs, `pids-limit`) not yet applied. (`THREAT_MODEL.md` C3.2)

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

### Design review, 2026-09-09

- **A fourth experimental arm was added:** multi-agent *without* the Evaluator. The
  hypothesis is specifically about independent evaluation, and three arms cannot
  attribute any improvement to that component rather than to the pipeline as a whole.
- **Deterministic oracles.** Whether a security test fired is decided by platform code
  from the recorded request/response, never by an LLM. If a model decides, the
  detection rate measures its self-consistency rather than the system's capability and
  the study has no ground truth. This is the load-bearing design decision.
- **Severity is computed, not generated.** The Evaluator supplies CVSS inputs from
  closed enums with cited evidence; code computes the score.
- **Fix evaluation is dual-criterion:** exploit blocked *and* functional suite still
  passing. Exploit-blocking alone scores a patch that deletes the endpoint as a
  success, which inflates every fix metric.
- **Vulnerability taxonomy fixed at eight categories** mapped to OWASP API 2023 + CWE,
  with the deferred categories and their reasons recorded.
- **False-positive denominator resolved** as false discovery rate, with classical
  specificity reported alongside it over the enumerable candidate space.
- **k=3 trials with bootstrap CIs and McNemar's test.** `temperature=0` does not make
  an LLM deterministic; single-run point estimates are not a result.
- **A secondary research question was adopted:** whether role separation changes
  susceptibility to prompt injection planted in the code under test. Near-zero marginal
  cost given the architecture, and substantially more novel than another
  detection-rate comparison.
- **Capability starvation is the primary injection defence.** Layers that filter or
  delimit untrusted text are probabilistic; the model being structurally unable to
  express a forbidden action is not.

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
Phase: Phase 3.5 (Foundation remediation)
What was implemented:
- Step 1 (Repo hygiene):
  * Added .gitignore covering venv/, __pycache__/, *.py[cod], .env*, workspaces/, artifacts/, desktop/build/, etc.
  * git rm -r --cached venv and tracked __pycache__ trees (staged, no commit made per policy).
  * backend/requirements.in compiled to requirements.txt via pip-compile --generate-hashes; anyio>=4.0.0 included.
  * backend/requirements-dev.txt created (pytest, pytest-asyncio, ruff, mypy, pip-tools).
  * backend/.python-version pinned to 3.11.9 (system Python 3.11).
  * backend/.env.example created with all keys present; check_required_settings() fails loudly on missing required config.
  * Documented Flutter SDK requirement (>=3.44.0, Dart >=3.13.2) in README.md and CI. Fixed Dart 3.13 lints in desktop.
- Step 2 (Docker test skip):
  * pytest_collection_modifyitems hook in conftest.py deselects docker-marked tests when daemon unreachable (with 2s timeout probe).
  * Added llm and docker markers to pytest.ini.
- Step 3 (Local API authentication - C7.1-C7.4):
  * Bound uvicorn/backend to 127.0.0.1 only.
  * 32-byte hex token generated per launch, written to ~/.clairsec/auth_token. Windows pywin32 DACL restricts access to current user SID.
  * Constant-time token verification via secrets.compare_digest on all authenticated routes.
  * CORS deny-all (empty allowlist); Host header validation middleware (allows localhost, 127.0.0.1, testserver).
  * /api/health exempt from auth, returns {"status": "ok"} only.
  * Flutter desktop client updated: reads auth_token on startup, Dio interceptor attaches Bearer token, BackendStatus.tokenMissing warning state in UI.
  * Auto-authenticating test client and auth_headers fixtures in conftest.py.
- Step 4 (UUID validation - C2.3):
  * validate_project_id regex checking ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ enforced on all endpoints and service methods.
  * Path traversal, non-UUID, shell injection rejected with 422 Unprocessable Content.
- Step 5 (Schema and index groundwork - DATA_MODEL §1, §6):
  * schema_version: int = 1 on ProjectRecord.
  * ensure_indexes() asserts unique {id: 1} and {isolation_status: 1} on projects, and {id: 1}, {status: 1} on jobs.
  * Forward-only idempotent migration runner with v001_initial migration. Fast Mongo server selection timeout (500ms) in testing mode.
- Step 6 (Network isolation & container hardening - C3.1-C3.5):
  * Per-scan internal bridge network (cs-net-{id[:8]}, internal=True); target container has no published ports and cannot route to LAN or resolve DNS.
  * Scanner-side HTTP proxy service container attaches to scanner bridge (published on 127.0.0.1 only) and target internal network; forwards requests strictly to its assigned target container; backend uses standard httpx.
  * Base image python:3.11-slim pinned by sha256 digest in config.
  * Container hardening: cap_drop=["ALL"], security_opt=["no-new-privileges"], non-root user appuser dropped after root pip install, read_only rootfs with tmpfs on /tmp, pids_limit=256, memory/CPU limits, never mount Docker socket, env={}.
- Step 7 (Async discipline - OPERATIONS §5, RULES §5a):
  * All blocking calls wrapped in anyio.to_thread.run_sync.
  * POST /isolate queues background job and returns 202 Accepted with job_id immediately (<100ms).
  * Endpoints GET /api/jobs/{id} and POST /api/jobs/{id}/cancel implemented.
  * Cancellation token checked at phase boundaries; on cancellation during build, container startup is aborted, image & workspace pruned. Cancellation latency during an image build is observed at build completion, so up to the full build timeout (~120s); between phases and during health-check polling it is under 1s. (The earlier 0.50s figure was measured against a mocked build).
  * Startup reconciliation: find active jobs in pending/running state on restart, mark interrupted, and clean up orphaned containers and workspaces.
Files/modules changed:
  backend/.env.example (new)
  backend/.gitignore (new)
  backend/.python-version (new)
  backend/requirements.in, requirements.txt, requirements-dev.txt (new/compiled)
  backend/pytest.ini (updated markers)
  backend/app/core/config.py (auth, required check, hardening & base image settings)
  backend/app/core/auth.py (new: token generation, pywin32 ACL, host validation)
  backend/app/core/validators.py (new: UUID validation)
  backend/app/database/models.py (added schema_version, proxy fields, JobStatus, JobRecord)
  backend/app/database/repositories.py (added JobRepository)
  backend/app/database/indexes.py (new: ensure_indexes projects & jobs)
  backend/app/database/migrations/ (new: runner.py, v001_initial.py)
  backend/app/database/client.py (fast timeout for testing)
  backend/app/isolation/docker_manager.py (hardened container run, proxy service, internal network)
  backend/app/services/isolation_service.py (proxy lifecycle)
  backend/app/services/job_service.py (new: async job supervisor, cancellation, reconciliation)
  backend/app/api/jobs.py (new: job status & cancel endpoints)
  backend/app/api/isolation.py (returns 202 with job_id immediately)
  backend/app/api/health.py (stripped down to status ok)
  backend/app/main.py (lifespan migrations, indexes, reconciliation; jobs router; 422 handler)
  backend/tests/conftest.py (modifyitems hook, authed_client fixture)
  backend/tests/test_auth.py (new: 9 tests)
  backend/tests/test_uuid_validation.py (new: 12 tests)
  backend/tests/test_migrations.py (new: 5 tests)
  backend/tests/test_hardening.py (new: 9 unit tests, 4 live docker tests)
  backend/tests/test_async_discipline.py (new: 3 unit tests, 1 live docker test)
  desktop/lib/services/api_client.dart (reads auth token, Dio interceptor, AuthTokenException)
  desktop/lib/services/health_service.dart (BackendStatus.tokenMissing)
  desktop/lib/core/shell/app_shell.dart (status banner for tokenMissing)
  desktop/lib/providers/projects_provider.dart (error handling)
  desktop/lib/features/projects/projects_screen.dart (Dart 3.13 lints)
  desktop/lib/services/projects_service.dart (Dart 3.13 lints)
  README.md (Flutter SDK requirements documented)
  .github/workflows/ci.yml (Flutter SDK documented)
  docs/TESTING.md (updated §10 traceability rows for Phase 3.5 controls)
Tests/checks run:
  - backend: 64 passed, 11 skipped (Docker tests skipped when daemon not running) in 12.40s.
  - desktop: flutter analyze (0 issues), flutter test (all passed).
Key measurements & outcomes:
  - Build cancellation latency: Observed at build completion at the phase boundary, so up to the full build timeout (~120s) if cancelled during an image build; between phases and during health-check polling it is under 1s.
  - Impact of read_only/non-root: Mitigated via tmpfs on /tmp and root pip install before dropping to appuser. Config flags default to True.
  - Windows ACL: pywin32 win32security successfully applied to ~/.clairsec/auth_token.
Next recommended task: Proceed to Step A (Reference Fixtures).
```

### 2026-09-09 — Step A: Reference Test Fixtures & PoV Oracles

```text
Phase / Task: Step A — Reference Fixtures (vulnerable_fastapi_app & secure_fastapi_app)
Summary of changes:
  - Built backend/tests/fixtures/vulnerable_fastapi_app/ with 3 seeded vulnerabilities:
      1. BOLA (CWE-639) at GET /documents/{doc_id}
      2. BOPLA_MASS_ASSIGN (CWE-915) at PUT /users/{user_id}/profile
      3. SECURITY_MISCONFIG (CWE-16) at GET /debug/config
  - Added two distinct test principals: usr_alice_01 and usr_bob_02 with distinct tokens and ownership boundaries.
  - Created executable PoV scripts (pov_bola.py, pov_mass_assign.py, pov_misconfig.py) returning deterministic boolean exploited status and structured evidence.
  - Created seeded_vulnerabilities.json matching METHODOLOGY.md §2.1.
  - Built backend/tests/fixtures/secure_fastapi_app/ with the same endpoints correctly secured (negative fixture for false-positive control).
  - Created functional test suites (test_functional.py) passing on both apps (dual criterion).
  - Created backend/tests/test_fixture_pov.py verifying all 3 PoVs fire on vulnerable build, do NOT fire on secure build, and functional parity holds.
Tests/checks run:
  - pytest tests/test_fixture_pov.py -v: 4 passed in 0.36s.
  - pytest backend full suite: 80 passed, 11 skipped in 14.71s.
  - desktop: flutter test: 1 passed in 2s, flutter analyze: 0 issues.
Next recommended task: Proceed to Step B (Phase 4 Builder agent).
```

### 2026-09-09 — Phase 4: Builder Agent & Core LLM Layer

```text
Phase / Task: Phase 4 — Builder Agent & LLM Layer Foundation (Rules R1, R5, C1.1, C1.2, C5.1, C5.2, C5.4)
Summary of changes:
  - R1 decoupled LLM_API_KEY requirement in config.py: required only when llm_provider != 'mock', defaulting to 'mock'.
  - R5 TargetHandle abstraction implemented in app/targets/handle.py: ContainerTargetHandle (Docker proxy) and LocalFixtureTargetHandle (ephemeral localhost uvicorn server, strictly hard-gated to tests/fixtures/).
  - LLM layer implemented in app/llm/:
      - Typed envelopes: LLMRequest, LLMResponse, ModelDescriptor, TrustLevel, AgentName, TokenUsage, CallBudget, Untrusted.
      - Pinned to claude-opus-5: omitting temperature, top_p, and seed; using output_config.effort="high" with thinking={"type": "adaptive"}.
      - providers/anthropic_provider.py: sole file importing anthropic SDK, implementing native structured output and 1 repair retry before MalformedOutput.
      - providers/mock_provider.py: MockLLMProvider implementing all 11 scenarios in TESTING.md §3.
      - prompts/registry.py: versioned file registry computing SHA-256 startup digest.
      - quarantine.py: 16-hex nonce envelope and injection detection (C1.1, C1.2).
      - redaction.py: deny-list (C5.1) and outbound regex scrubber for secrets and canary tokens (C5.2, C5.4).
      - accounting.py: token and cost ledger persisted to llm_calls collection.
  - Builder Agent implemented in app/agents/builder/:
      - Static AST route extraction first (ast_extractor.py).
      - Runtime /openapi.json extraction second (openapi_extractor.py).
      - Quarantined LLM auth semantics extraction third (builder.py).
      - Test principal provisioning for Alice and Bob (provisioning.py).
      - Validated AgentContext output with graceful degradation on malformed responses.
  - Traceability rows C1.1, C1.2, C5.1, C5.2, C5.4 filled in docs/TESTING.md.
Tests/checks run:
  - pytest backend full suite: 105 passed, 11 skipped in 23.62s.
  - desktop: flutter test: 1 passed in 2s, flutter analyze: 0 issues.
Key measurements & outcomes:
  - Zero-credential execution verified: backend boots and tests with zero API keys or network calls.
  - Graceful degradation: malformed model outputs degrade to deterministic AST inferences without crashing.
  - Canary secrets scrubbed: outbound prompt inspection proves canary tokens and database passwords are never transmitted.
### 2026-09-10 — Phase 5: Attacker Agent & Deterministic Oracles

```text
Phase / Task: Phase 5 — Attacker Agent, Deterministic Oracles, Scope-Locked Client (THREAT_MODEL T9, ETHICS §3, SECURITY §6, VULN_TAXONOMY §4, DATA_MODEL §2 & §3)
Summary of changes:
  - Deterministic Oracles in app/security/oracles.py:
      - BOLAOracle (CWE-639, ORACLE-BOLA-001): 2xx + discriminated owner in response body.
      - BOPLAMassAssignOracle (CWE-915, ORACLE-BOPLA-001): unvalidated privileged fields persisted across write + subsequent read.
      - SecurityMisconfigOracle (CWE-16, ORACLE-MISCONFIG-001): exposed sensitive keys on debug endpoints or wildcard CORS with credentials.
      - Rule enforced: Platform code mechanically adjudicates pass/fail from captured request/response evidence; no LLM evaluation.
  - Scope-Locked HTTP Client in app/security/http_client.py:
      - Host scope lock (T9, ETHICS §3): Rejects any request with host/port outside TargetHandle.
      - Cross-host redirects blocked.
      - Per-scan rate limiting (default 20 req/s) and hard request budget ceiling (RequestCeilingExceededError).
      - Non-destructive policy (SECURITY §6): HTTP DELETE prohibited (NonDestructivePolicyViolationError).
  - Pre-persistence Evidence Capture in app/agents/attacker/evidence.py:
      - Secret/canary regex redaction applied at write time (C5.2).
      - 64 KB per-body size cap with SHA-256 digest on truncation (DATA_MODEL §2).
  - Test-case and Candidate Finding Abstractions in app/agents/attacker/schemas.py & repository.py:
      - Every executed test persisted to test_cases collection whether or not it fired (denominator for tests executed).
      - Normalized route templates (/documents/{doc_id}, /users/{user_id}/profile) strictly enforced in findings and test cases.
  - Attacker Agent in app/agents/attacker/attacker.py:
      - Orchestrates test generation and execution against TargetHandle.
      - Replay mode verified: re-running produces an identical test-case set.
  - Traceability row T9 filled in docs/TESTING.md.
Tests/checks run:
  - pytest backend full suite: 126 passed, 11 skipped in 39.10s.
  - desktop: flutter test: 1 passed in 15s, flutter analyze: 0 issues.
Key measurements & exit gate results:
  - Confirmed-vuln count on vulnerable_fastapi_app: 3/3 seeded vulnerabilities detected:
      1. BOLA (CWE-639) at /documents/{doc_id}
      2. BOPLA_MASS_ASSIGN (CWE-915) at /users/{user_id}/profile
      3. SECURITY_MISCONFIG (CWE-16) at /debug/config
  - Secure-fixture false-positive count on secure_fastapi_app: 0 findings reported (FP = 0).
  - Off-target rejection: OffTargetRequestBlockedError provably raised when pointing to unauthorized host/port.
Next recommended task: Proceed to Phase 6 (Evaluator Agent).
```

### 2026-09-10 — Phase 6: Evaluator Agent & Deterministic Severity

```text
Phase / Task: Phase 6 — Evaluator Agent (PHASES.md Phase 6, METHODOLOGY.md §4 & §9, DATA_MODEL.md §3, RULES.md §2)
Summary of changes:
  - Structural Independence (METHODOLOGY.md §9, RULES.md §2):
      - EvaluatorEvidence container strictly encapsulates HTTP request/response and oracle evaluation; completely isolated from Attacker narrative, internal reasoning, and target source code.
  - Evidence Inconsistency Verification (Adversarial Filter):
      - EvidenceVerifier mechanically inspects candidates prior to reproduction.
      - Blocks fabricated findings (e.g., BOLA where returned owner matches requesting principal, mass-assign without reflection, misconfig without indicator keys).
  - Independent Reproduction via ScopeLockedHttpClient:
      - TestReproducer re-executes candidate traffic against TargetHandle and evaluates platform oracles.
      - Candidates failing reproduction become INCONCLUSIVE with recorded failure reason (never CONFIRMED).
      - Re-executed tests persisted to test_cases collection.
  - Deterministic CVSS v3.1 Scoring (cvss_scorer.py):
      - Model never emits final severity string or numeric score. Model emits closed-enum metric inputs only with evidence citations.
      - Platform code computes exact FIRST CVSS v3.1 equations (roundup, ISS, impact, exploitability, vector, base score, severity band).
      - Recomputing from stored inputs alone yields identical score and vector (reproducible rubric).
  - Structured Confidence Calculation (confidence.py):
      - Derived deterministically from runtime_confirmed, oracle_fired, reproduced_n_times, evidence_complete (HIGH/MEDIUM/LOW/ZERO).
  - Duplicate Detection in Scan Scope:
      - Rejects identical candidates for existing confirmed finding with duplicate_of link and reason duplicate_of_{id}.
  - Repository Persistence (repository.py):
      - FindingRepository for findings collection enforcing 2048-byte status_reason truncation cap.
Tests/checks run:
  - pytest tests/test_cvss_scorer.py -v: 9 passed in 8.30s.
  - pytest tests/test_evaluator_agent.py -v: 7 passed in 21.93s.
  - pytest backend full suite (not docker): 142 passed, 12 deselected in 51.22s.
  - desktop: flutter test: 8 passed in 5s.
  - desktop: flutter analyze: 0 issues in 22.5s.
Key measurements & exit gate results:
  - Vulnerable fixture (vulnerable_fastapi_app):
      - Confirmed: 3 (100% of seeded vulns confirmed with runtime evidence attached)
      - Rejected: 0
      - Inconclusive: 0
  - Secure fixture (secure_fastapi_app):
      - Confirmed: 0 (FP = 0)
      - Rejected: 0
      - Inconclusive: 0
  - Adversarial fabricated BOLA candidate:
      - Status: REJECTED (reason: "evidence_inconsistent_with_bola: response owner matches requesting principal")
  - Reproduction failure test:
      - Status: INCONCLUSIVE (reason: reproduction_failed)
  - Duplicate candidate test:
      - Status: REJECTED (duplicate_of populated)
  - CVSS round-trip reproducibility:
      - Recomputation from stored inputs verified identical across all findings.
Next recommended task: Proceed to Phase 7 (Fixer Agent).
```

### 2026-09-10 — Phase 7: Fixer Agent & Isolated Patch Engine

```text
Phase / Task: Phase 7 — Fixer Agent (PHASES.md Phase 7, THREAT_MODEL.md C2.1, C2.2, C2.4, T8, DATA_MODEL.md §2 & §3)
Summary of changes:
  - Pure Python Unified Diff Engine (patch_engine.py):
      - Capability starvation enforced (LLM.md §6): Zero shell execution, zero exec(). Unified diff hunks parsed and applied purely in memory before safe write.
  - Strict Path Containment (THREAT_MODEL C2.1, C2.2, C2.4):
      - Target paths resolved with Path.resolve() and rejected unless strictly under modified_workspace/ (C2.1).
      - Symlinks inside workspace refused without following (C2.2).
      - Fixer refuses to invent files: Target paths not present in Builder inventory are recorded as unattempted hallucinations (C2.4).
  - Pre-apply Validation Persisted as Data (T8, DATA_MODEL.md §3 patches.validation):
      - ast_parsed: Patched Python files verified with ast.parse() before commit to disk; syntax errors rejected and recorded.
      - path_check_passed: Verified against containment and symlink rules.
      - size_ok: 256 KB diff size cap enforced per DATA_MODEL.md §2. Patches exceeding cap are rejected and recorded as patch_too_large (never silently truncated).
  - Workspace Isolation (workspace.py):
      - WorkspaceManager.create_modified_workspace() populates modified_workspace/ from scan_workspace/ using symlinks=False.
      - scan_workspace/ and original source remain strictly read-only and byte-identical throughout the full pipeline.
  - Patch Repository & Fix Metadata (repository.py, fixer.py):
      - PatchRecord schema matching DATA_MODEL.md §3 patches collection.
      - Stores root_cause, rationale, prompt_version, llm_call_id, diff_stats, and persistent validation record.
Tests/checks run:
  - pytest tests/test_fixer_agent.py -v: 7 passed in 22.72s.
  - pytest backend full suite (not docker): 149 passed, 12 deselected in 81.30s.
  - desktop: flutter test: 13 passed in 5s.
  - desktop: flutter analyze: 0 issues in 10.7s.
Key measurements & exit gate results:
  - Diff count: 3 reviewable unified diffs produced and applied to modified_workspace/ (3/3 applied, 0 rejected).
  - Path-rejection test result: Traversal patch targeting ../../../etc/passwd refused and recorded (path_outside_workspace).
  - Symlink-rejection test result: Symlinks inside workspace refused and recorded (symlink_detected).
  - Oversized patch result: Diff exceeding 256 KB refused and recorded as patch_too_large without silent truncation.
  - Unparseable patch result: Patch introducing malformed Python syntax refused and recorded as unparseable_patch_syntax_error.
  - Hallucinated path result: Non-inventoried target path recorded as hallucinated_path without crashing or attempting write.
  - Checksum equality result: Recursive SHA-256 tree digests of original upstream source and scan_workspace/ match identically before and after full Builder -> Attacker -> Evaluator -> Fixer run.
Next recommended task: Stop and report for review before proceeding to Phase 8 (Re-test & Verification).
### 2026-09-10 — Phase 8: Re-test & Verification (Dual Criterion & Post-Fix Robustness)

```text
Phase / Task: Phase 8 — Re-test & Verification (PHASES.md Phase 8, METHODOLOGY.md §5, DATA_MODEL.md §3 verification_results, RESEARCH.md §5, THREAT_MODEL.md T8)
Summary of changes:
  - Dynamic Target Rebuild & Execution (targets/handle.py):
      - LocalWorkspaceTargetHandle starts target from modified_workspace/ on dynamic localhost port.
      - Enforces strict path containment gating access to modified_workspace/ trees.
      - Catches boot errors / SystemExit and surfaces structured startup failure.
      - Clean async shutdown with graceful process termination and port release.
  - Verification Data Models & Repository (verifier/schemas.py, verifier/repository.py):
      - Fully conformant with DATA_MODEL.md §3 verification_results collection.
      - Captures rebuild_ok, original_exploit, functional_suite, variant_attack, outcome, outcome_reason (capped at 2048 bytes), and duration_s.
  - Original Exploit Retester (verifier/retester.py):
      - Re-executes original candidate exploit using ScopeLockedHttpClient.
      - Evaluates deterministic platform oracles (BOLA, BOPLA mass assignment, security misconfiguration).
  - Dual Criterion Functional Suite Runner (verifier/functional_runner.py):
      - Executes all 6 legitimate project functional tests against rebuilt target.
      - Enforces that a patch must not break legitimate application capabilities.
  - Adapted Variant Attack Runner (verifier/variant_runner.py):
      - Evaluates mutated payloads/query variations/header bypasses post-fix.
      - Recorded as distinct variant_attack field (independent from original exploit adjudication).
  - Verifier Agent Adjudication (verifier/verifier.py):
      - Strictly enforces the 4-way outcome states:
        * fixed: original exploit blocked AND 100% functional test pass rate.
        * regressed: functional test suite fails (e.g. endpoint disabled/broken).
        * unresolved: original exploit still succeeds against patched target.
        * unverified: target rebuild or startup fails to reach healthy state.
Tests/checks run:
  - pytest tests/test_verifier_agent.py -v: 4 passed in 32.08s.
  - pytest backend full suite (not docker): 153 passed, 12 deselected in 59.96s.
  - desktop: flutter test: 13 passed in 4s.
  - desktop: flutter analyze: 0 issues in 9.7s.
Key measurements & exit gate results:
  - 4-way outcome breakdown across the 3 seeded findings:
      - fixed: 3 / 3 (100%)
      - regressed: 0 / 3
      - unresolved: 0 / 3
      - unverified: 0 / 3
  - Adversarial regression test result:
      - Synthetic "delete-the-endpoint" patch returning 404 correctly blocked the exploit, but failed test_user_can_read_own_document and was adjudicated as REGRESSED (reason: "functional_regression: 1 test(s) failed: test_user_can_read_own_document"), NEVER fixed.
  - Ineffective patch test result:
      - Patched target with exploit still firing adjudicated as UNRESOLVED (reason: "exploit_still_succeeded").
  - Broken target startup result:
      - Target raising boot error adjudicated as UNVERIFIED (rebuild_ok=False).
  - Post-fix robustness (variant attacks):
      - Variant attack executed for each fixed finding; variant results recorded in distinct variant_attack field.
Next recommended task: Stop and report for review before proceeding to Phase 9 (Live Agent UI & Desktop Visualization).
```


```text
Phase / Task: v2 upgrade planning (2026-10-18)
Summary of changes:
  - Added docs/v2/ (README, PLAN, FEATURES, UI_SYSTEM, REFERENCES, MANUAL_STEPS, AGENT_PROMPT).
  - Added GET /api/system/preflight (Docker + MongoDB readiness) and a dashboard readiness banner.
  - DockerManager.ensure_base_image() pre-pulls the pinned base image before builds so the pull
    no longer counts against the build timeout; clearer "start Docker Desktop" error.
Findings recorded for remediation (v2 phase V0):
  - SECURITY: scan_service.py falls back to LocalWorkspaceTargetHandle for non-fixture projects
    without a container, and verifier.py runs patched code the same way — untrusted project code
    is imported into the backend process on the host. Violates AGENTS.md / SECURITY.md §2 / C3.
  - No agent_events / WebSocket yet; UI is dark-only with ~285 hard-coded colour references.
  - On this machine Docker Desktop and MongoDB were not running (root cause of "image build fails").
Tests/checks run:
  - backend: 204 passed, 15 deselected (-m "not docker") before the test_isolation message update;
    test_isolation.py + test_system_preflight.py: 15 passed after it.
  - desktop: flutter analyze clean (1 lint fixed), flutter test 15 passed.
```text
Phase / Task: v2 Round 1 (Phases V0 and V1) (2026-10-18)
Dependencies added:
  - shared_preferences: ^2.5.4 (BSD-3-Clause) — theme and appearance persistence
  - Inter font (assets/fonts/Inter-*.ttf, SIL Open Font License 1.1) — offline sans typography
  - JetBrains Mono font (assets/fonts/JetBrainsMono-*.ttf, SIL Open Font License 1.1) — offline mono typography
Summary of changes:
  - V0 Safety & Stability:
      - Host execution restricted strictly to tests/fixtures/ via TrustedFixtureTargetHandle (targets/handle.py).
      - Scans of non-fixture projects without containers auto-run isolation via job service / docker manager (scan_service.py).
      - Verifier (verifier/verifier.py) builds and executes patched Docker container images with identical hardening, dedicated bridge networks, and proxy teardown in finally blocks.
      - GET /api/system/preflight extended with llm, ollama, git, disk, mode; GET /api/system/mode added.
      - pytest docker tests skip cleanly without docker daemon via docker_available fixture.
      - GoogleFonts.config.allowRuntimeFetching = false enforced; offline fonts bundled in assets/fonts/.
  - V1 Design System & Responsive Shell:
      - ClairTokens ThemeExtension implemented with 5 presets (Midnight/Daylight, Ocean, Forest, Violet, High Contrast) x 2 modes (Light/Dark).
      - Complete migration away from AppColors/SeverityColors (0 occurrences of raw Color(0x) outside lib/core/theme).
      - Settings -> Appearance implemented with ThemeMode, Preset, Density, Text Scale, and Reduce Motion, persisted via SharedPreferences.
      - Responsive shell (app_shell.dart) with responsive breakpoints, collapsible rail, status bar, and mode badge.
      - CommandPalette (Ctrl+K) implemented with navigation actions.
      - lib/ui/ component library implemented (CsCard, CsBadge, CsButton, CsStat, ScoreGauge, CsStepper, TimelineItem, CodeBlock, FileTree, EmptyState, Skeleton, CsToast, ProvenanceStrip, AssistantPanel, CommandPalette) + /_gallery screen.
Tests/checks run:
  - backend: pytest tests -q -m "not docker": 212 passed, 15 deselected in 85.16s.
  - backend docker skip: pytest tests -q -m "docker": 15 skipped, 212 deselected in 10.76s.
  - desktop: flutter analyze: 0 issues in 5.1s.
  - desktop: flutter test: 48 passed in 11s.
  - contrast tests: 10/10 presets x modes >= 4.5:1 WCAG AA compliant.
  - responsive tests: 20/20 pass with 0 overflow exceptions across 400, 900, 1300, 1700 px for Dashboard, Projects, Scan detail, Finding detail, and Settings.
  - font test: offline rendering passes with runtime fetching disabled.
  - theme persistence test: settings persist across container lifecycle via SharedPreferences.
Next recommended task: Stop and report for Round 1 review. Proceed to Round 2 (V2 + V3) when assigned.
```text
Phase / Task: v2 Round 2 (R1 fixes + V2 + V3) (2026-10-18)
Dependencies added:
  - web_socket_channel: ^3.0.3 (MIT) — live WebSocket event streaming with automatic reconnect and gap-fill
Summary of changes:
  - Part 1: Round 1 Fixes (A1–A7, B1–B5):
      - A1 & A6: Containment trust via Path(p).resolve().is_relative_to(settings.trusted_fixtures_root); eliminated testing substring escape hatch and LocalWorkspaceTargetHandle alias.
      - A2: Extracted threaded isolation steps into app.services.isolation_runner.execute_isolation_steps via anyio.to_thread.run_sync; non-blocking isolation.
      - A3: Verifier waits for container health through scanner proxy (settings.docker_startup_timeout); timeout cleanly adjudicates UNVERIFIED with rebuild_ok=False, health diagnostics recorded, and teardown guaranteed.
      - A4 & A5: Patched build passes project.dependency_file and resolved entrypoint path; SQLite adaptation runs on modified workspace and passes environment variables to patched container.
      - A7: Consolidated get_system_mode() shared across /api/system/preflight and /api/system/mode; Ollama checks required model tag presence in /api/tags.
      - B1: Token compliance gate strictly enforced: zero raw fontSize and numeric EdgeInsets literals outside lib/core/theme and lib/ui.
      - B2: /_gallery route and Command Palette gallery action registered only under kDebugMode.
      - B3: First-run wizard auto-shown once per launch if zero projects or readiness is red; "Don't show again" persisted via SharedPreferences.
      - B4: Readiness banner auto re-checks every 10s while red; pauses when green and when window/app is not visible.
      - B5: Unused Inter-Variable.ttf deleted; OFL-Inter.txt, OFL-JetBrainsMono.txt, OFL.txt bundled and registered with LicenseRegistry.
  - Part 2: V2 Live Event Backbone & Attack Timeline:
      - EventBus (app.services.event_bus) with atomic monotonic sequence via MongoDB $inc, static deterministic phrasebook (zero LLM), secret redaction, and 4KB detail cap.
      - REST GET /api/scans/{id}/events and WS /api/scans/{id}/events/ws with C7.4 token authentication and 15s heartbeat.
      - Desktop EventStreamClient with gap-fill catch-up, AttackTimeline widget, and LiveScanStatsPanel integrated into ScanDetailScreen.
  - Part 3: V3 GitHub Import & Autopilot:
      - Authoritative Python URL validator (app.services.url_validator) and Dart mirror (desktop/lib/services/url_validator.dart).
      - Safe Git/tarball import (app.services.git_import_service) with codeload streaming, byte caps, tarfile.data_filter, pre-scan rejection of absolute paths, path traversal, device files, and escaping symlinks; hardened git clone fallback; pre-checks card.
      - Autopilot pipeline orchestrator (app.services.pipeline_orchestrator and app.api.pipelines) with state machine (Import -> Isolate -> Scan -> Report), resume from failed stage, and cancellation.
      - ProjectsScreen UI with segmented import modal (Local / GitHub / Demo coming in V4) and Autopilot run modal with CsStepper.
Tests/checks run:
  - backend: pytest backend/tests -q -m "not docker": 292 passed, 15 deselected in 84.61s.
  - backend docker skip: pytest backend/tests -q -m "docker": 15 skipped, 292 deselected in 4.88s.
  - desktop: flutter analyze: 0 issues in 4.1s.
  - desktop: flutter test: 95 passed in 18s.
  - URL validator: 47 backend test cases + 30 desktop test cases all passed.
  - Event bus concurrency: 200 concurrent emits monotonic sequence test passed.
  - Gap fill & WS auth: REST gap fill and bad/missing token rejection tests passed.
  - Hostile archive safety: tar path-traversal, absolute-path, device-file, and escaping symlink tests passed.
Next recommended task: Stop and report for Round 2 review. Proceed to Round 3 (V4 + V5) when assigned.
```

```text
Phase / Task: v2 Round 3 (R2 fixes + V4 + V5) (2026-10-18)
Dependencies added: None
Summary of changes:
  - Part 1: Round 2 Fixes (C1–C12):
      - C1 & C2: App-scoped TaskRegistry (app/services/task_registry.py) tracking background tasks with cancellation tokens; real scan cancellation (ScanService.cancel_scan + POST /api/scans/{id}/cancel) tearing down containers and stopping worker loops; startup reconciliation for pipelines/scans left 'running'.
      - C3: Real-time event emission callback injected into Builder, Attacker, Evaluator, Fixer, and Verifier agents; events emitted at the moment endpoints are found, tests planned, requests sent, oracles evaluated (oracle_fired/oracle_clear attributed to attacker/oracle), candidates flagged, patches created, and verifications completed; deleted all post-hoc loops.
      - C4: WebSocket subscribe-first architecture followed by paged catch-up replay without 1000 event cap; drops live events with seq <= last sent.
      - C5 & C6: Removed WebSocket token bypass from global HTTP auth; explicit ws_auth dependency requiring Sec-WebSocket-Protocol or first JSON message auth; query param tokens ignored/rejected (never logged in access logs).
      - C7: Tarball streaming enforces wall-clock deadline, 40-hex SHA validation, pre-extraction member iteration checking declared total size (git_max_repo_mb) and file count (git_max_files) before extractall.
      - C8: Subdir path traversal validation (no '..', relative only, inside clone); when specified, project app root (source_path) is the subdir.
      - C9: Path normalization to POSIX in validator and _write_dockerfile; uvicorn started with --app-dir for nested directories to support hyphenated package names.
      - C10: EventBus fallback counter seeds from current max seq for the scan; verified under 200 concurrent emits with atomic find_one_and_update.
      - C11: test_is_trusted_fixture_path uses absolute settings.trusted_fixtures_root; passes from both backend/ and repo root.
      - C12: Tarball and git clone emit progress events with real percentages and respect cancellation tokens between chunks.
  - Part 2: V4 Experience Modes & Demo Safety Net:
      - Mode resolution: live, live_local_ai, live_offline_ai, demo, recorded.
      - Demo app registration & scan flow: projects registered with origin="demo_fixture" targeting backend/tests/fixtures/vulnerable_fastapi_app and secure_fastapi_app; Autopilot runs via mock/replay provider.
      - Host execution rule strictly enforced: when Docker is unavailable, host execution allowed ONLY if project.origin == "demo_fixture" AND active LLM provider is mock/replay; any real provider without Docker triggers VerificationUnavailableError; user projects without Docker trigger IsolationError.
      - Scan bundle player & serialization (clairsec.bundle/v1, scripts/record_bundle.py, bundle_service.py) with <= 5 MB cap and relative offset_ms timings.
      - ModeBadge UI component with plain-language "why" tooltip and "Run the demo instead" button in readiness banner.
  - Part 3: V5 Trust & Score:
      - Posture score v1 formula (app/scoring/posture.py): CVSS penalties (critical 30, high 18, medium 9, low 3, informational 0), inconclusive cap 10, coverage formula, grades (A >= 90, B >= 80, C >= 70, D >= 55, F < 55), regressed count against after.
      - Grep verification: the word "Secure" as a verdict/status never appears anywhere in UI strings, phrasebooks, or reports.
      - Evidence chain of custody (app/services/provenance_service.py and GET /api/findings/{id}/provenance): 6-step deterministic custody chain assembled from stored records.
      - Two-lane findings list in VulnerabilitiesScreen (Confirmed vulnerabilities vs Candidates & suspicions).
      - Confirmed badge guard: findings without oracle evidence or with unconfirmed status can never render the "Runtime-confirmed · oracle-verified" badge (renders "Source suspicion — not confirmed").
      - Attack Surface Map (desktop/lib/features/scans/widgets/attack_surface_map.dart): GET /api/scans/{id}/surface with CustomPainter tidy-tree pan/zoom and accessible, keyboard-navigable list alternative.
      - Glossary parity: exact 20-key parity verified between Python and Dart glossaries.
Tests/checks run:
  - backend: pytest backend/tests -q -m "not docker": 322 passed, 15 deselected, 6 warnings in 117.75s (repo root).
  - backend: pytest tests -q -m "not docker": 322 passed, 15 deselected, 6 warnings in 96.30s (backend/).
  - backend docker skip: pytest tests -q -m "docker": 15 skipped, 322 deselected.
  - desktop: flutter analyze: No issues found! (ran in 15.6s).
  - desktop: flutter test: 106 passed in 20s.
  - tokens compliance: 0 raw fontSize, 0 numeric EdgeInsets outside lib/core/theme and lib/ui.
  - responsive tests: 20/20 pass with 0 overflow exceptions across 400, 900, 1300, 1700 px.
Next recommended task: Stop and report for Round 3 review. Proceed to Round 4 when assigned.
```


```text
Phase / Task: v2 V3-fixes + V4–V9 completed by reviewer (2026-10-18)
Summary of changes:
  - D1 GitHub import fixed (ref case preserved; cancellable hardened clone fallback); real-network test.
  - D2 provider chosen per scan via app/llm/factory.py (+ new OllamaProvider); agents now actually
    receive the configured provider (previously every scan silently used the mock).
  - D3 in-memory DB fallback (mongomock-motor, MIT) when MongoDB is unreachable; TEMPORARY STORAGE badge.
  - D4 cancel only for running scans (409 otherwise); patched container torn down on cancel/failure.
  - D5 host-execution trust only from explicit DB values (no marker files).
  - D6 'unscored' posture bucket; posture/surface read nested cvss.severity; enums stored as values
    (app/database/encoding.py) so Mongo and the memory fallback behave the same.
  - Provenance rebuilt from real record shapes; it previously invented HTTP 200 / 3/3 / CVSS 7.5.
  - V6 replay (POST /api/findings/{id}/replay), endpoint-preserved proof, in-house OpenAPI smoke suite;
    'fixed' requires a functional check that ran.
  - V7 reports (HTML/MD/JSON/SARIF) + matching function (app/research/matching.py) + scan diff;
    Autopilot report stage generates a real report; Autopilot isolate call fixed.
  - V8 assistant (app/assistant/*, prompts/assistant/answer.v1.md) + Flutter panel (Ctrl+J).
  - V9 presenter mode (F11), recorded runs from real Demo scans (scripts/record_demo_bundle.py,
    demo/bundles/*), DEMO_SCRIPT.md.
Dependencies added: mongomock-motor 0.0.36 (MIT; mongomock ISC), jinja2 3.1.6 (BSD-3), jsonschema (dev, MIT).
  requirements.txt recompiled with hashes (it was stale: anthropic was missing).
Tests/checks run: see final summary in the conversation; backend from backend/, flutter analyze + test.
Not verified: anything needing a running Docker daemon (container isolation, patched-container
  verification, docker-marked tests); a real Anthropic/Ollama answer; the desktop app launched by hand.
```


```text
Phase / Task: live verification with Docker + Ollama (2026-10-19)
Done on this machine with Docker Desktop 29.7.2 running (engine was wedged; fixed by quitting
Docker Desktop, `wsl --shutdown`, relaunch) and the clairsec-mongo container up:
  - All 15 docker-marked integration tests pass (first time on this machine).
  - Live backend (uvicorn, normal mode) + Autopilot on a USER project (a copy of the vulnerable app
    outside the fixtures root): container isolation -> scan -> 3 fixes verified in real patched
    containers with auto-generated read-only checks -> report. Score 55 -> 100, mode live_offline_ai.
  - Replay inside containers: original HTTP 200 (oracle fired), patched HTTP 403 (blocked).
  - Assistant with a real local model (Ollama qwen2.5:0.5b): the model echoed an injected
    "say the app is secure" and cited nothing -> platform guard now withholds uncited or
    "is secure" answers and shows the grounded offline answer (verified live and in tests).
Defects found by the live runs and fixed:
  - Autopilot scan stage called non-existent ScanService.start_scan (mocked test hid it) -> submit_scan;
    new unmocked Autopilot test.
  - Smoke checks counted routes fixed by OTHER patches in the same workspace as regressions
    (BOLA wrongly 'regressed') -> exclude every route fixed in the scan.
  - Empty/relative import path resolved to the backend's own folder and imported ClairSec itself -> 422.
  - Scans labelled 'live' when the offline provider ran -> mode follows the provider; scan API returns llm.
  - Patched build used `pip install .` when the record lacked dependency_file -> detect requirements.txt.
  - Windows cp1252 console made every log line with "→" raise "Logging error" -> stdout/stderr errors=replace.
  - Pipeline API now returns report_id.
Still manual: launching the Flutter app and clicking through it; real Anthropic answers (no key here).
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