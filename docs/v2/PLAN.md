# ClairSec v2 — Phased Implementation Plan

**Window:** 2026-10-18 → presentation ≈ 2026-11-01 (two weeks).
**Specs:** `FEATURES.md` (what), `UI_SYSTEM.md` (how it looks), `REFERENCES.md` (prior
art). Base rules: `docs/RULES.md`, `docs/SECURITY.md`, `docs/THREAT_MODEL.md`,
`docs/ETHICS.md` — binding over anything here.

Work is delivered in **rounds**. Each round = a coding agent implements its phases,
then stops and reports (format in §4); the reviewer audits and issues the next round's
prompt. **Never start the next round's phases early** — an audit may change them.

---

## 1. Round & phase map

| Round | Phases | Theme | Target date |
|-------|--------|-------|-------------|
| R1 | V0, V1 | Make it safe, make it beautiful | 10-20 |
| R2 | V2, V3 | Make it live, import from GitHub | 10-23 |
| R3 | V4, V5 | Never fails on stage; trust & score | 10-26 |
| R4 | V6, V7 | Proof (replay, fix proofs) & reports | 10-28 |
| R5 | V8, V9 | AI assistant everywhere; polish & rehearsal | 10-30 |
| — | buffer | Audit fixes, rehearsals | 10-31 |

---

## 2. Phases

### V0 — Safety & stability foundation (F0, F1 backend part)

**Build**
- Remove host execution of non-fixture projects (F0): restrict the workspace target
  handle to trusted fixtures; scan auto-isolates or fails with `isolation_required`;
  verifier builds and runs a **patched container** from `modified_workspace/`.
- Extend `GET /api/system/preflight`: LLM provider + key-configured flag, Ollama
  reachability, git version, free disk, computed experience mode; add
  `GET /api/system/mode`.
- Docker-marked tests auto-skip without a daemon (`conftest.py` fixture).
- Bundle Inter + JetBrains Mono as assets; disable runtime font fetching.

**Done when**
- Canary test: a non-fixture project without a container is never imported by the
  backend process (canary file absent) — passes.
- Verifier test asserts a patched image build + hardened run (mocked Docker).
- Full backend suite passes with `-m "not docker"`; docker tests *skip*, not fail, with
  no daemon.
- App renders text with bundled fonts with networking disabled.

**Must not:** delete the fixture handle used by existing tests; weaken any container
hardening flag.

### V1 — Design system, themes, responsive shell (F1 UI part, F14 palette shell)

**Build**
- `ClairTokens` ThemeExtension (light + dark + 5 presets), typography, spacing, radius
  (`UI_SYSTEM.md` §2–§4); migrate **all** `AppColors`/`SeverityColors` usages; delete
  the old classes when references reach zero.
- Settings → Appearance (mode, preset, density, text size, reduce motion), persisted.
- Responsive app shell (`UI_SYSTEM.md` §5–§6): breakpoints helper, rail/drawer, top
  bar with mode badge + search entry + assistant toggle placeholder, status bar.
- `lib/ui/` component library (§7) and debug `/_gallery` route.
- First-run wizard + readiness banner on tokens (F1).
- Command palette (`Ctrl+K`) with navigation actions (F14 subset).

**Done when**
- `grep -R "Color(0x" lib/ | grep -v lib/core/theme` returns nothing.
- Contrast unit test passes for every preset × mode.
- Overflow-free widget tests at 400/900/1300/1700 px for Dashboard, Projects, Scan
  detail, Finding detail, Settings.
- Theme switch applies instantly and persists across restart.
- `flutter analyze` clean; all Flutter tests pass.

### V2 — Live event backbone & timeline (F5)

**Build**
- `agent_events` (schema, indexes, migration), `EventBus`, emission from every agent,
  job and pipeline stage; REST catch-up + authenticated WebSocket with `after_seq`.
- Desktop WebSocket client with reconnect/gap-fill; attack timeline; event-driven agent
  cards; live counters; cost/token meter.
- Plain-language `plain` field on every event (from a backend phrasebook keyed by event
  kind, not LLM-generated).

**Done when**
- Seq monotonic under 200 concurrent emits; reconnect test fills a gap; WS rejects bad
  token.
- A real fixture scan shows the full timeline in the app without refresh (manual check
  recorded in `MEMORY.md` with a screenshot path, or marked unverified if not run).

### V3 — GitHub import & Autopilot (F2, F3)

**Build**
- URL validator, tarball fetch + safe extract, hardened git fallback, limits, import
  pre-checks, monorepo candidate picker, file tree endpoint, authorization affirmation.
- Pipeline orchestrator (`POST /api/pipelines`) chaining import → isolate → scan →
  report with resume-from-failed-stage; stepper UI; plain-language stage lines.
- Projects screen segmented import (Local / GitHub / Demo).

**Done when**
- ≥ 25-case URL validator table test passes; tar path-traversal and symlink-escape
  fixtures are refused; size cap and timeout enforced; cancellation works.
- Pipeline state-machine tests (happy path, failure at each stage, resume, cancel).
- Manual: importing a small public FastAPI repo works end to end (record which repo, or
  mark unverified if the agent has no network).

### V4 — Experience modes & demo safety net (F4)

**Build**
- Mode resolution (Live / Live·local AI / Live·offline AI / Demo / Recorded replay) +
  top-bar badge + "why" tooltip; Ollama `LLMProvider`.
- Demo app flow: one click scans the bundled `vulnerable_fastapi_app`; "Trust check"
  scans `secure_fastapi_app`.
- Scan bundle format + `scripts/record_bundle.py` + replay player (1×/2×/5×/instant)
  feeding the same scan screen.

**Done when**
- Mode resolution tested for every dependency combination.
- With Docker stopped and no API key, Demo mode completes a real scan of the vulnerable
  fixture with ≥ 1 confirmed finding, and Trust check yields 0 confirmed findings.
- Bundle round-trip test passes; the recorded-run badge always shows the source date.

### V5 — Trust & score (F6, F7, F10)

**Build**
- `app/scoring/posture.py` (`posture_v1`) + persistence on scans + gauge UI + trend.
- Provenance endpoint + strip + two-lane findings list.
- Attack-surface endpoint + map (CustomPainter tree + list alternative) with live
  highlighting from events.

**Done when**
- Score formula table tests; "Secure" never appears anywhere (grep test over UI strings
  and report templates).
- A finding without an oracle record cannot render the confirmed badge (widget test).
- Surface builder unit test from fixture inventory.

### V6 — Proof: replay & fix proofs (F8, F9)

**Build**
- Replay endpoint/job (original + patched container), append-only replay test cases,
  side-by-side UI with highlighted leaked fields.
- Endpoint-preserved check; Schemathesis smoke suite against the container for
  projects without tests; three proof cards; `.patch` download.

**Done when**
- Demo fixture: original replay fires, patched replay clear.
- Delete-the-route patch fails "Endpoint preserved"; no-op patch fails "Exploit
  blocked".

### V7 — Reports (F12, F13)

**Build**
- Jinja2 HTML report (executive + technical + method + appendix), PDF, SARIF 2.1.0,
  Markdown, JSON; report jobs + download; Reports screen with preview.
- Scan-to-scan diff using the real matching function; trend chart.

**Done when**
- SARIF validates against the official schema; canary secret absent from every format;
  zero-finding report contains no "Secure"; report records model id, prompt versions,
  platform version, posture formula version and experience mode.

### V8 — Ask ClairSec assistant (F11)

**Build**
- Read-only tool layer, versioned assistant prompt, streaming endpoint, citations,
  suggested actions (user-clicked), conversation storage, offline rule-based answerer.
- Assistant panel on every screen with context + suggestion chips + "Explain simply".

**Done when**
- Tool tests; injection test; offline answers for every suggested question; the
  assistant has no code path that writes any finding/patch/scan field (test asserts the
  tool registry contains only read tools).

### V9 — Presenter polish & rehearsal (F14 rest)

**Build**
- Presenter mode, notifications, shortcuts sheet, glossary popovers everywhere,
  final consistency pass via the gallery, performance pass (no jank on 1 000-event
  timelines — use `ListView.builder`).
- `docs/v2/DEMO_SCRIPT.md`: a 7-minute talk track mapped to clicks, with a fallback
  branch for every step (Docker down → Demo; no network → skip GitHub step → bundled
  repo; LLM down → offline AI).

**Done when**
- Full demo script runs start to finish in Demo mode on a machine with Docker off.
- All suites green; `MEMORY.md` updated with what was verified manually.

---

## 3. Cross-cutting rules for every phase

- Backend: blocking work via `anyio.to_thread.run_sync`; long work is a job with events
  and cancellation; typed Pydantic models; redaction before persistence; new
  collections get `schema_version` + declared indexes + idempotent migration.
- Desktop: Riverpod providers per resource; services talk to the API only through
  `api_client.dart`; tokens/components only; every screen has its states.
- Tests: add tests with every feature; never delete or weaken an existing test to make
  a change pass — if a test is wrong, explain why in the report.
- Dependencies: justify each new one (license, maintenance) in `MEMORY.md`. Approved in
  advance: `web_socket_channel`, `shared_preferences`, `window_manager`, `pdf`,
  `printing`, `graphview` (if CustomPainter proves insufficient),
  `flutter_markdown_plus`, `jinja2`, `schemathesis`, `jsonschema`, `mongomock-motor` (in-memory DB fallback, added R4), `xhtml2pdf` (optional PDF). Forbidden: `litellm`,
  anything AGPL vendored into the codebase.
- Docs: update `docs/MEMORY.md` after each phase using its existing entry format; tick
  the phase in §5 below.
- Git: do not commit unless the user asks. If asked, focused commits, conventional
  messages, **no AI/assistant attribution trailers of any kind**.

---

## 4. Round report format (the agent must end every round with this)

```text
## Round Rn report
Phases attempted: Vx, Vy
### Per phase
- Status: done | partially done | blocked   (exit gate met? yes/no — quote each gate)
- What changed: files/modules (bullets, no full code)
- New endpoints / collections / settings
- Tests added (names) and results (exact pytest / flutter test summary lines)
- Manual verification performed (what, how, result) — or "not performed: <why>"
- Deviations from spec and why
- Known issues / risks / TODOs
### Commands to reproduce
- exact commands to run tests and the app
### Questions for the reviewer
```

Honesty rules for the report: never call something done because the code exists;
list skipped tests with reasons; say "unverified" when it is.

---

## 5. Progress tracker

| Phase | Status | Verified by | Notes |
|-------|--------|-------------|-------|
| V0 | done (re-audited 10-18) | reviewer: 291/292 backend pass from backend/ (1 cwd-dependent test, C11) | A1–A7 fixes confirmed in code |
| V1 | done (re-audited 10-18) | reviewer: flutter 95 passed, analyze clean | B1–B5 confirmed |
| V2 | done (re-audited R3) | reviewer: C3–C6, C10 fixes confirmed in code | real-time emits from agents, subscribe-first WS, token via subprotocol |
| V3 | done (fixed by reviewer 10-18) | real GitHub import re-verified (network test passes); D1 fixed | ref case preserved; cancellable hardened clone fallback; Autopilot isolate call fixed; demo projects skip container build |
| V4 | done (reviewer 10-18) | e2e: demo scan with NO Docker and NO MongoDB over HTTP → 3 confirmed, 3 verified, score 55→100 | D2 per-scan provider (no settings mutation; real provider now actually reaches agents); D3 in-memory DB fallback + TEMPORARY STORAGE badge; D4 cancel + patched teardown; D5 explicit trust; real bundles recorded from real Demo scans (demo/bundles) + Watch a recorded run |
| V5 | done (reviewer 10-18) | provenance rebuilt from real record shapes; score/surface read nested severities | provenance no longer invents HTTP 200 / 3/3 / CVSS 7.5; enums stored as values; gauge, provenance strip, surface map wired into real screens |
| V6 | done (reviewer 10-18) | replay e2e: original → oracle fired, patched → blocked, append-only; delete-the-route → regressed | in-house deterministic read-only OpenAPI smoke suite instead of Schemathesis; 'fixed' now requires a functional check that actually ran |
| V7 | done (reviewer 10-18) | SARIF validated against official 2.1.0 schema; canary absent in all formats; no 'secure' verdict | HTML/MD/JSON/SARIF; PDF via browser print (no PDF dependency); matching function (METHODOLOGY §3) + scan diff; Autopilot makes a real report |
| V8 | done (reviewer 10-18) | 9 backend tests incl. injection envelope + invented-citation drop; widget test | read-only tools, offline answerer, LLM path QUARANTINED; non-streaming (deviation) |
| V9 | done (reviewer 10-18) | presenter mode test; DEMO_SCRIPT.md | presenter mode (F11), recorded-run entry, demo script with fallbacks; visual rehearsal still manual |
