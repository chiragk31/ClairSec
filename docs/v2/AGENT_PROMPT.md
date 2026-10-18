# Coding-Agent Prompts & Review Loop

## How the loop works

1. Paste the **current round prompt** below into the coding agent.
2. The agent implements only that round's phases and ends with the report format from
   `PLAN.md` §4.
3. Paste the agent's report back to the reviewer (Claude). The reviewer audits the code
   and tests, fixes or lists defects, and writes the next round's prompt here.

---

## Round 1 prompt (V0 + V1)

```text
/goal Implement Round 1 (phases V0 and V1) of the ClairSec v2 upgrade exactly as specified in docs/v2/, then stop and report.

## Context
ClairSec (repo root: D:\ClairSec) is a Flutter desktop app + FastAPI backend that imports a user's FastAPI project, runs it in a hardened Docker sandbox, attacks it with LLM agents, confirms findings with deterministic oracles, generates fixes and verifies them. Phases 0–8 of docs/PHASES.md are implemented. We are now executing the v2 upgrade in rounds; you are doing Round 1.

## Read first, in this order (do not skip)
1. AGENTS.md (repo root)
2. docs/README.md, docs/RULES.md, docs/SECURITY.md, docs/THREAT_MODEL.md, docs/DESIGN.md
3. docs/v2/README.md, docs/v2/PLAN.md, docs/v2/FEATURES.md (F0, F1, F14), docs/v2/UI_SYSTEM.md (all), docs/v2/REFERENCES.md
4. docs/MEMORY.md (latest entries) to learn the current state

## Your scope: PLAN.md phases V0 and V1 only
V0 — Safety & stability (FEATURES.md F0 + F1 backend):
- Remove every code path where a NON-fixture project's code is imported/run by the backend process on the host. Today: app/services/scan_service.py falls back to LocalWorkspaceTargetHandle when there is no container, and app/agents/verifier/verifier.py runs patched code via LocalWorkspaceTargetHandle. Restrict the host handle to trusted fixtures under backend/tests/fixtures/ (or settings.testing). Scans of non-fixture projects without a container must auto-run isolation first (reuse JobService/DockerManager). The verifier must build and run a PATCHED container image from modified_workspace/ with identical hardening, its own internal network and proxy, then tear it down.
- Extend GET /api/system/preflight (backend/app/api/system.py, already exists) with: llm provider + key_configured boolean (never the key), ollama reachability, git version, free disk in WORKSPACE_ROOT, computed experience mode; add GET /api/system/mode. Update the Flutter readiness banner (desktop/lib/features/dashboard/widgets/readiness_banner.dart, already exists) to show the new checks.
- Make @pytest.mark.docker tests skip (not fail) when no Docker daemon is reachable.
- Bundle Inter and JetBrains Mono as Flutter assets; disable google_fonts runtime fetching.

V1 — Design system & responsive shell (UI_SYSTEM.md §2–§11, FEATURES.md F1 UI + F14 command palette):
- ClairTokens ThemeExtension with light + dark and the 5 presets; typography/spacing/radius tokens; migrate ALL AppColors/SeverityColors usages (~285) to tokens, then delete the old classes.
- Settings → Appearance (mode System/Light/Dark, preset, density, text size, reduce motion), persisted with shared_preferences, applied instantly.
- Responsive shell per UI_SYSTEM.md §5–§6 (breakpoints helper, rail/drawer, top bar with mode badge + Ctrl+K search + assistant toggle placeholder, status bar).
- lib/ui/ component library (UI_SYSTEM.md §7) + debug-only /_gallery route showing every component in both modes.
- First-run wizard + readiness banner restyled on tokens.
- Command palette (Ctrl+K) with navigation actions.

## Hard rules
- docs/RULES.md, SECURITY.md, THREAT_MODEL.md, ETHICS.md outrank docs/v2. If they conflict, follow the base rule and report it.
- Never fabricate results or progress. Never run untrusted project code on the host. LLMs never decide pass/fail, severity or scores.
- Inspect existing code before editing; extend, don't rewrite working modules. Do not touch phases V2+.
- No raw Color(...) / font sizes / paddings outside lib/core/theme and lib/ui.
- Blocking backend work goes through anyio.to_thread.run_sync. Typed models everywhere.
- Never delete or weaken an existing test to make something pass; if a test is wrong, explain why in your report.
- New dependencies only from the approved list in PLAN.md §3; record each in docs/MEMORY.md with its licence.
- Do NOT commit or push unless explicitly asked. If you ever commit, add no AI/assistant attribution or Co-Authored-By trailers.
- Uncommitted work already in the tree (preflight endpoint, readiness banner, base-image pre-pull in docker_manager.py, tests/test_system_preflight.py) is intentional — build on it.

## Environment notes (this machine)
- Windows 11, Git Bash. Backend tests: from backend/, run D:/ClairSec/venv/Scripts/python.exe -m pytest tests -q -m "not docker" (if that venv fails, create a fresh venv from requirements.txt + requirements-dev.txt).
- Flutter 3.47.2 works: cd desktop && flutter analyze && flutter test.
- Docker Desktop and MongoDB may be stopped. If you cannot run something, say "unverified" with the reason — never claim it works.

## Exit gates (quote each one in your report with met / not met + evidence)
V0: canary test proves a non-fixture project without a container is never imported by the backend; verifier test asserts patched-image build + hardened run (mocked Docker); backend suite passes with -m "not docker" and docker tests skip without a daemon; fonts render with networking disabled.
V1: `grep -R "Color(0x" desktop/lib | grep -v lib/core/theme` is empty; WCAG contrast unit test passes for every preset × mode; overflow-free widget tests at 400/900/1300/1700 px for Dashboard, Projects, Scan detail, Finding detail, Settings; theme persists across restart; flutter analyze clean; all Flutter tests pass.

## When done
1. Update docs/MEMORY.md (existing entry format) and tick V0/V1 in docs/v2/PLAN.md §5.
2. Stop. Do not start V2.
3. Reply with the Round report exactly in the format of docs/v2/PLAN.md §4, including exact test summary lines, skipped tests with reasons, deviations, and open questions.
```

---

## Round 1 audit (reviewer, 2026-10-18)

Re-verified independently: backend `212 passed, 15 deselected`; docker-marked
`15 skipped`; `flutter analyze` clean; `flutter test` 48 passed. Test numbers in the
report were accurate. Defects found in the code behind them:

| ID | Severity | Defect | Where |
|----|----------|--------|-------|
| A1 | **Critical (security)** | `is_trusted_fixture_path` trusts any path containing `tests` and `fixtures` segments, so `workspaces/<id>/source/tests/fixtures/app` — e.g. a GitHub repo shipping `tests/fixtures/` — runs on the host. Reopens the hole V0 closed. | `targets/handle.py`, used by `scan_service.py`, `verifier.py` |
| A2 | **Critical** | Auto-isolation in a scan calls `IsolationService.start_isolation`, which runs `build_image` (≤600 s), `start_container`, `start_proxy`, `wait_for_healthy` and cleanup **synchronously inside a coroutine** — the whole backend freezes during a build (`RULES.md` §5a). | `scan_service.py` → `isolation_service.py:137-262` |
| A3 | High | Patched container is never health-checked before retest/functional suite; requests race container boot and a 502 can be read as "exploit blocked" or as a regression. Must wait for health and record `unverified` on timeout. | `verifier.py::_acquire_patched_handle` |
| A4 | High | Patched build passes `dependency_file=None`, so every `requirements.txt` project gets the `pip install .` template and fails to build. The test asserts the `None`, enshrining the bug. Default `entry_point or "main:app"` is also the wrong format (expects a path like `main.py`). | `verifier.py`, `tests/test_v0_safety.py:250` |
| A5 | Medium | Patched container gets no SQLite adapter env vars (`environment=None`), so SQLite apps fail on the read-only rootfs. | `docker_manager.start_patched_target` call site |
| A6 | Medium | `settings.testing` escape hatch trusts any path containing `workspaces`, `fixtures` or `dummy`; substring trust logic duplicated in `scan_service.py` and `handle.py`; `LocalWorkspaceTargetHandle` alias keeps a misleading name alive; mid-file import in `handle.py`. | `handle.py`, `scan_service.py` |
| A7 | Low | Report's manual claim "mode = live_offline_ai with Docker offline" contradicts the code (correctly `demo`). Duplicated mode code in `/system/preflight` and `/system/mode`; Ollama "ready" doesn't check the configured model is pulled. | `api/system.py` |
| B1 | Medium | 45 raw `fontSize: <number>` literals outside theme/ui (wizard 10, app_shell 9, …) and 7 numeric `EdgeInsets` — violates UI_SYSTEM §11. | `desktop/lib/features/**`, `app_shell.dart` |
| B2 | Medium | `/_gallery` route registered in all builds; spec says debug-only. | `app_router.dart:125` |
| B3 | Medium | First-run wizard only opens from a button; spec: auto-show when no projects exist or readiness is red (once per launch, dismissible). | `app_shell.dart:259` |
| B4 | Low | No 10 s auto re-check while readiness is red. | readiness provider |
| B5 | Low | Bundled fonts (SIL OFL 1.1) shipped without their licence files; unused `Inter-Variable.ttf` (~800 KB). | `desktop/assets/fonts/` |

---

## Round 2 prompt (R1 fixes + V2 + V3)

```text
/goal Fix every Round 1 audit defect (A1–A7, B1–B5 in docs/v2/AGENT_PROMPT.md), then implement Round 2 — phases V2 (live event backbone & attack timeline) and V3 (GitHub import & Autopilot) — exactly as specified in docs/v2/, then stop and report.

## Read first
1. docs/v2/AGENT_PROMPT.md — section "Round 1 audit" (the defect table is your first task list)
2. docs/v2/PLAN.md (V2, V3, §3, §4), docs/v2/FEATURES.md (F2, F3, F5), docs/v2/UI_SYSTEM.md (§5–§10 for the new screens)
3. docs/ARCHITECTURE.md §4 (API design, long-running operations), docs/DATA_MODEL.md (agent_events), docs/THREAT_MODEL.md C2, C3, C7.4, docs/ETHICS.md §1, docs/OPERATIONS.md §5
4. docs/MEMORY.md latest entries

## Part 1 — Round 1 fixes (do these FIRST; each needs a test that fails before the fix)
A1: Replace substring trust with containment. Add settings.trusted_fixtures_root (default: the absolute backend/tests/fixtures directory computed from the package location). is_trusted_fixture_path(p) = Path(p).resolve().is_relative_to(that root). Tests: a path like <tmp>/workspaces/<id>/source/tests/fixtures/app is NOT trusted; a symlink inside the fixtures root pointing outside it is NOT trusted.
A2: No blocking Docker call may run on the event loop. Extract the threaded isolation steps from JobService into one reusable async function (every DockerManager call via anyio.to_thread.run_sync) and use it from scan auto-isolation AND from IsolationService (or delete IsolationService if unused by routes — check first). Emit progress events (V2). Test: during a mocked 2-second build, a concurrent GET /api/health returns in < 200 ms (follow tests/test_async_discipline.py patterns).
A3: After start_patched_target, wait for health through the proxy (DockerManager.wait_for_healthy in a thread, settings.docker_startup_timeout). On timeout: outcome "unverified", rebuild_ok=False, reason includes the health diagnostics, and teardown still runs. Test both paths.
A4: Pass project.dependency_file and project.entry_point (path format, e.g. main.py) to the patched build; fix the test that asserted None.
A5: Run the same SQLite adaptation on the patched workspace as isolation does and pass its env_vars to the patched container. Test that the env reaches start_container.
A6: Remove the settings.testing substring escape hatch — tests instead point settings.trusted_fixtures_root at a tmp dir via monkeypatch. Single trust function used everywhere. Delete the LocalWorkspaceTargetHandle alias (update imports/tests). Move the mid-file import to the top. When Docker IS available, patched code of fixtures also runs in a container (LLM-written code should not run on the host when a sandbox exists); host fixture handle only when Docker is unavailable (Demo mode).
A7: One shared mode-resolution function for both endpoints; Ollama counts as ready only if /api/tags lists settings.ollama_model; add the setting.
B1: Add the missing typography/spacing tokens and replace all 45 raw fontSize literals and 7 numeric EdgeInsets outside lib/core/theme and lib/ui. Add a test (Dart file-scan test) that fails on any `fontSize: <digit>` or `EdgeInsets.*(<digit>` outside those folders — like the Color(0x gate.
B2: Register /_gallery only when kDebugMode (and omit it from the command palette otherwise). Test.
B3: Auto-show the first-run wizard once per launch when there are zero projects or readiness is red; "Don't show again" persisted. Test.
B4: Readiness auto re-check every 10 s while any check is red; stops when green and when the app is not visible if cheap to detect. Test with fake async.
B5: Add OFL.txt for Inter and JetBrains Mono under desktop/assets/fonts/ (from the upstream repos) and list them via LicenseRegistry; remove the unused Inter-Variable.ttf.

## Part 2 — V2 Live event backbone & timeline (FEATURES.md F5)
- agent_events collection (schema_version, unique index (scan_id, seq), migration), EventBus.emit(scan_id, agent, kind, title, detail, plain, refs) — never blocks or raises into agents; per-scan monotonic seq that is safe under concurrency (atomic counter document with $inc, not max(seq)+1).
- Emit from every agent stage, isolation steps, verifier steps, pipeline stages. `plain` text comes from a backend phrasebook keyed by kind (no LLM).
- GET /api/scans/{id}/events?after_seq=&limit= and WS /api/scans/{id}/events/ws?after_seq= with token auth before subscribe (C7.4), heartbeat 15 s, catch-up then live.
- Desktop: web_socket_channel client with reconnect + gap fill; Attack timeline (UI_SYSTEM §10 scan detail), event-driven agent cards, live counters, cost/token meter from budget events. Replace the existing polled event_stream_panel rather than keeping two mechanisms. Use ListView.builder.

## Part 3 — V3 GitHub import & Autopilot (FEATURES.md F2, F3)
- Pure URL validator (Python authoritative, Dart mirror for live UX) with the ≥25-case table test.
- Tarball path first: resolve ref→SHA (git ls-remote with the hardened env, or GitHub API), stream https://codeload.github.com/<o>/<r>/tar.gz/<sha> with byte cap + progress, extract with tarfile filter="data" (reviewer checked: the venv is Python 3.11.9 and tarfile.data_filter exists; host git is 2.52.0). Hardened git clone fallback exactly as specified. Git ≥ 2.45.1 check.
- Limits (timeout, size, file count), post-extract symlink check, import pre-checks card, commit_sha recorded, authorization_affirmed required (422 otherwise) and stored with timestamp, monorepo candidate picker, GET /api/projects/{id}/tree.
- Import works WITHOUT Docker (it executes nothing). Scanning afterwards requires isolation — the UI says so plainly.
- Pipeline orchestrator POST /api/pipelines + GET /api/pipelines/{id}, stage state machine with resume-from-failed-stage and cancellation, events per stage. "Report" stage may be a placeholder that records "report generation arrives in V7" — do not fake a report.
- Projects screen: segmented Local folder | GitHub URL | Demo app (Demo app tab may show "coming in V4" state), import stepper with real git/tarball progress, file-tree preview, import notes card, "Run full check" (Autopilot) with CsStepper.
- Tests: validator table; tar path-traversal, absolute-path, device-file and symlink-escape archives refused; size cap and timeout enforced; cancellation; pipeline state machine (happy path, failure at each stage, resume, cancel). Network-dependent tests must be mocked; if you can manually import a real small public FastAPI repo, record which one, otherwise mark it unverified.

## Hard rules (unchanged from Round 1 — still binding)
- Base docs (RULES, SECURITY, THREAT_MODEL, ETHICS) outrank docs/v2. Never fabricate results/progress; never run untrusted code on the host; LLMs never decide pass/fail, severity or scores.
- Extend, don't rewrite; tokens/components only in Flutter; blocking work via anyio.to_thread.run_sync; typed models; redaction before persistence.
- Never delete or weaken an existing test to make something pass (fixing the A4 test that asserted the bug is the one sanctioned exception — say so in the report).
- New deps only from PLAN.md §3's approved list (httpx is already present); record licence in MEMORY.md.
- Do NOT commit or push. No AI attribution anywhere.
- Your report's "manual verification" section must only contain things you actually ran; quote command + output.

## Exit gates (quote each with met / not met + evidence)
R1 fixes: every A/B item has a named test that failed before and passes after (state that you saw it fail).
V2: seq monotonic under 200 concurrent emits; reconnect gap-fill test; WS rejects missing/invalid token; widget test renders a scripted event list; manual fixture scan timeline seen in the app OR marked unverified with reason.
V3: ≥25-case validator test; hostile-archive tests; size cap, timeout, cancellation tests; pipeline state-machine tests; real-repo import recorded or marked unverified.
Global: backend `-m "not docker"` all pass; docker tests skip without daemon; flutter analyze clean; flutter test all pass.

## When done
Update docs/MEMORY.md and docs/v2/PLAN.md §5 (mark A/B items fixed), stop (do not start V4), reply with the round report in the PLAN.md §4 format.
```

## Round 2 audit (reviewer, 2026-10-18)

Re-verified independently: flutter analyze clean, `flutter test` 95 passed; backend
docker-marked 15 skipped; backend `-m "not docker"` **291 passed, 1 failed when run from
`backend/`** (the documented location — see C11; the agent ran from the repo root).
A1–A7 and B1–B5 fixes confirmed in code. The reviewer performed a **real GitHub import**
(`tiangolo/uvicorn-gunicorn-fastapi-docker` → 20 files, 66 KB, SHA resolved, valid, 3.2 s),
so the report's "offline environment" claim was wrong — network was available.

| ID | Severity | Defect | Where |
|----|----------|--------|-------|
| C1 | **High** | `PipelineOrchestrator` is constructed per request and keeps tasks in a per-instance dict: cancel from a new request finds no task (status says cancelled while work continues), nothing holds a strong reference to the task (asyncio may GC it mid-run), and no startup reconciliation for pipelines left `running`. `ScanService` has the same per-instance pattern. | `pipeline_orchestrator.py:61-124`, `api/pipelines.py`, `scan_service.py:103-170` |
| C2 | **High** | `ScanService.cancel_scan` does not exist; the orchestrator's call raises AttributeError which `except Exception: pass` swallows — cancelling during the scan stage silently does nothing. Scans have no real cancellation at all (PHASES.md Phase 9 requirement). | `pipeline_orchestrator.py:127-131` |
| C3 | **High** | The "live" timeline is not live: `test_planned`/`request_sent`/`oracle_fired` events are emitted in a loop **after** each agent stage returns, so a 5-minute attack shows nothing, then a burst with wrong timestamps; `oracle_fired` is attributed to the evaluator. Violates "progress reflects actual backend events" (RULES §6, PHASES Phase 9). | `scan_service.py:357-605` |
| C4 | High | WS sends catch-up, *then* subscribes — events emitted in between are lost; catch-up capped at 1000 with no paging. | `api/scans.py:380-392` |
| C5 | Medium | Desktop sends the launch token in the WS **query string**; uvicorn's access log prints WebSocket paths with query → token in logs. | `event_stream_client.dart:63-65` |
| C6 | Medium | Global `verify_token` returns `""` for any websocket scope, so every future WS route on an authenticated router is unauthenticated unless it remembers to self-check. | `core/auth.py` |
| C7 | Medium | Tarball: only compressed bytes are capped; extracted size/count checked *after* `extractall` (gzip bomb fills disk first). `httpx` timeout is per-read — a slow-drip server is never cut off (no overall deadline). Resolved SHA not validated as 40-hex before URL use. | `git_import_service.py:279-397` |
| C8 | Medium | `subdir` is unvalidated (`../..` traverses out of the clone) and, when given, `source_path` stays the repo root while entry point/dependency file are relative to the subdir → the build is wrong. | `api/projects.py:36`, `git_import_service.py:257` |
| C9 | Medium (demo-breaking for real repos) | On Windows, `entry_point`/`dependency_file` are stored with backslashes (`docker-images\requirements.txt`) and written verbatim into the Linux Dockerfile (`COPY`, `pip install -r`) → build fails; nested dirs with `-` give an invalid module (`docker-images.app.main`). Reproduced by the reviewer's real import. | `fastapi_validator.py`, `docker_manager._write_dockerfile` |
| C10 | Low | EventBus fallback counter restarts at 1 if Mongo `$inc` fails mid-scan → unique-index collisions drop events. The 200-concurrent-emit gate only exercised the in-memory fallback (`EventBus(db=None)`), not `$inc`. | `event_bus.py:70-91`, `test_event_bus_concurrency.py` |
| C11 | Low | `test_is_trusted_fixture_path` uses a cwd-relative path; fails when pytest runs from `backend/`. | `test_v0_safety.py` |
| C12 | Low | Import progress has only start/finish events (spec: real % from Content-Length / git progress); import cancel doesn't stop the worker thread (rmtree races the extraction). | `git_import_service.py` |

---

## Round 3 prompt (R2 fixes + V4 + V5)

```text
/goal Fix every Round 2 audit defect (C1–C12 in docs/v2/AGENT_PROMPT.md), then implement Round 3 — phases V4 (experience modes & demo safety net) and V5 (trust & score) — exactly as specified in docs/v2/, then stop and report.

## Read first
1. docs/v2/AGENT_PROMPT.md — "Round 2 audit" table (your first task list) and "Round 1 audit" for context
2. docs/v2/PLAN.md (V4, V5, §3, §4), docs/v2/FEATURES.md (F4, F6, F7, F10, and F5 for C3/C4), docs/v2/UI_SYSTEM.md (§2.2 severity, §7 ScoreGauge/ProvenanceStrip, §9 glossary, §10 dashboard/finding blueprints)
3. docs/SECURITY.md §11 (status language), docs/METHODOLOGY.md §4 (severity rubric), docs/VULN_TAXONOMY.md §2 and §5 (oracles), docs/LLM.md §5 (replay cache), docs/RULES.md §5a and §6
4. docs/MEMORY.md latest entries

## Part 1 — Round 2 fixes FIRST (each with a test that fails before the fix; say you saw it fail)
C1+C2: Create one app-scoped task registry (e.g. app/services/task_registry.py, created in lifespan or as a module singleton) that holds strong references to every background task (pipelines, scans, imports) keyed by id, with a cancellation token per task. Pipeline and scan services use it regardless of which request instance they are. Implement real scan cancellation: ScanService.cancel_scan + POST /api/scans/{id}/cancel; the attacker/verifier check the token between HTTP requests and stages; cancellation tears down containers it started. Replace the bare `except Exception: pass` with logged handling. On startup, reconcile pipelines/scans left `running` to `interrupted` (with reason). Tests: cancel from a *different* service instance stops the task; a cancelled scan stops issuing requests (fake target counts requests); startup reconciliation.
C3: Make events real-time. Give Builder/Attacker/Evaluator/Fixer/Verifier an injected emitter callback (default no-op) and emit at the moment things happen: endpoint discovered, each test executed with its real oracle outcome (`oracle_fired` / `oracle_clear` from the attacker's own oracle evaluation, attributed to "attacker"/"oracle", not evaluator), each candidate, each confirmation/rejection, each patch, each verification step. Delete the post-hoc emit loops. Test: a fake attacker that executes 3 tests with small sleeps produces request/oracle events whose timestamps interleave *before* the attacker stage_finished event.
C4: WS: subscribe first, then send catch-up (paged, no 1000 cap), then live; drop live events with seq <= last sent. Test with an event emitted between catch-up read and subscribe.
C5: Desktop sends the token via Sec-WebSocket-Protocol (or the first JSON message); the server ignores/rejects `token` query params (do not log them). Test that a query-param token is not accepted.
C6: Remove the websocket bypass from the global HTTP dependency; give WS routes an explicit `ws_auth` dependency; add a test that enumerates all app WebSocket routes and asserts each requires auth.
C7: Before extractall: iterate members, sum declared sizes and count; refuse if over git_max_repo_mb (extracted cap, set e.g. 4× the download cap) or git_max_files. Enforce an overall wall-clock deadline for download (monotonic check per chunk). Validate SHA with ^[0-9a-f]{40}$. Tests for each.
C8: Validate subdir (relative, no `..`, no absolute, resolves inside the clone, is a directory). When subdir is used, the project's app root (source_path for building) is the subdir. Tests: traversal refused; monorepo import builds from the subdir.
C9: Normalise entry_point and dependency_file to POSIX in the validator (as_posix) and in _write_dockerfile defensively; for an entry point in a nested directory, run uvicorn with `--app-dir <dir>` and the bare module name (so hyphenated directories work). Tests: Dockerfile for entry `docker-images\app\main.py` + dep `docker-images\requirements.txt` contains only forward slashes and a valid uvicorn command. If you can reach GitHub, re-import tiangolo/uvicorn-gunicorn-fastapi-docker and show the generated Dockerfile (Docker build itself may be unverified if no daemon).
C10: Fallback counter seeds from the current max seq for the scan; add a test using a fake collection that implements find_one_and_update atomically under 200 concurrent emits.
C11: Build that path from settings.trusted_fixtures_root (or Path(__file__)); suite must pass from both backend/ and repo root — run both and quote both summary lines.
C12: Emit import progress events with real percentages (bytes read / Content-Length; git --progress parsing for the clone path) and make cancellation set a flag the worker checks between chunks/members before cleanup.

## Part 2 — V4 Experience modes & demo safety net (FEATURES.md F4)
- Mode badge already exists; add the plain-language "why" tooltip and a "Run the demo instead" action in the readiness banner when Docker is down.
- Demo app flow: Projects → "Demo app" tab registers a project that points at backend/tests/fixtures/vulnerable_fastapi_app (origin: "demo_fixture", never copied out of the trusted root as the *run* path) and runs Autopilot. "Trust check" does the same with secure_fastapi_app. Both available from the first-run wizard and the command palette.
- Host execution rule for Demo mode (binding): when Docker is unavailable, the trusted fixture handle may run (a) the fixture itself and (b) its modified_workspace ONLY if project.origin == "demo_fixture" AND the active LLM provider is mock/replay (so no model-written code runs on the host). Any real provider without Docker → patched verification is "Verification unavailable" with a plain explanation. In Demo mode the scan forces the mock/replay provider. Tests for all four combinations.
- Scan bundle: versioned schema (`clairsec.bundle/v1`), `scripts/record_bundle.py <scan_id>` exports events (with relative timings), findings, test cases, patches, verification results (redacted, ≤ 5 MB); a bundle player feeds the same scan screen at 1×/2×/5×/instant with badge `RECORDED RUN · <source date>`; "Watch a recorded run" entry in Scans and the command palette. Ship no hand-made bundle — if you cannot run a real scan to record one, ship the tooling + tests and say so.
- Tests: mode resolution matrix; Demo scan of vulnerable fixture with Docker unavailable produces ≥ 1 confirmed finding (backend integration test with mock provider); Trust check on secure fixture produces 0 confirmed; bundle round-trip yields identical event sequence and finding set; widget test that the badge matches provider state.

## Part 3 — V5 Trust & score (FEATURES.md F6, F7, F10)
- app/scoring/posture.py (`posture_v1`, exact formula from F6), stored on the scan (`posture` field + migration), computed after evaluation and recomputed after verification; GET exposure on scan detail; ScoreGauge before→after sweep (reduce-motion aware), breakdown, "what moved the score", coverage line, greyed "Limited coverage" under 50 %; dashboard score trend per project.
- Provenance endpoint GET /api/findings/{id}/provenance assembled only from stored records; ProvenanceStrip on finding detail; two-lane findings list (Confirmed vs Candidates & suspicions); only Confirmed feeds score and dashboards.
- Attack-surface: GET /api/scans/{id}/surface from Builder inventory + findings + test cases; CustomPainter tidy-tree map with pan/zoom + keyboard-navigable list alternative; nodes light up from live events (C3).
- Plain-language glossary (UI_SYSTEM §9) in one Dart file and one backend file with a key-parity test; ⓘ popovers on technical terms on the screens you touch.
- Tests: formula table (edge cases: no findings + low coverage, all fixed, regressed counts against after); grep test that the string "Secure" (as a verdict) appears nowhere in UI strings or backend report/phrasebook text; finding without oracle record cannot render the confirmed badge; surface builder unit test from fixture inventory; glossary parity.

## Hard rules (still binding)
- Base docs (RULES, SECURITY, THREAT_MODEL, ETHICS) outrank docs/v2. Never fabricate results/progress; never run untrusted or model-written code on the host except the Demo-mode rule above; LLMs never decide pass/fail, severity or scores.
- Extend, don't rewrite; tokens/components only; blocking work via anyio.to_thread.run_sync; typed models; redaction before persistence; new collections/fields get schema_version + migration.
- Never delete or weaken a test to pass; if a test was wrong (C11), say so.
- Deps only from PLAN.md §3. Do NOT commit or push. No AI attribution anywhere.
- Run the backend suite from backend/ (the documented location) AND from the repo root; quote both lines.
- "Manual verification" lists only what you actually ran, with command and output. Do not claim the network is unavailable without showing the failing command.

## Exit gates (quote each: met / not met + evidence)
R2 fixes: every C item has a named test that failed before and passes after.
V4: mode matrix test; Demo-mode integration test ≥1 confirmed with Docker unavailable; Trust check 0 confirmed; four-combination host-execution rule tests; bundle round-trip; badge widget test.
V5: formula tests; no-"Secure" grep test; confirmed-badge guard test; surface builder test; glossary parity test.
Global: backend `-m "not docker"` all pass from backend/ and root; docker tests skip without daemon; flutter analyze clean; flutter test all pass.

## When done
Update docs/MEMORY.md and docs/v2/PLAN.md §5 (mark C items fixed), stop (do not start V6), reply with the round report in PLAN.md §4 format.
```

## Round 3 audit (reviewer, 2026-10-18)

Re-verified independently from `backend/`: **322 passed**, 15 docker skipped; flutter
analyze clean; **106 passed**. C1–C12 fixes confirmed in code (task registry with strong
refs, real-time agent emitters, subscribe-first WS, token via subprotocol, explicit
`ws_auth`, pre-extraction size/count caps, subdir validation, POSIX paths, `--app-dir`).
Posture formula matches F6; no hand-made bundle shipped (correct). Defects:

| ID | Severity | Defect | Where |
|----|----------|--------|-------|
| D1 | **Critical (feature broken)** | Real GitHub import is broken. `_resolve_sha_github` lower-cases the ref, so `HEAD` → `head` (refs are case-sensitive): ls-remote and the API both miss → SHA `None` → tarball skipped. The fallback then calls `_hardened_git_clone(..., cancellation_flag=...)`, but that method's signature is `(url_info, dest_dir)` → `TypeError`. Reviewer reproduced with `tiangolo/uvicorn-gunicorn-fastapi-docker` (worked in R2). Mocked tests hid both. | `git_import_service.py` `_resolve_sha_github`, line ~341 vs ~525 |
| D2 | High | Demo scans set the **global** `settings.llm_provider = "mock"` at runtime — every later scan (including Live scans with a real key) silently uses the mock until restart, and `/system/mode` reports wrong. | `scan_service.py:253` |
| D3 | High (presentation) | Demo mode is not actually independent: the backend refuses to start without MongoDB, and MongoDB was set up in Docker — Docker down ⇒ no backend ⇒ no Demo. Reviewer changed MANUAL_STEPS to a native MongoDB service; the code also needs a fallback (below). | `main.py` lifespan, `database/client.py` |
| D4 | Medium | Cancel teardown is dead code: `register_container` is never called, and it calls `docker_mgr.remove_container`, which doesn't exist. `cancel_scan` also overwrites already-`completed`/`failed` scans to `cancelled`. | `scan_service.cancel_scan`, `task_registry.py` |
| D5 | Medium (defence in depth) | `TrustedFixtureTargetHandle` grants host-execution trust from a `.source_path` marker **file** found in the workspace's parent/grandparent — a trust decision read from disk next to untrusted repo content. Not exploitable with today's callers, but one nested-path caller away from a repo shipping its own marker. | `targets/handle.py` |
| D6 | Low | Posture: an unknown/missing CVSS band silently costs 9 (medium). Make it explicit (`unscored` counted and shown in inputs). | `scoring/posture.py:138` |

Reviewer answers to the R3 questions: (1) Recorded runs load from `demo/bundles/` **plus**
an "Open bundle…" file picker (schema + size validated); no drag-and-drop needed.
(2) Yes — the coverage line opens a popover listing untested categories with the reason.

---

## Round 4 prompt (R3 fixes + V6 + V7)

```text
/goal Fix every Round 3 audit defect (D1–D6 in docs/v2/AGENT_PROMPT.md), then implement Round 4 — phases V6 (exploit replay & three-proof fix review) and V7 (reports & regression watch) — exactly as specified in docs/v2/, then stop and report.

## Read first
1. docs/v2/AGENT_PROMPT.md — "Round 3 audit" (your first task list + answers to your questions)
2. docs/v2/PLAN.md (V6, V7, §3, §4), docs/v2/FEATURES.md (F8, F9, F12, F13; F4 for D3), docs/v2/UI_SYSTEM.md (§7 HttpExchangeView/DiffView, §9 glossary, §10 finding/fix/reports blueprints), docs/v2/REFERENCES.md (Schemathesis, SARIF, ZAP report split)
3. docs/METHODOLOGY.md §3 (matching function) and §5 (dual-criterion), docs/SECURITY.md §7, §9, §11, docs/THREAT_MODEL.md C2, C5.2, docs/DESIGN.md §8, §10a
4. docs/MEMORY.md latest entries

## Part 1 — Round 3 fixes FIRST (each with a test that fails before the fix; say you saw it fail)
D1: Never change the case of a ref. Make the git fallback's call match its signature (add cancellation support to _hardened_git_clone properly: Popen + poll the flag + kill on cancel). Tests WITHOUT mocking the internal call chain: (a) `_sync_fetch_and_verify` with the tarball path forced to fail falls back to a hardened clone of a local bare-repo fixture and succeeds; (b) ref "HEAD" and a mixed-case branch name reach ls-remote unchanged. Add a `@pytest.mark.network` test that imports tiangolo/uvicorn-gunicorn-fastapi-docker for real (auto-skip when github.com is unreachable — implement the skip, don't just mark it). Run it and quote its output.
D2: No runtime mutation of `settings`. Select the LLM provider per scan (scan.mode / an injected provider) and pass it down to the agents. Test: after a demo scan, `settings.llm_provider` is unchanged and the next user-project scan receives the configured provider. Grep the codebase for any other `settings.<x> =` assignment outside config/tests and remove them.
D3: Backend must start and be useful without MongoDB. If Mongo is unreachable at startup, fall back to an in-memory database (`mongomock-motor`, MIT — approved for this purpose) behind the same `get_database()` interface; preflight reports `mongodb: {ok:false, fallback:"memory"}`; the UI shows a persistent `TEMPORARY STORAGE — results disappear when the app closes` badge next to the mode badge. Demo mode, Trust check and Recorded replay must work end-to-end on the memory fallback (indexes, $inc counters and find_one_and_update are used — verify they work there). Test: app startup with an unreachable MONGODB_URL + Docker unavailable → demo scan completes with ≥1 confirmed finding.
D4: Register every container a scan starts (isolation target/proxy when auto-isolated by that scan, patched target/proxy) and tear them down on cancel via existing DockerManager methods; delete the remove_container call. cancel_scan only acts on non-terminal scans (409 otherwise). Tests for both.
D5: Remove the marker-file trust path. Trust is decided only from `is_trusted_fixture_path(...)` on paths passed explicitly by the caller from the database record (source_path) plus the workspace being inside the platform's workspace root for that project id. Test: a repo that ships `.source_path` pointing at the fixtures root gains no trust for any nested path.
D6: Missing/unknown CVSS band → `unscored` bucket with an explicit penalty constant recorded in `posture.inputs` and shown in the breakdown. Test.

## Part 2 — V6 Proof: replay & three-proof fix review (FEATURES.md F8, F9)
- POST /api/findings/{id}/replay {target: original|patched} → job; re-sends the exact stored request via ScopeLockedHttpClient to the original container or a patched container (reuse the verifier's patched-container path incl. health wait); in Demo mode (no Docker) use the trusted fixture handle under the same host-execution rule as the verifier. Evaluate the same oracle; persist a NEW test_cases record kind="replay" (append-only, never overwrite); emit events. GET the replay result.
- UI: "Replay attack" on confirmed findings → side-by-side HttpExchangeView (original vs patched) with oracle verdict chips, redacted bodies, highlighted leaked fields (fields named by the oracle result), and the plain-language caption per category from the glossary.
- Endpoint-preserved check: route table of modified_workspace via the existing AST extractor must still contain the finding's route+method; result stored on the verification record as a third proof. Three proof cards above the diff in Fix Review (Exploit blocked / App still works / Endpoint preserved) with SECURITY.md §11 wording; `.patch` download; "AI explanation" label on any LLM-written summary.
- Auto-generated smoke suite: when a project has no functional tests, generate cases with Schemathesis from the target's /openapi.json **through the proxy URL** (`schemathesis.openapi.from_url` — never from_asgi); record the pre-fix passing set as baseline; post-fix regressions = previously-passing non-exploit cases now failing. Label "App still works (auto-generated tests)". Add schemathesis (MIT) to requirements with a pinned version; if it cannot be installed or run here, implement behind a feature flag with tests using a stub and say so.
- Tests: demo fixture original replay → oracle fired, patched replay → clear, original test case unchanged; delete-the-route patch fails Endpoint preserved; no-op patch fails Exploit blocked; smoke-suite baseline/regression logic with a stubbed schema runner.

## Part 3 — V7 Reports & regression watch (FEATURES.md F12, F13)
- Jinja2 (autoescape on) templates in app/reporting/templates/: Executive page (score before→after + grade, 3-sentence plain summary built from data, top risks with impact sentences, fixed & verified, needs-a-human), Technical findings (CWE + OWASP API Top 10 2023, CVSS vector + computed score, endpoint/method, redacted evidence, provenance, reproduction count, source location, diff, three proofs, replay result), Coverage & method (tested / untested categories with reasons, tests executed, limitations, model id, prompt versions, platform version, posture formula version, experience mode, storage mode), Appendix (test-case table, timeline excerpt).
- Formats: HTML (self-contained, light/dark + print CSS), Markdown, JSON, SARIF 2.1.0 (stable tool.driver.name "ClairSec", CWE in taxa, CVSS in properties), PDF (choose backend xhtml2pdf OR desktop pdf/printing — justify in MEMORY.md; if neither is installable here, ship HTML-print instructions and say so).
- POST /api/scans/{id}/reports {formats, audience} → job → files under WORKSPACE_ROOT/reports/<scan_id>/; GET /api/reports/{id}/download?format=. Redaction before rendering. Autopilot's Report stage now generates the real report (replace the placeholder).
- Reports screen: list per scan, preview (native preview from report JSON), Executive/Technical toggle, export buttons, "Open folder", "Compare with previous scan".
- Regression watch: GET /api/projects/{id}/scan-diff?base=&head= using the real matching function from METHODOLOGY.md §3 (one Python implementation): New / Fixed since last scan / Still open / Came back; score trend chart per project; GitHub projects get "Check for new commits" (re-import at HEAD as a new project version + Autopilot; diff shows both commit SHAs).
- Tests: SARIF validates against the official 2.1.0 JSON schema (vendor the schema file into tests, record its source URL); a canary secret present in evidence is absent from every exported format; a zero-finding report never contains "Secure" as a verdict; report records model id, prompt versions, platform version, posture version, experience mode, storage mode; scan-diff with constructed finding sets for all four buckets.

## Hard rules (still binding)
- Base docs (RULES, SECURITY, THREAT_MODEL, ETHICS) outrank docs/v2. Never fabricate results/progress; never run untrusted or model-written code on the host except the Demo-mode rule; LLMs never decide pass/fail, severity, scores or report verdicts.
- Extend, don't rewrite; tokens/components only; blocking work via anyio.to_thread.run_sync; typed models; redaction before persistence AND before export; schema_version + migrations for new fields/collections.
- **Tests must exercise the real code path.** Mocks are allowed at process/network boundaries only (Docker daemon, remote HTTP, LLM provider) — not between our own functions. Every round so far had a defect that a mocked internal call hid.
- Never delete or weaken a test to pass. Deps: PLAN.md §3 list plus mongomock-motor, schemathesis, xhtml2pdf (if chosen) — pin versions, record licences in MEMORY.md.
- Run the backend suite from backend/ AND repo root; quote both. Do NOT commit or push. No AI attribution anywhere.
- "Manual verification" lists only what you actually ran, with command and output. Network IS available on this machine (the reviewer imported from GitHub) — don't claim otherwise without the failing command.

## Exit gates (quote each: met / not met + evidence)
R3 fixes: every D item has a named test that failed before and passes after; the network import test ran for real and passed (quote it).
V6: replay original→fired / patched→clear on the demo fixture with append-only records; endpoint-preserved test; three proof cards widget test; smoke-suite logic tests.
V7: SARIF schema validation; canary-redaction across all formats; no-"Secure" test; metadata test; scan-diff four-bucket test; Autopilot produces a real report.
Global: backend `-m "not docker"` all pass from backend/ and root; docker tests skip without daemon; flutter analyze clean; flutter test all pass.

## When done
Update docs/MEMORY.md and docs/v2/PLAN.md §5 (mark D items fixed), stop (do not start V8), reply with the round report in PLAN.md §4 format.
```

## Round 5+ prompts

Written by the reviewer after auditing each round.

## Status after Round 3 (2026-10-18)

At the user's request the reviewer implemented the rest directly instead of issuing a
Round 4 prompt: all Round 3 audit items (D1–D6) plus phases V6–V9, and several defects
found along the way (provenance fabricating defaults, posture never updating after
verification, scans never using the configured LLM provider, Autopilot's isolate stage
crashing for real projects, enum storage diverging between MongoDB and the memory
fallback, cwd-dependent bundle directory, bundle-name path traversal). See
`docs/MEMORY.md` (latest entry) and `PLAN.md` §5. No further agent rounds are planned;
remaining work is the manual verification in `MANUAL_STEPS.md`.
