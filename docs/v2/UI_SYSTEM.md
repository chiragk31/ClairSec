# ClairSec v2 — UI/UX System

Extends `docs/DESIGN.md` (still binding: security-workstation feel, severity never by
colour alone, evidence honesty, accessibility). This document adds the **token system,
light/dark modes, theme presets, responsive layout, components, motion and language**
needed for v2. Goal: every screen looks like it was designed by one person on one day.

---

## 1. Principles

1. **Calm by default, vivid on signal.** Neutral surfaces; colour is spent on severity,
   status and the one primary action per screen.
2. **One source of truth for style.** No widget may use a raw `Color(...)`, raw font
   size, or raw padding number. Everything comes from tokens (§2–§4).
3. **Explain, then detail.** Each screen leads with a plain-language sentence, then the
   precise data (§9).
4. **Never a dead end.** Empty, loading, error, offline and fallback states are designed,
   each with a next action.
5. **Fast feels real.** Skeleton loaders over spinners; optimistic UI only for local
   state (theme, filters), never for scan results.

---

## 2. Colour tokens

Implement as a `ThemeExtension<ClairTokens>` (`lib/core/theme/tokens.dart`) with
`light` and `dark` instances, accessed via `context.tokens`. Replace every
`AppColors.*` / `SeverityColors.*` reference (≈285 today) — keep the old classes only
as deprecated aliases during migration, then delete them.

### 2.1 Neutral & brand (default preset "Midnight / Daylight")

| Token | Dark | Light | Use |
|-------|------|-------|-----|
| `bg` | `#0D1117` | `#F6F8FA` | App background |
| `surface` | `#161B22` | `#FFFFFF` | Cards, panels |
| `surfaceRaised` | `#21262D` | `#EEF1F4` | Hover, nested panels, inputs |
| `border` | `#30363D` | `#D0D7DE` | Dividers, card borders |
| `textPrimary` | `#E6EDF3` | `#1F2328` | Body, titles |
| `textSecondary` | `#9198A1` | `#59636E` | Secondary text |
| `textMuted` | `#6E7681` | `#818B98` | Hints, disabled (not for required info) |
| `accent` | `#58A6FF` | `#0969DA` | Primary actions, links, focus |
| `accentMuted` | `#1F6FEB33` | `#0969DA1A` | Selected backgrounds |
| `focusRing` | `#58A6FF` | `#0969DA` | 2 px focus outline |

### 2.2 Severity (always paired with icon + label)

| Token | Dark | Light | Icon |
|-------|------|-------|------|
| `critical` | `#FF6B6B` | `#C9182B` | `Icons.dangerous` |
| `high` | `#FF9F43` | `#BC4C00` | `Icons.error` |
| `medium` | `#F2CC60` | `#9A6700` | `Icons.warning_amber` |
| `low` | `#56D4DD` | `#1B7C83` | `Icons.info` |
| `info` | `#9198A1` | `#59636E` | `Icons.help_outline` |

### 2.3 Status

| Token | Dark | Light | Meaning |
|-------|------|-------|---------|
| `success` | `#3FB950` | `#1A7F37` | Fix verified, check passed, ready |
| `warning` | `#D29922` | `#9A6700` | Inconclusive, limited coverage, degraded mode |
| `danger` | `#F85149` | `#CF222E` | Failed, regressed, unreachable |
| `running` | `#58A6FF` | `#0969DA` | In progress |
| `neutral` | `#9198A1` | `#59636E` | Not started, cancelled |

Agent identity colours (cards, timeline rails): Builder `#A371F7`/`#8250DF`,
Attacker `#FF7B72`/`#CF222E`, Evaluator `#F2CC60`/`#9A6700`, Fixer `#3FB950`/`#1A7F37`,
Verifier `#56D4DD`/`#1B7C83`, Assistant `#58A6FF`/`#0969DA`.

**Contrast is verified, not assumed:** add a unit test that computes WCAG contrast for
every text-bearing token pair (`textPrimary`/`textSecondary`/each severity/status on
`bg`, `surface`, `surfaceRaised`) in both modes and every preset, and fails below 4.5:1
(3:1 for icons and large text). Adjust values, not the test.

### 2.4 Theme presets ("templates")

Presets change **neutral tint and accent only**; severity and status colours stay
semantically identical across presets (users learn them once).

| Preset | Accent dark / light | Neutral tint |
|--------|--------------------|--------------|
| Midnight / Daylight (default) | `#58A6FF` / `#0969DA` | Cool grey |
| Ocean | `#39C5CF` / `#0E7C86` | Blue-slate |
| Forest | `#56D364` / `#1A7F37` | Green-grey |
| Violet | `#BC8CFF` / `#8250DF` | Purple-grey |
| High contrast | `#FFFFFF` on `#000000` / `#000000` on `#FFFFFF` | Pure black/white, 2 px borders |

Settings → Appearance: **Mode** (System / Light / Dark), **Preset** (live preview
tiles), **Density** (Comfortable / Compact), **Text size** (90–130 %), **Reduce
motion** (System / On / Off). Persist with `shared_preferences`; apply instantly with no
restart; respect OS mode when "System".

---

## 3. Typography

Bundle fonts as assets (offline demos): **Inter** (UI) and **JetBrains Mono** (code,
logs, requests). Set `GoogleFonts.config.allowRuntimeFetching = false`.

| Role | Size / weight / line height |
|------|-----------------------------|
| `display` (score, hero numbers) | 40 / 700 / 1.1 |
| `h1` page title | 24 / 650 / 1.25 |
| `h2` section | 18 / 600 / 1.3 |
| `h3` card title | 15 / 600 / 1.35 |
| `body` | 14 / 400 / 1.5 |
| `bodySmall` | 13 / 400 / 1.45 |
| `label` (chips, badges) | 12 / 600 / 1.2, +0.2 letter spacing |
| `mono` | 13 / 400 / 1.5 |

Presenter mode multiplies all sizes by 1.25.

## 4. Spacing, radius, elevation

- Spacing scale (4-pt): `xs 4, sm 8, md 12, lg 16, xl 24, xxl 32, xxxl 48`.
  Compact density = one step smaller for paddings inside lists/tables only.
- Radius: `sm 6` (chips, inputs), `md 10` (cards), `lg 14` (dialogs, panels), `pill 999`.
- Elevation: flat cards with 1 px `border`; shadows only on overlays (dialogs, palette,
  toasts) — dark mode uses a lighter surface instead of a shadow.

## 5. Responsive layout

Window classes by width (desktop windows get resized; it must work narrow):

| Class | Width | Navigation | Content | Assistant panel |
|-------|-------|------------|---------|-----------------|
| Compact | < 720 | Top bar + drawer | Single column; tables become cards | Full-screen sheet |
| Medium | 720–1199 | Collapsed `NavigationRail` (icons + tooltips) | 1–2 columns | Overlay panel |
| Expanded | 1200–1599 | Extended rail with labels | 2–3 columns; master-detail | Docked side panel (360 px), toggle |
| Large | ≥ 1600 | Extended rail | Max content width 1440, centred | Docked |

- One `LayoutBuilder`-based `Breakpoints` helper; screens never read
  `MediaQuery.size` directly.
- Master-detail screens (Vulnerabilities, Scans, Reports): side-by-side on Expanded+,
  push navigation on Compact/Medium.
- Minimum window size 900×600 (set via `window_manager` or platform runner); still
  test the Compact layout because users split screens.
- Tables: horizontal scroll inside their own container; the page itself never scrolls
  horizontally.
- Widget tests render key screens at 400, 900, 1300 and 1700 px widths with no overflow
  errors.

## 6. App shell

```text
┌─────────────────────────────────────────────────────────────────────┐
│ ◆ ClairSec   [Ctrl+K Search or jump to…]   [LIVE ▾]  ◐  ?  ✦ Ask   │ top bar
├──────┬──────────────────────────────────────────────┬───────────────┤
│ nav  │ Page header: title · plain-language subtitle │ Ask ClairSec  │
│ rail │ ─────────────────────────────────────────────│ (context-     │
│      │ content                                      │  aware chat)  │
│      │                                              │               │
├──────┴──────────────────────────────────────────────┴───────────────┤
│ status bar: backend ● mongo ● docker ● · active job · tokens $0.04 │
└─────────────────────────────────────────────────────────────────────┘
```

Navigation: Dashboard · Projects · Scans · Findings · Fixes · Agents · Reports ·
Research · Settings. The mode badge (`LIVE`, `DEMO APP`, …, see `FEATURES.md` F4) is
always visible in the top bar.

## 7. Component library (`lib/ui/` — build once, use everywhere)

| Component | Notes |
|-----------|-------|
| `CsCard` | Title, optional subtitle/plain line, trailing actions, body; hover state |
| `CsBadge` / `SeverityBadge` / `StatusBadge` / `ModeBadge` | Icon + label always |
| `CsButton` | primary / secondary / ghost / danger; loading state; keyboard focus |
| `CsStat` | Number + label + delta + optional sparkline |
| `ScoreGauge` | Radial gauge, before→after sweep animation, grade letter |
| `CsStepper` | Vertical stages with status, elapsed, plain line, error slot |
| `TimelineItem` | Agent rail colour, icon, title, plain line, time, link |
| `CodeBlock` / `DiffView` / `HttpExchangeView` | Mono, copy button, line numbers, redaction marks |
| `FileTree` | Collapsible, file-type icons, sizes |
| `EmptyState` / `ErrorState` / `OfflineState` | Illustration icon, explanation, primary action |
| `Skeleton` | Shimmer placeholders matching final layout (static when reduce motion) |
| `CsToast` | Success / info / warning / danger, auto-dismiss, action button |
| `ProvenanceStrip` | F7 step chain |
| `AssistantPanel` | F11 chat with citations and suggestion chips |
| `CommandPalette` | F14 |

Each component gets a widget test and appears in a **Gallery** screen (debug builds
only, route `/_gallery`) that renders every component in both modes — the fastest way
to catch inconsistency.

## 8. Motion

- Durations: 120 ms (hover/press), 200 ms (panels, tabs), 400 ms (page), 900 ms (score
  gauge sweep). Curves: `easeOutCubic` in, `easeInCubic` out.
- Meaningful only: a confirmed finding pulses once; the score sweeps once; the timeline
  slides new items in. No looping decorative animation.
- Reduce motion → all durations 0, pulses become a static highlight.

## 9. Language: precise + human

Every screen header has a plain-language subtitle, and every technical term has an `ⓘ`
that opens the glossary. Tone: calm, specific, no fear-mongering, no hacker clichés.

| Precise term | Plain language (shown beside it) |
|--------------|----------------------------------|
| Builder agent | "Reads your app and maps every door into it." |
| Attacker agent | "Tries those doors the way a real attacker would — safely, inside a sealed copy." |
| Evaluator agent | "Double-checks every attack with hard rules, so nothing is reported on a hunch." |
| Fixer agent | "Writes a code change that closes the door." |
| Verifier | "Tries the same attack again, and checks the app still works." |
| Isolation / container | "A sealed copy of your app that can't touch your computer or network." |
| BOLA | "Anyone can open anyone else's records just by changing a number in the address." |
| BFLA | "A regular user can press buttons that should only work for admins." |
| Mass assignment (BOPLA_MASS_ASSIGN) | "The app lets people change fields they should never control, like their own role." |
| Excessive data exposure (BOPLA_DATA_EXPOSURE) | "The app sends back more private details than the screen needs, like passwords or emails of others." |
| Unrestricted resource consumption (RESOURCE_CONSUMPTION) | "Nothing stops someone from hammering the app until it slows down or runs up costs." |
| Broken authentication | "The lock on the front door can be opened without the right key." |
| Injection | "The app runs text a visitor typed as if it were its own instructions." |
| Security misconfiguration | "A setting was left in an unsafe default, like a debug page open to everyone." |
| Oracle | "A strict, automatic rule that decides whether an attack really worked." |
| Confirmed | "We proved it: the attack worked, more than once." |
| Inconclusive | "Something looked wrong, but we could not prove it." |
| Regressed | "The fix stopped the attack but broke something else, so we don't count it as fixed." |
| CVSS | "A standard 0–10 scale for how serious a problem is." |
| Posture score | "A summary of what we found and fixed — not a guarantee that nothing else exists." |

The glossary lives in one Dart file **and** one backend file (for reports and the
offline assistant); a test asserts both have the same keys. Map the exact category names
to `docs/VULN_TAXONOMY.md` §2 — add entries for any category missing above.

## 10. Screen blueprints

**Dashboard:** readiness banner (only when not ready) → hero row: posture score gauge
for the most recent project + 4 `CsStat`s (projects, scans, confirmed, verified fixes)
→ "Active now" (running job stepper, if any) → recent scans → top confirmed findings →
score trend per project.

**Projects:** segmented import (Local folder / GitHub URL / Demo app) → import stepper
→ project cards with status, last score, "Run full check" (Autopilot).

**Scan detail (centrepiece):** header with mode badge + Autopilot stepper → agent cards
row → three columns on Expanded: attack timeline | attack-surface map | live counters &
cost; tabs on narrower widths.

**Finding detail:** title + severity/status badges + plain-language sentence → provenance
strip → tabs: Evidence (HTTP exchange) · Replay · Fix · Source · Explain. Sticky
"Ask about this finding" chip.

**Fix review:** split view (`DESIGN.md` §8) + three proof cards (F9) above the diff.

**Reports:** list per scan → preview → export buttons; "Executive" / "Technical" toggle.

## 11. Definition of done for any UI work

- Uses only tokens and `lib/ui/` components; no raw colours, sizes or paddings.
- Light and dark both checked; contrast test passes.
- Renders without overflow at 400 / 900 / 1300 / 1700 px.
- Keyboard reachable with visible focus; icon-only buttons have tooltips/semantics.
- Has empty / loading / error states; fallback mode explained where relevant.
- `flutter analyze` clean, widget tests added.
