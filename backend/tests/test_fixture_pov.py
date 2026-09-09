"""
Verification suite for ClairSec Tier A fixtures and Proof-of-Vulnerability (PoV) oracles.
Enforces:
  1. METHODOLOGY.md §2.1: SeededVulnerability records schema and integrity.
  2. METHODOLOGY.md §2.3: Every PoV fires on the vulnerable build and does NOT fire
     on the secure reference build.
  3. TESTING.md §5a: Dual criterion — functional suite passes on both builds.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from tests.fixtures.vulnerable_fastapi_app.main import (
    app as vuln_app,
    reset_state as vuln_reset,
)
from tests.fixtures.secure_fastapi_app.main import (
    app as secure_app,
    reset_state as secure_reset,
)
from tests.fixtures.vulnerable_fastapi_app.pov_bola import run_pov as pov_bola
from tests.fixtures.vulnerable_fastapi_app.pov_mass_assign import run_pov as pov_mass_assign
from tests.fixtures.vulnerable_fastapi_app.pov_misconfig import run_pov as pov_misconfig

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "vulnerable_fastapi_app"


@pytest.fixture
def vuln_client():
    vuln_reset()
    yield TestClient(vuln_app)
    vuln_reset()


@pytest.fixture
def secure_client():
    secure_reset()
    yield TestClient(secure_app)
    secure_reset()


def test_seeded_vulnerabilities_records_validity():
    """Verify seeded_vulnerabilities.json exists and strictly satisfies METHODOLOGY.md §2.1."""
    manifest_path = FIXTURE_DIR / "seeded_vulnerabilities.json"
    assert manifest_path.exists(), "seeded_vulnerabilities.json must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert len(records) == 3, "Exactly 3 seeded vulnerabilities required for Step A"

    required_fields = {
        "vuln_id",
        "project_id",
        "category",
        "cwe",
        "route_template",
        "method",
        "source_file",
        "source_line_range",
        "injected_by",
        "pov",
        "functional_tests",
    }

    categories = set()
    for rec in records:
        assert required_fields.issubset(rec.keys()), f"Missing fields in {rec}"
        assert rec["category"] in {"BOLA", "BOPLA_MASS_ASSIGN", "SECURITY_MISCONFIG"}
        assert rec["route_template"].startswith("/")
        assert rec["method"] in {"GET", "POST", "PUT", "DELETE", "PATCH"}
        assert len(rec["source_line_range"]) == 2
        assert rec["source_line_range"][0] <= rec["source_line_range"][1]
        assert len(rec["functional_tests"]) > 0
        categories.add(rec["category"])

    assert categories == {"BOLA", "BOPLA_MASS_ASSIGN", "SECURITY_MISCONFIG"}


def test_vulnerable_app_povs_fire(vuln_client):
    """Verify all 3 PoVs fire (exploited=True) on the vulnerable fixture."""
    res_bola = pov_bola(vuln_client)
    assert res_bola["exploited"] is True, f"BOLA PoV failed to fire: {res_bola}"
    assert res_bola["status_code"] == 200
    assert res_bola["evidence"]["returned_owner_id"] == "usr_bob_02"

    res_mass = pov_mass_assign(vuln_client)
    assert res_mass["exploited"] is True, f"BOPLA_MASS_ASSIGN PoV failed to fire: {res_mass}"
    assert res_mass["evidence"]["persisted_role"] == "admin"
    assert res_mass["evidence"]["persisted_is_admin"] is True

    res_misconfig = pov_misconfig(vuln_client)
    assert res_misconfig["exploited"] is True, f"SECURITY_MISCONFIG PoV failed to fire: {res_misconfig}"
    assert res_misconfig["evidence"]["database_url_exposed"] is True


def test_secure_app_povs_do_not_fire(secure_client):
    """Verify none of the 3 PoVs fire (exploited=False) on the secure reference fixture."""
    res_bola = pov_bola(secure_client)
    assert res_bola["exploited"] is False, f"BOLA PoV unexpectedly fired on secure app: {res_bola}"
    assert res_bola["status_code"] == 403

    res_mass = pov_mass_assign(secure_client)
    assert res_mass["exploited"] is False, f"BOPLA_MASS_ASSIGN PoV unexpectedly fired on secure app: {res_mass}"
    assert res_mass["put_status_code"] == 422  # Extra fields rejected

    res_misconfig = pov_misconfig(secure_client)
    assert res_misconfig["exploited"] is False, f"SECURITY_MISCONFIG PoV unexpectedly fired on secure app: {res_misconfig}"
    assert res_misconfig["status_code"] == 404  # Debug endpoint removed


def test_functional_parity_both_apps(vuln_client, secure_client):
    """Verify legitimate functionality passes on both vulnerable and secure builds."""
    for client in (vuln_client, secure_client):
        # 1. Health
        assert client.get("/health").status_code == 200

        # 2. Authenticated user can read own document
        headers = {"Authorization": "Bearer alice-token-123"}
        r_doc = client.get("/documents/doc_alice_01", headers=headers)
        assert r_doc.status_code == 200
        assert r_doc.json()["doc_id"] == "doc_alice_01"

        # 3. Create document
        r_create = client.post(
            "/documents",
            json={"title": "Parity Doc", "content": "Checking dual criterion."},
            headers=headers,
        )
        assert r_create.status_code == 200

        # 4. Update legitimate profile fields
        r_up = client.put(
            "/users/usr_alice_01/profile",
            json={"display_name": "Alice Verified", "bio": "Parity confirmed."},
            headers=headers,
        )
        assert r_up.status_code == 200

        # 5. Unauthorized access to another user's profile forbidden
        r_forbidden = client.put(
            "/users/usr_bob_02/profile",
            json={"bio": "Unauthorized"},
            headers=headers,
        )
        assert r_forbidden.status_code == 403
