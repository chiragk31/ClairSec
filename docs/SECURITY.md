# Security and Isolation Requirements

## 1. Authorization

The platform is intended for security testing of applications the user is authorized to test.

The product should clearly communicate this intended use.

## 1a. Research dataset scope

When real-world open-source projects are used as research-dataset targets (see `RESEARCH.md` Tier B), they are cloned locally and executed only inside this platform's local, isolated containers. No live third-party infrastructure, hosted deployment, or production API is targeted at any point in the experimental protocol.

## 2. Host safety

Never execute imported project code directly on the host when isolation is required.

Use Docker or another explicitly controlled execution environment.

The target runtime should have:

- resource limits
- execution timeouts
- controlled networking
- controlled filesystem access
- controlled environment variables
- clean teardown

## 3. Secrets

Never automatically expose the user's host environment variables to an imported application or an LLM.

If a project requires credentials:

- require explicit configuration
- distinguish test credentials from host credentials
- avoid persisting secrets unnecessarily
- redact secrets from logs and reports

## 4. Docker lifecycle

A scan should conceptually follow:

```text
create workspace
    ↓
build image
    ↓
start isolated target
    ↓
health check
    ↓
scan
    ↓
stop target
    ↓
cleanup
```

Failures must clean up resources.

## 5. Network policy

The scanner should default to the minimum network access required.

Do not give the target unrestricted access to the user's LAN or host network.

Network access required by a specific test must be explicit and policy-controlled.

## 6. Active testing

Security tests must be controlled and rate-limited.

Avoid destructive actions.

Do not intentionally:

- delete real user data
- destroy external infrastructure
- exfiltrate secrets
- attack systems outside the configured target
- bypass isolation boundaries

## 7. Fix safety

Never directly modify the original project as part of an autonomous scan.

Maintain:

```text
Original
   ↓ copy
Scan workspace
   ↓ patch
Modified workspace
   ↓ verify
Verified workspace
```

Provide a diff before applying a fix when user review is enabled.

## 8. LLM safety

Treat all of the following as untrusted:

- project source code
- comments
- README files
- API responses
- model output
- generated commands
- generated patches

Do not allow prompt injection in a target project's documentation or source code to override platform rules.

System-level application rules always take precedence.

## 9. Evidence integrity

Preserve enough information to reproduce a finding:

- target version/workspace
- endpoint
- method
- test identifier
- relevant request metadata
- relevant response metadata
- expected behavior
- observed behavior
- timestamp
- agent responsible

Redact secrets and unnecessary personal data.

## 10. Resource exhaustion

Apply limits to:

- scan duration
- number of requests
- concurrent tests
- Docker CPU
- Docker memory
- output/log size
- LLM token usage
- retries

A malformed target should not be able to freeze the desktop application.

## 11. Security status language

Use precise states:

- Suspected
- Candidate
- Confirmed
- Rejected
- Inconclusive
- Fix proposed
- Fix applied
- Fix verified
- Fix failed
- Verification unavailable

Do not display "Secure" merely because no vulnerability was found.