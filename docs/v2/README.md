# ClairSec v2 — Upgrade Pack

v2 turns the working pipeline into a product a non-technical audience can follow and a
technical audience can trust: GitHub import, one-click Autopilot, a live attack
timeline, a posture score, live exploit replay, three-proof fix review, real reports, an
AI assistant on every screen, light/dark themes, and an honest fallback chain that never
leaves a blank screen.

## Files

| File | Purpose |
|------|---------|
| `PLAN.md` | Phases V0–V9, rounds, exit gates, round-report format, progress tracker |
| `FEATURES.md` | Specs F0–F14: behaviour, APIs, safety rules, how each is proven |
| `UI_SYSTEM.md` | Tokens, light/dark, presets, typography, responsive layout, components, language |
| `REFERENCES.md` | Researched prior art (Strix, Shannon, ZAP, Schemathesis…) and what we borrow |
| `MANUAL_STEPS.md` | What the human must do: Docker, MongoDB, keys, running, rehearsal |
| `AGENT_PROMPT.md` | The prompt for the coding agent, and the review loop |
| `DEMO_SCRIPT.md` | (written in V9) the presentation talk track with fallbacks |

## Read order for a coding agent

1. `AGENTS.md` (repo root) and `docs/README.md` read order — the base rules still apply.
2. This file → `PLAN.md` → `FEATURES.md` → `UI_SYSTEM.md` → `REFERENCES.md`.
3. For the current round, re-read the base docs cited by its phases.

## Precedence

`docs/RULES.md`, `docs/SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/ETHICS.md` outrank
everything in `docs/v2/`. Within v2: `FEATURES.md` (behaviour) > `PLAN.md` (sequence) >
`UI_SYSTEM.md` (presentation). If v2 conflicts with a base rule, follow the base rule and
report the conflict.

## The three non-negotiables of v2

1. **Real or labelled.** Fallbacks use real recorded data or ClairSec's own bundled
   apps, always with a visible mode badge. Nothing is faked.
2. **AI proposes, code decides.** No LLM sets a status, severity, score or verdict —
   including the assistant.
3. **Strangers' code never runs on the host.** Imported and cloned projects run only in
   the hardened container.
