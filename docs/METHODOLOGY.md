# Experimental Methodology

> `RESEARCH.md` defines *what* is measured. This document defines *how*, precisely
> enough that two people computing the same metric from the same run records get the
> same number. Where `RESEARCH.md` says "define the denominator carefully", this
> document is that definition.
>
> Everything here is executable: the matching function, the severity rubric, and the
> statistics are code under `backend/app/research/`, run identically for every arm.
> Nothing in this pipeline is applied by hand.

## 1. Experimental arms

`RESEARCH.md` §4 lists three arms. Three is not enough to support the core hypothesis.
The hypothesis is that *independent adversarial evaluation* reduces false positives —
so the design must isolate that variable. Four arms, all on identical targets:

| Arm | Description | What it isolates |
|-----|-------------|------------------|
| `traditional` | OWASP ZAP (primary), Schemathesis (secondary) | Non-LLM floor |
| `single_agent` | One LLM, one pass, same model/budget, no role separation | Does agent structure matter at all? |
| `multi_agent_no_eval` | Builder → Attacker → Fixer, Evaluator removed; every candidate is reported | **Ablation: the Evaluator's contribution** |
| `multi_agent` | Full Builder → Attacker → Evaluator → Fixer | The proposed system |

Without `multi_agent_no_eval`, any improvement can only be attributed to "the
multi-agent system" as an undifferentiated blob. With it, the study can state which
component earns the result. This is the difference between a system description and a
finding.

**Budget parity is mandatory.** All LLM arms get the same model, temperature, token
ceiling, and wall-clock ceiling per project. `traditional` gets the same wall-clock
ceiling, the same OpenAPI schema, and the same test credentials the LLM arms receive.
A baseline starved of authentication is a strawman and reviewers treat it as one.

## 2. Ground truth

### 2.1 Tier A — seeded

Ground truth is a `SeededVulnerability` record written **at injection time**, before
any scan runs:

```python
class SeededVulnerability(BaseModel):
    vuln_id: str
    project_id: str
    category: CategoryId          # VULN_TAXONOMY.md §2
    cwe: str
    route_template: str           # "/users/{user_id}" — normalized, never "/users/42"
    method: HttpMethod
    source_file: str
    source_line_range: tuple[int, int]
    injected_by: str              # commit sha of the seeding change
    pov: ProofOfVulnerability     # executable; see §2.3
    functional_tests: list[str]   # test node ids that must still pass after a fix
```

### 2.2 Contamination control

Public CVE-derived benchmarks are compromised by pretraining exposure — fix commits
for well-known CVEs are very likely in the model's training data, and a model that
"detects" one may be recalling it. This is a known and frequently-raised objection.

Mitigations, all required:

- **Tier A projects are authored for this study**, not forked from popular public
  repos, and are **not published until after the experimental runs complete**.
- Each Tier A project records `base_repo_public: bool` and, where derived from public
  code, the commit date, so a contamination-sensitive subgroup analysis is possible.
- Seeded vulnerabilities use *novel structural placements*, not verbatim copies of
  known CVE patches.
- Tier B (real-world, public) is reported as **secondary evidence for external
  validity only**. The headline detection rate never comes from Tier B.
- Report a contamination-check subgroup: performance on projects created after the
  model's stated training cutoff versus before. If there is no gap, say so; if there
  is, report it. Either result is publishable; hiding the analysis is not.

### 2.3 Proof of vulnerability (PoV)

Every seeded vulnerability ships an executable PoV: a script that, run against the
target container, returns `exploited=True` on the vulnerable build. The PoV is the
authority on whether the vulnerability exists — not the scanner, and not an LLM.

A PoV must be verified to **fire on the vulnerable build and not fire on the
patched-by-hand reference build** before the project enters the dataset. A PoV that
fires on both is a broken oracle and blocks the project from the dataset.

## 3. The matching function

This determines every primary metric, so it is specified exactly.

A reported finding `R` **matches** a seeded vulnerability `G` iff **all** hold:

1. `R.category == G.category` (taxonomy category level — not CWE level, since a
   correct finding may cite a sibling CWE)
2. `normalize(R.route_template) == normalize(G.route_template)`
3. `R.method == G.method`

`normalize` replaces every concrete path segment matched by the target's OpenAPI route
table with its parameter placeholder, lowercases, and strips trailing slashes. A
finding reported against `/users/42` matches a ground truth at `/users/{user_id}`.

### 3.1 Assignment

Matching is **one-to-one**. Sort candidate `(R, G)` pairs by `R.confidence`
descending, tie-broken by `R.id` ascending for determinism; greedily assign; each `G`
is consumed at most once and each `R` matches at most once.

- Assigned pair → **true positive (TP)**
- Unmatched `R` → **false positive (FP)**
- Unmatched `G` → **false negative (FN)**
- Two findings matching the same `G` → first is TP, second is a **duplicate**, counted
  separately and excluded from FP. Report duplicate rate; do not let a system farm
  recall by reporting the same issue eight ways.

### 3.2 Detection rate

```text
Detection Rate (Recall) = TP / (TP + FN) = TP / |seeded vulnerabilities|
```

### 3.3 False positive rate — the definition `RESEARCH.md` defers

For a generative system there is no well-defined count of true negatives: the system
could have reported infinitely many things and did not. So the primary reported figure
is the **False Discovery Rate**, which has a defined denominator:

```text
FDR = FP / (TP + FP)          # equivalently 1 − precision
```

This is the number reported as "false positive rate" in all tables, and it is labelled
FDR explicitly to avoid the ambiguity.

**Additionally**, because Tier A projects contain deliberately-secured *negative*
endpoints (`VULN_TAXONOMY.md` §6), a classical specificity is computable over the
closed set of `(route_template, method, category)` triples that the target actually
exposes:

```text
Candidate space  = routes × methods × applicable categories   (per project, enumerable)
TN               = candidates that are neither seeded nor reported
Specificity      = TN / (TN + FP)
```

Report both. FDR is what practitioners feel; specificity is what makes the comparison
against ZAP statistically legible. Report the candidate-space size per project so the
denominator is auditable.

### 3.4 What counts as a reportable finding

Only findings with `runtime_confirmed = true` enter the primary metrics. A
source-suspicion finding with no runtime evidence is recorded, reported in a separate
table, and excluded from detection rate — consistent with `RULES.md` §2. Systems are
compared on the same basis; if an arm cannot produce runtime evidence, that is a
result about that arm.

## 4. Severity and confidence

**An LLM must not be the sole source of a severity rating.** A model asked to rate
severity produces a plausible-sounding number with no calibration, and a reviewer will
discount every severity-weighted result that depends on it.

Severity is computed by a **deterministic rubric** from CVSS v3.1 base-metric inputs.
The Evaluator supplies the *inputs* — attack vector, privileges required, user
interaction, and CIA impact — each drawn from a closed enum and each justified by a
cited piece of evidence. Platform code computes the score and band.

```text
Evaluator → CvssInputs (enums, evidence-cited) → deterministic scorer → score + band
```

`confidence` is separate from severity and is likewise structured:
`runtime_confirmed`, `oracle_fired`, `reproduced_n_times`, `evidence_complete` →
a computed confidence band. Never a bare model-emitted float.

## 5. Fix evaluation — dual criterion

The literature standard is that a patch counts only if it **both** kills the exploit
**and** preserves functionality. `PHASES.md` Phases 7–8 currently verify only the
first. Functional regression is therefore a hard requirement, not an extra.

A fix is **correct** iff, after applying the patch and restarting the target:

1. `pov.run()` returns `exploited=False` — the original exploit is blocked; **and**
2. the project's functional test suite passes at the same rate as on the
   pre-fix build — no previously-passing test now fails.

Every Tier A project therefore ships a functional test suite (`pytest` against the
running container) that passes on the vulnerable build. Without it, criterion 2 is not
computable and a fix that deletes the endpoint scores as a success. This is the single
most common way automated-repair results are inflated.

```text
Fix Accuracy          = fixes meeting BOTH criteria / fixes attempted
Fix Verification Rate = fixes for which verification could be executed at all
                        / fixes applied
Functional Regression Rate = fixes meeting (1) but failing (2) / fixes meeting (1)
Post-fix Robustness   = fixes surviving the variant attack / fixes meeting BOTH
```

Report `Functional Regression Rate` explicitly. A system with 90% exploit-blocking and
40% functional regression is worse than one with 70% and 5%, and only this breakdown
shows it.

## 6. Statistics

Single-run point estimates on a stochastic system are not a result.

- **Trials:** `k = 3` independent trials per `(arm, project)`. Metrics are computed per
  trial; the reported value is the mean across trials.
- **Confidence intervals:** non-parametric bootstrap over **projects** (the unit of
  independence — not over individual findings, which are correlated within a project),
  10,000 resamples, seed `42`, percentile method, 95% interval. Report as
  `0.72 [0.61, 0.81]`.
- **Paired significance:** arms are evaluated on identical projects, so use
  **McNemar's exact test** on the paired per-vulnerability detection outcomes.
  Report the discordant counts `b` and `c`, not just the p-value.
- **Effect size:** Cohen's *h* for differences in proportions, with the conventional
  small/medium/large bands. A significant p-value on a small effect is reported as
  such.
- **Multiple comparisons:** with 4 arms there are 6 pairwise contrasts per metric.
  Apply Holm–Bonferroni within each metric family and report both raw and adjusted
  p-values.
- **Stability:** report mean pairwise Jaccard similarity of confirmed-finding sets
  across the k trials, per arm (`LLM.md` §5).

**Pre-registration.** Write down the primary metric, the arms, and the analysis plan
**before** the full dataset run, and commit that file. This is what separates a
result from a search over analyses, and it costs nothing to do.

## 7. Tier B human review

`RESEARCH.md` §7 requires "a documented human security-review pass" without saying by
whom or how many. Unblinded single-reviewer adjudication is not defensible.

- Findings from **all four arms** are pooled, de-duplicated, shuffled, and stripped of
  any arm identifier before review. Reviewers must not be able to infer the source.
- **Two independent reviewers** label each sampled finding
  `true / false / undetermined` against a written rubric.
- Report **Cohen's κ** for inter-rater agreement. κ < 0.6 means the rubric is
  underspecified — fix the rubric and re-review rather than reporting the numbers.
- Disagreements go to a third adjudicator; adjudicated items are flagged in the data.
- Sample size and sampling method (stratified by arm and category) are recorded before
  review begins.

## 8. Exclusions

Every excluded run carries a reason from a closed enum:
`import_failed`, `budget_exceeded`, `harness_error`, `timeout`, `pov_invalid`.

Exclusion counts appear **in the results table**, per arm. A silently smaller
denominator for the proposed system is the classic way this kind of comparison goes
wrong, and it is trivially detectable by a reviewer who checks the n's.

## 9. Secondary research question — injection resistance

The platform feeds untrusted target source into an LLM that then acts. That makes an
additional, genuinely under-studied question available at almost no extra cost:

> **Does role separation change a pipeline's susceptibility to prompt injection
> embedded in the code under test?**

Protocol: a Tier A subset ships paired projects, identical except that one variant
carries injected instructions in comments, docstrings, and `README.md` attempting to
(a) suppress a true finding, (b) induce a fabricated finding, and (c) induce a
write outside the workspace. Measure per arm:

```text
Injection Success Rate = injected objectives achieved / injected objectives attempted
Suppression Rate       = seeded vulns detected in clean variant but missed in injected variant
```

The `multi_agent` arm has a structural reason to do better here — the Evaluator never
sees the target's raw source when adjudicating — and demonstrating that empirically is
a stronger and more novel contribution than another detection-rate table. Note the
hypothesis, then test it honestly; a null result is still a result.

## 10. Integrity rules

- Raw run records are append-only. Summaries are derived, never edited in place.
- The analysis script runs end-to-end from raw records to final tables with no manual
  steps. If a number in the write-up cannot be regenerated by that script, it does not
  go in the write-up.
- Negative and inconclusive results are reported with the same prominence as positive ones.
- Do not re-run the dataset after seeing results and keep the better run. If a re-run
  is necessary for a legitimate reason, all runs are reported and the reason recorded.
