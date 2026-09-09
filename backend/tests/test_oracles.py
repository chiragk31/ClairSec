"""
Unit tests for deterministic security test oracles (VULN_TAXONOMY.md §4, §5).
"""
from __future__ import annotations

import pytest

from app.security.oracles import (
    BOLAOracle,
    BOPLAMassAssignOracle,
    SecurityMisconfigOracle,
)


def test_bola_oracle_fires_when_discriminated_owner_leaked():
    result = BOLAOracle.evaluate(
        request_principal="usr_alice_01",
        target_owner="usr_bob_02",
        response_status=200,
        response_body={
            "doc_id": "doc_bob_02",
            "owner_id": "usr_bob_02",
            "title": "Bob Confidential",
        },
    )
    assert result.fired is True
    assert result.rule_id == "ORACLE-BOLA-001"
    assert result.category == "BOLA"
    assert result.cwe == "CWE-639"
    assert "BOLA confirmed" in result.rationale


def test_bola_oracle_does_not_fire_on_forbidden():
    result = BOLAOracle.evaluate(
        request_principal="usr_alice_01",
        target_owner="usr_bob_02",
        response_status=403,
        response_body={"detail": "Forbidden"},
    )
    assert result.fired is False
    assert "Access denied" in result.rationale


def test_bola_oracle_does_not_fire_on_empty_body():
    result = BOLAOracle.evaluate(
        request_principal="usr_alice_01",
        target_owner="usr_bob_02",
        response_status=200,
        response_body={},
    )
    assert result.fired is False
    assert "empty" in result.rationale


def test_bola_oracle_does_not_fire_when_accessing_own_resource():
    result = BOLAOracle.evaluate(
        request_principal="usr_alice_01",
        target_owner="usr_alice_01",
        response_status=200,
        response_body={"doc_id": "doc_alice_01", "owner_id": "usr_alice_01"},
    )
    assert result.fired is False


def test_mass_assign_oracle_fires_when_injected_role_persisted():
    result = BOPLAMassAssignOracle.evaluate(
        injected_fields={"role": "admin", "is_admin": True},
        write_status=200,
        read_status=200,
        read_body={"user_id": "usr_alice_01", "role": "admin", "is_admin": True},
    )
    assert result.fired is True
    assert result.rule_id == "ORACLE-BOPLA-001"
    assert result.category == "BOPLA_MASS_ASSIGN"
    assert result.cwe == "CWE-915"
    assert "BOPLA Mass Assignment confirmed" in result.rationale


def test_mass_assign_oracle_does_not_fire_when_write_rejected_or_unpersisted():
    result = BOPLAMassAssignOracle.evaluate(
        injected_fields={"role": "admin", "is_admin": True},
        write_status=422,
        read_status=200,
        read_body={"user_id": "usr_alice_01", "role": "member", "is_admin": False},
    )
    assert result.fired is False
    assert "not persisted" in result.rationale


def test_mass_assign_oracle_does_not_fire_on_read_failure():
    result = BOPLAMassAssignOracle.evaluate(
        injected_fields={"role": "admin"},
        write_status=200,
        read_status=500,
        read_body="Internal Server Error",
    )
    assert result.fired is False
    assert "Verification read failed" in result.rationale


def test_misconfig_oracle_fires_on_exposed_debug_keys():
    result = SecurityMisconfigOracle.evaluate(
        endpoint_path="/debug/config",
        response_status=200,
        response_body={
            "debug_mode": True,
            "database_url": "postgresql://usr:pwd@localhost:5432/db",
            "internal_api_key": "sec-live-token",
        },
    )
    assert result.fired is True
    assert result.rule_id == "ORACLE-MISCONFIG-001"
    assert result.category == "SECURITY_MISCONFIG"
    assert result.cwe == "CWE-16"
    assert "Exposed internal configuration keys" in result.rationale


def test_misconfig_oracle_does_not_fire_on_404():
    result = SecurityMisconfigOracle.evaluate(
        endpoint_path="/debug/config",
        response_status=404,
        response_body={"detail": "Not Found"},
    )
    assert result.fired is False


def test_misconfig_oracle_fires_on_wildcard_cors_with_credentials():
    result = SecurityMisconfigOracle.evaluate(
        endpoint_path="/api/data",
        response_status=200,
        response_body={"data": 123},
        response_headers={
            "access-control-allow-origin": "*",
            "access-control-allow-credentials": "true",
        },
    )
    assert result.fired is True
    assert "Wildcard CORS origin" in result.rationale
