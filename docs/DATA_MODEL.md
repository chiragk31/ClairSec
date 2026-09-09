# Data Model

> `ARCHITECTURE.md` §6 lists collection names. This document specifies their contents,
> indexes, size limits, and lifecycle. `RULES.md` §7 requires indexes on frequently
> queried fields and size limits on payloads; those are defined here, not left to
> whoever writes the repository class.

## 1. Conventions

- **Ids:** server-generated UUIDv4 strings, never `ObjectId` in the API surface. Every
  id used in a filesystem path or container name is validated against
  `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` before use
  (`THREAT_MODEL.md` C2.3).
- **Correlation:** every operational record carries `scan_id`. Every research record
  carries `run_id` and `experiment_id`.
- **Timestamps:** UTC, timezone-aware, ISO-8601 on the wire. Every document has
  `created_at`; mutable ones have `updated_at`.
- **Enums:** every status field is a closed Python enum, persisted as its string value.
  No free-form status strings.
- **Immutability:** `findings`, `agent_events`, `llm_calls`, `verification_results`,
  and `experiment_runs` are append-only. Corrections are new documents that supersede,
  never in-place edits (`METHODOLOGY.md` §10).
- **Schema version:** every document carries `schema_version: int`. Migrations live in
  `backend/app/database/migrations/` and are idempotent and forward-only.

## 2. Size limits

Unbounded documents are the fastest way to make a research database unusable.
Enforced at the repository layer, not by convention:

| Field kind | Cap | Overflow behaviour |
|-----------|-----|--------------------|
| HTTP request/response body in evidence | 64 KB each | Truncate, set `truncated: true`, store `sha256` of the full body |
| Container logs | 100 KB | Head + tail, middle elided |
| Error/reason strings | 2 KB | Truncate |
| Patch diff | 256 KB | Reject the patch; record `patch_too_large` |
| LLM raw text retained | 32 KB | Truncate |
| Source excerpt in a finding | 8 KB | Truncate around the cited line range |

Anything exceeding its cap after truncation goes to the filesystem artifact store
(`OPERATIONS.md` §6) with only a path and digest in Mongo.

## 3. Collections

### `projects`
Already implemented (Phase 2/3). Additions required: `schema_version`, `tier`
(`seeded` / `real_world` / `user`), `dataset_id` (nullable), `base_repo_public: bool`,
`base_repo_commit_date` (contamination analysis, `METHODOLOGY.md` §2.2).

Indexes: `{id: 1}` unique, `{isolation_status: 1}`, `{dataset_id: 1, tier: 1}`.

### `scans`
```text
id, project_id, arm, state, created_at, started_at, ended_at,
config_hash, prompt_registry_digest, model_descriptor, seed, trial_index,
cancel_requested: bool, terminal_reason: enum|null,
counters: {tests_executed, candidates, confirmed, rejected, inconclusive,
           fixes_proposed, fixes_applied, fixes_verified},
budget: {llm_calls, tokens_in, tokens_out, usd, wall_clock_s}
```
`state` follows the state machine in `ARCHITECTURE.md` §5.
Indexes: `{id:1}` unique, `{project_id:1, created_at:-1}`, `{state:1}`,
`{experiment_id:1, arm:1}`.

### `agent_events`
The WebSocket stream's durable backing store — the UI replays from here on reconnect,
so events must be ordered and gap-detectable.
```text
id, scan_id, seq (monotonic int per scan), agent, type, level,
message, payload (bounded), timestamp
```
Indexes: `{scan_id:1, seq:1}` unique. **`seq` is what makes reconnect correct**; a
client resubscribes with its last-seen `seq` and receives the gap.

### `agent_context`
Typed Builder output — the shared context other agents read. Never a text blob
(`ARCHITECTURE.md` §6).
```text
id, scan_id, route_inventory: [RouteSpec], auth_schemes: [AuthSpec],
models: [ModelSpec], principals: [TestPrincipal], openapi_present: bool,
config_findings: [...], truncation_notes: [...]
```

### `test_cases`
Every executed test, whether or not it produced a finding — required for
"tests executed" in `RESEARCH.md` §6 and for replay.
```text
id, scan_id, category, route_template, method, principal_id,
request: {method, url_path, headers(redacted), body(bounded)},
response: {status, headers(redacted), body(bounded), elapsed_ms},
oracle_result: {fired: bool, rule_id, rationale},
generated_by: {agent, prompt_id, prompt_version, llm_call_id|null},
executed_at
```
Indexes: `{scan_id:1}`, `{scan_id:1, category:1}`.

### `findings`
The vulnerability record from `PRD.md` §8, plus the fields the research requires:
```text
id, scan_id, project_id, title, category (VULN_TAXONOMY enum), cwe: [str],
route_template, method, description, impact,
runtime_confirmed: bool, oracle_rule_id,
cvss: {inputs: CvssInputs, vector: str, score: float, band: Severity},
confidence: {inputs: {...}, band: Confidence},
evidence_ids: [test_case_id], reproduction_summary,
source_locations: [{file, line_start, line_end}],
status: enum(suspected|candidate|confirmed|rejected|inconclusive),
status_reason, agent_provenance: {proposed_by, evaluated_by, prompt_versions},
duplicate_of: id|null, superseded_by: id|null,
created_at
```
Note `cvss.inputs` is stored alongside the score so the rubric can be recomputed if it
changes (`METHODOLOGY.md` §4). Storing only the score would make the study
irreproducible after any rubric revision.

Indexes: `{scan_id:1, status:1}`, `{project_id:1}`, `{category:1}`,
`{scan_id:1, route_template:1, method:1, category:1}` (the matching function's access path).

### `patches`
```text
id, finding_id, scan_id, files: [{path, diff}], diff_stats: {files, added, removed},
rationale, root_cause, prompt_version, llm_call_id,
applied: bool, applied_at, apply_error, workspace: "modified",
validation: {ast_parsed: bool, path_check_passed: bool, size_ok: bool}
```
`validation` records the `THREAT_MODEL.md` T8/C2.1 checks as data, so a rejected
patch is analysable rather than merely logged.

### `verification_results`
```text
id, finding_id, patch_id, scan_id,
rebuild_ok: bool,
original_exploit: {ran: bool, exploited: bool},
functional_suite: {ran: bool, passed: int, failed: int, newly_failing: [test_id]},
variant_attack: {ran: bool, exploited: bool, variant_kind},
outcome: enum(fixed|unresolved|unverified|regressed),
duration_s, created_at
```
`functional_suite` and `variant_attack` are **separate fields** — `RESEARCH.md` §5
requires robustness reported distinctly from verification, and `METHODOLOGY.md` §5
requires the dual criterion.

### `llm_calls`
```text
id, scan_id, agent, prompt_id, prompt_version, trust_level,
model_descriptor, usage: {input, output, cache_read, total}, cost_usd,
latency_ms, attempts, finish_reason, schema_valid: bool,
cache_hit: bool, cache_key, injection_attempt_detected: bool,
truncation_applied: bool, created_at
```
Indexes: `{scan_id:1}`, `{prompt_id:1, prompt_version:1}`.
This collection alone answers "cost per confirmed finding" (`LLM.md` §9).

### `datasets` / `dataset_projects`
Dataset manifest with per-project pinned source, commit sha, content digest, tier, and
the `SeededVulnerability` list (`METHODOLOGY.md` §2.1). A dataset is versioned and
immutable once an experiment references it.

### `experiments` / `experiment_runs`
```text
experiments:     id, name, hypothesis, arms, dataset_id, k_trials,
                 analysis_plan_path, preregistered_at, created_at
experiment_runs: id, experiment_id, arm, project_id, trial_index, scan_id,
                 metrics: {tp, fp, fn, duplicates, candidate_space_size, ...},
                 excluded: bool, exclusion_reason: enum|null,
                 config_hash, started_at, ended_at
```
`experiment_runs` is the append-only raw layer of `METHODOLOGY.md` §10. Summary tables
are computed from it and never written back into it.

### `reports`
Generated report metadata plus artifact path and digest; the rendered document lives
on the filesystem.

## 4. Redaction at write time

`THREAT_MODEL.md` C5.2 redaction runs **before** persistence, not before display.
Once a secret is in Mongo it is in every backup and every exported artifact. Headers
`authorization`, `cookie`, `set-cookie`, `x-api-key`, and `proxy-authorization` are
replaced with `<redacted:len>`; bodies pass the secret-pattern scrubber.

The exception: test-principal tokens minted by the platform itself are retained, since
reproduction requires them and they are worthless outside the scan. They are marked
`synthetic: true`.

## 5. Retention

- Scan workspaces: removed on cleanup; orphans garbage-collected at startup.
- `agent_events`: TTL of 90 days for `level=debug`; other levels retained.
- Research collections: never auto-expired.
- A `--purge-project` command removes all documents and artifacts for a project, used
  before publishing artifacts.

## 6. Migration and integrity

- Startup runs pending migrations, then asserts every declared index exists
  (`create_index` is idempotent) — never rely on an index having been created by hand
  on a developer machine.
- A `verify-integrity` command checks: every `finding.scan_id` resolves; every
  `evidence_id` resolves to a `test_case`; every `experiment_run.scan_id` resolves;
  no `experiment_run` references a mutated dataset digest.
