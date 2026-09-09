# Testing Strategy

## 1. Testing pyramid

```text
             E2E
            /   \
      Integration
        /       \
      Unit tests
```

## 2. Backend unit tests

Test:

- Pydantic schemas
- agent state transitions
- repository methods
- finding classification
- severity logic
- patch validation
- verification result logic
- configuration validation
- error handling

## 3. Agent tests

Use deterministic fixtures where possible.

Do not make the entire test suite depend on a live LLM provider.

Create mock LLM responses for:

- valid output
- malformed output
- refusal
- timeout
- hallucinated file
- invalid patch
- contradictory result

## 4. Docker integration tests

Verify:

- target starts
- health check succeeds
- target stops
- failed builds are handled
- timeouts work
- resources are cleaned up
- workspace isolation works

## 5. End-to-end tests

At least one intentionally vulnerable toy FastAPI application should be included as a controlled fixture.

The E2E flow should verify:

```text
import
→ build
→ start
→ discover
→ attack
→ evaluate
→ patch
→ restart
→ verify
→ report
```

## 6. Regression tests

Every confirmed bug in the platform should become a regression test where practical.

## 7. Flutter tests

Test:

- navigation
- providers
- API service behavior
- WebSocket event handling
- loading states
- empty states
- error states
- vulnerability display
- fix review
- scan cancellation

## 8. Verification principle

A generated patch is not a successful fix until the relevant security test is re-run and the expected secure behavior is observed.

## 9. Definition of done

A feature is done only when:

- implementation exists
- tests exist
- failure paths are handled
- UI is connected if applicable
- documentation is updated
- `MEMORY.md` is updated