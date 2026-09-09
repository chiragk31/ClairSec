# System Architecture

## 1. High-level architecture

```text
Flutter Desktop
      |
      | REST + WebSocket
      v
FastAPI Application Backend
      |
      +----------------------+
      |                      |
      v                      v
Scan Orchestrator       MongoDB Context
      |
      +-------------------------------+
      |               |               |
      v               v               v
   Builder         Attacker       Evaluator
                                      |
                                      v
                                    Fixer
                                      |
                                      v
                                Verification
                                      |
                                      v
                               Scan Result
      |
      v
Docker / Isolated Runtime
      |
      v
Imported FastAPI Target
```

## 2. Technology stack

### Desktop

- Flutter
- Dart
- Riverpod for state management
- go_router for navigation
- Dio or equivalent HTTP client
- WebSocket client for live scan events
- A maintained chart library for metrics
- A maintained code/diff viewer for source inspection

### Backend

- Python
- FastAPI
- Pydantic
- asyncio
- httpx
- pytest

### Agent layer

Use a modular Python agent abstraction.

Do not tightly couple the product to one LLM vendor.

Provide an LLM provider interface so providers/models can be swapped for experiments.

### Persistence

- MongoDB for scan context, findings, agent events, projects, and experiment metadata.
- Local filesystem for scan workspaces, logs, temporary build artifacts, and generated reports where appropriate.

### Isolation

- Docker for running imported applications and controlled security tests.
- Each scan should have an isolated workspace and predictable lifecycle.

## 3. Backend module boundaries

Recommended structure:

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── projects.py
│   │   ├── scans.py
│   │   ├── vulnerabilities.py
│   │   ├── reports.py
│   │   ├── isolation.py
│   │   └── websocket.py
│   ├── agents/
│   │   ├── base.py
│   │   ├── builder.py
│   │   ├── attacker.py
│   │   ├── evaluator.py
│   │   └── fixer.py
│   ├── orchestration/
│   │   ├── pipeline.py
│   │   ├── state.py
│   │   ├── events.py
│   │   └── jobs.py            # background job supervisor, cancellation, deadlines
│   ├── security/
│   │   ├── target_manager.py
│   │   ├── test_engine.py
│   │   ├── oracles.py         # deterministic per-category oracles (VULN_TAXONOMY §5)
│   │   ├── scoped_client.py   # host-locked HTTP client (THREAT_MODEL T9)
│   │   ├── redaction.py       # secret deny-list + scrubber (THREAT_MODEL C5)
│   │   ├── evidence.py
│   │   └── policies.py
│   ├── isolation/
│   │   ├── docker_manager.py
│   │   ├── workspace.py
│   │   └── network.py         # internal network + scanner-side container
│   ├── llm/
│   │   ├── provider.py        # Protocol; see LLM.md §1
│   │   ├── providers/         # one module per vendor; the only place SDKs are imported
│   │   ├── prompts/           # versioned .md files + registry.py (LLM.md §4)
│   │   ├── quarantine.py      # untrusted-content envelope (LLM.md §6)
│   │   ├── cache.py           # content-addressed replay cache (LLM.md §5)
│   │   └── schemas.py
│   ├── patching/
│   │   ├── patch_service.py   # diff application; never executes model output
│   │   └── validation.py      # path containment, AST parse, size caps
│   ├── research/
│   │   ├── matching.py        # the matching function (METHODOLOGY §3)
│   │   ├── metrics.py
│   │   ├── statistics.py      # bootstrap, McNemar, effect sizes
│   │   ├── runner.py          # headless resumable batch runner (OPERATIONS §7)
│   │   └── arms/              # traditional | single_agent | no_eval | multi_agent
│   ├── database/
│   │   ├── client.py
│   │   ├── repositories.py
│   │   ├── migrations/
│   │   └── models.py
│   └── services/
│       ├── project_service.py
│       ├── isolation_service.py
│       ├── scan_service.py
│       └── report_service.py
└── tests/
```

`research/` must not import from `api/`. `RESEARCH.md` §11 requires the evaluation
engine to run without Flutter, and roughly 600 scans cannot be driven through a
desktop UI — so the dependency runs one way only.

Recommended Flutter structure:

```text
desktop/
└── lib/
    ├── main.dart
    ├── core/
    │   ├── networking/
    │   ├── routing/
    │   ├── theme/
    │   └── errors/
    ├── models/
    ├── providers/
    ├── services/
    └── features/
        ├── dashboard/
        ├── projects/
        ├── scans/
        ├── agents/
        ├── vulnerabilities/
        ├── fixes/
        ├── reports/
        └── settings/
```

## 4. API design

Use REST for CRUD and commands.

Example endpoints:

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{id}

POST   /api/scans
GET    /api/scans
GET    /api/scans/{id}
POST   /api/scans/{id}/cancel

GET    /api/scans/{id}/findings
GET    /api/findings/{id}

POST   /api/findings/{id}/apply-fix
POST   /api/findings/{id}/verify

GET    /api/reports/{scan_id}
```

Use WebSocket for:

```text
/ws/scans/{scan_id}
```

Events should be structured, for example:

```json
{
  "type": "agent.status",
  "scan_id": "scan_123",
  "seq": 417,
  "agent": "attacker",
  "status": "running",
  "message": "Testing endpoint",
  "timestamp": "..."
}
```

`seq` is a monotonic per-scan sequence number and events are persisted to
`agent_events` before broadcast. A client reconnecting mid-scan resubscribes with its
last-seen `seq` and receives the gap. A purely in-memory broadcast loses the stream on
any hiccup during a 30-minute scan, and the loss is silent.

### Long-running operations

Isolation and scans are **background jobs**, not synchronous handlers. A command
endpoint validates, enqueues, and returns a job id immediately; progress arrives over
the WebSocket. Blocking Docker, subprocess, and filesystem work runs off the event
loop (`RULES.md` §5a). Every job carries a cancellation token and a
supervisor-enforced deadline.

The local HTTP surface is authenticated and bound to `127.0.0.1`
(`SECURITY.md` §5a) — it drives Docker and writes to disk, so it is a privileged
interface even though it is local.

## 5. Agent state machine

Use explicit states instead of relying on informal LLM conversation:

```text
CREATED
  ↓
ANALYZING
  ↓
TARGET_READY
  ↓
ATTACKING
  ↓
EVALUATING
  ↓
FIXING
  ↓
VERIFYING
  ↓
COMPLETED
```

Allow safe terminal states:

- `COMPLETED`
- `FAILED`
- `CANCELLED`
- `PARTIAL`

## 6. Shared context

MongoDB is the shared persistence layer, but agents should communicate through typed records rather than arbitrary text blobs.

Suggested collections:

```text
projects
scans
agent_events
agent_context
test_cases
findings
patches
verification_results
reports
experiments
```

Use `scan_id` as the primary correlation identifier.

## 7. Separation of concerns

Flutter must not contain:

- LLM prompts
- security test logic
- Docker execution logic
- source-code patching logic
- database credentials

The Python backend owns those responsibilities.

The backend must not depend on Flutter-specific concepts.

## 8. Local desktop runtime

For the first version, prefer:

```text
Flutter executable
     +
Local Python backend process
     +
Local MongoDB / configured MongoDB instance
     +
Docker
     +
Remote or local LLM provider
```

Keep the backend modular enough that it can later be deployed remotely.