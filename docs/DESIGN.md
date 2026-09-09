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
- multi-agent vs single-agent vs traditional baseline

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