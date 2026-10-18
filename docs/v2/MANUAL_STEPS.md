# What You Must Do By Hand

Things a coding agent cannot do for you. Do **Part A once now**, Part B each time you run
the app, Part C before the presentation.

## A. One-time setup (Windows)

1. **Docker Desktop**
   - Open PowerShell as admin: `wsl --update` then `wsl --shutdown`.
   - Start Docker Desktop; wait for **"Engine running"** (bottom-left).
   - Check: `docker info` prints a Server Version (no "cannot find the file" error).
   - Pre-pull the pinned base image so the first build is fast:
     `docker pull python:3.11-slim` (the app also does this automatically now).
2. **MongoDB — install it natively, NOT in Docker.** If MongoDB lives in a Docker
   container, stopping Docker also kills the database, and then the Demo safety net
   cannot start either. Install MongoDB Community Server as a Windows service:
   `winget install MongoDB.Server` (or the MSI from mongodb.com, "Install as a Service"
   ticked). Check: `Get-Service MongoDB` shows Running, or `netstat -ano | findstr 27017`.
   (Docker alternative only if you accept that limitation:
   `docker run -d --name clairsec-mongo --restart unless-stopped -p 27017:27017 mongo:7`.)
3. **Python backend environment** (in `backend/`):
   `python -m venv .venv` → `.venv\Scripts\activate` → `pip install -r requirements.txt -r requirements-dev.txt`
4. **Flutter**: `cd desktop && flutter pub get` (Flutter 3.47+ is already installed).
5. **AI provider (choose one)**
   - Cloud: put your key in `backend/.env` as `LLM_API_KEY=...` and set
     `LLM_PROVIDER=anthropic`. Never commit `.env`.
   - Local, free: install Ollama, run `ollama pull qwen2.5-coder:7b` (or set
     `OLLAMA_MODEL` in `backend/.env` to the model you pulled), set `LLM_PROVIDER=ollama`.
   - None: leave `LLM_PROVIDER=mock` — the app runs in offline-AI/Demo mode.
6. **Git** ≥ 2.45.1 (`git --version`) for GitHub imports of non-GitHub hosts.

## B. Every time you run it

```text
1. Start Docker Desktop → wait for "Engine running"
2. MongoDB service is running (it starts with Windows if installed as a service)
3. cd backend && .venv\Scripts\activate && uvicorn app.main:app --host 127.0.0.1 --port 8000
4. cd desktop && flutter run -d windows
5. In the app: Dashboard banner should be green. If not, it tells you what to fix.
```

## C. Before the presentation

- [ ] Run a full **Live** scan of the Demo app and of one small public GitHub FastAPI
      repo; keep both in scan history.
- [ ] Two recordings from real Demo scans already ship in `demo/bundles/` (re-create any
      time with `python scripts/record_demo_bundle.py` and `--fixture secure`). Optionally
      record your best Live run too: `python scripts/record_bundle.py <scan_id>`
      (needs MongoDB). In the app: Scans → **Watch a recorded run**.
- [ ] Rehearse `docs/v2/DEMO_SCRIPT.md` twice, once with Docker **stopped** to practise
      the fallback path.
- [ ] Press **F11** for Presenter mode (or Settings → Appearance), pick the theme that reads best on the projector (try
      Light/Daylight on bright rooms), close other apps, disable notifications.
- [ ] Have the exported HTML report open in a browser tab as a final fallback.
- [ ] Charge the laptop; projector test with the actual cable/adapter.

## Quick self-check (2 minutes, no Docker needed)

```text
cd backend && ..\venv\Scripts\python.exe -m pytest tests -q -m "not docker"   (≈5 min, all should pass)
cd desktop && flutter analyze && flutter test
```

## When something breaks

| Symptom | Fix |
|---------|-----|
| Banner: Docker red | Start Docker Desktop; if it won't start: `wsl --shutdown`, restart Docker |
| Banner: MongoDB red | `net start MongoDB` (admin) — or `docker start clairsec-mongo` if you used Docker |
| Banner: Backend unreachable | Start uvicorn (step B3); check port 8000 is free |
| Build fails with "Windows-only package" | Remove `pywin32` etc. from the project's requirements |
| Build timeout | Increase `DOCKER_BUILD_TIMEOUT` in `backend/.env` |
| GitHub import fails | Check internet; use Demo app instead |
| Anything else on stage | Switch to Demo app or "Watch a recorded run" |
