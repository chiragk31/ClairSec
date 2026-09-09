# Research and Evaluation Plan

## 1. Research question

Can a specialized adversarial multi-agent architecture improve automated REST API vulnerability detection and remediation compared with single-agent and traditional security-testing approaches?

## 2. Core hypothesis

A pipeline with specialized agents that challenge and independently evaluate each other's outputs should reduce false positives and improve useful remediation compared with a single general-purpose agent.

This is a hypothesis to test, not an assumption to present as a result.

## 3. System under evaluation

Primary system:

```text
Builder → Attacker → Evaluator → Fixer → Verification
```

Shared context:

```text
MongoDB
```

Execution:

```text
Docker-isolated FastAPI target
```

## 4. Baselines

Where technically and legally appropriate, compare against:

1. Traditional scanner/tool baseline — OWASP ZAP as the primary baseline, with Schemathesis (OpenAPI-driven property-based fuzzing) as a secondary baseline where the target exposes a usable OpenAPI schema. Name and pin exact tool versions in the experiment record (see §9).
2. Single-agent LLM baseline — the same underlying model configuration as the multi-agent system, given the same target and told to find and fix vulnerabilities in one pass, with no Builder/Attacker/Evaluator/Fixer role separation.
3. Proposed multi-agent system.

Keep:

- target applications
- test environment
- vulnerability set
- model configuration
- resource budget

as comparable as practical.

### LLM cost/call budget

Before running the full dataset, define and record a per-project budget ceiling (e.g., max LLM calls and max tokens per project per system) so a single misbehaving run cannot silently consume the experiment's compute/cost budget. Runs that exceed the ceiling are marked `budget_exceeded` rather than allowed to continue unbounded, and are reported as a rate alongside the primary metrics.

## 5. Primary metrics

### Vulnerability detection rate

Measure the proportion of known vulnerabilities correctly identified.

A useful definition:

```text
Detection Rate = True Positives / Actual Vulnerabilities
```

### False positive rate

Measure how often the system reports a vulnerability that is not actually present.

Define the denominator carefully and keep it consistent across experiments.

### Fix accuracy

Measure how often generated fixes correctly remediate the vulnerability without introducing unacceptable regressions.

### Fix verification rate

Measure the proportion of applied fixes for which the original exploit/test can be re-run and verified.

### Post-fix robustness rate

After a fix is verified against the original exploit/test, the Attacker agent attempts one adapted variant of the same attack against the patched endpoint (for example, a mutated payload, an alternate encoding, or a different parameter targeting the same underlying weakness). Measure the proportion of verified fixes that also withstand this variant attempt.

```text
Post-fix Robustness Rate = Fixes Surviving Variant Attack / Fixes Verified
```

This distinguishes a fix that patches the exact reported exploit from a fix that addresses the underlying vulnerability class, and should be reported as a distinct metric rather than folded into fix verification rate.

## 6. Secondary metrics

Collect:

- scan duration
- LLM calls
- token/cost usage where available
- number of tests executed
- number of candidate findings
- number of confirmed findings
- number of rejected findings
- severity distribution
- vulnerability categories
- patch size
- verification outcome
- application startup failures

## 7. Dataset

Target a diverse set of 50+ FastAPI projects if the final research protocol supports that scale, split into two tiers with different ground-truth handling. Do not treat all 50+ as equally verified — a reviewer will ask how ground truth was established, and the two tiers answer that differently.

### Tier A — seeded benchmark (majority, ~30–35 projects)

FastAPI applications with deliberately injected, known vulnerabilities drawn from the OWASP API Security Top 10 (e.g., broken object-level authorization, broken authentication, mass assignment, injection, rate-limit bypass). Ground truth is exact because the vulnerability set is planted and recorded at injection time. This tier is the primary source for detection rate and false positive rate.

### Tier B — real-world sample (~15–20 projects)

Actual open-source FastAPI repositories, run through the pipeline without seeding. Ground truth is established by:

- cross-referencing flagged findings against known CVE/GHSA records for that project where available, and
- a documented human security-review pass on a defined sample of the pipeline's findings (not necessarily all 50+), used to estimate real-world false positive rate.

This tier supports external validity claims; it is not the basis for the headline detection-rate number.

### Import failure handling

Not every real-world project will containerize or launch successfully (dependency resolution failures, missing entry points, failed health checks). A project that cannot be automatically sandboxed within a defined number of attempts is marked `import_failed`, excluded from the scored dataset, and the reason is logged. Report the import failure rate itself as a finding rather than silently dropping these projects — the proportion of real-world repositories that cannot be automatically sandboxed is a legitimate result.

### Record for each project

- project identifier
- tier (seeded / real-world)
- source/version
- vulnerability labels (planted, for Tier A; cross-referenced, for Tier B)
- endpoint inventory
- dependencies
- authentication style
- database style
- expected findings
- import status (`ready` / `import_failed`, with reason)

Do not expose sensitive project data in published artifacts.

### Scope and ethics note

All real-world Tier B projects are cloned locally from public open-source repositories and executed only inside local, isolated containers under this platform's isolation policy (see `SECURITY.md`). No live third-party infrastructure, hosted deployment, or production API is targeted at any point in the experimental protocol.

## 8. Reproducibility

Record:

- model/provider
- model version where available
- prompt version
- application version
- scanner version
- Docker image/runtime information
- experiment configuration
- random seeds where applicable
- timestamps
- resource limits

## 9. Experimental records

Each experiment should be represented structurally.

Example:

```json
{
  "experiment_id": "exp_001",
  "system": "multi_agent",
  "project_id": "project_001",
  "model": "configured-model",
  "detected": 12,
  "true_positives": 10,
  "false_positives": 2,
  "fixes_attempted": 10,
  "fixes_verified": 8
}
```

## 10. Research integrity

Do not alter metrics to make the proposed architecture look better.

Store raw experimental outcomes separately from calculated summaries.

Document failures and inconclusive cases.

## 11. Product/research separation

The desktop application is the interface.

The evaluation engine should be usable without Flutter so experiments can be automated and repeated.