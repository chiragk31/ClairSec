# Adversarial FastAPI Security Platform — Agent Documentation

## Purpose

This folder is the source of truth for AI coding agents working on this project.

The product is a desktop application that accepts an existing, user-authorized FastAPI project, analyzes it, runs controlled adversarial security tests, evaluates findings, generates fixes, applies them in a safe workspace, and re-tests the application.

## Read order for coding agents

Before changing code, read these files in this order:

1. `PRD.md` — what we are building and why.
2. `ARCHITECTURE.md` — system architecture, boundaries, components, data flow, and folder structure.
3. `RULES.md` — non-negotiable engineering and security rules.
4. `DESIGN.md` — Flutter desktop UI/UX requirements.
5. `PHASES.md` — implementation roadmap and definition of done.
6. `SECURITY.md` — security-specific implementation constraints.
7. `TESTING.md` — testing and validation strategy.
8. `RESEARCH.md` — research contribution, metrics, and experiment design.
9. `MEMORY.md` — living project memory. Update it after meaningful implementation progress.

### Specification documents

The nine documents above state intent. These five state the contracts precisely
enough to implement without guessing. Read the ones relevant to your phase:

10. `THREAT_MODEL.md` — threats against the platform itself, with numbered controls. Read before any phase touching Docker, the filesystem, the LLM, or the HTTP surface.
11. `LLM.md` — the LLM provider contract: structured output, prompt versioning, determinism, caching, budgets, and the quarantine pattern for untrusted content. **Read before Phase 4.**
12. `VULN_TAXONOMY.md` — the closed set of vulnerability categories, with deterministic oracles. **Read before Phase 5.**
13. `METHODOLOGY.md` — experimental arms, ground truth, the matching function, severity rubric, dual-criterion fix evaluation, and statistics. Read before Phase 6 and again before Phase 11.
14. `DATA_MODEL.md` — collection schemas, indexes, size caps, redaction, retention.
15. `ETHICS.md` — coordinated disclosure, dual-use, research integrity. **Read before the first Tier B run.**
16. `OPERATIONS.md` — repo hygiene, pinning, CI, async discipline, batch runner, packaging, artifact release.

When a document in 1–9 states a goal and a document in 10–16 states the mechanism,
the mechanism is binding — that is what those documents are for. Where they appear to
conflict on substance rather than detail, raise it rather than choosing silently.

## Agent operating principle

Do not attempt to build the entire product in one step.

Work phase-by-phase. Before implementing a phase:

- Read the relevant documentation.
- Inspect the existing repository.
- Preserve working functionality.
- Implement the smallest coherent increment.
- Run appropriate tests/checks.
- Update `MEMORY.md`.
- Report what changed, what was verified, and what remains.

## Source of truth hierarchy

When instructions conflict:

1. User's explicit current request.
2. `RULES.md`.
3. `SECURITY.md` and `THREAT_MODEL.md`.
4. `ETHICS.md`.
5. `PRD.md`.
6. `METHODOLOGY.md` (binding for anything that produces a research number).
7. `ARCHITECTURE.md`, `LLM.md`, `DATA_MODEL.md`, `VULN_TAXONOMY.md`.
8. `PHASES.md`.
9. `DESIGN.md`, `OPERATIONS.md`.
10. Existing implementation details.

Do not invent requirements that are not supported by these documents.

## Important security boundary

The scanner is intended for projects the user is authorized to test.

All execution of imported target applications and active security testing must occur inside controlled isolation. Never execute untrusted project code directly on the host merely because it was imported into the desktop application.

## Definition of a good implementation

A feature is not considered complete merely because the UI exists or an LLM returns text.

A feature is complete when:

- Its backend behavior exists.
- Its UI state is connected to the backend.
- Errors are handled.
- Relevant tests exist.
- Security boundaries are respected.
- The feature works through the real application flow.
- Documentation/memory is updated.