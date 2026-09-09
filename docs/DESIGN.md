# Desktop UI/UX Design

## 1. Design goal

The application should feel like a professional security-analysis workstation, not a generic CRUD dashboard.

The visual language should communicate:

- security
- observability
- technical precision
- trust
- controlled automation

Avoid excessive hacker/cyberpunk decoration.

## 2. Theme

Primary experience:

- dark desktop-first interface
- high contrast
- restrained accent color
- clear severity indicators
- readable code and logs

Use semantic colors consistently:

- Critical
- High
- Medium
- Low
- Informational
- Success
- Warning
- Error

Do not communicate severity using color alone; include labels/icons/text.

## 3. Main navigation

Recommended navigation:

```text
Dashboard
Projects
Scans
Vulnerabilities
Agents
Reports
Research
Settings
```

## 4. Dashboard

Show:

- total projects
- total scans
- vulnerabilities found
- vulnerabilities fixed
- critical/high findings
- recent scans
- current scan status
- detection/fix metrics when research mode is enabled

## 5. Project import screen

Provide:

- folder picker
- optional project name
- detected FastAPI entry point
- dependency information
- validation result
- isolation readiness

Do not make users understand Docker internals to start a scan.

## 6. Scan screen

The scan screen is the centerpiece.

Show four agent cards:

```text
Builder       Attacker       Evaluator       Fixer
  ✓              ⚡              ◌              ◌
```

Each card should display:

- status
- current task
- progress when measurable
- event count
- elapsed time

Below it:

- live event stream
- discovered endpoints
- tests executed
- findings discovered
- findings confirmed
- fixes generated
- verification results

## 7. Vulnerability screen

Each finding should show:

- title
- severity
- confidence
- endpoint
- HTTP method
- category
- explanation
- impact
- evidence
- source location
- reproduction summary
- fix status
- verification status

## 8. Fix review

Use a split layout:

```text
┌───────────────────┬──────────────────────┐
│ Vulnerability     │ Proposed Fix         │
│                   │                      │
│ Explanation       │ Source diff          │
│ Evidence          │                      │
│                   │                      │
└───────────────────┴──────────────────────┘
```

Actions:

- Apply Fix
- Reject
- Re-run Verification
- Open Source
- Revert

## 9. Agent observability

Allow users to inspect structured agent activity.

Do not expose raw internal chain-of-thought.

Show concise operational information such as:

- task
- input context summary
- action
- result
- evidence
- status
- duration

## 10. Research dashboard

Show charts/tables for:

- detection rate
- false positive rate
- fix accuracy
- verification success
- average scan duration
- findings by severity
- findings by vulnerability category
- multi-agent vs multi-agent-without-evaluator vs single-agent vs traditional baseline

Presentation rules that follow from `METHODOLOGY.md`:

- **Never plot a point estimate without its interval.** Every rate is shown as
  `0.72 [0.61, 0.81]` or as a bar with error bars. A bare number implies a precision
  the k=3 trials do not support, and screenshots of dashboards end up in papers.
- Label the false-positive figure **FDR**, not "false positive rate", so the
  denominator is unambiguous.
- Show the **n** and the exclusion count for every cell. A comparison drawn over
  different denominators must be visibly different.
- Show cost and tokens alongside detection, not on a separate screen. The trade-off is
  the interesting part of the result.
- The dashboard reads from computed summaries; it never recomputes metrics in Dart.
  One implementation of the matching function, in Python, for every consumer.

## 10a. Evidence honesty in the UI

The UI is where a finding stops being data and becomes a claim, so the distinctions
`SECURITY.md` §11 draws must survive into pixels:

- **Runtime-confirmed and source-suspicion findings must be visually distinct** — not
  merely a different word in a details pane. A suspicion presented like a confirmation
  is how a security tool loses a user's trust permanently.
- `inconclusive` is a first-class state, not a variant of `rejected`.
- A fix that blocked the exploit but broke the functional suite shows as `regressed`,
  never as a success.
- Show the model, prompt version, and platform version on any exported report.
- A live cost/token meter during scans (`OPERATIONS.md` §8).

## 10b. Accessibility

`DESIGN.md` §2 already forbids conveying severity by colour alone. Extend that:

- Keyboard navigation for every action; visible focus indicators.
- Contrast meeting WCAG AA against the dark theme — verify, do not assume; dark
  themes fail contrast checks more often than light ones.
- Semantic labels on icon-only controls for screen readers.
- Respect the OS reduced-motion setting for any progress animation.
- Do not rely on hover alone to reveal information a user needs to act.

## 11. Typography

Prioritize readability.

Recommended approach:

- one UI font family
- monospace font for code/logs
- strong hierarchy for page titles and section titles
- compact tables
- comfortable spacing

## 12. UX principles

- Every long-running operation has visible status.
- Every important action has feedback.
- Never hide why a scan failed.
- Preserve scan history.
- Let users inspect evidence before trusting a finding.
- Let users see exactly what code will change before applying a fix.