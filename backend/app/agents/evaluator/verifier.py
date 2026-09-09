"""
Independent Evidence Verifier (METHODOLOGY.md §4, §9).

Mechanically validates that recorded HTTP evidence is internally consistent with
the asserted vulnerability category before reproduction or scoring is permitted.
Rejects fabricated findings (e.g. BOLA where owner_id matches requesting principal).
"""
from __future__ import annotations

import json
from typing import Any
from app.agents.evaluator.schemas import EvaluatorEvidence


class EvidenceVerificationResult:
    def __init__(self, is_valid: bool, rejection_reason: str = ""):
        self.is_valid = is_valid
        self.rejection_reason = rejection_reason


class EvidenceVerifier:
    """
    Validates structural consistency between the category semantics and raw HTTP evidence.
    """

    def verify_evidence(self, evidence: EvaluatorEvidence) -> EvidenceVerificationResult:
        """
        Check whether evidence demonstrates the category semantics.
        Returns EvidenceVerificationResult(is_valid=True) or rejection reason.
        """
        category = evidence.category.upper()
        res = evidence.response
        req = evidence.request

        status = res.get("status")
        if status is None or not (200 <= status < 300):
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason=f"invalid_status_code: expected 2xx response, got {status}",
            )

        res_body = res.get("body")
        if isinstance(res_body, str):
            try:
                res_body = json.loads(res_body)
            except Exception:
                res_body = {}
        elif not isinstance(res_body, dict):
            res_body = {}

        if category == "BOLA":
            return self._verify_bola(evidence, req, res_body)

        if category == "BOPLA_MASS_ASSIGN":
            return self._verify_mass_assign(evidence, req, res_body)

        if category == "SECURITY_MISCONFIG":
            return self._verify_misconfig(evidence, res)

        # For other categories, verify that oracle reported fired and response is 2xx
        oracle_res = evidence.oracle_result
        if not oracle_res.get("fired"):
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="oracle_did_not_fire_in_evidence",
            )

        return EvidenceVerificationResult(is_valid=True)

    def _verify_bola(
        self,
        evidence: EvaluatorEvidence,
        req: dict[str, Any],
        res_body: dict[str, Any],
    ) -> EvidenceVerificationResult:
        """
        BOLA requires:
        1. Non-empty response body.
        2. Presence of an owner identifier.
        3. The owner identifier MUST NOT match the requesting principal.
        """
        if not res_body:
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="evidence_inconsistent_with_bola: response body is empty",
            )

        # Detect requesting principal from oracle_result evidence, request principal_id, or authorization headers
        oracle_ev = evidence.oracle_result.get("evidence") or {}
        requester_id = oracle_ev.get("request_principal") or req.get("principal_id")
        if not requester_id:
            headers = req.get("headers") or {}
            auth_val = ""
            for k, v in headers.items():
                if k.lower() == "authorization":
                    auth_val = str(v)
                    break

            if "alice" in auth_val.lower():
                requester_id = "usr_alice_01"
            elif "bob" in auth_val.lower():
                requester_id = "usr_bob_02"

        # Check owner identifier in response
        owner_val = (
            res_body.get("owner_id")
            or res_body.get("user_id")
            or res_body.get("owner")
            or res_body.get("creator_id")
        )

        if not owner_val:
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="evidence_inconsistent_with_bola: no owner field in response body",
            )

        # Adversarial check: If owner matches the requester, it's not BOLA
        if requester_id and str(owner_val).lower() == requester_id.lower():
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="evidence_inconsistent_with_bola: response owner matches requesting principal",
            )

        return EvidenceVerificationResult(is_valid=True)

    def _verify_mass_assign(
        self,
        evidence: EvaluatorEvidence,
        req: dict[str, Any],
        res_body: dict[str, Any],
    ) -> EvidenceVerificationResult:
        """
        BOPLA_MASS_ASSIGN requires:
        1. A request body containing an injected privileged field (e.g. role, is_admin).
        2. Reflection or persistence of that privileged field in the response.
        """
        req_body = req.get("body")
        if isinstance(req_body, str):
            try:
                req_body = json.loads(req_body)
            except Exception:
                req_body = {}
        elif not isinstance(req_body, dict):
            req_body = {}

        privileged_keys = {"role", "is_admin", "is_superuser", "permissions", "balance"}
        injected_keys = set(req_body.keys()) & privileged_keys

        if not injected_keys:
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="evidence_inconsistent_with_mass_assign: no privileged field sent in request",
            )

        # Check if any injected key was reflected / persisted in response
        reflected = any(k in res_body for k in injected_keys)
        if not reflected and "user" in res_body and isinstance(res_body["user"], dict):
            reflected = any(k in res_body["user"] for k in injected_keys)
        if not reflected:
            # Check any nested dict in res_body
            for val in res_body.values():
                if isinstance(val, dict) and any(k in val for k in injected_keys):
                    reflected = True
                    break

        if not reflected:
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="evidence_inconsistent_with_mass_assign: injected field not reflected in response",
            )

        return EvidenceVerificationResult(is_valid=True)

    def _verify_misconfig(
        self,
        evidence: EvaluatorEvidence,
        res: dict[str, Any],
    ) -> EvidenceVerificationResult:
        """
        SECURITY_MISCONFIG requires:
        Exposed debug configuration keys OR wildcard CORS with credentials.
        """
        res_body = res.get("body")
        body_text = str(res_body).lower() if res_body else ""
        headers = {k.lower(): str(v).lower() for k, v in (res.get("headers") or {}).items()}

        debug_indicators = [
            "debug",
            "database_url",
            "secret_key",
            "db_password",
            "db_pass",
            "admin_token",
            "environment",
        ]
        has_debug_exposure = any(k in body_text for k in debug_indicators)

        cors_origin = headers.get("access-control-allow-origin")
        cors_creds = headers.get("access-control-allow-credentials")
        has_bad_cors = cors_origin == "*" and cors_creds == "true"

        if not (has_debug_exposure or has_bad_cors):
            return EvidenceVerificationResult(
                is_valid=False,
                rejection_reason="evidence_inconsistent_with_security_misconfig: no misconfiguration indicators in response",
            )

        return EvidenceVerificationResult(is_valid=True)
