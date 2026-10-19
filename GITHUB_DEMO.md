# GitHub Demo Repos for ClairSec

Public repositories you can import in ClairSec (**Projects → Import → GitHub URL**) during a demo.

**How to import:** paste the URL → (only if listed) put the path in the **sub-folder** field →
tick **"I am authorised to test this code"** → **Import** → on the new project card press **Run full check**.
Importing needs internet but **not** Docker; the scan (Run full check) needs Docker running.

---

## 1. Guaranteed full demo — verified end to end

| URL | Sub-folder | What you will see |
|---|---|---|
| `https://github.com/chiragk31/ClairSec` | `backend/tests/fixtures/vulnerable_fastapi_app` | Import (file tree, commit SHA, masked exposed secrets) → scan in a sealed container → **3 confirmed vulnerabilities** (BOLA, mass assignment, debug-config leak) → fixed → each fix verified in its own container → score **55 (D) → 100 (A)** → report (PDF/HTML/SARIF). |
| `https://github.com/chiragk31/ClairSec` | `backend/tests/fixtures/secure_fastapi_app` | "Trust check": the same API, correctly secured → expect **0 confirmed findings**. Shows ClairSec does not invent problems. |

## 2. Third-party repos — import tested, scan not yet verified

All of these were imported successfully with ClairSec's real importer (download + validation + secret scan;
nothing from the repo was executed). Whether the app boots in the sandbox and how many findings a scan
reports has **not** been verified yet — try them before presenting.

| Repo | What it is | Import result | Best used to show |
|---|---|---|---|
| [Ganapatiramanan13/fastapi-security-lab](https://github.com/Ganapatiramanan13/fastapi-security-lab) | Deliberately vulnerable FastAPI app + its secure version (BOLA, mass assignment, weak JWT); SQLite, no external database | ✅ valid, 58 files | ClairSec on someone else's code. **Note:** ClairSec auto-selects `secure_app/main.py` (the secured version); the vulnerable app cannot be chosen via the sub-folder field because it imports from the repo root (`from vulnerable_app...`). |
| [Checkmarx/capital](https://github.com/Checkmarx/capital) | Well-known built-to-be-vulnerable API (OWASP API Top 10), FastAPI + React | ✅ valid, 217 files, **11 exposed secrets found (shown masked)** | The **import + secret detection** step. Its scan will most likely fail to boot because it needs PostgreSQL — use it for import only. |
| [naryal2580/vfapi](https://github.com/naryal2580/vfapi) | Vulnerable FastAPI app based on the OWASP Top 10 (2021) | ✅ valid, single `main.py` | A simple real-world vulnerable app. |
| [trottomv/python-insecure-app](https://github.com/trottomv/python-insecure-app) | Vulnerable FastAPI app (hard-coded secrets, template injection) | ✅ valid, `app/main.py` | Import + scan; ClairSec does not test template injection, so expect few findings. |
| [tiangolo/uvicorn-gunicorn-fastapi-docker](https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker) | Popular FastAPI Docker image repo with a tiny example app | ✅ valid, 20 files | A clean real repo; expect few or no findings. |
| [burhan-727/crud-api](https://github.com/burhan-727/crud-api) | Tiny in-memory to-do API | ⚠️ imports, but has no `requirements.txt` | **Not for scanning** — the container cannot be built without a dependency file. |

## 3. Suggested demo order

1. Import **Checkmarx/capital** → show the file tree and the **masked exposed secrets** card.
2. Import **chiragk31/ClairSec** with sub-folder `backend/tests/fixtures/vulnerable_fastapi_app` →
   **Run full check** → find → fix → verify → score 55 → 100 → **Open PDF** report.
3. Optional: the `secure_fastapi_app` sub-folder as the trust check (0 findings).

## 4. If there is no internet or Docker

- No internet: **Projects → Import → Demo app** (scans ClairSec's bundled demo app, no download needed).
- No Docker: the Demo app still runs (badge `DEMO APP`), or **Scans → Watch a recorded run** (a real earlier scan, badge `RECORDED RUN`).
- Full fallback manual: [`ClairSec_Final_Presentation_Guide.pdf`](ClairSec_Final_Presentation_Guide.pdf), section 6.
