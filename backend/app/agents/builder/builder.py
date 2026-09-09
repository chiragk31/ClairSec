"""
Builder Agent implementation (LLM.md, THREAT_MODEL C1.1, C1.2, C5.1, C5.2, C5.4).
Produces validated AgentContext from static AST first, /openapi.json second, and quarantined LLM third.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.builder.schemas import (
    AgentContext,
    RouteItem,
    RouteSemanticBatch,
    TestPrincipal,
)
from app.agents.builder.ast_extractor import extract_routes_from_project
from app.agents.builder.openapi_extractor import (
    extract_openapi_schema,
    parse_openapi_routes,
)
from app.agents.builder.provisioning import provision_test_principals
from app.llm.accounting import LLMCallLedger
from app.llm.models import (
    AgentName,
    CallBudget,
    LLMRequest,
    Message,
    TrustLevel,
    Untrusted,
)
from app.llm.prompts.registry import registry
from app.llm.provider import LLMProvider
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.quarantine import wrap_quarantined, enforce_quarantine_discipline
from app.llm.redaction import filter_allowed_files, redact_secrets
from app.targets.handle import TargetHandle


class BuilderAgent:
    """
    Constructs the target project inventory and agent context.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        ledger: LLMCallLedger | None = None,
    ):
        self._provider = llm_provider or MockLLMProvider()
        self._ledger = ledger or LLMCallLedger()

    async def build_context(
        self,
        *,
        project_id: str,
        scan_id: str,
        project_dir: str | Path,
        target_handle: TargetHandle | None = None,
        custom_principals: list[TestPrincipal] | None = None,
    ) -> AgentContext:
        """
        Execute Builder pipeline:
          1. Deterministic static AST route extraction (FIRST)
          2. /openapi.json extraction from target container/handle (SECOND)
          3. Quarantined LLM extraction for semantic auth/ownership (THIRD)
          4. Test principal provisioning
          5. Emit validated AgentContext
        """
        root = Path(project_dir).resolve()

        # ---------------------------------------------------------------------
        # Step 1: Deterministic Static AST Extraction (C5.1 Deny-list applied)
        # ---------------------------------------------------------------------
        py_files = [
            f for f in root.glob("**/*.py")
            if not any(
                p.startswith(".") or p in ("venv", ".venv", "__pycache__", "node_modules")
                for p in f.relative_to(root).parts
            )
        ]
        allowed_files = filter_allowed_files(py_files)

        ast_routes: list[RouteItem] = []
        for py_file in sorted(allowed_files):
            from app.agents.builder.ast_extractor import extract_routes_from_file
            routes, _ = extract_routes_from_file(py_file)
            ast_routes.extend(routes)

        route_map: dict[tuple[str, str], RouteItem] = {
            (r.route_template, r.method): r for r in ast_routes
        }

        # ---------------------------------------------------------------------
        # Step 2: Runtime /openapi.json Extraction
        # ---------------------------------------------------------------------
        if target_handle is not None:
            openapi_dict = await extract_openapi_schema(target_handle.base_url)
            if openapi_dict:
                openapi_routes = parse_openapi_routes(openapi_dict)
                for o_route in openapi_routes:
                    key = (o_route.route_template, o_route.method)
                    if key in route_map:
                        # Enhance existing AST route with runtime parameter fields
                        existing = route_map[key]
                        if not existing.input_fields and o_route.input_fields:
                            existing.input_fields = o_route.input_fields
                    else:
                        route_map[key] = o_route

        # ---------------------------------------------------------------------
        # Step 3: Quarantined LLM Semantic Extraction (LLM.md §6)
        # ---------------------------------------------------------------------
        # Extract brief code context for each route to query auth semantics
        route_summaries = []
        for (tmpl, meth), item in sorted(route_map.items()):
            snippet = ""
            src_path = root / item.source_file
            if src_path.exists() and item.source_line_range != (0, 0):
                try:
                    lines = src_path.read_text(encoding="utf-8").splitlines()
                    start_l, end_l = item.source_line_range
                    snippet = "\n".join(lines[max(0, start_l - 1) : end_l])
                except Exception:
                    snippet = ""

            summary_text = (
                f"Route: {meth} {tmpl} (Handler: {item.handler_name}, Source: {item.source_file}:{item.source_line_range})"
            )
            if snippet:
                summary_text += f"\nCode:\n{snippet}"
            route_summaries.append(summary_text)

        raw_routes_text = "\n\n".join(route_summaries)

        # Pre-flight redaction (C5.2, C5.4)
        scrubbed_content = redact_secrets(raw_routes_text)

        # Quarantine envelope (C1.1, C1.2)
        untrusted = Untrusted(content=scrubbed_content, origin="ast:routes")
        wrapped_prompt, nonce, injection_detected = wrap_quarantined(untrusted)

        system_prompt = registry.get_prompt("builder.route_extract", "v1")

        llm_req = LLMRequest(
            prompt_id="builder.route_extract",
            prompt_version="v1",
            system=system_prompt,
            messages=[Message(role="user", content=wrapped_prompt)],
            response_schema=RouteSemanticBatch,
            trust=TrustLevel.QUARANTINED,
            scan_id=scan_id,
            agent=AgentName.BUILDER,
            budget=CallBudget(),
        )

        enforce_quarantine_discipline(llm_req)

        # Execute completion
        resp = await self._provider.complete(request=llm_req)

        # Record call in ledger
        await self._ledger.record_call(
            request=llm_req,
            response=resp,
            injection_detected=injection_detected,
        )

        # Graceful degradation: if response is malformed, retain deterministic AST attributes
        if resp.parsed and isinstance(resp.parsed, RouteSemanticBatch):
            for semantic_item in resp.parsed.routes:
                key = (semantic_item.route_template, semantic_item.method)
                if key in route_map:
                    target_item = route_map[key]
                    target_item.requires_auth = target_item.requires_auth or semantic_item.requires_auth
                    if semantic_item.resource_owner_param:
                        target_item.resource_owner_param = semantic_item.resource_owner_param
                    if semantic_item.extra_fields_allowed:
                        target_item.extra_fields_allowed = True
                    if semantic_item.is_debug_or_internal:
                        target_item.is_debug_or_internal = True

        # ---------------------------------------------------------------------
        # Step 4: Provision Test Principals
        # ---------------------------------------------------------------------
        principals = provision_test_principals(custom_principals)

        # ---------------------------------------------------------------------
        # Step 5: Final Typed AgentContext
        # ---------------------------------------------------------------------
        final_routes = sorted(route_map.values(), key=lambda r: (r.route_template, r.method))

        auth_schemes = ["bearer_token"] if any(r.requires_auth for r in final_routes) else []

        return AgentContext(
            project_id=project_id,
            scan_id=scan_id,
            routes=final_routes,
            auth_schemes=auth_schemes,
            principals=principals,
            canary_clean=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
