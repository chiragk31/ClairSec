# Implementation Phases

Do not implement the entire project at once.

Each phase has a clear goal and definition of done.

Do not Implement the git setup user will manually perform this.

## Note on research track sequencing

Phase 11 (Research/evaluation) builds the full experiment harness, but do not wait until Phase 11 to validate whether the metrics pipeline itself works. As soon as Builder → Attacker → Evaluator exist end-to-end against the one intentionally vulnerable fixture app (see `TESTING.md` §5), start computing detection rate and false positive rate against that fixture, headless and without Flutter. This is a thin slice of Phase 11 pulled forward — not a new phase — so that a flawed evaluation/ground-truth design is caught around Phase 5–6 rather than after the desktop UI (Phases 9–10) is already built. Tier A seeded-benchmark project construction (see `RESEARCH.md` §7) should also begin during Phases 4–7, in parallel with agent development, rather than starting cold in Phase 11.

## Phase 0 — Repository bootstrap

### Build

- Root documentation.
- Flutter desktop project.
- Python backend project.
- Basic environment/configuration system.
- Basic CI/test commands if appropriate.

### Done when

- Flutter launches.
- FastAPI backend launches.
- Health endpoint works.
- Project structure matches architecture.
- Documentation is present.

---

## Phase 1 — Flutter shell

### Build

- Desktop window/layout.
- Navigation.
- Theme.
- Dashboard placeholder.
- Projects page.
- Scans page.
- Vulnerabilities page.
- Settings page.

### Done when

The application feels like a coherent desktop product even though scanning is not implemented.

---

## Phase 2 — Project import

### Build

- Local folder selection.
- Project metadata.
- FastAPI project validation.
- Basic entry-point detection.
- Project creation API.
- Project persistence.

### Done when

A user can select a local FastAPI project and see a validated project record.

---

## Phase 3 — Isolation and target lifecycle

### Build

- Scan workspace creation.
- Docker target lifecycle.
- Start/stop/rebuild.
- Health checks.
- Logs.
- Timeout handling.
- Cleanup.
- Basic resource limits (CPU/memory/scan duration) — do not defer these entirely to Phase 12. Running 50+ unattended dataset scans later (Phase 11) depends on a misbehaving target not being able to hang the whole batch.
- Import failure fallback policy: if a project fails to build, resolve dependencies, or pass its health check within a defined number of automated attempts, mark it `import_failed` with a logged reason and stop attempting that project rather than retrying indefinitely or blocking other work.

### Done when

An imported FastAPI application can be safely launched, tested, stopped, and removed inside the controlled environment, and a project that cannot be containerized fails predictably into `import_failed` rather than hanging or crashing the pipeline.

---

## Phase 4 — Builder agent

### Build

- Agent abstraction.
- LLM provider abstraction.
- Project analyzer.
- Route discovery.
- OpenAPI extraction.
- Structured context.
- MongoDB persistence.

### Done when

Builder produces a structured API/project inventory for a test FastAPI project.

---

## Phase 5 — Attacker agent

### Build

- Test-case abstraction.
- Controlled request execution.
- Security test selection.
- Evidence capture.
- Candidate finding generation.

Start with a small set of well-defined API security categories rather than trying to support everything.

### Done when

The Attacker can run reproducible tests and produce structured candidate findings.

---

## Phase 6 — Evaluator agent

### Build

- Independent finding evaluation.
- Reproduction.
- Confidence.
- Severity.
- False-positive handling.
- Evidence normalization.

### Done when

Candidate findings can become:

- confirmed
- rejected
- inconclusive

with a recorded reason.

---

## Phase 7 — Fixer agent

### Build

- Source-code location mapping.
- Patch generation.
- Diff generation.
- Patch validation.
- Workspace-only modification.
- Fix metadata.

### Done when

A confirmed finding can produce a reviewable patch in the isolated workspace.

---

## Phase 8 — Re-test and verification

### Build

- Rebuild/restart target.
- Re-run original test.
- Attempt one adapted variant of the same attack (mutated payload, alternate encoding, or different parameter targeting the same vulnerability class) after the original test is confirmed blocked — see "Post-fix robustness rate" in `RESEARCH.md`.
- Compare before/after behavior.
- Verification record, including the variant-attack outcome as a separate field from original-exploit verification.
- Fixed/unresolved/unverified states.

### Done when

The platform can demonstrate whether a generated fix actually blocks the original test, and whether it also withstands at least one adapted variant of that attack.

---

## Phase 9 — Live agent UI

### Build

- WebSocket event stream.
- Agent cards.
- Scan progress.
- Logs.
- Finding notifications.
- Cancellation.

### Done when

A user can watch a real scan from start to completion without refreshing.

---

## Phase 10 — Reports

### Build

- Scan summary.
- Finding details.
- Evidence.
- Fixes.
- Verification results.
- Export.

### Done when

A completed scan can be exported as a useful security report.

---

## Phase 11 — Research/evaluation

### Build

- Experiment dataset representation, split into Tier A (seeded benchmark) and Tier B (real-world sample) per `RESEARCH.md` §7.
- Baseline runner: OWASP ZAP as the primary traditional-scanner baseline, Schemathesis as a secondary baseline where an OpenAPI schema is available.
- Single-agent runner.
- Multi-agent runner.
- Per-project LLM call/token budget ceiling, with `budget_exceeded` as a recorded outcome.
- Metric calculation, including post-fix robustness rate (Phase 8) and import failure rate (Phase 3).
- Result export.

### Done when

Experiments can be reproduced and produce structured results suitable for analysis, and the thin evaluation slice pulled forward into Phases 5–6 has already validated that the metrics pipeline behaves sensibly before this phase's full-scale run.

---

## Phase 12 — Hardening

### Build

- Security review.
- Permission checks.
- Resource limits.
- Timeouts.
- Secret handling review.
- Docker isolation review.
- Failure recovery.
- Regression tests.
- Packaging.

### Done when

The application is stable enough for demonstration and controlled research use.

---

# Agent execution rule

After every phase:

1. Run tests/checks.
2. Verify the feature manually when practical.
3. Update `MEMORY.md`.
4. Do not begin a later phase if the current phase is fundamentally broken.
5. Preserve working behavior while extending the system.