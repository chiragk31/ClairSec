# Product Requirements Document

## 1. Product name

Working name: **Adversarial Security Platform**

The name can change later without changing the architecture.

## 2. Product vision

Build a desktop security platform that can take an existing FastAPI project and autonomously perform a controlled security assessment using collaborating specialized agents:

**Builder → Attacker → Evaluator → Fixer → Re-test**

The platform should turn security testing and remediation into an observable, reproducible workflow rather than a black-box LLM call.

## 3. Primary user

The initial target user is a developer, security researcher, student, or authorized tester who has a FastAPI project and wants to discover and remediate API vulnerabilities.

## 4. Core user journey

1. User opens the desktop application.
2. User imports/selects a FastAPI project.
3. Application validates the project and creates an isolated scan workspace.
4. Builder analyzes the project.
5. Target application is started inside isolation.
6. Attacker performs controlled security tests.
7. Evaluator validates candidate findings and determines severity/evidence.
8. Fixer proposes source-code changes.
9. User reviews or enables automatic application of fixes according to the configured policy.
10. Application rebuilds/restarts the isolated target.
11. Original exploit/test is re-run.
12. Findings are marked fixed, unresolved, or fix-unverified.
13. User can inspect the source diff, evidence, agent reasoning summary, logs, and metrics.
14. User can export a report.

## 5. MVP goals

The MVP must support:

- Importing a local FastAPI project.
- Project validation.
- Isolated target execution.
- Basic project/API discovery.
- Four-agent orchestration.
- Shared scan context.
- Vulnerability records.
- Fix proposals.
- Safe patch application to a scan workspace.
- Re-test after fixes.
- Live scan progress in Flutter.
- Vulnerability dashboard.
- Scan history.
- Basic report export.

## 6. Non-goals for the first MVP

Do not initially attempt:

- Arbitrary programming-language support.
- Cloud multi-tenancy.
- Distributed scanning.
- Fully autonomous execution on the user's host.
- Perfect vulnerability coverage.
- Guaranteed automatic fixes for every vulnerability.
- Production deployment of repaired applications.
- Secret extraction from target systems.
- Destructive exploitation.

## 7. Agent responsibilities

### Builder

Purpose: understand the target.

Responsibilities:

- Inspect project structure.
- Identify FastAPI entry points.
- Identify routes and HTTP methods.
- Parse OpenAPI information when available.
- Identify authentication and authorization mechanisms.
- Identify models, dependencies, configuration, and relevant database access.
- Produce structured target context.

The Builder does not decide that a vulnerability is confirmed.

### Attacker

Purpose: challenge the target.

Responsibilities:

- Select security tests based on the discovered API surface.
- Generate controlled test cases.
- Execute tests against the isolated target.
- Record request/response evidence.
- Produce candidate vulnerabilities.

The Attacker must not claim confirmation solely from source-code suspicion.

### Evaluator

Purpose: independently validate findings.

Responsibilities:

- Review attacker evidence.
- Reproduce candidate findings where possible.
- Compare expected vs actual authorization behavior.
- Assess exploitability and impact.
- Remove false positives.
- Assign severity and confidence.
- Produce a structured finding.

### Fixer

Purpose: remediate confirmed findings.

Responsibilities:

- Inspect relevant source code.
- Generate a minimal patch.
- Explain the root cause.
- Explain the proposed fix.
- Apply the patch only to the controlled scan workspace.
- Trigger verification.
- Never silently overwrite the user's original project.

## 8. Required vulnerability record

Each finding should contain, at minimum:

- `id`
- `scan_id`
- `title`
- `category`
- `severity`
- `confidence`
- `endpoint`
- `method`
- `description`
- `impact`
- `evidence`
- `reproduction_summary`
- `source_locations`
- `fix_summary`
- `patch`
- `verification_status`
- timestamps
- agent provenance

## 9. Product success criteria

The platform should make it easy to answer:

- What did the Builder discover?
- What did the Attacker test?
- Which findings were actually confirmed?
- Why was each finding considered vulnerable?
- What code change was proposed?
- Was the fix applied?
- Did the original exploit fail after the fix?
- What happened across the complete scan?

## 10. Research-oriented requirements

The application must preserve enough structured data to calculate:

- vulnerability detection rate
- false positive rate
- fix accuracy
- fix verification rate
- scan duration
- vulnerabilities by category/severity
- comparison between multi-agent, single-agent, and traditional approaches

Do not store only free-form LLM text. Important experimental data must be structured.