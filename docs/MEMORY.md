# Project Memory

> This file is a living state document for AI coding agents.
> Update it after meaningful implementation progress.
> Do not turn it into a dump of every source file or every conversation.

## Current status

- Project stage: Documentation / bootstrap
- Current phase: Phase 0
- Overall status: Not implemented yet

## Product

Working name: Adversarial FastAPI Security Platform

Core workflow:

```text
Import FastAPI project
→ isolate
→ Builder
→ Attacker
→ Evaluator
→ Fixer
→ verify
→ report
```

## Technology decisions

### Desktop

- Flutter
- Dart
- Riverpod
- REST + WebSocket

### Backend

- Python
- FastAPI
- Pydantic
- asyncio

### Data

- MongoDB
- Local scan workspace/filesystem

### Isolation

- Docker

### AI

- Provider-agnostic LLM abstraction

## Current architecture decisions

- Flutter is presentation/client layer.
- Python owns orchestration, agents, security testing, Docker, and patching.
- MongoDB stores structured shared scan context.
- Imported source is treated as immutable input.
- Fixes are applied to a controlled workspace.
- Every fix should be re-tested.
- LLM output is never trusted blindly.

## Implemented features

None yet.

## In-progress work

None.

## Known issues

None.

## Important decisions log

### Initial decision

The product will focus on existing FastAPI projects as input rather than generating an application from scratch.

### Initial decision

The four agents have distinct responsibilities:

- Builder = understand
- Attacker = challenge
- Evaluator = verify
- Fixer = remediate

### Initial decision

Research data must be structured enough to compare multi-agent, single-agent, and traditional approaches.

## Agent handoff notes

When changing phases, add:

```text
Date:
Phase:
What was implemented:
Files/modules changed:
Tests/checks run:
Known limitations:
Next recommended task:
```

## Do not record here

- secrets
- API keys
- passwords
- huge logs
- complete source files
- private user data
- raw LLM chain-of-thought

Keep this file concise enough that a new coding agent can understand the project quickly.