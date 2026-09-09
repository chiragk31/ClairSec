"""
Attacker Agent implementation (VULN_TAXONOMY.md §4, THREAT_MODEL.md T9, DATA_MODEL.md §3).

CRITICAL CONSTRAINTS:
1. Pure platform-code oracles: LLM NEVER adjudicates pass/fail.
2. Scope-locked HTTP client: requests strictly bound to TargetHandle; off-target requests blocked (T9).
3. Every executed test is persisted to test_cases whether or not it fired.
4. Pre-persistence redaction (C5.2) and 64 KB size limits (DATA_MODEL.md §2).
5. Normalized route templates in candidate findings (/documents/{doc_id}, never /documents/doc_bob_02).
"""
from __future__ import annotations

import time
from typing import Any

from app.agents.builder.schemas import AgentContext, RouteItem, TestPrincipal
from app.agents.attacker.evidence import (
    capture_request_evidence,
    capture_response_evidence,
)
from app.agents.attacker.repository import FindingRepository, TestCaseRepository
from app.agents.attacker.schemas import (
    AttackerScanResult,
    CandidateFinding,
    TestCaseRecord,
    normalize_route_path,
)
from app.llm.accounting import LLMCallLedger
from app.llm.provider import LLMProvider
from app.llm.providers.mock_provider import MockLLMProvider
from app.security.http_client import ScopeLockedHttpClient
from app.security.oracles import (
    BOLAOracle,
    BOPLAMassAssignOracle,
    SecurityMisconfigOracle,
)
from app.targets.handle import TargetHandle


class AttackerAgent:
    """
    Autonomous Attacker Agent for API security testing.
    Executes scoped adversarial test cases against a TargetHandle.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        ledger: LLMCallLedger | None = None,
        test_case_repo: TestCaseRepository | None = None,
        finding_repo: FindingRepository | None = None,
        *,
        rate_limit_rps: float = 20.0,
        max_requests: int = 100,
    ):
        self._provider = llm_provider or MockLLMProvider()
        self._ledger = ledger or LLMCallLedger()
        self._test_case_repo = test_case_repo or TestCaseRepository()
        self._finding_repo = finding_repo or FindingRepository()
        self._rate_limit_rps = rate_limit_rps
        self._max_requests = max_requests

    async def run_scan(
        self,
        *,
        context: AgentContext,
        target_handle: TargetHandle,
        replay_mode: bool = False,
    ) -> AttackerScanResult:
        """
        Execute security test suite against the target and emit test cases and candidate findings.
        """
        executed_tests: list[TestCaseRecord] = []
        candidate_findings: list[CandidateFinding] = []

        # Extract principals
        alice = next((p for p in context.principals if "alice" in p.username.lower()), None)
        bob = next((p for p in context.principals if "bob" in p.username.lower()), None)

        if not alice:
            alice = TestPrincipal(
                user_id="usr_alice_01",
                username="alice",
                token="Bearer alice-token-123",
                role="member",
            )
        if not bob:
            bob = TestPrincipal(
                user_id="usr_bob_02",
                username="bob",
                token="Bearer bob-token-456",
                role="member",
            )

        known_templates = [r.route_template for r in context.routes]

        async with ScopeLockedHttpClient(
            base_url=target_handle.base_url,
            rate_limit_rps=self._rate_limit_rps,
            max_requests=self._max_requests,
        ) as client:

            # ─────────────────────────────────────────────────────────────────
            # Category 1: BOLA (Broken Object Level Authorization / CWE-639)
            # ─────────────────────────────────────────────────────────────────
            # Identify routes with object identifier parameters requiring auth
            bola_routes = [
                r for r in context.routes
                if "{" in r.route_template and ("doc_id" in r.route_template or "id" in r.route_template)
            ]

            for route in bola_routes:
                norm_template = route.route_template
                # Target path: Alice requests Bob's document / object
                target_path = norm_template.replace("{doc_id}", "doc_bob_02").replace("{id}", "doc_bob_02")
                req_headers = {"Authorization": alice.token}

                t0 = time.perf_counter()
                resp = await client.get(target_path, headers=req_headers)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                # Platform oracle evaluation (No LLM adjudication)
                oracle_res = BOLAOracle.evaluate(
                    request_principal=alice.user_id,
                    target_owner=bob.user_id,
                    response_status=resp.status_code,
                    response_body=resp.text,
                )

                req_ev = capture_request_evidence("GET", target_path, req_headers, body=None)
                resp_ev = capture_response_evidence(resp.status_code, dict(resp.headers), resp.text, elapsed_ms)

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=BOLAOracle.CATEGORY,
                    route_template=norm_template,
                    method="GET",
                    principal_id=alice.user_id,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                )
                await self._test_case_repo.save(test_case)
                executed_tests.append(test_case)

                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Broken Object Level Authorization (BOLA) at {norm_template}",
                        category=BOLAOracle.CATEGORY,
                        cwe=[BOLAOracle.CWE],
                        route_template=norm_template,
                        method="GET",
                        description=oracle_res.rationale,
                        impact=(
                            "An authenticated user can retrieve confidential resources "
                            "belonging to other users without authorization."
                        ),
                        runtime_confirmed=True,
                        oracle_rule_id=oracle_res.rule_id,
                        evidence_ids=[test_case.id],
                        reproduction_summary=(
                            f"GET {target_path} using token of principal '{alice.username}' "
                            f"returned status {resp.status_code} with private data of '{bob.username}'."
                        ),
                        source_locations=[
                            {
                                "file": route.source_file,
                                "line_start": route.source_line_range[0],
                                "line_end": route.source_line_range[1],
                            }
                        ] if route.source_file else [],
                        status="candidate",
                    )
                    await self._finding_repo.save(finding)
                    candidate_findings.append(finding)

            # ─────────────────────────────────────────────────────────────────
            # Category 2: BOPLA_MASS_ASSIGN (Mass Assignment / CWE-915)
            # ─────────────────────────────────────────────────────────────────
            # Identify write routes updating user/entity profiles
            mass_assign_routes = [
                r for r in context.routes
                if r.method in ("PUT", "POST", "PATCH") and "profile" in r.route_template
            ]

            for route in mass_assign_routes:
                norm_template = route.route_template
                # Target path: Alice updates her profile injecting privileged fields
                target_path = norm_template.replace("{user_id}", alice.user_id).replace("{id}", alice.user_id)
                read_path = f"/users/{alice.user_id}"

                req_headers = {"Authorization": alice.token}
                injected_payload = {
                    "display_name": "Alice Exploit",
                    "bio": "Privilege escalation security test probe.",
                    "role": "admin",
                    "is_admin": True,
                }

                # Step 1: Write attempt
                t0 = time.perf_counter()
                put_resp = await client.put(target_path, json=injected_payload, headers=req_headers)
                put_elapsed_ms = int((time.perf_counter() - t0) * 1000)

                # Step 2: Verification read
                t1 = time.perf_counter()
                get_resp = await client.get(read_path, headers=req_headers)
                get_elapsed_ms = int((time.perf_counter() - t1) * 1000)

                # Platform oracle evaluation
                oracle_res = BOPLAMassAssignOracle.evaluate(
                    injected_fields={"role": "admin", "is_admin": True},
                    write_status=put_resp.status_code,
                    read_status=get_resp.status_code,
                    read_body=get_resp.text,
                )

                req_ev = capture_request_evidence("PUT", target_path, req_headers, body=injected_payload)
                resp_ev = capture_response_evidence(
                    put_resp.status_code,
                    dict(put_resp.headers),
                    put_resp.text,
                    put_elapsed_ms,
                )

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=BOPLAMassAssignOracle.CATEGORY,
                    route_template=norm_template,
                    method="PUT",
                    principal_id=alice.user_id,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                )
                await self._test_case_repo.save(test_case)
                executed_tests.append(test_case)

                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Mass Assignment via Privileged Field Injection at {norm_template}",
                        category=BOPLAMassAssignOracle.CATEGORY,
                        cwe=[BOPLAMassAssignOracle.CWE],
                        route_template=norm_template,
                        method="PUT",
                        description=oracle_res.rationale,
                        impact=(
                            "An unprivileged user can escalate privileges by submitting undeclared "
                            "privileged fields ('role': 'admin', 'is_admin': true) during profile updates."
                        ),
                        runtime_confirmed=True,
                        oracle_rule_id=oracle_res.rule_id,
                        evidence_ids=[test_case.id],
                        reproduction_summary=(
                            f"PUT {target_path} injected privileged fields which persisted and were "
                            f"confirmed on subsequent GET {read_path}."
                        ),
                        source_locations=[
                            {
                                "file": route.source_file,
                                "line_start": route.source_line_range[0],
                                "line_end": route.source_line_range[1],
                            }
                        ] if route.source_file else [],
                        status="candidate",
                    )
                    await self._finding_repo.save(finding)
                    candidate_findings.append(finding)

            # ─────────────────────────────────────────────────────────────────
            # Category 3: SECURITY_MISCONFIG (Security Misconfiguration / CWE-16)
            # ─────────────────────────────────────────────────────────────────
            # Inspect routes for internal/debug endpoints or standard probe routes
            misconfig_targets: list[tuple[str, str, RouteItem | None]] = []

            # Check context routes
            for r in context.routes:
                if r.is_debug_or_internal or "debug" in r.route_template:
                    misconfig_targets.append((r.route_template, r.method, r))

            # Ensure /debug/config probe is tested
            if not any(t[0] == "/debug/config" for t in misconfig_targets):
                misconfig_targets.append(("/debug/config", "GET", None))

            for endpoint_path, method, route_item in misconfig_targets:
                norm_template = normalize_route_path(endpoint_path, known_templates)

                t0 = time.perf_counter()
                resp = await client.get(endpoint_path)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                oracle_res = SecurityMisconfigOracle.evaluate(
                    endpoint_path=endpoint_path,
                    response_status=resp.status_code,
                    response_body=resp.text,
                    response_headers=dict(resp.headers),
                )

                req_ev = capture_request_evidence("GET", endpoint_path, headers=None, body=None)
                resp_ev = capture_response_evidence(
                    resp.status_code,
                    dict(resp.headers),
                    resp.text,
                    elapsed_ms,
                )

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=SecurityMisconfigOracle.CATEGORY,
                    route_template=norm_template,
                    method="GET",
                    principal_id=None,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                )
                await self._test_case_repo.save(test_case)
                executed_tests.append(test_case)

                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Security Misconfiguration: Exposed Internal Endpoint at {norm_template}",
                        category=SecurityMisconfigOracle.CATEGORY,
                        cwe=[SecurityMisconfigOracle.CWE],
                        route_template=norm_template,
                        method="GET",
                        description=oracle_res.rationale,
                        impact=(
                            "Internal system configuration, database connection strings, or debug "
                            "flags are publicly accessible without authentication."
                        ),
                        runtime_confirmed=True,
                        oracle_rule_id=oracle_res.rule_id,
                        evidence_ids=[test_case.id],
                        reproduction_summary=(
                            f"GET {endpoint_path} returned status {resp.status_code} "
                            f"exposing sensitive internal keys or tracebacks."
                        ),
                        source_locations=[
                            {
                                "file": route_item.source_file,
                                "line_start": route_item.source_line_range[0],
                                "line_end": route_item.source_line_range[1],
                            }
                        ] if route_item and route_item.source_file else [],
                        status="candidate",
                    )
                    await self._finding_repo.save(finding)
                    candidate_findings.append(finding)

        return AttackerScanResult(
            scan_id=context.scan_id,
            project_id=context.project_id,
            test_cases=executed_tests,
            findings=candidate_findings,
            counters={
                "tests_executed": len(executed_tests),
                "candidates": len(candidate_findings),
            },
        )
