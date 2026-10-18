#!/usr/bin/env python3
"""
CLI tool to export a completed scan as a versioned scan bundle (FEATURES.md F4).
Usage:
    python scripts/record_bundle.py <scan_id> [--output <path>]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure backend package is in python path
repo_root = Path(__file__).resolve().parent.parent
backend_path = repo_root / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.database.client import close_client, get_database, init_client, storage_mode
from app.services.bundle_service import record_scan_bundle, save_bundle


async def _main(scan_id: str, output: str | None) -> None:
    # The backend's database must be initialised before use (MONGODB_URL from backend/.env).
    await init_client()
    if storage_mode() != "mongodb":
        print("[!] MongoDB is not reachable, so there are no stored scans to export.", file=sys.stderr)
        sys.exit(2)
    db = get_database()
    print(f"[*] Exporting scan '{scan_id}' from MongoDB...")
    try:
        bundle = await record_scan_bundle(scan_id, db)
    except ValueError as err:
        print(f"[!] Error: {err}", file=sys.stderr)
        sys.exit(1)

    out_file = save_bundle(bundle, output)
    size_kb = bundle.get("bundle_size_bytes", 0) / 1024
    print(f"[+] Bundle successfully created: {out_file}")
    print(f"    - Events: {len(bundle.get('events', []))}")
    print(f"    - Findings: {len(bundle.get('findings', []))}")
    print(f"    - Size: {size_kb:.1f} KB ({bundle.get('bundle_size_bytes', 0)} bytes)")
    print(f"    - Recorded at: {bundle.get('recorded_at')}")
    await close_client()


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a ClairSec scan bundle for playback.")
    parser.add_argument("scan_id", help="The scan ID to export.")
    parser.add_argument("--output", "-o", help="Optional output filepath for the bundle.")
    args = parser.parse_args()

    asyncio.run(_main(args.scan_id, args.output))


if __name__ == "__main__":
    main()
