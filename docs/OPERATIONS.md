# Operations, Tooling, and Reproducibility

> None of the existing docs cover repository hygiene, CI, the batch experiment runner,
> observability, or how the research artifact gets published. Those are what turn a
> working prototype into something a second person can run.

## 1. Repository hygiene — fix before anything else

The repository currently has **no `.gitignore`**, and a full Python virtualenv plus
compiled `.pyc` files are committed. The committed `venv/` was built by a different
user on a different drive and does not work on any other machine, which means the
project as checked out is not runnable by anyone but its author. That is a
reproducibility failure at the root.

Required:

```gitignore
venv/
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.env
.env.*
!.env.example
workspaces/
artifacts/
desktop/build/
desktop/.dart_tool/
*.log
.DS_Store
```

Then `git rm -r --cached venv` and remove the tracked `__pycache__` trees. The history
rewrite is optional; stopping the bleeding is not.

## 2. Environment pinning

Reproducibility requires exact versions, and `requirements.txt` currently uses
`>=` ranges throughout — meaning two installs a month apart get different code.

- `requirements.in` (direct deps, ranges) → compiled to `requirements.txt`
  (fully pinned with hashes) via `pip-compile`. Commit both.
- `requirements-dev.txt` for test/lint tooling, kept separate.
- Pin the Python version in `.python-version` and assert it at startup.
- Pin the Flutter/Dart SDK constraint to a version the team actually has installed.
  The current `pubspec.yaml` requires Dart `^3.13.2`; a checkout on Flutter 3.38.7
  (Dart 3.10.7) fails at version solving, so `flutter pub get`, `analyze`, and `test`
  all fail. Either lower the constraint or document the required Flutter version in
  the README and CI.
- Record `docker version`, base image digests (by `sha256`, not tag), and OS in every
  experiment run.

## 3. Configuration

- All config through `pydantic-settings`, one `Settings` object, no scattered
  `os.environ` reads.
- `.env.example` committed with every key present and no real values.
- Startup **fails loudly** on a missing required setting. Never silently default an
  LLM API key, a Mongo URI, or a workspace root.
- Config values that affect results are hashed into `config_hash` and stored on every
  scan (`DATA_MODEL.md` §3).

## 4. CI

A pull request must not merge without:

| Gate | Tool |
|------|------|
| Lint + format | `ruff check`, `ruff format --check` |
| Types | `mypy --strict` on `app/`, no `Any` escapes in new code |
| Tests | `pytest -m "not docker and not llm"` |
| Docker integration | `pytest -m docker` on a runner with Docker available |
| Flutter | `flutter analyze`, `flutter test` |
| Secrets | `gitleaks` or equivalent over the diff |
| Dependency audit | `pip-audit` |
| Coverage floor | fail under an agreed threshold on `app/` |

The Docker-marked tests currently **fail rather than skip** when no daemon is present.
Add a session-scoped availability fixture that calls `pytest.skip` so a developer
without Docker Desktop running gets a clean signal instead of five red tests.

## 5. Runtime architecture — async discipline

`RULES.md` §6 says the UI must never freeze; the equivalent backend rule is missing
and is currently violated. `IsolationService.start_isolation` performs blocking
Docker I/O — including a 120-second image build — directly inside an `async def`
request handler, which stalls the entire event loop for every other request and every
WebSocket client for the duration of a build.

**Rules:**

- No blocking I/O in a coroutine. Wrap the `docker` SDK, `subprocess`, and filesystem
  copies in `anyio.to_thread.run_sync`, or move them behind a worker.
- Long operations (isolation, scans) are **background jobs** returning a job id
  immediately; progress arrives over WebSocket. `POST /isolate` returning `202` after
  doing 120 seconds of synchronous work is `202` in name only.
- Every job carries a cancellation token checked at phase boundaries and between HTTP
  requests, so `POST /scans/{id}/cancel` actually stops work.
- Every job has a wall-clock deadline enforced by the supervisor, not by the job.
- Graceful shutdown stops containers and marks in-flight scans `interrupted`.

## 6. Artifact store

Filesystem layout, separate from the workspace tree:

```text
artifacts/
├── scans/{scan_id}/
│   ├── evidence/          # oversized bodies referenced from Mongo by digest
│   ├── logs/
│   └── patches/
├── reports/{scan_id}/
└── llm_cache/             # content-addressed, see LLM.md §5
```

Content-addressed by `sha256`; Mongo stores path + digest only. A `verify-artifacts`
command re-hashes and reports drift.

## 7. Batch experiment runner

The headline experiment is roughly `50 projects × 4 arms × 3 trials ≈ 600 scans`.
That cannot be driven from the desktop UI, and `RESEARCH.md` §11 already requires the
evaluation engine to run without Flutter.

```bash
python -m app.research.runner \
  --experiment exp_001 --dataset ds_v1 \
  --arms multi_agent,multi_agent_no_eval,single_agent,traditional \
  --trials 3 --concurrency 4 --resume
```

Requirements:

- **Resumable.** Each `(arm, project, trial)` is an independently checkpointed unit;
  `--resume` skips completed units. A 600-scan batch will be interrupted, and
  restarting from zero is not acceptable.
- **Bounded concurrency**, with a global container cap so parallel targets do not
  exhaust host memory.
- **Per-unit isolation of failure**: one crashed scan records an exclusion reason and
  the batch continues (`METHODOLOGY.md` §8).
- **Deterministic ordering** with a recorded seed, so a resumed batch is comparable.
- **Live progress** to stdout and a machine-readable status file.
- `--dry-run` prints the unit plan and estimated token cost before spending anything.

## 8. Observability

- **Structured JSON logging** with `scan_id`, `project_id`, `agent`, `arm`, and
  `run_id` on every record. Never bare `print`.
- Log levels used meaningfully; the target's own output is logged as untrusted data,
  never interpolated into a format string.
- A `/api/metrics` endpoint exposing counters (scans by state, LLM calls, tokens,
  cost, container count) for a local dashboard.
- A live **cost meter** surfaced in the UI during research runs — the fastest way to
  notice a runaway loop is to watch spend, not logs.

## 9. Packaging

`PHASES.md` Phase 12 says "Packaging" and nothing else. Concretely:

- Backend distributed as a wheel plus a launcher that starts `uvicorn` bound to
  `127.0.0.1` on an ephemeral port, writes the port and auth token
  (`THREAT_MODEL.md` C7.2) to an owner-only file, and shuts down with the UI.
- Flutter desktop build per platform; document the Windows MSBuild/Developer-shell
  requirement already noted in `MEMORY.md`.
- A preflight check on first launch: Docker present and running, Mongo reachable, LLM
  key configured, disk space available — each with a specific remediation message
  rather than a generic failure.
- Version stamped from a single source and shown in the UI and in every experiment record.

## 10. Research artifact release

For the paper to be reproducible by a third party, publish:

1. Source at a tagged commit, with a DOI.
2. The dataset manifest: Tier A projects in full; Tier B as pinned URLs + commit shas
   (subject to the embargo in `ETHICS.md` §2.4).
3. Raw `experiment_runs` records — the append-only layer, not just summaries.
4. The analysis script that regenerates every table and figure from those records.
5. The redacted LLM response cache, enabling `replay` mode so a reviewer can re-derive
   results with no API key and no cost (`LLM.md` §5).
6. Prompt files at their exact versions, with the registry digest.
7. A `REPRODUCE.md` giving the exact commands, expected runtime, and expected cost.

Item 5 is the one most projects skip and the one that most increases the chance
anybody actually reproduces the work.
