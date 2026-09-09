"""
Proof of Vulnerability (PoV) for SECURITY_MISCONFIG (CWE-16)
Target: GET /debug/config

Checks if unauthenticated endpoints expose internal environment variables,
database connection strings, or production API keys.
Oracle (VULN_TAXONOMY.md §4):
  - Exploited (True): Request to /debug/config returns 200 with sensitive keys
    (database_url, internal_api_key, etc.).
  - Secure (False): Route not found (404) or forbidden (403), exposing no secrets.
"""
from __future__ import annotations

import sys
from typing import Any
import httpx


def run_pov(client_or_url: Any) -> dict[str, Any]:
    """Execute SECURITY_MISCONFIG PoV against a TestClient, httpx.Client, or base URL."""
    target_path = "/debug/config"

    if isinstance(client_or_url, str):
        url = client_or_url.rstrip("/") + target_path
        with httpx.Client() as client:
            resp = client.get(url, timeout=5.0)
    else:
        resp = client_or_url.get(target_path)

    if resp.status_code == 200:
        data = resp.json()
        if "database_url" in data or "internal_api_key" in data:
            return {
                "exploited": True,
                "vuln_id": "VULN-MISCONFIG-001",
                "category": "SECURITY_MISCONFIG",
                "cwe": "CWE-16",
                "status_code": resp.status_code,
                "evidence": {
                    "database_url_exposed": "database_url" in data,
                    "internal_api_key_exposed": "internal_api_key" in data,
                    "debug_mode": data.get("debug_mode"),
                },
            }

    return {
        "exploited": False,
        "vuln_id": "VULN-MISCONFIG-001",
        "category": "SECURITY_MISCONFIG",
        "cwe": "CWE-16",
        "status_code": resp.status_code,
    }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    result = run_pov(target)
    print(result)
    sys.exit(0 if result["exploited"] else 1)
