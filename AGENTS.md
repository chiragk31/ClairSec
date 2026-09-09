# Coding Agent Instructions

This repository contains the Adversarial FastAPI Security Platform.

Before making changes, read:

1. `docs/README.md`
2. `docs/PRD.md`
3. `docs/ARCHITECTURE.md`
4. `docs/RULES.md`
5. `docs/SECURITY.md`
6. `docs/DESIGN.md`
7. `docs/PHASES.md`
8. `docs/TESTING.md`
9. `docs/RESEARCH.md`
10. `docs/MEMORY.md`

`docs/` is the project instruction source of truth.

Work incrementally according to `docs/PHASES.md`.

Never execute imported FastAPI project code directly on the host when isolation is required. Use the controlled runtime described in `docs/SECURITY.md`.

Do not modify the user's original imported project during autonomous fixing. Work in a scan workspace and preserve a diff.

After meaningful progress, update `docs/MEMORY.md`.

Do not claim a vulnerability is confirmed without evidence or claim a fix is successful without verification.
