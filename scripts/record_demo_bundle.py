#!/usr/bin/env python3
"""
Record the shipped demo bundle from a REAL Demo-mode scan (FEATURES.md F4).

Runs the full ClairSec pipeline (Builder → Attacker → Evaluator → Fixer → Verifier)
against ClairSec's own bundled vulnerable app on the trusted fixture runner with the
offline AI provider, on a temporary in-memory database, then exports that scan as a
`clairsec.bundle/v1` file. Nothing in the bundle is hand-written: every event,
finding, patch and verification result is what the real run produced.

Usage (from the repo root):
    python scripts/record_demo_bundle.py [--fixture vulnerable|secure] [--output PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "backend"))
os.environ.setdefault("MONGODB_URL", "mongodb://127.0.0.1:9")  # force the in-memory database
os.environ.setdefault("LLM_PROVIDER", "mock")
# Scan workspaces go to a throwaway temp folder, never into the current directory.
import tempfile  # noqa: E402

os.environ.setdefault("WORKSPACE_ROOT", tempfile.mkdtemp(prefix="clairsec-record-"))


async def _main(fixture: str, output: str | None) -> None:
    from app.core.config import settings
    from app.database.client import get_database, init_client
    from app.database.models import IsolationStatus, ProjectRecord, ValidationStatus
    from app.services.bundle_service import record_scan_bundle, save_bundle
    from app.services.scan_service import ScanService

    await init_client()
    db = get_database()
    source = Path(settings.trusted_fixtures_root) / (
        "secure_fastapi_app" if fixture == "secure" else "vulnerable_fastapi_app"
    )
    project = ProjectRecord(
        id=str(uuid.uuid4()),
        name="Trust Check: Secure FastAPI App" if fixture == "secure" else "Demo: Vulnerable FastAPI App",
        source_path=str(source),
        entry_point="main.py",
        validation_status=ValidationStatus.VALID,
        isolation_status=IsolationStatus.READY,
        origin="demo_fixture",
    )
    service = ScanService(db)
    await service._project_repo.create(project)
    scan = await service.submit_scan(project.id)
    print(f"[*] Running a real Demo scan of {source.name} (scan {scan.id[:8]})...")
    for _ in range(600):
        current = await service.get_scan(scan.id)
        if current and current.state in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.5)
    if current.state != "completed":
        print(f"[!] Scan ended as {current.state}: {current.error}", file=sys.stderr)
        sys.exit(1)

    bundle = await record_scan_bundle(scan.id, db)
    bundle["recorded_from"] = "real Demo-mode scan (trusted fixture runner, offline AI provider)"
    default = repo_root / "demo" / "bundles" / f"demo-{fixture}.clairsec.json"
    path = save_bundle(bundle, output or default)
    p = current.posture or {}
    print(f"[+] Bundle written: {path}")
    print(f"    events={len(bundle.get('events', []))} findings={len(bundle.get('findings', []))} "
          f"score {p.get('before')} -> {p.get('after')}")


def main() -> None:
    logging.disable(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--fixture", choices=("vulnerable", "secure"), default="vulnerable")
    parser.add_argument("--output", "-o")
    args = parser.parse_args()
    asyncio.run(_main(args.fixture, args.output))


if __name__ == "__main__":
    main()
