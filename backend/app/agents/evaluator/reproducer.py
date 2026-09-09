"""
Live Test Case Reproducer (PHASES.md Phase 6, METHODOLOGY.md §4).

Re-executes candidate test cases against the TargetHandle using ScopeLockedHttpClient.
Evaluates the deterministic oracle from app.security.oracles.
Persists reproduced test cases to the test_cases repository.
"""
from __future__ import annotations

import json
from typing import Any
import uuid

from app.agents.attacker.repository import TestCaseRepository
from app.agents.attacker.schemas import TestCaseRecord
from app.agents.evaluator.schemas import EvaluatorEvidence
from app.security.http_client import ScopeLockedHttpClient
from app.security.oracles import BOLAOracle, BOPLAMassAssignOracle, SecurityMisconfigOracle
from app.targets.handle import TargetHandle


class ReproductionResult:
    def __init__(
        self,
        reproduced: bool,
        reproduced_request: dict[str, Any],
        reproduced_response: dict[str, Any],
        oracle_result: dict[str, Any],
        test_case_id: str | None = None,
        failure_reason: str = "",
    ):
        self.reproduced = reproduced
        self.reproduced_request = reproduced_request
        self.reproduced_response = reproduced_response
        self.oracle_result = oracle_result
        self.test_case_id = test_case_id
        self.failure_reason = failure_reason


class TestReproducer:
    """
    Re-executes candidate test cases to verify independent repeatability.
    """

    def __init__(self, test_case_repo: TestCaseRepository | None = None):
        self._test_case_repo = test_case_repo or TestCaseRepository()

    async def reproduce(
        self,
        *,
        evidence: EvaluatorEvidence,
        target_handle: TargetHandle,
        scan_id: str,
    ) -> ReproductionResult:
        """
        Re-execute the test case against the target and evaluate the oracle.
        """
        req = evidence.request
        method = req.get("method", "GET").upper()
        url_path = req.get("url_path", "/")
        headers = req.get("headers") or {}
        req_body = req.get("body")

        category = evidence.category.upper()
        oracle_evidence = evidence.oracle_result.get("evidence") or {}

        try:
            async with ScopeLockedHttpClient(base_url=target_handle.base_url) as client:
                resp = await client.request(
                    method=method,
                    url=url_path,
                    headers=headers,
                    json=req_body if isinstance(req_body, (dict, list)) else None,
                )

                rep_req_data = {
                    "method": method,
                    "url_path": url_path,
                    "headers": headers,
                    "body": req_body,
                }
                rep_res_data = {
                    "status": resp.status_code,
                    "headers": dict(resp.headers),
                    "body": resp.text,
                    "elapsed_ms": resp.elapsed.total_seconds() * 1000.0,
                }

                # Evaluate oracle on reproduced traffic
                oracle_result_obj = None

                if category == "BOLA":
                    req_principal = oracle_evidence.get("request_principal") or "usr_alice_01"
                    target_owner = oracle_evidence.get("target_owner") or "usr_bob_02"
                    oracle_result_obj = BOLAOracle.evaluate(
                        request_principal=req_principal,
                        target_owner=target_owner,
                        response_status=resp.status_code,
                        response_body=resp.text,
                    )

                elif category == "BOPLA_MASS_ASSIGN":
                    injected_fields = oracle_evidence.get("injected_fields") or {"role": "admin", "is_admin": True}
                    # Verification read step: if write path was /users/{id}/profile, read path is /users/{id}
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

                    oracle_result_obj = BOPLAMassAssignOracle.evaluate(
                        injected_fields=injected_fields,
                        write_status=resp.status_code,
                        read_status=read_resp.status_code,
                        read_body=read_text,
                    )
                    rep_res_data["body"] = read_resp.text
                    rep_res_data["status"] = read_resp.status_code

                elif category == "SECURITY_MISCONFIG":
                    oracle_result_obj = SecurityMisconfigOracle.evaluate(
                        endpoint_path=url_path,
                        response_status=resp.status_code,
                        response_body=resp.text,
                        response_headers=dict(resp.headers),
                    )
                else:
                    # Generic fallback: if 2xx and oracle fired originally
                    if 200 <= resp.status_code < 300:
                        oracle_result_dict = {"fired": True, "rule_id": "GENERIC", "rationale": "2xx response"}
                    else:
                        oracle_result_dict = {"fired": False, "rule_id": "GENERIC", "rationale": f"Status {resp.status_code}"}
                    oracle_result_obj = None

                if oracle_result_obj is not None:
                    oracle_result_dict = oracle_result_obj.model_dump()

                if not oracle_result_dict.get("fired"):
                    return ReproductionResult(
                        reproduced=False,
                        reproduced_request=rep_req_data,
                        reproduced_response=rep_res_data,
                        oracle_result=oracle_result_dict,
                        failure_reason=f"reproduction_failed: oracle did not fire on re-test ({oracle_result_dict.get('rationale', '')})",
                    )

                # Persist reproduction test case
                tc = TestCaseRecord(
                    scan_id=scan_id,
                    category=evidence.category,
                    route_template=evidence.route_template,
                    method=method,
                    request=rep_req_data,
                    response=rep_res_data,
                    oracle_result=oracle_result_dict,
                    generated_by={
                        "agent": "evaluator",
                        "prompt_id": "evaluator_reproducer",
                        "prompt_version": "v1.0",
                        "llm_call_id": None,
                    },
                )
                await self._test_case_repo.save(tc)

                return ReproductionResult(
                    reproduced=True,
                    reproduced_request=rep_req_data,
                    reproduced_response=rep_res_data,
                    oracle_result=oracle_result_dict,
                    test_case_id=tc.id,
                )

        except Exception as exc:
            return ReproductionResult(
                reproduced=False,
                reproduced_request={"method": method, "url_path": url_path},
                reproduced_response={},
                oracle_result={"fired": False, "error": str(exc)},
                failure_reason=f"reproduction_transport_error: {exc}",
            )
