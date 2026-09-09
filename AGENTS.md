# Coding Agent Instructions

This repository contains the Adversarial FastAPI Security Platform.

Before making changes, read:

1. `docs/README.md` — start here; it defines the full read order and precedence.
2. `docs/PRD.md`
3. `docs/ARCHITECTURE.md`
4. `docs/RULES.md`
5. `docs/SECURITY.md`
6. `docs/DESIGN.md`
7. `docs/PHASES.md`
8. `docs/TESTING.md`
9. `docs/RESEARCH.md`
10. `docs/MEMORY.md`

Then the specification documents relevant to your phase — these state the mechanisms
the documents above only state as goals, and they are binding where they apply:

11. `docs/THREAT_MODEL.md` — numbered controls C1.1–C7.4
12. `docs/LLM.md` — required before Phase 4
13. `docs/VULN_TAXONOMY.md` — required before Phase 5
14. `docs/METHODOLOGY.md` — required before Phase 6 and Phase 11
15. `docs/DATA_MODEL.md`
16. `docs/ETHICS.md` — required before the first Tier B run
17. `docs/OPERATIONS.md`

`docs/` is the project instruction source of truth.

Work incrementally according to `docs/PHASES.md`. Phases 0–3 are implemented;
**Phase 3.5 is remediation work that must land before Phase 4.**

Never execute imported FastAPI project code directly on the host when isolation is required. Use the controlled runtime described in `docs/SECURITY.md`.

Do not modify the user's original imported project during autonomous fixing. Work in a scan workspace and preserve a diff.

After meaningful progress, update `docs/MEMORY.md`.

Do not claim a vulnerability is confirmed without evidence or claim a fix is successful without verification.

Two rules that are violated most often and cost the most:

- **An LLM never decides whether a security test passed, and never emits a final
  severity.** Oracles and the severity rubric are platform code. If a model adjudicates
  its own output, the research has no ground truth.
- **A fix is verified only if it blocks the exploit *and* leaves the functional test
  suite passing.** A patch that deletes the endpoint blocks the exploit perfectly.

Report honestly at the end of every phase: which tests ran, which were skipped and
why, and what remains unverified. Do not mark a phase done because the code exists —
meet the exit gate in `docs/PHASES.md`.
