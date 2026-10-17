"""
Unit tests for deterministic security test oracles (VULN_TAXONOMY.md §4, §5).
"""
from __future__ import annotations

import pytest

from app.security.oracles import (
    BFLAOracle,
    BOLAOracle,
    BOPLAMassAssignOracle,
    PathTraversalOracle,
    SQLInjectionOracle,
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


def test_bfla_oracle_fires_when_unprivileged_accesses_admin():
    result = BFLAOracle.evaluate(
        request_principal_role="member",
        endpoint_path="/admin/users",
        response_status=200,
        response_body={"users": ["alice", "bob"]},
    )
    assert result.fired is True
    assert result.rule_id == "ORACLE-BFLA-001"
    assert result.category == "BFLA"
    assert result.cwe == "CWE-285"
    assert "BFLA confirmed" in result.rationale


def test_bfla_oracle_does_not_fire_on_403_or_401():
    result = BFLAOracle.evaluate(
        request_principal_role="member",
        endpoint_path="/admin/users",
        response_status=403,
        response_body={"detail": "Admin required"},
    )
    assert result.fired is False
    assert "enforced" in result.rationale


def test_path_traversal_oracle_fires_on_source_code_leak():
    result = PathTraversalOracle.evaluate(
        endpoint_path="/download?file=../../app/main.py",
        response_status=200,
        response_body="from fastapi import FastAPI\napp = FastAPI()",
    )
    assert result.fired is True
    assert result.category == "PATH_TRAVERSAL"
    assert result.cwe == "CWE-22"
    assert "Path Traversal confirmed" in result.rationale


def test_path_traversal_oracle_does_not_fire_on_404():
    result = PathTraversalOracle.evaluate(
        endpoint_path="/download?file=../../app/main.py",
        response_status=404,
        response_body={"detail": "File not found"},
    )
    assert result.fired is False


def test_sqli_oracle_fires_on_syntax_error():
    result = SQLInjectionOracle.evaluate(
        endpoint_path="/items?search=' OR '1'='1",
        response_status=500,
        response_body="sqlite3.OperationalError: unrecognized token near '1'",
    )
    assert result.fired is True
    assert result.category == "SQL_INJECTION"
    assert result.cwe == "CWE-89"
    assert "SQL Injection confirmed" in result.rationale


def test_sqli_oracle_does_not_fire_on_clean_response():
    result = SQLInjectionOracle.evaluate(
        endpoint_path="/items?search=apples",
        response_status=200,
        response_body={"items": []},
    )
    assert result.fired is False
