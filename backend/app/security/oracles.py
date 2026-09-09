"""
Deterministic Security Test Oracles (VULN_TAXONOMY.md §4 & §5).

CRITICAL RESEARCH RULE:
Platform code decides "did the oracle fire" from the recorded request/response pair.
No LLM adjudication of pass/fail, EVER. If a model decides whether a test passed,
the detection rate measures the model's self-consistency rather than the platform's
security capability.
"""
from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field


class OracleResult(BaseModel):
    """Mechanically computed result of a security test oracle."""
    fired: bool
    rule_id: str
    category: str
    cwe: str
    rationale: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class BOLAOracle:
    """
    Oracle for Broken Object Level Authorization (BOLA / OWASP API1 / CWE-639).
    VULN_TAXONOMY.md §4:
      Principal A requests Principal B's object.
      Vulnerable iff the response is 2xx AND the body contains B's discriminating field.
      A 2xx with an empty or filtered body is NOT a finding.
    """
    RULE_ID = "ORACLE-BOLA-001"
    CATEGORY = "BOLA"
    CWE = "CWE-639"

    @classmethod
    def evaluate(
        cls,
        *,
        request_principal: str,
        target_owner: str,
        response_status: int,
        response_body: Any,
    ) -> OracleResult:
        if not (200 <= response_status < 300):
            return OracleResult(
                fired=False,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale=f"Response status {response_status} is not 2xx. Access denied or resource not found.",
                evidence={"status": response_status, "request_principal": request_principal, "target_owner": target_owner},
            )

        # Parse body if JSON string
        data = response_body
        if isinstance(data, (str, bytes)):
            try:
                data = json.loads(data)
            except Exception:
                data = {}

        if not data:
            return OracleResult(
                fired=False,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale="Response is 2xx but body is empty. No object data leaked.",
                evidence={"status": response_status},
            )

        # Look for the target owner's discriminating ownership field
        discriminated_owner = None
        if isinstance(data, dict):
            discriminated_owner = data.get("owner_id") or data.get("user_id") or data.get("owner")
            # If doc_id belongs to target owner
            if discriminated_owner == target_owner and request_principal != target_owner:
                return OracleResult(
                    fired=True,
                    rule_id=cls.RULE_ID,
                    category=cls.CATEGORY,
                    cwe=cls.CWE,
                    rationale=(
                        f"BOLA confirmed: Principal '{request_principal}' retrieved resource "
                        f"owned by '{target_owner}' (owner_id='{discriminated_owner}') with status {response_status}."
                    ),
                    evidence={
                        "request_principal": request_principal,
                        "target_owner": target_owner,
                        "returned_owner": discriminated_owner,
                        "doc_id": data.get("doc_id"),
                        "title": data.get("title"),
                    },
                )
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    owner = item.get("owner_id") or item.get("user_id")
                    if owner == target_owner and request_principal != target_owner:
                        return OracleResult(
                            fired=True,
                            rule_id=cls.RULE_ID,
                            category=cls.CATEGORY,
                            cwe=cls.CWE,
                            rationale=(
                                f"BOLA confirmed: Principal '{request_principal}' retrieved list "
                                f"containing resource owned by '{target_owner}'."
                            ),
                            evidence={"target_owner": target_owner, "item": item},
                        )

        return OracleResult(
            fired=False,
            rule_id=cls.RULE_ID,
            category=cls.CATEGORY,
            cwe=cls.CWE,
            rationale="Response body does not contain target owner's discriminating data.",
            evidence={"status": response_status, "returned_owner": discriminated_owner},
        )


class BOPLAMassAssignOracle:
    """
    Oracle for Mass Assignment / BOPLA (OWASP API3 / CWE-915).
    VULN_TAXONOMY.md §4:
      Send privileged field not present in declared input schema (role, is_admin, balance, owner_id).
      Vulnerable iff subsequent read shows the field was persisted.
    """
    RULE_ID = "ORACLE-BOPLA-001"
    CATEGORY = "BOPLA_MASS_ASSIGN"
    CWE = "CWE-915"

    @classmethod
    def evaluate(
        cls,
        *,
        injected_fields: dict[str, Any],
        write_status: int,
        read_status: int,
        read_body: Any,
    ) -> OracleResult:
        if not (200 <= read_status < 300):
            return OracleResult(
                fired=False,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale=f"Read status {read_status} is not 2xx. Verification read failed.",
                evidence={"write_status": write_status, "read_status": read_status},
            )

        data = read_body
        if isinstance(data, (str, bytes)):
            try:
                data = json.loads(data)
            except Exception:
                data = {}

        if not isinstance(data, dict):
            return OracleResult(
                fired=False,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale="Read response body is not a JSON object.",
                evidence={"read_status": read_status},
            )

        persisted_injections: dict[str, Any] = {}
        for key, expected_val in injected_fields.items():
            if key in data and data[key] == expected_val:
                persisted_injections[key] = data[key]

        if persisted_injections:
            return OracleResult(
                fired=True,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale=(
                    f"BOPLA Mass Assignment confirmed: Injected privileged fields "
                    f"{list(persisted_injections.keys())} were persisted and verified on subsequent read."
                ),
                evidence={
                    "write_status": write_status,
                    "read_status": read_status,
                    "injected_fields": injected_fields,
                    "persisted_fields": persisted_injections,
                },
            )

        return OracleResult(
            fired=False,
            rule_id=cls.RULE_ID,
            category=cls.CATEGORY,
            cwe=cls.CWE,
            rationale="Subsequent read confirms injected privileged fields were not persisted.",
            evidence={"write_status": write_status, "read_status": read_status},
        )


class SecurityMisconfigOracle:
    """
    Oracle for Security Misconfiguration (OWASP API8 / CWE-16).
    VULN_TAXONOMY.md §4:
      Debug endpoints (/debug/config), database connection strings, unhandled
      exceptions with stack traces, or wildcard CORS with credentials.
    """
    RULE_ID = "ORACLE-MISCONFIG-001"
    CATEGORY = "SECURITY_MISCONFIG"
    CWE = "CWE-16"

    SENSITIVE_KEYS = {
        "database_url",
        "db_password",
        "internal_api_key",
        "secret_key",
        "private_key",
        "master_key",
    }

    @classmethod
    def evaluate(
        cls,
        *,
        endpoint_path: str,
        response_status: int,
        response_body: Any,
        response_headers: dict[str, str] | None = None,
    ) -> OracleResult:
        headers = {k.lower(): v for k, v in (response_headers or {}).items()}

        # Check CORS misconfig: wildcard origin + credentials: true
        if (
            headers.get("access-control-allow-origin") == "*"
            and headers.get("access-control-allow-credentials", "").lower() == "true"
        ):
            return OracleResult(
                fired=True,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale="Wildcard CORS origin ('*') combined with Access-Control-Allow-Credentials: true.",
                evidence={"cors_headers": headers},
            )

        if not (200 <= response_status < 300):
            return OracleResult(
                fired=False,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale=f"Endpoint {endpoint_path} returned status {response_status} (not accessible).",
                evidence={"endpoint_path": endpoint_path, "status": response_status},
            )

        data = response_body
        raw_text = ""
        if isinstance(data, (str, bytes)):
            raw_text = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
            try:
                data = json.loads(data)
            except Exception:
                pass

        # 1. Exposed sensitive keys on debug/config endpoint
        found_sensitive_keys: list[str] = []
        if isinstance(data, dict):
            for k in data.keys():
                if k.lower() in cls.SENSITIVE_KEYS:
                    found_sensitive_keys.append(k)

        if found_sensitive_keys or (endpoint_path == "/debug/config" and isinstance(data, dict) and data.get("debug_mode") is True):
            return OracleResult(
                fired=True,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale=(
                    f"Security Misconfiguration confirmed at {endpoint_path}: "
                    f"Exposed internal configuration keys: {found_sensitive_keys or ['debug_mode']}."
                ),
                evidence={
                    "endpoint_path": endpoint_path,
                    "status": response_status,
                    "exposed_keys": found_sensitive_keys,
                    "debug_mode": data.get("debug_mode") if isinstance(data, dict) else None,
                },
            )

        # 2. Exposed Python stack trace in response
        if "Traceback (most recent call last):" in raw_text:
            return OracleResult(
                fired=True,
                rule_id=cls.RULE_ID,
                category=cls.CATEGORY,
                cwe=cls.CWE,
                rationale=f"Security Misconfiguration confirmed at {endpoint_path}: Unhandled stack trace exposed in response.",
                evidence={"endpoint_path": endpoint_path, "status": response_status, "traceback_detected": True},
            )

        return OracleResult(
            fired=False,
            rule_id=cls.RULE_ID,
            category=cls.CATEGORY,
            cwe=cls.CWE,
            rationale=f"No security misconfiguration detected on {endpoint_path}.",
            evidence={"endpoint_path": endpoint_path, "status": response_status},
        )
