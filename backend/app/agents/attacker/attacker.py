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

import asyncio
import logging
import re
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
from app.security.http_client import (
    NonDestructivePolicyViolationError,
    ScopeLockedHttpClient,
    is_method_prohibited,
)
from app.security.oracles import (
    BFLAOracle,
    BOLAOracle,
    BOPLAMassAssignOracle,
    PathTraversalOracle,
    SQLInjectionOracle,
    SecurityMisconfigOracle,
)
from app.targets.handle import TargetHandle

logger = logging.getLogger(__name__)


def resolve_path_template(
    template: str,
    *,
    principal_id: str | None = None,
    target_owner: str | None = None,
    default_id: str = "doc_bob_02",
) -> str:
    """
    Safely resolve all {param} in route template without leaving literal {param}.
    Substitutes appropriate values for known parameters (doc_id, user_id, id, etc.).
    """
    path = template
    subs = {
        "{doc_id}": default_id,
        "{document_id}": default_id,
        "{id}": default_id,
        "{user_id}": target_owner or principal_id or "usr_bob_02",
        "{username}": target_owner or principal_id or "bob",
        "{item_id}": "1",
        "{post_id}": "1",
        "{filename}": "main.py",
        "{file_path}": "main.py",
        "{filepath}": "main.py",
        "{path}": "main.py",
    }
    for placeholder, val in subs.items():
        if placeholder in path:
            path = path.replace(placeholder, str(val))

    # Generic fallback for any remaining {variable} or {variable:type}
    path = re.sub(r"\{[a-zA-Z0-9_:]+\}", "1", path)
    return path


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
        emitter: Any = None,
    ):
        self._provider = llm_provider or MockLLMProvider()
        self._ledger = ledger or LLMCallLedger()
        self._test_case_repo = test_case_repo or TestCaseRepository()
        self._finding_repo = finding_repo or FindingRepository()
        self._rate_limit_rps = rate_limit_rps
        self._max_requests = max_requests
        self._emitter = emitter

    async def _emit(
        self,
        scan_id: str,
        kind: str,
        title: str,
        detail: str = "",
        refs: dict[str, Any] | None = None,
    ) -> None:
        if self._emitter:
            try:
                await self._emitter(scan_id, "attacker", kind, title, detail=detail, refs=refs)
            except Exception:
                pass

    async def _record_and_emit(
        self,
        scan_id: str,
        test_case: TestCaseRecord,
        all_tests: list[TestCaseRecord],
        finding: CandidateFinding | None = None,
        candidate_findings: list[CandidateFinding] | None = None,
    ) -> None:
        await self._test_case_repo.save(test_case)
        all_tests.append(test_case)
        if finding is not None and candidate_findings is not None:
            await self._finding_repo.save(finding)
            candidate_findings.append(finding)

        tc_cat = getattr(test_case, "category", "TEST")
        tc_route = getattr(test_case, "route_template", "")
        tc_method = getattr(test_case, "method", "GET")
        tc_id = getattr(test_case, "id", None)
        await self._emit(scan_id, "test_planned", f"{tc_cat} on {tc_route}", refs={"test_case_id": tc_id})
        await self._emit(scan_id, "request_sent", f"{tc_method} {tc_route}", refs={"test_case_id": tc_id})
        oracle_res = getattr(test_case, "oracle_result", {}) or {}
        fired = oracle_res.get("fired", False) if isinstance(oracle_res, dict) else getattr(oracle_res, "fired", False)
        rule_id = oracle_res.get("rule_id", "CHECK") if isinstance(oracle_res, dict) else getattr(oracle_res, "rule_id", "CHECK")
        rationale = oracle_res.get("rationale", "") if isinstance(oracle_res, dict) else getattr(oracle_res, "rationale", "")
        oracle_kind = "oracle_fired" if fired else "oracle_clear"
        oracle_title = f"Oracle {rule_id}: {rationale}" if fired else f"Oracle {rule_id} clear"
        await self._emit(scan_id, oracle_kind, oracle_title, refs={"test_case_id": tc_id})
        if finding is not None:
            await self._emit(scan_id, "finding_candidate", getattr(finding, "title", "Candidate finding"), refs={"finding_id": getattr(finding, "id", None)})

    async def _record_policy_skip(
        self,
        *,
        scan_id: str,
        category: str,
        route_template: str,
        method: str,
        principal_id: str | None,
        target_path: str,
        headers: dict[str, str] | None = None,
        reason: str,
        all_tests: list[TestCaseRecord],
    ) -> TestCaseRecord:
        logger.info(
            "Skipping test case by non-destructive policy: %s %s (%s)",
            method,
            route_template,
            reason,
            extra={
                "event": "scan.attacker.test_skipped_policy",
                "method": method,
                "route_template": route_template,
                "reason": reason,
            },
        )
        test_case = TestCaseRecord(
            scan_id=scan_id,
            category=category,
            route_template=route_template,
            method=method,
            principal_id=principal_id,
            request={
                "method": method,
                "url_path": target_path,
                "headers": headers or {},
                "body": None,
                "skipped": True,
            },
            response={
                "status_code": None,
                "headers": {},
                "body": "",
                "skipped": True,
            },
            oracle_result={
                "fired": False,
                "rule_id": "POLICY_SKIP",
                "rationale": reason,
            },
            status="skipped_policy",
            skip_reason=reason,
        )
        await self._test_case_repo.save(test_case)
        all_tests.append(test_case)
        return test_case

    async def _record_execution_error(
        self,
        *,
        scan_id: str,
        category: str,
        route_template: str,
        method: str,
        principal_id: str | None,
        target_path: str,
        headers: dict[str, str] | None = None,
        error_detail: str,
        all_tests: list[TestCaseRecord],
    ) -> TestCaseRecord:
        logger.warning(
            "Test case execution error for %s %s: %s",
            method,
            route_template,
            error_detail,
            extra={
                "event": "scan.attacker.test_failed_error",
                "method": method,
                "route_template": route_template,
                "error": error_detail,
            },
        )
        test_case = TestCaseRecord(
            scan_id=scan_id,
            category=category,
            route_template=route_template,
            method=method,
            principal_id=principal_id,
            request={
                "method": method,
                "url_path": target_path,
                "headers": headers or {},
                "body": None,
            },
            response={
                "status_code": None,
                "headers": {},
                "body": "",
                "error": error_detail,
            },
            oracle_result={
                "fired": False,
                "rule_id": "ERROR",
                "rationale": f"Request failed: {error_detail}",
            },
            status="failed_error",
            error_detail=error_detail,
        )
        await self._test_case_repo.save(test_case)
        all_tests.append(test_case)
        return test_case

    async def run_scan(
        self,
        *,
        context: AgentContext,
        target_handle: TargetHandle,
        replay_mode: bool = False,
        cancellation_token: asyncio.Event | None = None,
    ) -> AttackerScanResult:
        """
        Execute security test suite against the target and emit test cases and candidate findings.
        """
        all_tests: list[TestCaseRecord] = []
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
            bola_routes = [
                r for r in context.routes
                if "{" in r.route_template
                and ("doc" in r.route_template or "{id}" in r.route_template or "{item_id}" in r.route_template or "{resource_id}" in r.route_template)
                and not r.route_template.endswith("/{user_id}")
            ]

            for route in bola_routes:
                if cancellation_token and cancellation_token.is_set():
                    logger.info("AttackerAgent stopped: cancellation requested")
                    break
                norm_template = route.route_template
                method = route.method if route.method in ("GET", "HEAD") else "GET"
                # Target path: Alice requests Bob's document / object
                target_path = resolve_path_template(
                    norm_template,
                    target_owner=bob.user_id,
                    default_id="doc_bob_02",
                )
                req_headers = {"Authorization": alice.token}

                # Preflight policy check
                if ScopeLockedHttpClient.is_prohibited(method):
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=BOLAOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=f"HTTP {method} is prohibited by ClairSec non-destructive testing policy.",
                        all_tests=all_tests,
                    )
                    continue

                try:
                    t0 = time.perf_counter()
                    resp = await client.request(method, target_path, headers=req_headers)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=BOLAOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                    continue
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=BOLAOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )
                    continue

                # Platform oracle evaluation (No LLM adjudication)
                oracle_res = BOLAOracle.evaluate(
                    request_principal=alice.user_id,
                    target_owner=bob.user_id,
                    response_status=resp.status_code,
                    response_body=resp.text,
                )

                req_ev = capture_request_evidence(method, target_path, req_headers, body=None)
                resp_ev = capture_response_evidence(resp.status_code, dict(resp.headers), resp.text, elapsed_ms)

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=BOLAOracle.CATEGORY,
                    route_template=norm_template,
                    method=method,
                    principal_id=alice.user_id,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                    status="executed",
                )
                finding = None
                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Broken Object Level Authorization (BOLA) at {norm_template}",
                        category=BOLAOracle.CATEGORY,
                        cwe=[BOLAOracle.CWE],
                        route_template=norm_template,
                        method="GET",
                        principal_id=alice.user_id,
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

                await self._record_and_emit(
                    scan_id=context.scan_id,
                    test_case=test_case,
                    all_tests=all_tests,
                    finding=finding,
                    candidate_findings=candidate_findings,
                )

            # ─────────────────────────────────────────────────────────────────
            # Category 2: BOPLA_MASS_ASSIGN (Mass Assignment / CWE-915)
            # ─────────────────────────────────────────────────────────────────
            # Identify write routes updating user/entity profiles
            mass_assign_routes = [
                r for r in context.routes
                if r.method in ("PUT", "POST", "PATCH") and "profile" in r.route_template
            ]

            for route in mass_assign_routes:
                if cancellation_token and cancellation_token.is_set():
                    logger.info("AttackerAgent stopped: cancellation requested")
                    break
                norm_template = route.route_template
                method = route.method
                # Target path: Alice updates her profile injecting privileged fields
                target_path = resolve_path_template(
                    norm_template,
                    principal_id=alice.user_id,
                    target_owner=alice.user_id,
                    default_id=alice.user_id,
                )
                read_path = f"/users/{alice.user_id}"

                req_headers = {"Authorization": alice.token}
                injected_payload = {
                    "display_name": "Alice Exploit",
                    "bio": "Privilege escalation security test probe.",
                    "role": "admin",
                    "is_admin": True,
                }

                # Preflight policy check
                if ScopeLockedHttpClient.is_prohibited(method):
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=BOPLAMassAssignOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=f"HTTP {method} is prohibited by ClairSec non-destructive testing policy.",
                        all_tests=all_tests,
                    )
                    continue

                try:
                    # Step 1: Write attempt
                    t0 = time.perf_counter()
                    put_resp = await client.request(method, target_path, json=injected_payload, headers=req_headers)
                    put_elapsed_ms = int((time.perf_counter() - t0) * 1000)

                    # Step 2: Verification read
                    t1 = time.perf_counter()
                    get_resp = await client.get(read_path, headers=req_headers)
                    get_elapsed_ms = int((time.perf_counter() - t1) * 1000)
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=BOPLAMassAssignOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                    continue
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=BOPLAMassAssignOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )
                    continue

                # Platform oracle evaluation
                oracle_res = BOPLAMassAssignOracle.evaluate(
                    injected_fields={"role": "admin", "is_admin": True},
                    write_status=put_resp.status_code,
                    read_status=get_resp.status_code,
                    read_body=get_resp.text,
                )

                req_ev = capture_request_evidence(method, target_path, req_headers, body=injected_payload)
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
                    method=method,
                    principal_id=alice.user_id,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                    status="executed",
                )
                finding = None
                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Mass Assignment via Privileged Field Injection at {norm_template}",
                        category=BOPLAMassAssignOracle.CATEGORY,
                        cwe=[BOPLAMassAssignOracle.CWE],
                        route_template=norm_template,
                        method="PUT",
                        principal_id=alice.user_id,
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

                await self._record_and_emit(
                    scan_id=context.scan_id,
                    test_case=test_case,
                    all_tests=all_tests,
                    finding=finding,
                    candidate_findings=candidate_findings,
                )

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
                if cancellation_token and cancellation_token.is_set():
                    logger.info("AttackerAgent stopped: cancellation requested")
                    break
                norm_template = normalize_route_path(endpoint_path, known_templates)
                req_headers = {"Origin": "http://evil.example.com"}

                if ScopeLockedHttpClient.is_prohibited(method):
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=SecurityMisconfigOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=None,
                        target_path=endpoint_path,
                        headers=req_headers,
                        reason=f"HTTP {method} is prohibited by ClairSec non-destructive testing policy.",
                        all_tests=all_tests,
                    )
                    continue

                try:
                    t0 = time.perf_counter()
                    resp = await client.request(method, endpoint_path, headers=req_headers)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=SecurityMisconfigOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=None,
                        target_path=endpoint_path,
                        headers=req_headers,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                    continue
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=SecurityMisconfigOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=None,
                        target_path=endpoint_path,
                        headers=req_headers,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )
                    continue

                oracle_res = SecurityMisconfigOracle.evaluate(
                    endpoint_path=endpoint_path,
                    response_status=resp.status_code,
                    response_body=resp.text,
                    response_headers=dict(resp.headers),
                    request_origin="http://evil.example.com",
                )

                req_ev = capture_request_evidence(method, endpoint_path, headers=req_headers, body=None)
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
                    method=method,
                    principal_id=None,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                    status="executed",
                )
                finding = None
                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Security Misconfiguration: Exposed Internal Endpoint at {norm_template}",
                        category=SecurityMisconfigOracle.CATEGORY,
                        cwe=[SecurityMisconfigOracle.CWE],
                        route_template=norm_template,
                        method=method,
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

                await self._record_and_emit(
                    scan_id=context.scan_id,
                    test_case=test_case,
                    all_tests=all_tests,
                    finding=finding,
                    candidate_findings=candidate_findings,
                )

            # Probe CORS on root / if no misconfig candidate was emitted yet
            if not any(f.category == SecurityMisconfigOracle.CATEGORY for f in candidate_findings):
                cors_path = "/"
                norm_template = normalize_route_path(cors_path, known_templates)
                req_headers = {"Origin": "http://evil.example.com"}
                try:
                    t0 = time.perf_counter()
                    resp = await client.get(cors_path, headers=req_headers)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)

                    oracle_res = SecurityMisconfigOracle.evaluate(
                        endpoint_path=cors_path,
                        response_status=resp.status_code,
                        response_body=resp.text,
                        response_headers=dict(resp.headers),
                        request_origin="http://evil.example.com",
                    )

                    req_ev = capture_request_evidence("GET", cors_path, headers=req_headers, body=None)
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
                        status="executed",
                    )
                    finding = None
                    if oracle_res.fired:
                        finding = CandidateFinding(
                            scan_id=context.scan_id,
                            project_id=context.project_id,
                            title=f"Security Misconfiguration: Insecure CORS Policy at {norm_template}",
                            category=SecurityMisconfigOracle.CATEGORY,
                            cwe=[SecurityMisconfigOracle.CWE],
                            route_template=norm_template,
                            method="GET",
                            description=oracle_res.rationale,
                            impact="Cross-origin requests from arbitrary origins are permitted with user credentials.",
                            runtime_confirmed=True,
                            oracle_rule_id=oracle_res.rule_id,
                            evidence_ids=[test_case.id],
                            reproduction_summary=f"GET {cors_path} with Origin header allowed arbitrary origin with credentials.",
                            source_locations=[],
                            status="candidate",
                        )

                    await self._record_and_emit(
                        scan_id=context.scan_id,
                        test_case=test_case,
                        all_tests=all_tests,
                        finding=finding,
                        candidate_findings=candidate_findings,
                    )
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=SecurityMisconfigOracle.CATEGORY,
                        route_template=norm_template,
                        method="GET",
                        principal_id=None,
                        target_path=cors_path,
                        headers=req_headers,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=SecurityMisconfigOracle.CATEGORY,
                        route_template=norm_template,
                        method="GET",
                        principal_id=None,
                        target_path=cors_path,
                        headers=req_headers,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )

            # ─────────────────────────────────────────────────────────────────
            # Category 4: BFLA (Broken Function Level Authorization / CWE-285)
            # ─────────────────────────────────────────────────────────────────
            bfla_routes = [
                r for r in context.routes
                if ("/admin" in r.route_template or "/manage" in r.route_template or "admin" in r.route_template)
                and r.method in ("GET", "POST", "PUT", "DELETE")
            ]
            for route in bfla_routes:
                if cancellation_token and cancellation_token.is_set():
                    logger.info("AttackerAgent stopped: cancellation requested")
                    break
                norm_template = route.route_template
                method = route.method
                target_path = resolve_path_template(norm_template, principal_id=alice.user_id, default_id="1")
                req_headers = {"Authorization": alice.token}

                # Preflight policy check
                if ScopeLockedHttpClient.is_prohibited(method):
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=BFLAOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=f"HTTP {method} is prohibited by ClairSec non-destructive testing policy.",
                        all_tests=all_tests,
                    )
                    continue

                try:
                    t0 = time.perf_counter()
                    resp = await client.request(method, target_path, headers=req_headers)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=BFLAOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                    continue
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=BFLAOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        target_path=target_path,
                        headers=req_headers,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )
                    continue

                oracle_res = BFLAOracle.evaluate(
                    request_principal_role=alice.role,
                    endpoint_path=target_path,
                    response_status=resp.status_code,
                    response_body=resp.text,
                )

                req_ev = capture_request_evidence(method, target_path, req_headers, body=None)
                resp_ev = capture_response_evidence(
                    resp.status_code,
                    dict(resp.headers),
                    resp.text,
                    elapsed_ms,
                )

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=BFLAOracle.CATEGORY,
                    route_template=norm_template,
                    method=method,
                    principal_id=alice.user_id,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                    status="executed",
                )
                finding = None
                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Broken Function Level Authorization (BFLA) at {norm_template}",
                        category=BFLAOracle.CATEGORY,
                        cwe=[BFLAOracle.CWE],
                        route_template=norm_template,
                        method=method,
                        principal_id=alice.user_id,
                        description=oracle_res.rationale,
                        impact="Unprivileged users can invoke administrative endpoints without proper role checks.",
                        runtime_confirmed=True,
                        oracle_rule_id=oracle_res.rule_id,
                        evidence_ids=[test_case.id],
                        reproduction_summary=f"{method} {target_path} by role '{alice.role}' returned status {resp.status_code}.",
                        source_locations=[
                            {
                                "file": route.source_file,
                                "line_start": route.source_line_range[0],
                                "line_end": route.source_line_range[1],
                            }
                        ] if route.source_file else [],
                        status="candidate",
                    )

                await self._record_and_emit(
                    scan_id=context.scan_id,
                    test_case=test_case,
                    all_tests=all_tests,
                    finding=finding,
                    candidate_findings=candidate_findings,
                )

            # ─────────────────────────────────────────────────────────────────
            # Category 5: PATH_TRAVERSAL (Path Traversal / CWE-22)
            # ─────────────────────────────────────────────────────────────────
            FILE_PARAM_NAMES = {"file", "filename", "filepath", "path", "doc_path", "template", "page", "dir", "document"}
            traversal_routes: list[RouteItem] = []

            for r in context.routes:
                if r.method != "GET":
                    continue
                path_param_names = {p.get("name", "").lower() for p in getattr(r, "path_params", [])}
                query_param_names = {p.get("name", "").lower() for p in getattr(r, "query_params", [])}
                has_file_param = bool(path_param_names & FILE_PARAM_NAMES or query_param_names & FILE_PARAM_NAMES)
                is_file_route = any(kw in r.route_template.lower() for kw in ("/file", "/files", "/download", "/static"))
                has_user_id = any(uid in r.route_template for uid in ("{user_id}", "{account_id}", "{doc_id}"))

                if (has_file_param or (is_file_route and "{" in r.route_template)) and not has_user_id:
                    traversal_routes.append(r)

            if not traversal_routes:
                logger.info(
                    "Path Traversal: no eligible file-serving routes discovered in target (category skipped)",
                    extra={"event": "attacker.path_traversal.skipped", "reason": "no_file_routes"},
                )

            for route in traversal_routes:
                if cancellation_token and cancellation_token.is_set():
                    logger.info("AttackerAgent stopped: cancellation requested")
                    break
                norm_template = route.route_template
                method = route.method

                # Construct URL-encoded traversal probe so HTTP client does not collapse dot segments to /app/main.py
                target_path = re.sub(r"\{[a-zA-Z0-9_:]+\}", "..%2fapp/main.py", norm_template)

                # Determine authentication headers and principal context
                req_headers: dict[str, str] = {}
                active_principal_id: str | None = None
                if (route.requires_auth or bool(context.auth_schemes)) and alice:
                    req_headers["Authorization"] = alice.token
                    active_principal_id = alice.user_id

                # Preflight policy check
                if ScopeLockedHttpClient.is_prohibited(method):
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=PathTraversalOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=active_principal_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=f"HTTP {method} is prohibited by ClairSec non-destructive testing policy.",
                        all_tests=all_tests,
                    )
                    continue

                try:
                    t0 = time.perf_counter()
                    resp = await client.request(method, target_path, headers=req_headers)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=PathTraversalOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=active_principal_id,
                        target_path=target_path,
                        headers=req_headers,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                    continue
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=PathTraversalOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=active_principal_id,
                        target_path=target_path,
                        headers=req_headers,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )
                    continue

                oracle_res = PathTraversalOracle.evaluate(
                    endpoint_path=target_path,
                    response_status=resp.status_code,
                    response_body=resp.text,
                )

                req_ev = capture_request_evidence(method, target_path, headers=req_headers, body=None)
                resp_ev = capture_response_evidence(
                    resp.status_code,
                    dict(resp.headers),
                    resp.text,
                    elapsed_ms,
                )

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=PathTraversalOracle.CATEGORY,
                    route_template=norm_template,
                    method=method,
                    principal_id=active_principal_id,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                    status="executed",
                )
                finding = None
                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"Path Traversal at {norm_template}",
                        category=PathTraversalOracle.CATEGORY,
                        cwe=[PathTraversalOracle.CWE],
                        route_template=norm_template,
                        method=method,
                        principal_id=active_principal_id,
                        description=oracle_res.rationale,
                        impact="Arbitrary host or application source files can be read by unauthorized users.",
                        runtime_confirmed=True,
                        oracle_rule_id=oracle_res.rule_id,
                        evidence_ids=[test_case.id],
                        reproduction_summary=f"GET {target_path} returned internal source file contents.",
                        source_locations=[
                            {
                                "file": route.source_file,
                                "line_start": route.source_line_range[0],
                                "line_end": route.source_line_range[1],
                            }
                        ] if route.source_file else [],
                        status="candidate",
                    )

                await self._record_and_emit(
                    scan_id=context.scan_id,
                    test_case=test_case,
                    all_tests=all_tests,
                    finding=finding,
                    candidate_findings=candidate_findings,
                )

            # ─────────────────────────────────────────────────────────────────
            # Category 6: SQL_INJECTION (SQL Injection / CWE-89)
            # ─────────────────────────────────────────────────────────────────
            sqli_routes = [
                r for r in context.routes
                if r.method == "GET" and any(kw in r.route_template.lower() for kw in ("search", "find", "query", "filter"))
            ]
            for route in sqli_routes:
                if cancellation_token and cancellation_token.is_set():
                    raise asyncio.CancelledError("Attacker execution cancelled")
                norm_template = route.route_template
                method = route.method
                base_path = resolve_path_template(norm_template, default_id="1")
                sep = "&" if "?" in base_path else "?"
                target_path = f"{base_path}{sep}q=' OR '1'='1"

                # Preflight policy check
                if ScopeLockedHttpClient.is_prohibited(method):
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=SQLInjectionOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=None,
                        target_path=target_path,
                        headers=None,
                        reason=f"HTTP {method} is prohibited by ClairSec non-destructive testing policy.",
                        all_tests=all_tests,
                    )
                    continue

                try:
                    t0 = time.perf_counter()
                    resp = await client.request(method, target_path)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                except NonDestructivePolicyViolationError as exc:
                    await self._record_policy_skip(
                        scan_id=context.scan_id,
                        category=SQLInjectionOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=None,
                        target_path=target_path,
                        headers=None,
                        reason=str(exc),
                        all_tests=all_tests,
                    )
                    continue
                except (asyncio.CancelledError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    await self._record_execution_error(
                        scan_id=context.scan_id,
                        category=SQLInjectionOracle.CATEGORY,
                        route_template=norm_template,
                        method=method,
                        principal_id=None,
                        target_path=target_path,
                        headers=None,
                        error_detail=str(exc),
                        all_tests=all_tests,
                    )
                    continue

                oracle_res = SQLInjectionOracle.evaluate(
                    endpoint_path=target_path,
                    response_status=resp.status_code,
                    response_body=resp.text,
                )

                req_ev = capture_request_evidence(method, target_path, headers=None, body=None)
                resp_ev = capture_response_evidence(
                    resp.status_code,
                    dict(resp.headers),
                    resp.text,
                    elapsed_ms,
                )

                test_case = TestCaseRecord(
                    scan_id=context.scan_id,
                    category=SQLInjectionOracle.CATEGORY,
                    route_template=norm_template,
                    method=method,
                    principal_id=None,
                    request=req_ev,
                    response=resp_ev,
                    oracle_result=oracle_res.model_dump(),
                    status="executed",
                )

                if oracle_res.fired:
                    finding = CandidateFinding(
                        scan_id=context.scan_id,
                        project_id=context.project_id,
                        title=f"SQL Injection at {norm_template}",
                        category=SQLInjectionOracle.CATEGORY,
                        cwe=[SQLInjectionOracle.CWE],
                        route_template=norm_template,
                        method=method,
                        description=oracle_res.rationale,
                        impact="Unsanitized user inputs are incorporated directly into SQL statements, leaking data.",
                        runtime_confirmed=True,
                        oracle_rule_id=oracle_res.rule_id,
                        evidence_ids=[test_case.id],
                        reproduction_summary=f"GET {target_path} triggered database syntax error.",
                        source_locations=[
                            {
                                "file": route.source_file,
                                "line_start": route.source_line_range[0],
                                "line_end": route.source_line_range[1],
                            }
                        ] if route.source_file else [],
                        status="candidate",
                    )
                else:
                    finding = None

                await self._record_and_emit(
                    scan_id=context.scan_id,
                    test_case=test_case,
                    all_tests=all_tests,
                    finding=finding,
                    candidate_findings=candidate_findings,
                )

        executed_tests = [tc for tc in all_tests if tc.status == "executed"]
        skipped_policy_tests = [tc for tc in all_tests if tc.status == "skipped_policy"]
        failed_error_tests = [tc for tc in all_tests if tc.status == "failed_error"]

        return AttackerScanResult(
            scan_id=context.scan_id,
            project_id=context.project_id,
            test_cases=all_tests,
            findings=candidate_findings,
            counters={
                "tests_generated": len(all_tests),
                "tests_executed": len(executed_tests),
                "tests_skipped_policy": len(skipped_policy_tests),
                "tests_failed_error": len(failed_error_tests),
                "candidates": len(candidate_findings),
            },
        )
