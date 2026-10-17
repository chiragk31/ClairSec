"""
Runtime /openapi.json extractor querying target via TargetHandle (Step 2 of analysis).
"""
from __future__ import annotations

from typing import Any
import httpx

from app.agents.builder.schemas import RouteItem
from app.agents.builder.ast_extractor import normalize_route_template


async def extract_openapi_schema(base_url: str) -> dict[str, Any] | None:
    """Fetch /openapi.json from the running target container or local fixture."""
    url = f"{base_url.rstrip('/')}/openapi.json"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


def parse_openapi_routes(openapi_dict: dict[str, Any]) -> list[RouteItem]:
    """Convert openapi.json paths and operations into normalized RouteItem records with test plans."""
    routes: list[RouteItem] = []
    paths = openapi_dict.get("paths", {})

    for raw_path, path_item in paths.items():
        route_template = normalize_route_template(raw_path)
        path_level_params = path_item.get("parameters", [])

        for method_name, op in path_item.items():
            if method_name.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue

            method = method_name.upper()
            op_id = op.get("operationId", f"{method.lower()}_{route_template.replace('/', '_')}")
            security = op.get("security", path_item.get("security", []))
            requires_auth = len(security) > 0 or "admin" in route_template.lower()

            # Merge path-level and operation-level parameters
            all_params = list(path_level_params) + list(op.get("parameters", []))
            input_fields = [p.get("name") for p in all_params if "name" in p]

            path_params = [
                {
                    "name": p.get("name"),
                    "type": (p.get("schema") or {}).get("type", "string"),
                    "required": p.get("required", True),
                }
                for p in all_params
                if p.get("in") == "path" and "name" in p
            ]

            # If path template has {param} but openapi didn't declare it in parameters
            import re
            template_placeholders = re.findall(r"\{([^}:]+)(?::[^}]+)?\}", route_template)
            existing_param_names = {p["name"] for p in path_params}
            for ph in template_placeholders:
                if ph not in existing_param_names:
                    path_params.append({"name": ph, "type": "string", "required": True})

            query_params = [
                {
                    "name": p.get("name"),
                    "type": (p.get("schema") or {}).get("type", "string"),
                    "required": p.get("required", False),
                }
                for p in all_params
                if p.get("in") == "query" and "name" in p
            ]

            # Request body schema
            req_body = op.get("requestBody", {})
            content = req_body.get("content", {})
            json_content = content.get("application/json", {})
            body_schema = json_content.get("schema")
            content_type = "application/json" if json_content else "application/json"

            owner_param = None
            for p in ("user_id", "owner_id", "doc_id", "id", "account_id"):
                if f"{{{p}}}" in route_template or any(pp["name"] == p for pp in path_params):
                    owner_param = p
                    break

            is_debug = "debug" in route_template.lower() or "config" in route_template.lower()

            # Determine applicable test categories
            applicable_categories: list[str] = []
            tmpl_lower = route_template.lower()

            if path_params:
                if any(k in tmpl_lower for k in ("doc", "user", "item", "order", "note", "account")):
                    applicable_categories.append("BOLA")
                if "file" in tmpl_lower or "download" in tmpl_lower:
                    applicable_categories.append("PATH_TRAVERSAL")
                if "admin" in tmpl_lower:
                    applicable_categories.append("BFLA")

            if "admin" in tmpl_lower and "BFLA" not in applicable_categories:
                applicable_categories.append("BFLA")

            if method in ("PUT", "POST", "PATCH") and (
                "profile" in tmpl_lower or "user" in tmpl_lower or "account" in tmpl_lower or body_schema
            ):
                applicable_categories.append("BOPLA_MASS_ASSIGN")

            if is_debug or tmpl_lower in ("/", "/health", "/docs", "/openapi.json"):
                applicable_categories.append("SECURITY_MISCONFIG")

            if any(qp["name"].lower() in ("q", "query", "search", "filter", "username", "name") for qp in query_params):
                applicable_categories.append("SQL_INJECTION")

            if "tool" in tmpl_lower or "ping" in tmpl_lower or "exec" in tmpl_lower:
                applicable_categories.append("COMMAND_INJECTION")

            can_gen = True
            skip_reason = None
            if not applicable_categories and not path_params:
                # Can still test security misconfig (CORS, headers)
                applicable_categories.append("SECURITY_MISCONFIG")

            routes.append(
                RouteItem(
                    route_template=route_template,
                    method=method,
                    handler_name=op_id,
                    source_file="",
                    source_line_range=(0, 0),
                    requires_auth=requires_auth,
                    resource_owner_param=owner_param,
                    input_fields=input_fields,
                    is_debug_or_internal=is_debug,
                    path_params=path_params,
                    query_params=query_params,
                    request_body_schema=body_schema,
                    request_body_content_type=content_type,
                    security_requirements=security if isinstance(security, list) else [],
                    operation_id=op_id,
                    applicable_categories=applicable_categories,
                    can_generate_test=can_gen,
                    skip_reason=skip_reason,
                )
            )

    routes.sort(key=lambda r: (r.route_template, r.method))
    return routes
