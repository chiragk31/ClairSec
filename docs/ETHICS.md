# Research Ethics and Disclosure Policy

> `RESEARCH.md` §7 introduces Tier B — real open-source FastAPI repositories — and
> notes the scanning is local and isolated. That covers the *scanning* ethics. It does
> not cover what happens when the pipeline finds a **real, previously unknown
> vulnerability in someone else's software**, which is a near-certainty at n≈15–20 and
> which creates obligations that begin the moment the finding exists.
>
> This document is required reading before the first Tier B run. Any institution with
> an ethics board will ask for it, and there is no way to write it retroactively once
> findings are already sitting in a database.

## 1. Authorization and scope

- Tier A projects are authored by the research team. No third-party authorization is
  implicated.
- Tier B projects are **public open-source repositories, cloned locally**. Only the
  locally-cloned copy, running in a local container, is ever targeted.
- **No live, hosted, or production deployment of any third-party project is scanned at
  any point.** The Attacker's HTTP client is technically constrained to the scan's own
  container (`THREAT_MODEL.md` T9), so this is enforced in code, not only in policy.
- The desktop product ships an explicit authorization affirmation at project import:
  the user confirms they are authorized to test the selected project. This is recorded
  with the project record.

## 2. The disclosure obligation

A confirmed, runtime-verified finding against a real open-source project is a real
vulnerability affecting real users. The research team **discloses it**. Publishing a
paper that says "we found 40 vulnerabilities in open-source FastAPI projects" without
having told the maintainers is not an acceptable outcome.

### 2.1 What gets disclosed

Only findings that are **runtime-confirmed** (`METHODOLOGY.md` §3.4) and have survived
human review (`METHODOLOGY.md` §7). Unreviewed machine output is never sent to a
maintainer — that shifts triage cost onto volunteers, which is the central ethical
criticism of large-scale automated scanning research.

### 2.2 Channel selection

Follow the project's own stated preference, in this order:

1. `SECURITY.md` / `SECURITY` policy in the repository.
2. A GitHub private security advisory, where the repository has them enabled.
3. Maintainer email from repository metadata.
4. If none of the above exist and the project is small and inactive: a private email
   to the primary committer.

### 2.3 Public-issue policy

Do **not** open a public issue describing an unfixed vulnerability. The literature
records a specific hazard here: on a popular project, even the *existence* of a filed
issue signals to observers which repositories are vulnerable. Triage heuristics:

| Repository | Action |
|-----------|--------|
| ≥ 200 stars | Private channel only. Never a public issue. |
| 5–200 stars, commit within 365 days | Private channel preferred; public issue only after the embargo expires and only if unfixed and unacknowledged |
| < 5 stars or no commit in 365 days | Best-effort private contact; document non-response |

### 2.4 Embargo

**90 days** from first contact before any public description, extendable on maintainer
request where a fix is in progress. This is within the common 60–180 day band and is
recorded per finding.

The paper may be submitted during an embargo, but must not identify an
unfixed project by name. Aggregate statistics ("N findings across M projects") are
publishable during embargo; `project → vulnerability` attribution is not.

### 2.5 Include the patch

Every disclosure includes the generated, human-reviewed patch and the reproduction
steps. Reports paired with validated patches are far more likely to be acted on, and
the maintainer-burden objection is substantially weaker when the report arrives with a
fix attached. This platform generates patches anyway — sending them is nearly free and
materially changes the ethics.

### 2.6 Disclosure tracking

Every Tier B confirmed finding gets a `disclosure` record: channel, contact date,
acknowledgement date, fix date, embargo expiry, current state
(`not_started` / `contacted` / `acknowledged` / `fixed` / `disputed` / `no_response` /
`published`). **Disclosure outcome rates are themselves a reportable result** — the
proportion of maintainers who respond and remediate is a genuine empirical
contribution, and the field has published exactly this.

## 3. Dual-use

This platform automates finding *and* exploiting API vulnerabilities. That is
dual-use, and the honest position is to say so rather than to claim the tool is purely
defensive.

Mitigating design choices, all already required elsewhere in these docs:

- The Attacker is **scope-locked in code** to the scan's own container; it cannot be
  pointed at an arbitrary host without modifying the source (`THREAT_MODEL.md` T9).
- Tests are non-destructive by policy (`SECURITY.md` §6): no data deletion, no real
  DoS — rate-limit findings prove *absence of a limit*, they do not attempt to exhaust
  a target.
- The system produces a **patch alongside every proof of vulnerability**, which shifts
  the marginal value toward defenders.
- No weaponized exploit chains, no persistence, no post-exploitation tooling.
- The released research artifact excludes the Tier B target list until embargoes
  expire.

The write-up must contain an explicit dual-use statement. Reviewers of autonomous
security-agent research increasingly expect one, and its absence is now itself a
review finding.

## 4. Data handling

- Tier B repositories may contain committed secrets. The scanner does not extract,
  store, or report them beyond noting the *class* of exposure; the redaction pass
  (`THREAT_MODEL.md` C5.2) applies to findings, evidence, and reports alike.
- No personal data from any target is retained. Where a fixture requires user records,
  they are synthetic.
- Published artifacts are generated by an export path that runs redaction and the
  `--purge-project` filter, never by copying the working database.

## 5. Research integrity

Covered operationally in `METHODOLOGY.md` §10. The ethical restatement:

- Report negative and null results with equal prominence.
- Do not tune the proposed system against the test set and report the tuned number.
  Hold out a development subset for iteration and freeze it before the final run.
- Declare all LLM provider relationships, funding, and compute sources.
- Acknowledge that the multi-agent hypothesis may be false. `RESEARCH.md` §2 already
  states this correctly — "a hypothesis to test, not an assumption to present as a
  result" — and that framing must survive into the write-up even if the numbers are
  disappointing.

## 6. Human subjects

The Tier B human review (`METHODOLOGY.md` §7) involves human reviewers rating
findings. If reviewers are external to the research team, check whether the
institution's ethics process treats this as human-subjects research. It usually does
not — the humans are instruments, not subjects — but the determination should be
requested rather than assumed, and the answer recorded.

## 7. Checklist before the first Tier B run

- [ ] Disclosure tracking implemented and tested
- [ ] Embargo policy agreed with any supervisor/institution
- [ ] Attacker scope-lock test passing (`THREAT_MODEL.md` T9)
- [ ] Redaction test passing with a canary secret (`THREAT_MODEL.md` C5.4)
- [ ] Human review rubric written and κ-piloted on a small sample
- [ ] Dual-use statement drafted
- [ ] Ethics-board determination requested where applicable
