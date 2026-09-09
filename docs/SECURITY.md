# Security and Isolation Requirements

> This document states the security requirements for handling **the target**.
> `THREAT_MODEL.md` models threats against **the platform itself** — a malicious
> repository attacking the scanner — and assigns numbered, testable controls
> (C1.1 … C7.4). The two are complements; read both before any phase that touches
> Docker, the filesystem, the LLM, or the HTTP surface.

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

### Required topology

The target attaches to a Docker network created with `internal=True`. Health checks
and Attacker traffic originate from a **scanner-side container** attached to both that
internal network and a bridge — not from the host.

**Known deviation in the current implementation.** Phase 3 dropped `internal=True`
because it blocked host→container health checks. That restored the health check by
removing the isolation: a hostile target can currently reach the user's LAN. The
scanner-side container is the correct resolution and is scheduled as `PHASES.md`
Phase 3.5. Until it lands, this is an open, documented risk rather than a solved
problem, and it must not be described as isolation in any write-up.

### Container flags

`--cap-drop=ALL`, `--security-opt=no-new-privileges`, non-root user, read-only rootfs
with a writable tmpfs, `pids-limit`, memory and CPU caps, and a hard wall-clock kill.
**Never mount the Docker socket into a target container.**

## 5a. The platform's own HTTP surface

The backend drives Docker and writes to disk, so anything that can reach it can do
those things. It must therefore:

- bind to `127.0.0.1` only, never `0.0.0.0`;
- require a per-launch bearer token on every REST and WebSocket request, handed to the
  Flutter client through an owner-readable local file;
- set a strict CORS policy with no wildcard origin, and validate the `Host` header
  against an allowlist — the Starlette `Host`-header handling bypass class of
  vulnerability makes this concrete rather than theoretical.

Details and rationale in `THREAT_MODEL.md` T7.

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

### How that is achieved

Stating that injection must not succeed is not a control. The mechanism, specified in
`LLM.md` §6 and `THREAT_MODEL.md` T1, is four layers:

1. **Quarantine** — untrusted target text is processed by a narrow extraction call
   that emits a typed schema. Only the schema reaches a prompt that plans or decides.
2. **Envelope** — untrusted spans are fenced with a per-call random nonce, and content
   inside is declared to be data. Content that itself contains the nonce or marker is
   an injection attempt: strip it and record the event as a measured quantity.
3. **Capability starvation** — the model cannot express a forbidden action, because it
   emits structured intent rather than commands, paths, or URLs. This is the layer
   that holds when the others fail, and it is the one to protect in review.
4. **Validation at the boundary** — paths resolved against the workspace root, patches
   AST-parsed and size-capped, requests host-locked to the target container.

Injection defences are probabilistic and layer 3 is the only one that is not. Design
accordingly: assume layers 1 and 2 will eventually be defeated, and ensure that a fully
compromised model still cannot write outside the workspace or send a request off-target.

An injection-canary fixture ships with the test suite, and injection resistance is
measured per experimental arm (`METHODOLOGY.md` §9).

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