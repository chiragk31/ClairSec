# ClairSec — Project Status

**Adversarial Multi-Agent Security Platform for FastAPI Applications**

Last updated: 10 September 2026

---

## 1. What ClairSec Is

ClairSec imports a FastAPI project, runs it inside a hardened Docker container, and drives four
LLM agents plus a verification stage against it:

```
Import → Isolate → Builder → Attacker → Evaluator → Fixer → Verify → Report
```

The distinguishing property is that **nothing is reported as confirmed on a model's say-so**.
Every finding is backed by a real HTTP request and response captured against the running
application, and whether that exchange constitutes a violation is decided by deterministic
platform code — not by a prompt.

---

## 2. Current State

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repository bootstrap, health endpoint, config | Complete |
| 1 | Flutter desktop shell, theme, navigation | Complete |
| 2 | Project import, static FastAPI validation, persistence | Complete |
| 3 | Docker isolation, container lifecycle, workspace management | Complete |
| 3.5 | Foundation remediation (network isolation, auth, async, hygiene) | Complete |
| 4 | Builder agent + full LLM provider layer | Complete |
| 5 | Attacker agent + deterministic oracles | Complete |
| 6 | Evaluator agent + CVSS scoring + confidence | Complete |
| 7 | Fixer agent + patch engine + path containment | Complete |
| 8 | Re-test and verification (dual criterion) | Complete |
| 9 | Live agent UI (WebSocket streaming) | Not started |
| 10 | Report export | Not started |
| 11 | Research/evaluation harness | Not started |

**Test status:** 153 backend tests passing (12 Docker-marked, all passing with the daemon up),
13 Flutter tests passing, `flutter analyze` clean.

---

## 3. What Actually Works End to End

Verified by running it, not by assertion:

1. **Import** — folder picker validates a FastAPI project via AST parsing without executing any
   of its code. Detects entry point, parses dependency manifest.
2. **Isolate** — copies source to a scan workspace, generates a Dockerfile, builds an image, and
   starts a container with `cap-drop=ALL`, `no-new-privileges`, non-root user, read-only rootfs,
   pids/memory/CPU limits, on an internal network with no published ports. A scanner-side proxy
   container bridges to it for health checks and test traffic.
3. **Scan** — Builder discovers routes (AST first, OpenAPI second, LLM only for auth semantics);
   Attacker executes controlled tests through a scope-locked HTTP client; deterministic oracles
   adjudicate; Evaluator independently confirms from evidence alone; Fixer generates unified
   diffs; Verifier rebuilds and re-tests.
4. **Results in the UI** — Dashboard counters, scan list, findings with severity/CWE/status, a
   Fix Review screen showing the actual colour-coded diff, per-scan report summaries, and
   confirmed findings listed inline on the scan view. Every data screen has a refresh control.

### Measured result on the benchmark

Against `vulnerable_fastapi_app`:

| Finding | Severity | Status | Remediation |
|---------|----------|--------|-------------|
| BOLA at `GET /documents/{doc_id}` | Medium (CWE-639) | Confirmed | Fix verified |
| Mass assignment at `PUT /users/{user_id}/profile` | High (CWE-915) | Confirmed | Fix verified |
| Security misconfig at `GET /debug/config` | High (CWE-16) | Confirmed | Fix verified |

Against `secure_fastapi_app` (the false-positive control): **0 findings**.

Both numbers matter. A scanner that flags everything scores 3/3 on the first table.

### Example generated patch

```diff
     # VULNERABILITY: Missing ownership check
+    if doc["owner_id"] != current_user["user_id"]:
+        raise HTTPException(status_code=403, detail="Forbidden")
     return doc
```

---

## 4. Architecture

**Backend** — Python / FastAPI / Pydantic / Motor (MongoDB) / Docker SDK.
**Desktop** — Flutter / Dart / Riverpod / go_router / dio.
**Data** — MongoDB for structured scan records; local filesystem for workspaces.
**LLM** — provider abstraction, pinned model id, mandatory structured output, versioned prompt
files with a registry digest, full token/cost accounting.

### Key design commitments

- **Deterministic oracles.** Platform code decides whether a security test fired, from the
  recorded request/response pair. If an LLM decided, detection rate would measure the model's
  self-consistency rather than the system's capability.
- **Structural independence.** The Evaluator receives request, response and oracle result — never
  the Attacker's narrative and never the target's source.
- **Computed severity.** The Evaluator supplies CVSS v3.1 enum inputs with evidence citations;
  platform code computes vector, score and band using the FIRST equations. Inputs are stored so
  scores can be recomputed if the rubric changes.
- **Capability starvation.** Model output is never a shell command, file path, URL or executable
  source. It is a typed proposal that platform code validates before anything happens. This is
  the layer that holds even if prompt injection succeeds.
- **Dual-criterion verification.** A fix counts only if it blocks the exploit *and* leaves the
  functional suite passing. A patch that deletes the endpoint is recorded as `regressed`, not
  `fixed`.
- **Immutable source.** The original project is never modified — asserted by a recursive SHA-256
  checksum of the source tree before and after a full pipeline run.

---

## 5. Documentation

`docs/` is the source of truth. Sixteen documents covering intent and binding contracts:

| Document | Purpose |
|----------|---------|
| `README.md` | Read order and precedence |
| `PRD.md` | Product requirements |
| `ARCHITECTURE.md` | System boundaries, modules, API design |
| `RULES.md` | Non-negotiable engineering rules |
| `SECURITY.md` | Isolation and testing constraints |
| `THREAT_MODEL.md` | Threats against the platform itself, controls C1.1–C7.4 |
| `LLM.md` | Provider contract, prompt versioning, quarantine pattern |
| `VULN_TAXONOMY.md` | Closed category set with deterministic oracles |
| `METHODOLOGY.md` | Matching function, FDR definition, statistics |
| `DATA_MODEL.md` | Collection schemas, indexes, size caps |
| `ETHICS.md` | Coordinated disclosure, dual-use |
| `OPERATIONS.md` | CI, pinning, batch runner, packaging |
| `TESTING.md` | Test strategy + control traceability table |
| `DESIGN.md` | Desktop UI/UX requirements |
| `PHASES.md` | Roadmap with exit gates |
| `MEMORY.md` | Living project state |

---

## 6. Running It

```bash
# 1. MongoDB
docker start clairsec-mongo

# 2. Backend (generates the auth token the desktop client reads)
cd backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. Desktop client
cd desktop
flutter run -d windows
```

Or open the repo root in VS Code and use **Run and Debug → "Run Backend + Desktop"**.

**Order matters** — the backend must start first, because it generates the per-launch bearer
token that the Flutter client reads at startup.

### Tests

```bash
cd backend
..\venv\Scripts\pytest.exe -m "not docker and not llm" -v   # fast
..\venv\Scripts\pytest.exe -v                               # with Docker

cd desktop
flutter analyze && flutter test
```

---

## 7. Known Issues

### Fixed

1. **Auth token clobbered by the test suite** — `tests/conftest.py` called `initialize_auth()`
   against the real `~/.clairsec/auth_token`, so any `pytest` run 401'd a running backend and
   its connected client. A session-scoped autouse fixture now redirects `auth_token_path` to a
   temporary directory for the whole test session.
2. **Empty source locations on findings** — findings are produced from runtime evidence and
   carry no source position. Where the Fixer generated a patch, locations are now derived from
   the diff hunk headers, so the finding detail shows the affected file and line range.
3. **Re-isolation wedged a project** — pressing Isolate a second time failed with "scan
   workspace already exists" and left the project permanently in `import_failed`. Re-isolation
   now cleans up any stale workspace first and is idempotent.

### Outstanding

1. **No live event streaming.** The scan detail screen derives agent card state from the
   backend's reported stage, refreshed manually. WebSocket streaming is Phase 9.
2. **`GET /api/scans/{id}/findings` fans out client-side.** The Vulnerabilities screen requests
   findings per scan. Fine at demo scale; needs a dedicated endpoint if scan counts grow.
3. **Report export is summary-only.** The Reports screen presents per-scan metrics and findings;
   document export (PDF/HTML) is Phase 10.

---

## 8. Next Steps

- Fix the conftest auth-token issue (small, and it actively disrupts manual testing)
- Phase 9: WebSocket event stream with monotonic sequence numbers and reconnect
- Phase 10: report export
- Phase 11: research harness — four experimental arms, matching function, bootstrap CIs,
  McNemar's test, and the Tier A seeded benchmark at scale

---

## 9. Repository Layout

```
ClairSec/
├── backend/            FastAPI backend, agents, isolation, tests
│   ├── app/
│   │   ├── agents/     builder, attacker, evaluator, fixer, verifier
│   │   ├── api/        health, projects, isolation, jobs, scans
│   │   ├── isolation/  docker_manager, workspace
│   │   ├── llm/        provider, prompts, quarantine, redaction
│   │   ├── security/   oracles, http_client
│   │   └── services/   project, isolation, job, scan services
│   └── tests/          153 tests + benchmark fixtures
├── desktop/            Flutter desktop client
│   └── lib/
│       ├── features/   dashboard, projects, scans, vulnerabilities, fixes
│       ├── models/     typed API models
│       ├── providers/  Riverpod state
│       └── services/   API clients
├── docs/               16 specification documents
└── college-report/     Academic report (Chapters 1–3)
```
