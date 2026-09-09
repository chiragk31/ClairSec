# Research and Evaluation Plan

> **Companion document.** This file states the research design. `METHODOLOGY.md`
> states how each quantity is computed — the matching function, the false-positive
> denominator, the severity rubric, the statistics, and the review protocol. Where
> this document says "define carefully", `METHODOLOGY.md` contains the definition and
> is binding.

## 1. Research question

Can a specialized adversarial multi-agent architecture improve automated REST API vulnerability detection and remediation compared with single-agent and traditional security-testing approaches?

### Secondary research question

Does role separation change a pipeline's **susceptibility to prompt injection embedded
in the code under test**? The platform necessarily feeds untrusted target source to an
LLM that then acts on it, so this is measurable at near-zero marginal cost, and it is
markedly less well-studied than detection rate. Protocol in `METHODOLOGY.md` §9;
implementation in `PHASES.md` Phase 11.5.

This may be the stronger contribution of the two. Detection-rate comparisons between
agent topologies are becoming crowded; a controlled measurement of whether an
independent-evaluator stage resists adversarial input planted in the target is not.

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
3. **Ablation arm — multi-agent without the Evaluator.** Builder → Attacker → Fixer, with every candidate finding reported unevaluated.
4. Proposed multi-agent system.

Arm 3 is not optional. The core hypothesis (§2) is specifically that *independent
adversarial evaluation* reduces false positives. Comparing only arms 1, 2 and 4 shows
that the proposed system differs from the baselines but cannot attribute the difference
to the Evaluator rather than to, say, better route discovery in the Builder. The
ablation is what converts a system description into a finding about mechanism, and it
is the first thing a reviewer will ask for.

**Baseline fairness is a result-validity requirement, not a courtesy.** The traditional
arm receives the same OpenAPI schema, the same test credentials, and the same
wall-clock budget as the LLM arms. A scanner run unauthenticated against an
authenticated API will find almost nothing, and a reviewer will correctly read that as
a strawman rather than as evidence.

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

Matching a reported finding to a known vulnerability is done by the executable
matching function in `METHODOLOGY.md` §3 — category, normalized route template, and
method, assigned one-to-one by descending confidence. Never by hand, and identically
for every arm.

### False positive rate

Measure how often the system reports a vulnerability that is not actually present.

The denominator is defined in `METHODOLOGY.md` §3.3. Summary: the headline figure is
the **false discovery rate**, `FP / (TP + FP)`, because a generative system has no
well-defined true-negative count. It is labelled FDR in every table so it is not
confused with a classical FPR. Because Tier A projects also contain deliberately
secured *negative* endpoints, a classical specificity over the enumerable
`(route, method, category)` candidate space is reported alongside it — that is the
figure that makes the comparison against ZAP statistically legible.

### Fix accuracy

Measure how often generated fixes correctly remediate the vulnerability without introducing unacceptable regressions.

**Dual criterion.** A fix counts only if it both blocks the original exploit **and**
leaves the project's functional test suite passing at the pre-fix rate
(`METHODOLOGY.md` §5). Exploit-blocking alone is not sufficient: a patch that deletes
or breaks the endpoint blocks the exploit perfectly and is worthless. Every Tier A
project therefore ships a functional test suite, and **functional regression rate** is
reported as its own metric rather than folded into fix accuracy.

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
- **cost per confirmed finding** and **cost per verified fix** — not only totals. A
  system that detects 10% more at 4× the token cost is a materially different result
  from one that does so at parity, and only the normalized figure shows it.
- **malformed structured-output rate** per agent and prompt version
- **duplicate finding rate** — a system must not be able to inflate recall by
  reporting one issue several ways
- **run-to-run stability** — mean pairwise Jaccard similarity of the confirmed-finding
  sets across the k trials (`LLM.md` §5)
- **injection attempts detected** in target content
- **budget-exceeded rate** and **import failure rate**

## 7. Dataset

Target a diverse set of 50+ FastAPI projects if the final research protocol supports that scale, split into two tiers with different ground-truth handling. Do not treat all 50+ as equally verified — a reviewer will ask how ground truth was established, and the two tiers answer that differently.

### Tier A — seeded benchmark (majority, ~30–35 projects)

FastAPI applications with deliberately injected, known vulnerabilities drawn from the OWASP API Security Top 10 (e.g., broken object-level authorization, broken authentication, mass assignment, injection, rate-limit bypass). Ground truth is exact because the vulnerability set is planted and recorded at injection time. This tier is the primary source for detection rate and false positive rate.

Categories are the closed set in `VULN_TAXONOMY.md` §2, each with a deterministic
oracle. Each Tier A project must additionally ship:

- an **executable proof of vulnerability (PoV)** per seeded vulnerability, verified to
  fire on the vulnerable build and *not* fire on a hand-patched reference build. The
  PoV, not the scanner and not an LLM, is the authority on whether the vulnerability
  exists.
- a **functional test suite** that passes on the vulnerable build, without which
  functional regression (§5) is not computable;
- **negative endpoints** — correctly secured routes of the same shape — without which
  specificity has no denominator.

### Data contamination

Benchmarks built from public CVEs are compromised by pretraining exposure: the fix
commits are very likely in the model's training data, so apparent "detection" may be
recall. Required mitigations (detail in `METHODOLOGY.md` §2.2): Tier A projects are
**authored for this study** and withheld from publication until the runs complete;
seeded vulnerabilities use novel structural placements rather than verbatim CVE
patterns; each project records whether it derives from public code and when; and a
subgroup analysis compares performance on material predating versus postdating the
model's training cutoff. Report that analysis whichever way it comes out.

### Tier B — real-world sample (~15–20 projects)

Actual open-source FastAPI repositories, run through the pipeline without seeding. Ground truth is established by:

- cross-referencing flagged findings against known CVE/GHSA records for that project where available, and
- a documented human security-review pass on a defined sample of the pipeline's findings (not necessarily all 50+), used to estimate real-world false positive rate.

This tier supports external validity claims; it is not the basis for the headline detection-rate number.

The human review must be **blinded and multi-rater**: findings from all four arms are
pooled, shuffled, and stripped of arm identifiers; two independent reviewers label each
against a written rubric; Cohen's κ is reported; disagreements go to a third
adjudicator (`METHODOLOGY.md` §7). Single-reviewer unblinded adjudication of one's own
system's output is not defensible and will be read as such.

A confirmed Tier B finding is a real vulnerability in someone else's software and
triggers a disclosure obligation. `ETHICS.md` is required reading before the first
Tier B run — it cannot be written retroactively once findings exist.

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
- model version where available — a pinned, fully-qualified id, never a floating alias
- prompt version, plus the SHA-256 digest of the whole prompt registry
- application version
- scanner version
- Docker image/runtime information, by image digest rather than tag
- experiment configuration, plus a `config_hash` stored on every scan
- random seeds where applicable
- timestamps
- resource limits
- LLM cache mode (`off` for headline runs)

**LLMs are not deterministic, and `temperature=0` does not make them so.** Recording
seeds is necessary but not sufficient. The design therefore runs **k = 3 trials** per
(arm, project), reports means with bootstrap confidence intervals rather than single
point estimates, and reports run-to-run stability as its own metric. A content-addressed
response cache supports a `replay` mode so a third party can re-derive the published
tables with no API key and no cost (`LLM.md` §5).

### Statistical treatment

Point estimates without intervals are not results. Required, in full in
`METHODOLOGY.md` §6:

- bootstrap 95% CIs, resampling over **projects** (the unit of independence), 10,000
  resamples, fixed seed;
- **McNemar's exact test** for paired per-vulnerability outcomes between arms, with the
  discordant counts reported, not only p;
- Cohen's *h* effect sizes, so a significant-but-tiny difference is visible as such;
- Holm–Bonferroni correction across the pairwise contrasts within each metric family;
- a **pre-registered analysis plan** committed before the full dataset run.

## 9. Experimental records

Each experiment should be represented structurally.

Example:

```json
{
  "experiment_id": "exp_001",
  "run_id": "run_0001",
  "arm": "multi_agent",
  "project_id": "project_001",
  "trial_index": 0,
  "model_descriptor": {"provider": "...", "model_id": "...", "temperature": 0.0, "seed": 42},
  "prompt_registry_digest": "sha256:...",
  "config_hash": "sha256:...",
  "cache_mode": "off",
  "detected": 12,
  "true_positives": 10,
  "false_positives": 2,
  "false_negatives": 3,
  "duplicates": 1,
  "candidate_space_size": 184,
  "fixes_attempted": 10,
  "fixes_blocking_exploit": 8,
  "fixes_passing_functional_suite": 7,
  "fixes_surviving_variant": 5,
  "llm_calls": 96,
  "tokens": {"in": 412000, "out": 38000},
  "cost_usd": 2.14,
  "excluded": false,
  "exclusion_reason": null
}
```

Two properties of this record matter more than its exact fields. It is **append-only** —
summaries are derived from it and never written back into it. And every excluded run
carries a reason from a closed enum (`import_failed`, `budget_exceeded`,
`harness_error`, `timeout`, `pov_invalid`) with the exclusion counts printed in the
results table per arm. A quietly smaller denominator for the proposed system is the
classic way this comparison goes wrong, and it is trivially detectable by any reviewer
who checks the n's.

Full schema in `DATA_MODEL.md` §3 (`experiment_runs`).

## 10. Research integrity

Do not alter metrics to make the proposed architecture look better.

Store raw experimental outcomes separately from calculated summaries.

Document failures and inconclusive cases.

## 11. Product/research separation

The desktop application is the interface.

The evaluation engine should be usable without Flutter so experiments can be automated and repeated.