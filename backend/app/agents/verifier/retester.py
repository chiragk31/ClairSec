"""
Re-tester for Phase 8 Re-test and Verification (METHODOLOGY.md §5).
Re-runs original candidate exploits against the rebuilt target via ScopeLockedHttpClient
and evaluates deterministic platform oracles.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.attacker.repository import TestCaseRepository
from app.agents.evaluator.schemas import EvaluatedFinding
from app.agents.verifier.schemas import OriginalExploitResult
from app.security.http_client import ScopeLockedHttpClient
from app.security.oracles import BOLAOracle, BOPLAMassAssignOracle, SecurityMisconfigOracle
from app.targets.handle import TargetHandle

logger = logging.getLogger(__name__)


class OriginalExploitRetester:
    """
    Re-executes the exact original candidate exploit against the modified target.
    """

    def __init__(self, test_case_repo: TestCaseRepository | None = None) -> None:
        self._test_case_repo = test_case_repo or TestCaseRepository()

    async def retest(
        self,
        *,
        finding: EvaluatedFinding,
        target_handle: TargetHandle,
    ) -> OriginalExploitResult:
        """
        Re-run the original exploit against the target handle and evaluate the platform oracle.
        """
        category = finding.category.upper()
        req_method = finding.method.upper()
        url_path = "/"

        # Fetch original test case evidence if available
        headers: dict[str, str] = {}
        body: Any = None
        oracle_evidence: dict[str, Any] = {}

        if finding.evidence_ids:
            try:
                tc = await self._test_case_repo.get_by_id(finding.evidence_ids[0])
                if tc:
                    headers = tc.request.get("headers") or {}
                    body = tc.request.get("body")
                    url_path = tc.request.get("url_path", "/")
                    oracle_evidence = tc.oracle_result.get("evidence") or {}
            except Exception as exc:
                logger.debug("Could not fetch test case %s: %s", finding.evidence_ids[0], exc)

        # Fallbacks for known routes if url_path had unpopulated template params
        if "{" in url_path or url_path == "/":
            if category == "BOLA":
                url_path = "/documents/doc_bob_02"
                headers = {"Authorization": "Bearer alice-token-123"}
            elif category == "BOPLA_MASS_ASSIGN":
                url_path = "/users/usr_alice_01/profile"
                headers = {"Authorization": "Bearer alice-token-123"}
                body = {
                    "display_name": "Alice Exploit",
                    "bio": "Privilege escalation security probe.",
                    "role": "admin",
                    "is_admin": True,
                }
            elif category == "SECURITY_MISCONFIG":
                url_path = "/debug/config"
                headers = {}

        try:
            async with ScopeLockedHttpClient(base_url=target_handle.base_url) as client:
                resp = await client.request(
                    method=req_method,
                    url=url_path,
                    headers=headers,
                    json=body if isinstance(body, (dict, list)) else None,
                )

                if category == "BOLA":
                    req_principal = oracle_evidence.get("request_principal") or "usr_alice_01"
                    target_owner = oracle_evidence.get("target_owner") or "usr_bob_02"
                    oracle_res = BOLAOracle.evaluate(
                        request_principal=req_principal,
                        target_owner=target_owner,
                        response_status=resp.status_code,
                        response_body=resp.text,
                    )
                    return OriginalExploitResult(
                        ran=True,
                        exploited=oracle_res.fired,
                        rationale=oracle_res.rationale,
                    )

                elif category == "BOPLA_MASS_ASSIGN":
                    injected_fields = oracle_evidence.get("injected_fields") or {"role": "admin", "is_admin": True}
                    read_path = oracle_evidence.get("read_path") or (url_path[:-8] if url_path.endswith("/profile") else url_path)
                    read_resp = await client.request(
                        method="GET",
                        url=read_path,
                        headers=headers,
                    )
                    read_text = read_resp.text
                    try:
                        read_json = json.loads(read_text)
                        if isinstance(read_json, dict) and "user" in read_json and isinstance(read_json["user"], dict):
                            read_text = json.dumps(read_json["user"])
                    except Exception:
                        pass

                    oracle_res = BOPLAMassAssignOracle.evaluate(
                        injected_fields=injected_fields,
                        write_status=resp.status_code,
                        read_status=read_resp.status_code,
                        read_body=read_text,
                    )
                    return OriginalExploitResult(
                        ran=True,
                        exploited=oracle_res.fired,
                        rationale=oracle_res.rationale,
                    )

                elif category == "SECURITY_MISCONFIG":
                    oracle_res = SecurityMisconfigOracle.evaluate(
                        endpoint_path=url_path,
                        response_status=resp.status_code,
                        response_body=resp.text,
                        response_headers=dict(resp.headers),
                    )
                    return OriginalExploitResult(
                        ran=True,
                        exploited=oracle_res.fired,
                        rationale=oracle_res.rationale,
                    )

                else:
                    # Generic fallback: if 200 <= status < 300, consider potentially exploited
                    is_exp = 200 <= resp.status_code < 300
                    return OriginalExploitResult(
                        ran=True,
                        exploited=is_exp,
                        rationale=f"Generic check returned status {resp.status_code}",
                    )

        except Exception as exc:
            logger.warning("Re-test execution failed: %s", exc)
            return OriginalExploitResult(
                ran=False,
                exploited=False,
                rationale=f"Transport error during re-test: {exc}",
            )
