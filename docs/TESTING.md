# Testing Strategy

## 1. Testing pyramid

```text
             E2E
            /   \
      Integration
        /       \
      Unit tests
```

## 2. Backend unit tests

Test:

- Pydantic schemas
- agent state transitions
- repository methods
- finding classification
- severity logic
- patch validation
- verification result logic
- configuration validation
- error handling

## 3. Agent tests

Use deterministic fixtures where possible.

Do not make the entire test suite depend on a live LLM provider. **No test in the
default suite may require network access or an API key.** Marked `llm` tests may hit a
live provider and are excluded from the default run.

Create mock LLM responses for:

- valid output
- malformed output
- refusal
- timeout
- hallucinated file
- invalid patch
- contradictory result
- schema-violating output that is then repaired on the single retry
- schema-violating output that fails twice — the agent must degrade, not crash
- a path-traversal file path (`../../etc/...`)
- an oversized response exceeding the token/size cap
- output echoing an injected instruction from target content
- output claiming a severity inconsistent with its own cited evidence

## 3a. Determinism and replay tests

- The same scan run twice in `replay` cache mode produces an identical test-case set
  and identical findings.
- A cache miss in `replay` mode is a hard error, not a silent live call.
- The prompt registry digest is stable across runs and changes when a prompt changes.
- `config_hash` changes when any result-affecting setting changes.

## 4. Docker integration tests

Verify:

- target starts
- health check succeeds
- target stops
- failed builds are handled
- timeouts work
- resources are cleaned up
- workspace isolation works
- the target cannot reach the host LAN (`THREAT_MODEL.md` C3.3)
- the Docker socket is not present inside the container
- resource limits are actually applied to the running container, not merely requested
- orphaned containers and workspaces are garbage-collected at startup

Docker-marked tests must **skip**, not fail, when no daemon is available. Use a
session-scoped availability fixture calling `pytest.skip`. Five red tests on a
developer machine without Docker Desktop running is a false signal that trains people
to ignore the suite.

## 5. End-to-end tests

At least one intentionally vulnerable toy FastAPI application should be included as a controlled fixture.

The E2E flow should verify:

```text
import
→ build
→ start
→ discover
→ attack
→ evaluate
→ patch
→ restart
→ verify
→ report
```

### Required fixture applications

| Fixture | Purpose |
|---------|---------|
| `valid_fastapi_app` | Healthy baseline (exists) |
| `broken_fastapi_app` | Build failure → `import_failed` (exists) |
| `vulnerable_fastapi_app` | One seeded vulnerability per `VULN_TAXONOMY.md` category, each with an executable PoV **and** a functional test suite |
| `secure_fastapi_app` | The same endpoints, correctly secured — the false-positive fixture. Any finding here is a FP by construction. |
| `injected_fastapi_app` | Identical to `vulnerable_fastapi_app` plus prompt-injection payloads in comments, docstrings, and `README.md` |
| `hostile_fastapi_app` | Attempts host egress, socket access, fork bomb, and disk fill — verifies containment, not detection |

`secure_fastapi_app` is as important as the vulnerable one and is the fixture most
often omitted. Without it the suite can only measure recall, and a system that reports
every endpoint as vulnerable passes.

## 5a. Fix verification tests — dual criterion

A patch is verified only if it blocks the exploit **and** leaves the functional suite
passing (`METHODOLOGY.md` §5). Required cases:

- fix blocks exploit, functional suite passes → `fixed`
- fix blocks exploit, functional suite regresses → `regressed`, never `fixed`
- fix does not block exploit → `unresolved`
- verification could not run (rebuild failed) → `unverified`
- fix blocks the original exploit but not the variant → `fixed` with
  `variant_attack.exploited = true`

The second case is the one that matters: a patch that deletes the endpoint blocks the
exploit perfectly. If the suite does not catch that, every fix metric in the study is
inflated.

## 6. Regression tests

Every confirmed bug in the platform should become a regression test where practical.

## 7. Flutter tests

Test:

- navigation
- providers
- API service behavior
- WebSocket event handling
- loading states
- empty states
- error states
- vulnerability display
- fix review
- scan cancellation

## 8. Verification principle

A generated patch is not a successful fix until the relevant security test is re-run and the expected secure behavior is observed.

## 9. Definition of done

A feature is done only when:

- implementation exists
- tests exist
- failure paths are handled
- UI is connected if applicable
- documentation is updated
- `MEMORY.md` is updated

## 10. Security control traceability

Every numbered control in `THREAT_MODEL.md` §5 maps to at least one test here. A
control with no test is not a control; it is a wish. Maintain this table and fill it in
as controls are implemented — Phase 12 cannot close while a row is empty without an
explicit, written accepted-risk note.

| Control | What it requires | Test |
|---------|------------------|------|
| C1.1 | Untrusted text never reaches a privileged prompt | `test_llm_security.py::test_c1_1_privileged_prompt_rejects_raw_untrusted_marker` |
| C1.2 | Nonce envelope; nonce-collision detected and recorded | `test_llm_security.py::test_c1_2_quarantine_envelope_and_collision_detection` |
| C1.3 | Model output cannot express a forbidden action | `test_cvss_scorer.py::test_cvss_round_trip_reproducibility`, `test_evaluator_agent.py::test_evaluator_severity_reproducible_from_stored_cvss_inputs` (Model emits closed-enum metric inputs only; platform calculates CVSS vector and severity) |
| C1.4 | Correct findings on the injection-canary fixture | *(pending)* |
| C2.1 | Path outside workspace refused | `test_fixer_agent.py::test_path_containment_refuses_traversal_paths_c2_1` |
| C2.2 | Symlinks not followed on patch apply | `test_fixer_agent.py::test_path_containment_refuses_symlinks_c2_2` |
| C2.3 | Non-UUID `project_id` refused before path use | `backend/tests/test_uuid_validation.py` (12 tests) |
| C2.4 | New-file creation confined to the resolved root | `test_fixer_agent.py::test_fixer_records_hallucinated_path_without_crashing` (Fixer refuses to invent files; target path must be in workspace inventory, hallucinated paths recorded without write) |
| C3.1 | No Docker socket in the container | `test_hardening.py::test_no_docker_socket_mounted` (Unit: passed); `test_hardening.py::TestContainerHardeningLive::test_live_no_docker_socket_in_container` (Live: verified passed) |
| C3.2 | Hardening flags present on the running container | `test_hardening.py` (`TestDockerfileHardening`, `test_container_hardening_flags_enforced` Unit: passed); `test_hardening.py::TestContainerHardeningLive::test_live_hardening_flags_applied` (Live: verified passed) |
| C3.3 | Target cannot reach the host LAN | `test_hardening.py` (`test_target_network_internal_and_no_published_ports`, `test_scanner_proxy_attached_to_both_networks`, `test_scanner_proxy_scoped_only_to_target` Unit: passed); `test_hardening.py::TestContainerHardeningLive::test_live_dns_resolution_fails_from_target`, `test_live_connect_default_gateway_fails`, `test_isolation.py::TestDockerLifecycle::test_build_and_start_valid_app` (Live: verified passed) |
| C3.4 | pids/memory/CPU limits and wall-clock kill enforced | `test_hardening.py::test_container_hardening_flags_enforced` (Unit: passed); `test_async_discipline.py::test_event_loop_unblocked_during_build` (Unit: passed); `test_async_discipline.py::TestAsyncDisciplineDocker::test_two_concurrent_builds`, `test_isolation.py::TestDockerLifecycle::test_stop_container` (Live: verified passed) |
| C3.5 | No host env vars in the container | `test_hardening.py::test_container_hardening_flags_enforced` (Unit: passed asserts env={}); `test_hardening.py::TestContainerHardeningLive::test_live_hardening_flags_applied` (Live: verified passed) |
| C5.1 | Deny-listed files never read for LLM context | `test_llm_security.py::test_c5_1_secret_deny_list` |
| C5.2 | Redaction applied before persistence | `test_llm_security.py::test_c5_2_outbound_regex_redaction` |
| C5.4 | Canary secret never appears in outbound payloads | `test_llm_security.py::test_c5_4_canary_secret_never_present_in_outbound_payload`, `test_builder_agent.py::test_builder_canary_secret_never_present_in_outbound_payload` |
| C6.x | Raw records append-only; exclusions carry a reason | *(pending)* |
| C7.1–7.4 | Localhost bind, token auth, CORS/Host, WS auth | `backend/tests/test_auth.py` (9 tests), `desktop/test/widget_test.dart` |
| T8 | Oversized/unparseable patch rejected; functional suite must pass | `test_fixer_agent.py::test_patch_engine_rejects_oversized_diff_t8`, `test_fixer_agent.py::test_patch_engine_rejects_unparseable_python_syntax_t8`, `test_verifier_agent.py::test_adversarial_regression_delete_endpoint_patch_lands_on_regressed` |
| T9 | Off-target HTTP request refused | `test_scope_locked_client.py::test_off_target_absolute_url_refused_t9`, `test_scope_locked_client.py::test_cross_host_redirect_blocked_by_scope_lock`, `test_attacker_agent.py::test_off_target_request_refused_t9_in_scan` |

## 11. Research pipeline tests

The metrics code is research infrastructure and needs tests like any other code — an
error here silently corrupts every reported number.

- The matching function on hand-built cases: exact match, route-template
  normalization (`/users/42` ↔ `/users/{user_id}`), category mismatch, method
  mismatch, one-to-one assignment with two findings competing for one ground truth,
  duplicate counting.
- Metric arithmetic against worked examples computed by hand.
- Bootstrap CI reproducibility with a fixed seed.
- McNemar's exact test against a known reference result.
- Batch runner resume: kill mid-batch, resume, verify no unit is run twice and none is
  skipped.
- Exclusion accounting: every excluded unit appears in the reported totals.