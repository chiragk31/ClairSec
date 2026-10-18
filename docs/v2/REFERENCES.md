# Prior Art & Borrowed Ideas (researched 2026-10-18)

Ideas are borrowed freely; **code is only reused when its licence allows**. Do not copy
code from AGPL projects (Shannon, Vulnhuntr, Deadend, TruffleHog) or CAI
(research-only licence). Self-reported benchmark numbers below are marked as such.

## Comparable projects

| Project | Licence | What it is | What ClairSec borrows |
|---------|---------|-----------|------------------------|
| Strix (usestrix/strix) | Apache-2.0 | Multi-agent AI pentester, Docker sandbox, PoC-validated findings | Live agent-team view + viewable past runs (→ F4 recorded replay, F5); diff-scoped re-tests (→ F13) |
| Shannon (KeygraphHQ/shannon) | AGPL-3.0 (ideas only) | White-box AI pentester; PDF/MD/JSON/SARIF reports | "No exploit, no report" two lanes (→ F7); ships sample reports for demos (→ F4); read-only repo mount (→ F2) |
| RedAmon | MIT | Attack-surface/attack-chain graph, approval gates, fix PRs | Attack graph visual (→ F10); per-solve transcripts as evidence standard |
| PentAGI | MIT (+EULA) | Go/React UI, Docker sandbox, Langfuse-style traces | Token/cost/latency per agent (→ F5 meter) |
| PentestGPT | MIT | Agentic pentester, reports cost per solve (self-reported) | Cost-per-confirmed-finding metric |
| hackingBuddyGPT | MIT | Research framework for LLM hacking agents | Evaluation framing |
| Schemathesis | MIT | Property-based API tests from OpenAPI | **Reused as a library** for the auto-generated functional suite (→ F9), via `from_url` against the container |
| OWASP ZAP | Apache-2.0 | DAST; report templates (high-level, modern HTML, risk×confidence, SARIF) | Executive vs technical report split, risk matrix (→ F12); already the planned baseline (`PHASES.md` Phase 11) |
| Nuclei | MIT | YAML template scanner | Declarative matcher design for oracles (future); use ≥ v3.8 (GHSA-29rg-wmcw-hpf4) |
| DefectDojo | BSD-3 | Vuln management | SARIF interoperability: stable `tool.driver.name`, CWE in `taxa`, CVSS in `properties` (→ F12) |
| Copilot Autofix / Snyk / CodeMender | Proprietary | Autofix | Failure modes to avoid: fixes that suppress the finding; CodeMender uses an **LLM judge** — ClairSec deliberately does not (talking point) |
| XBOW validation-benchmarks | Apache-2.0 | 104 Dockerised challenges | Saturated — smoke test only |
| BountyBench, CyberGym-E2E, CVE-Bench | papers | Detect/Exploit/Patch benchmarks | CyberGym-E2E's PoC + patch + still-works criterion matches ClairSec's dual criterion — cite in RESEARCH |

## Libraries

| Package | Licence | Use |
|---------|---------|-----|
| `schemathesis` (pip) | MIT | F9 smoke suite (4.x API: `schemathesis.openapi.from_url`) |
| `jinja2` (pip) | BSD-3 | F12 HTML report templates (autoescape on) |
| `jsonschema` (pip) | MIT | Validate SARIF output in tests |
| `cvss` (pip, RedHat) | LGPL-3.0+ | Optional cross-check of CVSS computation — import unmodified only |
| `pdf` + `printing` (pub) | Apache-2.0 | F12 PDF from the desktop side (alternative to a backend renderer) |
| `graphview` (pub) | MIT | F10 fallback if CustomPainter layout is insufficient |
| `flutter_markdown_plus` (pub) | BSD-3 | Assistant answers (F11); `flutter_markdown` is discontinued |
| `web_socket_channel`, `shared_preferences`, `window_manager` (pub) | BSD/MIT | F5, theming persistence, min window size |

## Security notes from the research

- **Do not add `litellm`**: compromised on PyPI in the March 2026 TeamPCP campaign
  (same campaign as Trivy CVE-2026-33634). If Trivy is ever used, pin by digest.
- Git: require ≥ 2.45.1 (CVE-2024-32002/32004) for the clone fallback; prefer the
  tarball path (F2).

## Not verified during research

Strix/Shannon "chat with your scan" (none found in OSS — F11 is a genuine
differentiator); several vendor autofix statistics; Shannon's and PentestGPT's XBOW
numbers (self-reported).
