# ClairSec — 7-Minute Demo Script

Audience: a college panel (mixed technical and non-technical). Every step has a
fallback, so nothing on stage depends on Docker, the internet or an API key.

Before you start: Presenter mode ON (press **F11**), theme that reads well on the
projector (Settings → Appearance; Daylight for bright rooms), notifications off,
backend running, Dashboard banner checked.

---

## 0:00 — The problem (30 s, no clicks)

> "AI writes more code every day, and nobody has time to pen-test it. ClairSec attacks
> your API the way a real attacker would — inside a sealed box — proves what it finds,
> writes the fix, and proves the fix works. And no AI is allowed to grade its own work."

## 0:30 — Readiness and honesty (30 s)

- Show the **Dashboard banner**: Backend / MongoDB / Docker / AI / Git, each with its fix.
- Point at the **mode badge** in the top bar (`LIVE`, `DEMO APP`, …) and, if shown,
  `TEMPORARY STORAGE`.
> "It always tells you what it's running on. Nothing on screen is ever faked."

**Fallback:** if the backend is down, the banner says so — start it (`uvicorn`) or go
straight to *Watch a recorded run* (step 6 fallback).

## 1:00 — Import (1 min)

- Projects → **Import** → *GitHub URL* → paste `https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker`
  → tick "I am authorised" → Import. Show the live steps, the file tree, the commit SHA
  and the **Import notes** card.
> "It downloads a snapshot, never runs anything from the repo on my laptop, and refuses
> archives that try to escape the folder."

**Fallback (no internet):** Import → *Demo app* → *Scan Demo* (ClairSec's own
deliberately vulnerable API).

## 2:00 — Run full check on the Demo app (1 min)

- On the **Demo: Vulnerable FastAPI App** card → **Run full check** (Autopilot).
- Open the scan: agent cards, **attack timeline** filling live, the **attack-surface
  map**.
> "Builder maps every door, Attacker tries them, Evaluator double-checks with hard rules,
> Fixer writes the patch, Verifier tries the attack again."

## 3:00 — The score (30 s)

- **Security score 55 (D) → 100 (A)** with the "limited coverage" note.
> "Computed by code from confirmed findings only. A high score means we didn't find these
> problems — never that the app is 'secure'."

## 3:30 — A finding you can trust (1 min)

- Open **BOLA at /documents/{doc_id}**. Read the *In plain words* line.
- **Why you can trust this finding**: AI proposal → platform sent request → oracle fired →
  reproduced → CVSS computed → fix verified.
> "The AI only proposes. Every verdict after that is platform code."

## 4:30 — Live proof: replay (1 min) — the wow moment

- **Replay attack** on *Original app* → `ORACLE FIRED: the attack worked`, HTTP 200 with
  Bob's document.
- **Replay attack** on *Patched app* → `ORACLE CLEAR: the attack was blocked`.
> "Same request, same judge. Before: leaked. After: blocked."

## 5:30 — Three proofs (30 s)

- **View Fix** → *Original exploit blocked* ✓ · *App still works* ✓ · *Endpoint
  preserved* ✓ · "No AI model voted on whether this fix works."
> "Deleting the endpoint would 'block' the attack too — that's why the third proof exists."

## 6:00 — Ask ClairSec (30 s)

- **Ctrl+J** → toggle *Explain simply* → chip *Is the fix safe?* → show the answer, its
  citation chips and the "Open this finding" link.
> "It can only read what was recorded, it cites its sources, and it can't change anything."

## 6:30 — Report (30 s)

- Reports → **Generate report** → **Open HTML**: executive page first, technical detail
  after; mention SARIF for GitHub/IDEs and "Print → Save as PDF".
- Optional: *Compare with previous scan* after re-running.

## 7:00 — Close

> "Real attacks, real evidence, verified fixes — and an AI that's never allowed to mark its
> own homework."

---

## Fallback map

| If this fails… | Do this instead |
|---|---|
| Docker off | Demo app runs without Docker (badge `DEMO APP`) |
| MongoDB off | Backend runs on temporary in-memory storage (badge `TEMPORARY STORAGE`) |
| No internet | Skip the GitHub step; use the Demo app |
| No AI key | Offline AI is used automatically; the assistant says "Offline assistant" |
| A live scan misbehaves | Scans → **Watch a recorded run** → *Demo: Vulnerable FastAPI App* (a real earlier run, badged `RECORDED RUN`) |
| Laptop/projector disaster | Open the exported HTML report in a browser |

## Likely panel questions

- **"Isn't this just ChatGPT finding bugs?"** No — an LLM never decides a verdict.
  Oracles (code) decide; the LLM proposes tests and patches. Show the provenance strip.
- **"How do you know the fix didn't break the app?"** Dual criterion plus endpoint check:
  the exploit is re-run and blocked, the app's checks still pass (or auto-generated
  read-only checks from its OpenAPI schema for real projects), and the route still exists.
- **"Is it safe to scan a random GitHub repo?"** It's downloaded as a tarball with size,
  file-count, path and symlink checks; it runs only inside a hardened container
  (no capabilities, read-only filesystem, internal network); ClairSec's own demo apps
  are the only code ever run directly.
- **"What's novel?"** Verified-fix proof (exploit blocked + still works + endpoint kept),
  injection-resistant grounded assistant, and an honest fallback chain that never fakes data.
