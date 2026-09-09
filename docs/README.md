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
3. `SECURITY.md`.
4. `PRD.md`.
5. `ARCHITECTURE.md`.
6. `PHASES.md`.
7. `DESIGN.md`.
8. Existing implementation details.

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