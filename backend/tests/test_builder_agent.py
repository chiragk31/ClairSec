"""
Phase 4 Exit Gate Verification Suite for Builder Agent.
Enforces:
  1. Builder produces a validated, typed inventory for vulnerable_fastapi_app using MockLLMProvider.
  2. Malformed LLM responses degrade gracefully to AST defaults and are recorded rather than crashing.
  3. Canary secrets in fixtures are provably never present in captured outbound payloads (C5.4).
  4. Test-principals provision at least two distinct authenticated identities.
"""
from pathlib import Path
import pytest

from app.agents.builder.builder import BuilderAgent
from app.llm.accounting import LLMCallLedger
from app.llm.providers.mock_provider import MockLLMProvider
from app.targets.handle import LocalFixtureTargetHandle

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.anyio
async def test_builder_produces_typed_inventory_for_vulnerable_app():
    """Verify Builder Agent extracts complete normalized inventory from vulnerable fixture."""
    vuln_dir = FIXTURES_DIR / "vulnerable_fastapi_app"
    ledger = LLMCallLedger()
    provider = MockLLMProvider(mode="valid")
    builder = BuilderAgent(llm_provider=provider, ledger=ledger)

    context = await builder.build_context(
        project_id="test-vuln-project",
        scan_id="scan-builder-01",
        project_dir=vuln_dir,
    )

    assert context.project_id == "test-vuln-project"
    assert context.scan_id == "scan-builder-01"

    # Verify route templates are normalized and captured
    route_templates = {(r.route_template, r.method) for r in context.routes}
    assert ("/documents/{doc_id}", "GET") in route_templates
    assert ("/users/{user_id}/profile", "PUT") in route_templates
    assert ("/debug/config", "GET") in route_templates
    assert ("/health", "GET") in route_templates
    assert ("/documents", "POST") in route_templates

    # Check that AST identified BOLA target parameter
    doc_route = next(r for r in context.routes if r.route_template == "/documents/{doc_id}")
    assert doc_route.requires_auth is True
    assert doc_route.resource_owner_param == "doc_id"

    # Check that AST identified BOPLA_MASS_ASSIGN target parameter and extra allow
    profile_route = next(r for r in context.routes if r.route_template == "/users/{user_id}/profile")
    assert profile_route.resource_owner_param == "user_id"
    assert profile_route.extra_fields_allowed is True

    # Check that AST identified SECURITY_MISCONFIG debug route
    debug_route = next(r for r in context.routes if r.route_template == "/debug/config")
    assert debug_route.is_debug_or_internal is True

    # Check test principals: at least two distinct authenticated identities
    assert len(context.principals) >= 2
    principal_ids = {p.user_id for p in context.principals}
    assert "usr_alice_01" in principal_ids
    assert "usr_bob_02" in principal_ids
    assert context.principals[0].token != context.principals[1].token

    # Verify ledger recorded the call and token accounting
    totals = ledger.get_scan_totals("scan-builder-01")
    assert totals["calls_count"] == 1
    assert totals["total_tokens"] > 0
    assert totals["malformed_calls_count"] == 0


@pytest.mark.anyio
async def test_builder_graceful_degradation_on_malformed_response():
    """Verify that a malformed LLM response degrades gracefully and is recorded rather than crashing."""
    vuln_dir = FIXTURES_DIR / "vulnerable_fastapi_app"
    ledger = LLMCallLedger()
    # Configure mock provider to fail schema validation twice
    provider = MockLLMProvider(mode="malformed")
    builder = BuilderAgent(llm_provider=provider, ledger=ledger)

    context = await builder.build_context(
        project_id="test-vuln-project",
        scan_id="scan-builder-malformed",
        project_dir=vuln_dir,
    )

    # Context still produced using deterministic AST extraction
    assert len(context.routes) >= 5
    route_templates = {r.route_template for r in context.routes}
    assert "/documents/{doc_id}" in route_templates

    # Ledger recorded the schema failure as a research metric
    totals = ledger.get_scan_totals("scan-builder-malformed")
    assert totals["calls_count"] == 1
    assert totals["malformed_calls_count"] == 1


@pytest.mark.anyio
async def test_builder_canary_secret_never_present_in_outbound_payload():
    """Verify C5.4: Canary secrets in code are scrubbed before prompt submission."""
    vuln_dir = FIXTURES_DIR / "vulnerable_fastapi_app"
    ledger = LLMCallLedger()
    provider = MockLLMProvider(mode="valid")
    builder = BuilderAgent(llm_provider=provider, ledger=ledger)

    await builder.build_context(
        project_id="test-vuln-project",
        scan_id="scan-builder-canary",
        project_dir=vuln_dir,
    )

    assert len(provider.call_history) == 1
    req = provider.call_history[0]
    prompt_text = req.messages[0].content

    # The raw database password and API key in vulnerable_fastapi_app/main.py must be scrubbed
    assert "prod_secret_pass_99" not in prompt_text
    assert "sec-prod-internal-master-key-999" not in prompt_text
    assert "<redacted:internal_key>" in prompt_text or "<redacted:password>" in prompt_text


@pytest.mark.anyio
async def test_builder_with_local_fixture_target_handle_seam():
    """Verify Builder Agent successfully integrates with R5 LocalFixtureTargetHandle."""
    vuln_dir = FIXTURES_DIR / "vulnerable_fastapi_app"
    handle = LocalFixtureTargetHandle(vuln_dir)
    await handle.start()

    try:
        ledger = LLMCallLedger()
        provider = MockLLMProvider(mode="valid")
        builder = BuilderAgent(llm_provider=provider, ledger=ledger)

        context = await builder.build_context(
            project_id="test-vuln-project",
            scan_id="scan-builder-handle",
            project_dir=vuln_dir,
            target_handle=handle,
        )

        assert len(context.routes) >= 5
        assert context.canary_clean is True
    finally:
        await handle.stop()
