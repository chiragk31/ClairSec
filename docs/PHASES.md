# Implementation Phases

Do not implement the entire project at once.

Each phase has a clear goal and definition of done.

Do not Implement the git setup user will manually perform this.

## How to read this document

Each phase has **Build** (what to make), **Done when** (the exit gate), and where
relevant **Must not** (the failure modes that make a phase look finished when it is
not). A phase is not complete because the code exists — it is complete when the exit
gate is demonstrably met and `MEMORY.md` records how it was verified.

Phases 0–3 are implemented. Phase 3.5 is remediation work identified by a review of
that implementation and must land before Phase 4 builds on top of it.

## Note on research track sequencing

Phase 11 (Research/evaluation) builds the full experiment harness, but do not wait until Phase 11 to validate whether the metrics pipeline itself works. As soon as Builder → Attacker → Evaluator exist end-to-end against the one intentionally vulnerable fixture app (see `TESTING.md` §5), start computing detection rate and false positive rate against that fixture, headless and without Flutter. This is a thin slice of Phase 11 pulled forward — not a new phase — so that a flawed evaluation/ground-truth design is caught around Phase 5–6 rather than after the desktop UI (Phases 9–10) is already built. Tier A seeded-benchmark project construction (see `RESEARCH.md` §7) should also begin during Phases 4–7, in parallel with agent development, rather than starting cold in Phase 11.

The metrics computed in that thin slice must use the **real matching function** from
`METHODOLOGY.md` §3, not an ad-hoc comparison. The point of pulling it forward is to
find out early whether that function is workable.

---

## Phase 0 — Repository bootstrap ✅ implemented

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

## Phase 1 — Flutter shell ✅ implemented

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

## Phase 2 — Project import ✅ implemented

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

## Phase 3 — Isolation and target lifecycle ✅ implemented

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

## Phase 3.5 — Foundation remediation ⚠️ required before Phase 4

Phase 3 shipped working isolation, but a review found four issues that Phase 4+ would
build on top of and make progressively more expensive to fix. This phase is small and
must land first.

### Build

- **Restore true network isolation.** The target network currently drops
  `internal=True` so the *host* can reach the container for health checks, which also
  lets a hostile target reach the user's LAN. Correct design: target on an
  `internal=True` network; health checks and Attacker traffic originate from a
  scanner-side container attached to both that network and a bridge.
  (`THREAT_MODEL.md` C3.3)
- **Container hardening:** `--cap-drop=ALL`, `no-new-privileges`, non-root user,
  read-only rootfs with a writable tmpfs, `pids-limit`. Never mount the Docker socket.
  (`THREAT_MODEL.md` C3.1, C3.2)
- **Async discipline.** Move blocking Docker/filesystem work off the event loop and
  make isolation a real background job with a job id, progress events, and working
  cancellation. `POST /isolate` currently performs a 120-second synchronous build
  inside an `async def`, stalling every other request. (`OPERATIONS.md` §5)
- **Identifier validation.** Validate `project_id` against the UUID pattern before it
  is used in any filesystem path or container name. (`THREAT_MODEL.md` C2.3)
- **Local API authentication.** Bind to `127.0.0.1`, per-launch bearer token, strict
  CORS and `Host` validation, authenticated WebSocket. (`THREAT_MODEL.md` T7)
- **Repository hygiene.** Add `.gitignore`, untrack `venv/` and `__pycache__`, pin
  dependencies, fix the Flutter SDK constraint mismatch, make Docker tests skip rather
  than fail when no daemon is present. (`OPERATIONS.md` §1, §2, §4)
- **Schema and index groundwork.** `schema_version` on documents; declared indexes
  asserted at startup. (`DATA_MODEL.md` §1, §6)

### Done when

A hostile target container cannot reach the host LAN, the backend stays responsive
during a 120-second image build, cancellation works, a fresh clone runs the test suite
on a second machine without manual repair, and every control above has a test.

### Must not

Proceed to Phase 4 with the event loop still blocking. Every later phase adds
long-running work, and retrofitting concurrency after four agents exist is far more
expensive than doing it now.

---

## Phase 4 — Builder agent

### Build

- Agent abstraction.
- LLM provider abstraction — implement `LLM.md` §1–§4 in full: typed request/response,
  pinned model descriptor, mandatory structured output, file-based versioned prompts
  with a registry digest.
- Project analyzer.
- Route discovery — **static AST extraction first, LLM second.** The route table is
  derivable deterministically from FastAPI decorators; use the LLM to interpret what
  static analysis cannot (auth semantics, ownership relationships), not to re-derive
  what it can. A deterministic route table also makes the `normalize()` step of the
  matching function reliable.
- OpenAPI extraction — from the running container's `/openapi.json` where available,
  which is authoritative and free.
- Structured context — the typed `agent_context` document, never a text blob.
- MongoDB persistence.
- **Quarantine pattern** for all target-derived text (`LLM.md` §6, `THREAT_MODEL.md` C1).
- **Secret deny-list and redaction** before any file content enters a prompt
  (`THREAT_MODEL.md` C5).
- **Token/cost accounting** per call from the first call (`DATA_MODEL.md` `llm_calls`).
- Test-principal provisioning: at least two distinct authenticated identities, which
  BOLA and BFLA testing require in Phase 5.

### Done when

Builder produces a structured API/project inventory for a test FastAPI project.

Additionally: the inventory is a validated typed document; a malformed LLM response
degrades gracefully and is recorded rather than crashing the scan; a fixture containing
a canary secret is provably never sent to the provider; and the full suite runs with a
mock provider and no network.

### Must not

Ship free-text-parsed output, floating model aliases, or inline f-string prompts.
Each of those is cheap now and irreversible once experiment records exist.

---

## Phase 5 — Attacker agent

### Build

- Test-case abstraction.
- Controlled request execution.
- Security test selection.
- Evidence capture.
- Candidate finding generation.

Start with a small set of well-defined API security categories rather than trying to support everything.

That set is now specified: the eight categories in `VULN_TAXONOMY.md` §2, each with
preconditions and a deterministic oracle. Additionally:

- **Deterministic oracles.** Whether a test fired is computed by platform code from the
  recorded request/response pair, never decided by an LLM (`VULN_TAXONOMY.md` §5).
  This is the load-bearing requirement of the entire research design.
- **Scope lock.** The Attacker's HTTP client rejects any request whose host is not the
  current scan's target container; no cross-host redirects
  (`THREAT_MODEL.md` T9, `ETHICS.md` §3).
- **Rate limiting and request ceilings** per scan (`SECURITY.md` §6, §10).
- **Non-destructive policy** enforced in code: no deletion of target data, no real DoS.
- Every executed test persisted to `test_cases` whether or not it fired — the
  denominator for "tests executed" and the basis for replay.
- Full request/response capture with redaction applied at write time.

### Done when

The Attacker can run reproducible tests and produce structured candidate findings.

Additionally: re-running the same scan with the LLM cache in `replay` mode produces the
identical test-case set; the scope lock has a test that proves an off-target request is
refused.

---

## Phase 6 — Evaluator agent

### Build

- Independent finding evaluation.
- Reproduction.
- Confidence.
- Severity.
- False-positive handling.
- Evidence normalization.

Plus:

- **Structural independence.** The Evaluator receives the *evidence* — request,
  response, oracle result — not the Attacker's narrative and not the target's raw
  source. This is what makes the independence claim in `RULES.md` §2 real rather than
  nominal, and it is also why the multi-agent arm should resist prompt injection better
  (`METHODOLOGY.md` §9).
- **Deterministic severity.** The Evaluator emits CVSS v3.1 *inputs* from closed enums
  with cited evidence; platform code computes the score and band
  (`METHODOLOGY.md` §4). An LLM-emitted severity string is not acceptable.
- **Structured confidence** computed from `runtime_confirmed`, `oracle_fired`,
  `reproduced_n_times`, `evidence_complete` — not a bare model float.
- Reproduction re-executes the test; a candidate that cannot be reproduced becomes
  `inconclusive`, never `confirmed`.
- Duplicate detection against already-confirmed findings in the same scan.

### Done when

Candidate findings can become:

- confirmed
- rejected
- inconclusive

with a recorded reason.

Additionally: severity is reproducible from stored inputs, and the thin evaluation
slice (see sequencing note) computes detection rate and FDR against the vulnerable
fixture using the real matching function.

---

## Phase 7 — Fixer agent

### Build

- Source-code location mapping.
- Patch generation.
- Diff generation.
- Patch validation.
- Workspace-only modification.
- Fix metadata.

Plus:

- **Path containment.** Every model-supplied path is resolved and rejected unless it
  is under `modified_workspace/`; symlinks are not followed
  (`THREAT_MODEL.md` C2.1, C2.2, C2.4).
- **Patches are unified diffs applied by platform code.** Never execute a
  model-produced shell command or `exec()` model-produced source
  (`LLM.md` §6 capability starvation).
- **Pre-apply validation:** the patched file must parse as Python (AST); diff size and
  file-count ceilings enforced; validation outcome persisted as data
  (`DATA_MODEL.md` `patches.validation`).
- The Fixer must not invent files — every target path must exist in the workspace
  inventory, and a hallucinated path is a recorded outcome.
- `modified_workspace/` is populated here; the convention was reserved in Phase 3.

### Done when

A confirmed finding can produce a reviewable patch in the isolated workspace.

Additionally: a patch attempting to write outside the workspace is refused and
recorded, and the original imported project is provably byte-identical after a full
scan (checksum test).

---

## Phase 8 — Re-test and verification

### Build

- Rebuild/restart target.
- Re-run original test.
- **Run the project's functional test suite and compare against the pre-fix baseline.**
  A fix that blocks the exploit by breaking the endpoint is not a fix. This dual
  criterion — exploit blocked **and** functionality preserved — is the standard the
  automated-repair literature applies, and results without it are not comparable
  (`METHODOLOGY.md` §5).
- Attempt one adapted variant of the same attack (mutated payload, alternate encoding, or different parameter targeting the same vulnerability class) after the original test is confirmed blocked — see "Post-fix robustness rate" in `RESEARCH.md`.
- Compare before/after behavior.
- Verification record, including the variant-attack outcome as a separate field from original-exploit verification, and the functional-suite outcome as a third distinct field.
- Fixed/unresolved/unverified states, plus `regressed` for a fix that blocks the
  exploit but breaks functionality.

### Done when

The platform can demonstrate whether a generated fix actually blocks the original test, whether functionality survived, and whether it also withstands at least one adapted variant of that attack.

### Must not

Report `fixed` on exploit-blocking alone. That single shortcut inflates every fix
metric in the study.

---

## Phase 9 — Live agent UI

### Build

- WebSocket event stream.
- Agent cards.
- Scan progress.
- Logs.
- Finding notifications.
- Cancellation.

Plus:

- **Durable, ordered events.** Events persist to `agent_events` with a monotonic `seq`
  per scan; the client reconnects with its last-seen `seq` and receives the gap
  (`DATA_MODEL.md`). A pure in-memory broadcast loses the stream on any hiccup during
  a 30-minute scan.
- Authenticated WebSocket (`THREAT_MODEL.md` C7.4).
- Cancellation propagates to a real cancellation token and stops container work —
  not just a UI state change.
- Progress reflects actual backend events; no synthetic progress (`RULES.md` §6).
- Backend-unreachable and scan-failed states are distinct and both explained.
- Live cost/token meter during the scan (`OPERATIONS.md` §8).

### Done when

A user can watch a real scan from start to completion without refreshing, and a client
that disconnects mid-scan reconnects without losing events.

---

## Phase 10 — Reports

### Build

- Scan summary.
- Finding details.
- Evidence.
- Fixes.
- Verification results.
- Export.

Plus:

- Redaction applied to every exported artifact (`THREAT_MODEL.md` C5.2).
- Precise status language from `SECURITY.md` §11 — never "Secure" merely because
  nothing was found.
- Findings that are source-suspicion only are visually distinct from
  runtime-confirmed ones.
- Report records the model, prompt versions, and platform version used.
- Fix review split view with the diff shown before any promotion (`DESIGN.md` §8).

### Done when

A completed scan can be exported as a useful security report that a maintainer could
act on without access to the tool.

---

## Phase 11 — Research/evaluation

### Build

- Experiment dataset representation, split into Tier A (seeded benchmark) and Tier B (real-world sample) per `RESEARCH.md` §7.
- **Four arms**, not three: `traditional`, `single_agent`, `multi_agent_no_eval`
  (ablation), `multi_agent` (`METHODOLOGY.md` §1). The ablation arm is what lets the
  study attribute any improvement to the Evaluator rather than to the system as a whole.
- Baseline runner: OWASP ZAP as the primary traditional-scanner baseline, Schemathesis as a secondary baseline where an OpenAPI schema is available — given the same OpenAPI schema, credentials, and wall-clock budget as the LLM arms.
- Single-agent runner.
- Multi-agent runner.
- Per-project LLM call/token budget ceiling, with `budget_exceeded` as a recorded outcome.
- **Executable matching function, severity rubric, and metric calculation**
  (`METHODOLOGY.md` §3–§5), applied identically to every arm.
- **Statistics:** bootstrap CIs over projects, McNemar's exact test for paired
  comparisons, Cohen's *h*, Holm–Bonferroni correction, k=3 trials with run-to-run
  stability reported (`METHODOLOGY.md` §6).
- **Contamination controls** and the pre/post-cutoff subgroup analysis
  (`METHODOLOGY.md` §2.2).
- **Blinded two-reviewer Tier B protocol** with Cohen's κ (`METHODOLOGY.md` §7).
- Metric calculation, including post-fix robustness rate (Phase 8), functional
  regression rate (Phase 8), and import failure rate (Phase 3).
- Resumable batch runner with bounded concurrency and per-unit failure isolation
  (`OPERATIONS.md` §7).
- Result export.
- A written, committed analysis plan **before** the full run (`METHODOLOGY.md` §6).

### Done when

Experiments can be reproduced and produce structured results suitable for analysis, and the thin evaluation slice pulled forward into Phases 5–6 has already validated that the metrics pipeline behaves sensibly before this phase's full-scale run.

Additionally: the analysis script regenerates every table from raw records with no
manual steps, and a 600-unit batch survives interruption and resumes.

---

## Phase 11.5 — Injection-resistance study

A small phase with a disproportionate payoff. The platform already feeds untrusted
target source to an acting LLM, so the secondary research question in
`METHODOLOGY.md` §9 costs a fixture set and a metric, and it is substantially more
novel than another detection-rate table.

### Build

- Paired Tier A variants: identical projects, one carrying injected instructions in
  comments, docstrings, and `README.md`.
- Three injection objectives: suppress a true finding, induce a fabricated finding,
  induce a write outside the workspace.
- `Injection Success Rate` and `Suppression Rate` per arm.
- `injection_attempt_detected` events surfaced as a measured quantity.

### Done when

Every arm has been run against both variants and the resistance comparison is
reported — including if the result is null or unfavourable to the proposed system.

---

## Phase 12 — Hardening

### Build

- Security review — against `THREAT_MODEL.md`, with the control-to-test traceability
  table complete (`TESTING.md` §10). Every control ID has a passing test or a
  documented, accepted residual risk.
- Permission checks.
- Resource limits.
- Timeouts.
- Secret handling review.
- Docker isolation review.
- Failure recovery — orphaned container/workspace garbage collection at startup,
  graceful shutdown, interrupted-scan reconciliation.
- Regression tests.
- Packaging per `OPERATIONS.md` §9, including the first-launch preflight check.

### Done when

The application is stable enough for demonstration and controlled research use, and
no control in `THREAT_MODEL.md` §5 is unimplemented and untested without an explicit
accepted-risk note.

---

## Phase 13 — Reproducibility artifact and disclosure

The research is not finished when the numbers exist.

### Build

- Tagged release, `REPRODUCE.md`, dataset manifest with pinned shas and digests.
- Raw `experiment_runs` export plus the analysis script.
- Redacted LLM response cache enabling `replay` mode with no API key
  (`LLM.md` §5, `OPERATIONS.md` §10).
- Prompt files at exact versions with the registry digest.
- Tier B coordinated disclosure executed and tracked per `ETHICS.md` §2, with
  disclosure-outcome rates reported as a result.
- Dual-use statement and limitations section.

### Done when

A third party with the artifact and no API key can regenerate every table in the
write-up, and every Tier B finding has a recorded disclosure state.

---

# Agent execution rule

After every phase:

1. Run tests/checks.
2. Verify the feature manually when practical.
3. Update `MEMORY.md`.
4. Do not begin a later phase if the current phase is fundamentally broken.
5. Preserve working behavior while extending the system.

Additionally:

6. Do not mark a phase done on the basis of code existing. Meet the exit gate.
7. If a phase's exit gate cannot be met, record why in `MEMORY.md` and stop rather
   than proceeding and accumulating the debt silently.
8. Report honestly: which tests ran, which were skipped and why, and what remains
   unverified.
