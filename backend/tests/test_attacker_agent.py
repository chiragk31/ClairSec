"""
Integration tests for Phase 5 Attacker Agent exit gate.

EXIT GATE CRITERIA:
1. Attacker finds all three seeded vulnerabilities in vulnerable_fastapi_app via LocalFixtureTargetHandle.
   (Confirmed vuln count == 3: BOLA, BOPLA_MASS_ASSIGN, SECURITY_MISCONFIG).
2. Attacker reports ZERO findings against secure_fastapi_app via LocalFixtureTargetHandle.
   (Secure fixture false-positive count == 0).
3. Both numbers matter equally.
4. Route templates in candidate findings and test cases are normalized (/documents/{doc_id}, never /documents/doc_bob_02).
5. All executed tests are persisted to test_cases whether or not they fired.
6. Re-running in replay mode produces an identical test-case set.
7. Off-target HTTP request is provably refused by scope lock (T9).
"""
from __future__ import annotations

import uuid
from pathlib import Path
import pytest

from app.agents.builder.builder import BuilderAgent
from app.agents.attacker.attacker import AttackerAgent
from app.security.http_client import OffTargetRequestBlockedError
from app.targets.handle import LocalFixtureTargetHandle

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VULN_FIXTURE = FIXTURES_DIR / "vulnerable_fastapi_app"
SECURE_FIXTURE = FIXTURES_DIR / "secure_fastapi_app"


@pytest.mark.asyncio
async def test_attacker_finds_all_three_seeded_vulns_in_vulnerable_app():
    """
    Phase 5 Exit Gate: Attacker finds all 3 seeded vulnerabilities in vulnerable_fastapi_app.
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        # Step 1: Run Builder to extract context and routes
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="vulnerable_fastapi_app",
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        # Step 2: Run Attacker Agent
        attacker = AttackerAgent()
        result = await attacker.run_scan(
            context=context,
            target_handle=handle,
        )

        # Assertions
        assert len(result.test_cases) >= 3, "Expected at least 3 security test cases executed"
        for tc in result.test_cases:
            assert tc.scan_id == scan_id
            assert "{" not in tc.request["url_path"] or "{" in tc.route_template

        # Must find exactly the 3 seeded vulnerabilities
        categories_found = {f.category for f in result.findings}
        assert "BOLA" in categories_found, "Attacker failed to detect BOLA (CWE-639)"
        assert "BOPLA_MASS_ASSIGN" in categories_found, "Attacker failed to detect BOPLA_MASS_ASSIGN (CWE-915)"
        assert "SECURITY_MISCONFIG" in categories_found, "Attacker failed to detect SECURITY_MISCONFIG (CWE-16)"
        assert len(result.findings) == 3, f"Expected exactly 3 candidate findings, got {len(result.findings)}"

        # Check route template normalization (must be /documents/{doc_id}, never /documents/doc_bob_02)
        bola_finding = next(f for f in result.findings if f.category == "BOLA")
        assert bola_finding.route_template == "/documents/{doc_id}"
        assert bola_finding.cwe == ["CWE-639"]
        assert bola_finding.runtime_confirmed is True

        mass_finding = next(f for f in result.findings if f.category == "BOPLA_MASS_ASSIGN")
        assert mass_finding.route_template == "/users/{user_id}/profile"
        assert mass_finding.cwe == ["CWE-915"]
        assert mass_finding.runtime_confirmed is True

        misconfig_finding = next(f for f in result.findings if f.category == "SECURITY_MISCONFIG")
        assert misconfig_finding.route_template == "/debug/config"
        assert misconfig_finding.cwe == ["CWE-16"]
        assert misconfig_finding.runtime_confirmed is True

        # Denominator check: every test case persisted whether or not it fired
        test_case_records = await attacker._test_case_repo.list_by_scan(scan_id)
        assert len(test_case_records) == len(result.test_cases)

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_attacker_reports_zero_findings_against_secure_app():
    """
    Phase 5 Exit Gate: Attacker reports ZERO findings against secure_fastapi_app (FP = 0).
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=SECURE_FIXTURE)
    await handle.start()

    try:
        # Step 1: Run Builder
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="secure_fastapi_app",
            scan_id=scan_id,
            project_dir=SECURE_FIXTURE,
            target_handle=handle,
        )

        # Step 2: Run Attacker Agent
        attacker = AttackerAgent()
        result = await attacker.run_scan(
            context=context,
            target_handle=handle,
        )

        # Assertions
        assert len(result.test_cases) >= 3, "Expected tests were still executed against secure app"
        # Zero candidate findings reported (false positive rate = 0)
        assert len(result.findings) == 0, f"Expected 0 findings against secure app, got {len(result.findings)}"
        # None of the oracles fired
        for tc in result.test_cases:
            assert tc.oracle_result["fired"] is False

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_attacker_replay_mode_produces_identical_test_case_set():
    """
    Phase 5 Requirement: Re-running in replay mode produces an identical test-case set.
    """
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="vulnerable_fastapi_app",
            scan_id=str(uuid.uuid4()),
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        attacker1 = AttackerAgent()
        res1 = await attacker1.run_scan(context=context, target_handle=handle, replay_mode=True)

        attacker2 = AttackerAgent()
        res2 = await attacker2.run_scan(context=context, target_handle=handle, replay_mode=True)

        assert len(res1.test_cases) == len(res2.test_cases)
        for tc1, tc2 in zip(res1.test_cases, res2.test_cases):
            assert tc1.category == tc2.category
            assert tc1.route_template == tc2.route_template
            assert tc1.method == tc2.method
            assert tc1.oracle_result["fired"] == tc2.oracle_result["fired"]
            assert tc1.request["url_path"] == tc2.request["url_path"]

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_off_target_request_refused_t9_in_scan():
    """
    Phase 5 & THREAT_MODEL T9: Proves an off-target request is refused by the scope lock.
    """
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        from app.security.http_client import ScopeLockedHttpClient
        client = ScopeLockedHttpClient(base_url=handle.base_url)

        # Attempt off-target request to external host
        with pytest.raises(OffTargetRequestBlockedError):
            await client.get("https://unauthorized-domain.org/data")

        # Attempt off-target request to local loopback on different port
        with pytest.raises(OffTargetRequestBlockedError):
            await client.get("http://127.0.0.1:8000/data")

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_prohibited_delete_method_skipped_by_preflight_and_safe_tests_continue():
    """
    Regression Test: Proves that an adversarial route with DELETE is skipped by policy
    during preflight, does NOT abort the scan, is marked 'skipped_policy', is NOT counted
    as an executed test or vulnerability, and subsequent safe tests execute normally.
    """
    from app.agents.builder.schemas import AgentContext, RouteItem, TestPrincipal

    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        # Construct synthetic context containing a prohibited DELETE route and safe GET routes
        context = AgentContext(
            project_id="test_project",
            scan_id=scan_id,
            routes=[
                # Prohibited DELETE route in BFLA
                RouteItem(
                    route_template="/admin/users/{user_id}",
                    method="DELETE",
                    handler_name="delete_user",
                    source_file="admin.py",
                    source_line_range=(50, 70),
                    requires_auth=True,
                ),
                # Safe GET route in BFLA
                RouteItem(
                    route_template="/admin/users",
                    method="GET",
                    handler_name="list_users",
                    source_file="admin.py",
                    source_line_range=(20, 45),
                    requires_auth=True,
                ),
                # Safe GET debug config route
                RouteItem(
                    route_template="/debug/config",
                    method="GET",
                    handler_name="get_debug_config",
                    source_file="main.py",
                    source_line_range=(198, 208),
                    requires_auth=False,
                    is_debug_or_internal=True,
                ),
            ],
            principals=[
                TestPrincipal(user_id="usr_alice_01", username="alice", token="Bearer alice-token-123", role="member"),
            ],
            auth_schemes=["OAuth2PasswordBearer"],
        )

        attacker = AttackerAgent()
        result = await attacker.run_scan(context=context, target_handle=handle)

        # 1. Prohibited DELETE test was generated and recorded as skipped_policy
        delete_tcs = [tc for tc in result.test_cases if tc.method == "DELETE"]
        assert len(delete_tcs) == 1
        delete_tc = delete_tcs[0]
        assert delete_tc.status == "skipped_policy"
        assert delete_tc.skip_reason is not None
        assert "DELETE is prohibited" in delete_tc.skip_reason
        assert delete_tc.oracle_result["fired"] is False
        assert delete_tc.response.get("skipped") is True

        # 2. DELETE is NOT classified as a candidate finding
        for f in result.findings:
            assert f.method != "DELETE"

        # 3. Safe GET routes were executed
        executed_tcs = [tc for tc in result.test_cases if tc.status == "executed"]
        assert len(executed_tcs) >= 1
        assert any(tc.route_template == "/debug/config" for tc in executed_tcs)

        # 4. Counters are accurately partitioned
        assert result.counters["tests_generated"] == len(result.test_cases)
        assert result.counters["tests_skipped_policy"] >= 1
        assert result.counters["tests_executed"] == len(executed_tcs)
        assert result.counters["tests_failed_error"] == 0
        assert result.counters["tests_executed"] < result.counters["tests_generated"]

        # 5. Denominator: all test cases (both skipped and executed) were persisted to repository
        persisted = await attacker._test_case_repo.list_by_scan(scan_id)
        assert len(persisted) == len(result.test_cases)

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_policy_violation_exception_at_boundary_does_not_abort_scan():
    """
    Regression Test: If NonDestructivePolicyViolationError is raised at runtime
    at the HTTP client boundary, it is safely caught, recorded as 'skipped_policy',
    and does not abort the scan.
    """
    from unittest.mock import patch
    from app.agents.builder.schemas import AgentContext, RouteItem, TestPrincipal
    from app.security.http_client import NonDestructivePolicyViolationError, ScopeLockedHttpClient

    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        context = AgentContext(
            project_id="test_project",
            scan_id=scan_id,
            routes=[
                RouteItem(
                    route_template="/documents/{doc_id}",
                    method="GET",
                    handler_name="get_document",
                    source_file="main.py",
                    source_line_range=(120, 130),
                    requires_auth=True,
                ),
            ],
            principals=[
                TestPrincipal(user_id="usr_alice_01", username="alice", token="Bearer alice-token-123", role="member"),
                TestPrincipal(user_id="usr_bob_02", username="bob", token="Bearer bob-token-456", role="member"),
            ],
        )

        attacker = AttackerAgent()

        orig_request = ScopeLockedHttpClient.request

        async def mock_request(self, method, url, **kwargs):
            if "doc_bob_02" in url:
                raise NonDestructivePolicyViolationError("Simulated boundary policy error")
            return await orig_request(self, method, url, **kwargs)

        with patch.object(ScopeLockedHttpClient, "request", new=mock_request):
            result = await attacker.run_scan(context=context, target_handle=handle)

        bola_tcs = [t for t in result.test_cases if t.route_template == "/documents/{doc_id}"]
        assert len(bola_tcs) == 1
        tc = bola_tcs[0]
        assert tc.status == "skipped_policy"
        assert "Simulated boundary policy error" in (tc.skip_reason or "")
        assert result.counters["tests_skipped_policy"] == 1
        assert result.counters["tests_executed"] >= 1

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_unexpected_runtime_error_recorded_as_failed_error_without_abort():
    """
    Regression Test: Unexpected runtime error during test case execution is caught,
    recorded as 'failed_error', increments tests_failed_error, and does not crash scan.
    """
    from unittest.mock import patch
    from app.agents.builder.schemas import AgentContext, RouteItem, TestPrincipal
    from app.security.http_client import ScopeLockedHttpClient

    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        context = AgentContext(
            project_id="test_project",
            scan_id=scan_id,
            routes=[
                RouteItem(
                    route_template="/documents/{doc_id}",
                    method="GET",
                    handler_name="get_document",
                    source_file="main.py",
                    source_line_range=(120, 130),
                    requires_auth=True,
                ),
                RouteItem(
                    route_template="/debug/config",
                    method="GET",
                    handler_name="get_debug_config",
                    source_file="main.py",
                    source_line_range=(198, 208),
                    requires_auth=False,
                    is_debug_or_internal=True,
                ),
            ],
            principals=[
                TestPrincipal(user_id="usr_alice_01", username="alice", token="Bearer alice-token-123", role="member"),
                TestPrincipal(user_id="usr_bob_02", username="bob", token="Bearer bob-token-456", role="member"),
            ],
        )

        attacker = AttackerAgent()

        orig_request = ScopeLockedHttpClient.request

        async def mock_request(self, method, url, **kwargs):
            if "doc_bob_02" in url:
                raise ConnectionResetError("Connection abruptly closed by peer")
            return await orig_request(self, method, url, **kwargs)

        with patch.object(ScopeLockedHttpClient, "request", new=mock_request):
            result = await attacker.run_scan(context=context, target_handle=handle)

        assert result.counters["tests_failed_error"] == 1
        assert result.counters["tests_executed"] >= 1
        error_tcs = [tc for tc in result.test_cases if tc.status == "failed_error"]
        assert len(error_tcs) == 1
        assert "Connection abruptly closed" in (error_tcs[0].error_detail or "")

    finally:
        await handle.stop()


@pytest.mark.docker
@pytest.mark.asyncio
async def test_attacker_live_docker_containerized_target_confirmatory(tmp_path):
    """
    Confirmatory live Docker test: runs the Attacker against vulnerable_fastapi_app
    running inside a real hardened Docker container via the scanner proxy (C3.3).
    LocalFixtureTargetHandle remains the default for unit/integration runs per R1/R5.
    """
    from app.isolation.docker_manager import DockerManager
    from app.isolation.workspace import WorkspaceManager
    from app.targets.handle import ContainerTargetHandle

    project_id = str(uuid.uuid4())
    scan_id = str(uuid.uuid4())

    ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    workspace = ws.create_scan_workspace(project_id, str(VULN_FIXTURE))

    dm = DockerManager()
    container_id = None
    try:
        image_tag = dm.build_image(
            project_id=project_id,
            workspace_path=workspace,
            entry_point="main.py",
            dependency_file="requirements.txt",
        )
        assert image_tag is not None

        container_id, container_name = dm.start_container(project_id, image_tag)
        proxy_id, proxy_port = dm.start_proxy(project_id, container_name)

        healthy = dm.wait_for_healthy(proxy_port, startup_timeout=30)
        assert healthy, "Live target container failed health check via proxy"

        handle = ContainerTargetHandle(
            proxy_port=proxy_port,
            container_id=container_id,
            docker_manager=dm,
        )

        builder = BuilderAgent()
        context = await builder.build_context(
            project_id=project_id,
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        attacker = AttackerAgent()
        result = await attacker.run_scan(
            context=context,
            target_handle=handle,
        )

        categories_found = {f.category for f in result.findings}
        assert "BOLA" in categories_found
        assert "BOPLA_MASS_ASSIGN" in categories_found
        assert "SECURITY_MISCONFIG" in categories_found
        assert len(result.findings) == 3
    finally:
        dm.cleanup_all(project_id, container_id=container_id)
        try:
            ws.cleanup_workspace(project_id)
        except Exception:
            pass

