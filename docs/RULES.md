# Rules for AI Coding Agents

These rules are mandatory.

## 1. General engineering rules

- Inspect existing code before editing it.
- Do not rewrite working modules without a reason.
- Prefer small, testable changes.
- Keep responsibilities separated.
- Use typed models/schemas for agent communication.
- Avoid hidden global state.
- Use dependency injection where appropriate.
- Keep configuration in configuration files/environment variables.
- Never hard-code API keys, passwords, tokens, or database credentials.
- Do not commit secrets.
- Do not add dependencies unless they have a clear purpose.

## 2. Agent behavior

- Do not fabricate scan results.
- Do not call a vulnerability confirmed without evidence.
- Distinguish source-code suspicion from runtime confirmation.
- Every confirmed finding should have evidence or clearly state why runtime confirmation was unavailable.
- The Evaluator must be logically independent from the Attacker.
- The Fixer must not invent files or source locations.
- If the source cannot be safely modified, produce a patch proposal rather than pretending it was applied.
- Never claim a fix works until verification has been performed.

## 3. LLM rules

- Treat LLM output as untrusted data.
- Validate all structured model output with schemas.
- Do not execute arbitrary code returned by an LLM without passing it through the appropriate controlled execution path.
- Keep prompts versioned.
- Record model/provider information for research reproducibility.
- Handle malformed model responses gracefully.
- Use bounded retries.
- Avoid sending unnecessary source code or secrets to external providers.
- Never expose environment variables or credentials to the model.

The mechanisms are specified in `LLM.md` and are binding. The rules that are most
often violated in practice, restated concretely:

- **The model emits proposals, never actions.** Model output is never a shell command,
  never a file path used without validation, never a URL used without validation,
  never source passed to `exec()`. It is a typed structure that platform code
  inspects and decides upon. This single rule survives a successful prompt injection;
  the others do not.
- **Prompts are files, versioned, immutable once used in a recorded run.** Changing
  behaviour means adding `v4`, never editing `v3`. Inline f-string prompts are not
  acceptable.
- **`model_id` is pinned and fully qualified.** No `latest`, no undated aliases. A
  silent model change mid-dataset is undetectable after the fact and invalidates
  comparability.
- **Untrusted target text never enters a privileged planning prompt.** It passes
  through a quarantined extraction call that emits a typed schema first
  (`LLM.md` §6).
- **An LLM never decides whether a security test passed.** Oracles are platform code
  (`VULN_TAXONOMY.md` §5). An LLM never emits a final severity either — it supplies
  rubric inputs and code computes the score (`METHODOLOGY.md` §4).
- Retry only transport errors, 429, 5xx, and timeouts, with exponential backoff and
  jitter. A refusal or a schema violation is not a transient fault; retrying it
  unchanged is a loop.

## 4. Source-code modification rules

The original imported project must be treated as immutable input.

Use a separate scan workspace:

```text
original_project/
    ↓
scan_workspace/
    ↓
modified_workspace/
```

The Fixer modifies only the controlled workspace.

Every patch must have:

- source file
- old content/diff
- new content/diff
- reason
- finding ID
- timestamp
- verification result

Never silently overwrite the user's original files.

## 5. Error handling

Every external boundary must handle failure:

- filesystem
- Docker
- MongoDB
- LLM provider
- subprocess
- HTTP requests
- WebSocket
- project startup
- project shutdown

Errors must be:

- logged
- associated with a scan when possible
- shown to the user in understandable language
- represented by structured error states

Do not swallow exceptions silently.

## 5a. Concurrency rules

The UI rule below has a backend counterpart that is easy to violate invisibly.

- **No blocking I/O inside a coroutine.** The Docker SDK, `subprocess`, and
  `shutil.copytree` are blocking. Wrap them in `anyio.to_thread.run_sync` or move
  them behind a worker. A 120-second image build inside an `async def` stalls every
  other request and every WebSocket client for two minutes.
- Long operations return a job id immediately; progress arrives over WebSocket.
  Returning `202 Accepted` after synchronously doing the work is `202` in name only.
- Every long-running job carries a cancellation token checked at phase boundaries and
  between HTTP requests, so cancellation stops work rather than merely updating a
  status field.
- Every job has a supervisor-enforced wall-clock deadline.
- Shared mutable state between concurrent scans is not permitted; scans are isolated
  by `scan_id` at every layer.

## 6. UI rules

- Never freeze the Flutter UI during a scan.
- Long-running work belongs in backend processes.
- Show progress based on actual backend events.
- Do not fake progress bars.
- Clearly distinguish running, completed, failed, cancelled, and unverified states.
- Destructive actions require an explicit confirmation.

## 7. Database rules

- Use indexes for frequently queried fields.
- Always correlate records with `scan_id`.
- Avoid storing enormous raw payloads without size limits.
- Store structured evidence separately from display text.
- Never store secrets unnecessarily.

Schemas, the specific indexes, and the specific size caps are in `DATA_MODEL.md` and
are binding. Additionally:

- Indexes are declared in code and asserted at startup — never created by hand on one
  developer's machine.
- Redaction runs **before** persistence, not before display. Once a secret is in the
  database it is in every backup and every exported artifact.
- Research collections (`findings`, `test_cases`, `llm_calls`, `experiment_runs`,
  `verification_results`, `agent_events`) are append-only. Corrections supersede;
  they do not overwrite.
- Every document carries `schema_version`; migrations are idempotent and forward-only.

## 8. Testing rules

Before declaring a feature complete:

1. Run unit tests.
2. Run relevant integration tests.
3. Test failure paths.
4. Test cancellation for long-running operations where applicable.
5. Verify no secrets were introduced.
6. Verify the original project remains untouched.

## 9. Dependency rules

Prefer stable, maintained libraries.

Before adding a dependency, determine:

- whether an existing dependency already solves the problem
- whether it supports the required desktop/platform targets
- whether it is actively maintained
- whether its license is compatible with the project

## 10. Git rules

Use focused commits.

Examples:

```text
feat: add scan orchestration
feat: add attacker agent
fix: handle docker startup failure
test: add evaluator verification tests
ui: add live scan dashboard
```

Do not make giant unrelated commits.

## 11. When uncertain

Do not invent architecture.

Inspect:

- current code
- documentation
- types
- tests
- configuration

Then make the smallest safe assumption and document it in `MEMORY.md`.