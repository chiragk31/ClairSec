# Vulnerability Taxonomy

> `PHASES.md` Phase 5 says "start with a small set of well-defined API security
> categories" without naming them. This document names them. It is the single
> shared vocabulary for the Attacker's test selection, the Evaluator's
> classification, the Tier A seeding process, and the ground-truth matching
> function in `METHODOLOGY.md` §3.
>
> Nothing outside this list may be reported as a finding category in the MVP.
> A closed enum is what makes detection rate computable.

## 1. Alignment

Categories are anchored to **OWASP API Security Top 10 (2023)** — the current
edition — and each carries a **CWE** identifier. CWE is what makes the results
comparable to the wider literature; OWASP alone is too coarse.

## 2. In-scope categories (MVP)

| ID | Name | OWASP API 2023 | Primary CWE | Runtime-confirmable |
|----|------|----------------|-------------|---------------------|
| `BOLA` | Broken Object Level Authorization | API1 | CWE-639 | Yes |
| `BROKEN_AUTH` | Broken Authentication | API2 | CWE-287 | Yes |
| `BOPLA_MASS_ASSIGN` | Mass assignment (writable property not authorized) | API3 | CWE-915 | Yes |
| `BOPLA_DATA_EXPOSURE` | Excessive data exposure in response | API3 | CWE-213 | Yes |
| `BFLA` | Broken Function Level Authorization | API5 | CWE-285 | Yes |
| `RESOURCE_CONSUMPTION` | Missing rate limiting / unbounded work | API4 | CWE-770 | Yes |
| `INJECTION` | SQL / NoSQL / command / template injection | — (API8-adjacent) | CWE-89, CWE-943, CWE-78 | Yes |
| `SECURITY_MISCONFIG` | Debug mode, wildcard CORS, verbose errors, missing TLS flags | API8 | CWE-16 | Partly |

Eight categories. `INJECTION` is retained despite not having its own 2023 OWASP API
slot because it is the category most comparable to traditional-scanner baselines —
dropping it would make the ZAP comparison unfair to ZAP.

## 3. Deferred categories, with reasons

Recording *why* something is out of scope matters as much as scoping it; a reviewer
will otherwise read the omission as a limitation the authors did not notice.

| OWASP | Name | Why deferred |
|-------|------|--------------|
| API6 | Unrestricted Access to Sensitive Business Flows | Requires per-application business-logic ground truth; not mechanically seedable |
| API7 | Server Side Request Forgery | Needs a second controlled internal service and an egress-observation sink; feasible in a later phase |
| API9 | Improper Inventory Management | A deployment/fleet property, not observable from a single container |
| API10 | Unsafe Consumption of APIs | Requires a controlled malicious upstream dependency |

Deferred categories must still be **reported as out of scope in results tables** so
detection rate is never mistaken for coverage of the full Top 10.

## 4. Per-category specification

Each category has a fixed record used by both the Attacker and the seeder:

```python
class CategorySpec(BaseModel):
    id: CategoryId
    owasp_api_2023: str | None
    cwe: list[str]
    preconditions: list[str]     # what must exist on the target to test this
    oracle: OracleSpec           # how a violation is decided — see §5
    default_severity: Severity   # rubric baseline, adjustable per METHODOLOGY §4
    seedable: bool               # can Tier A plant this mechanically
```

### BOLA
- **Preconditions:** an authenticated route with an object identifier in path or query,
  and at least two distinct test principals.
- **Oracle:** principal A requests principal B's object. Vulnerable iff the response is
  2xx **and** the body contains B's discriminating field. A 2xx with an empty or
  filtered body is *not* a finding.
- **Common FastAPI root cause:** `Depends(get_current_user)` authenticates but the query
  lacks an ownership predicate.

### BROKEN_AUTH
- **Preconditions:** a route that returns 401/403 without credentials.
- **Oracle:** the same route returns 2xx with an absent, malformed, expired,
  `alg:none`, wrong-signature, or another user's token.

### BOPLA_MASS_ASSIGN
- **Preconditions:** a write route (POST/PUT/PATCH) with a request body.
- **Oracle:** send a privileged field not present in the declared input schema
  (`is_admin`, `role`, `balance`, `owner_id`). Vulnerable iff a subsequent read shows
  the field was persisted.
- **Common FastAPI root cause:** `Model(**payload.dict())` without `extra="forbid"`
  and without separate `Create`/`AdminUpdate` schemas.

### BOPLA_DATA_EXPOSURE
- **Preconditions:** any route returning an object.
- **Oracle:** the response contains a field on the sensitive-field list
  (`password`, `password_hash`, `token`, `secret`, `ssn`, `api_key`, internal ids)
  that the declared `response_model` should have excluded.

### BFLA
- **Preconditions:** a route reachable only by a privileged role.
- **Oracle:** an unprivileged principal receives 2xx and the side effect occurs.
  Distinguished from BOLA by targeting a *function*, not another user's *object*.

### RESOURCE_CONSUMPTION
- **Preconditions:** any route.
- **Oracle:** N requests within a window all succeed where a limit was expected; or a
  pagination/limit parameter accepts an unbounded value and the response size or
  latency scales accordingly. **Must be rate-capped by policy** (`SECURITY.md` §6) —
  the test proves absence of a limit, it does not attempt a real DoS.

### INJECTION
- **Preconditions:** a parameter reaching a query, template, or subprocess.
- **Oracle:** differential response between a benign and a payload input that indicates
  parsing of the payload (error signature, boolean-difference, or observed side effect).
  Time-based blind techniques are **disabled by default** — they are slow and produce
  the largest share of false positives in traditional scanners.

### SECURITY_MISCONFIG
- **Preconditions:** none.
- **Oracle:** `/docs` or `/openapi.json` exposed when config claims production;
  `Access-Control-Allow-Origin: *` together with credentialed responses;
  unhandled exceptions returning stack traces; `debug=True`.
- **Note:** partly static. Findings from static observation only must carry
  `runtime_confirmed = false` and are excluded from the primary detection metric —
  see `METHODOLOGY.md` §3.4.

## 5. Oracle discipline

Every category's oracle must be **mechanically decidable from captured evidence**
without asking an LLM. The Evaluator agent may *explain* a finding, assess impact,
and reject implausible ones, but the boolean "did the oracle fire" is computed by
platform code from the recorded request/response pair.

This is the single most important design rule in this document. If an LLM decides
whether a test passed, the detection rate measures the LLM's self-consistency rather
than the system's security capability, and the study has no ground truth.

## 6. Extending the taxonomy

Adding a category requires, in the same change: the `CategorySpec`, a deterministic
oracle, at least one seeded Tier A fixture, at least one *negative* fixture (a
correctly-secured version of the same endpoint, for false-positive measurement), and
an entry in the results table. A category without a negative fixture cannot
contribute to a false-positive rate and therefore must not ship.
