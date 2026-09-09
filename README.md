# ClairSec — Adversarial Multi-Agent FastAPI Security Research Platform

ClairSec is an adversarial multi-agent security research platform for FastAPI applications. It pairs an autonomous adversarial testing pipeline with an isolated runtime environment and structured evaluation.

## Prerequisites

- **Python**: `3.11.x` (see `backend/.python-version`). Python 3.12 is not supported.
- **Flutter**: `>=3.44.0` with Dart `>=3.13.2 <4.0.0` (as recorded in `desktop/pubspec.lock`).
  Run `flutter upgrade` if your local Flutter SDK is below 3.44.0.
- **Docker**: Docker Desktop or Docker Engine running with Linux container support.
- **MongoDB**: MongoDB 7.0+ listening on `mongodb://localhost:27017` (configurable via `MONGODB_URL`).

## Architecture Overview

- `backend/`: FastAPI backend with container isolation, MongoDB persistence, and research agent orchestrators.
- `desktop/`: Flutter desktop application communicating over authenticated loopback HTTP/WebSocket with the backend.
- `docs/`: Comprehensive specifications, threat models, methodology, and phase definitions.

## Getting Started

### Backend

1. Create a Python 3.11 virtual environment:
   ```bash
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   pip install -r backend/requirements-dev.txt
   ```
3. Configure environment:
   ```bash
   cp backend/.env.example backend/.env
   # Fill in required values (MONGODB_URL, WORKSPACE_ROOT, LLM_API_KEY)
   ```
4. Run tests:
   ```bash
   cd backend
   pytest -m "not docker and not llm" -v
   ```

### Desktop

1. Verify Flutter version:
   ```bash
   flutter --version  # Must be >=3.44.0 (Dart >=3.13.2)
   ```
2. Fetch dependencies and run tests:
   ```bash
   cd desktop
   flutter pub get
   flutter analyze
   flutter test
   ```
