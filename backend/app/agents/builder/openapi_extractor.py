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
    """Convert openapi.json paths and operations into normalized RouteItem records."""
    routes: list[RouteItem] = []
    paths = openapi_dict.get("paths", {})

    for raw_path, path_item in paths.items():
        route_template = normalize_route_template(raw_path)
        for method_name, op in path_item.items():
            if method_name.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue

            method = method_name.upper()
            op_id = op.get("operationId", f"{method.lower()}_{route_template.replace('/', '_')}")
            security = op.get("security", [])
            requires_auth = len(security) > 0

            # Extract parameter names
            params = op.get("parameters", [])
            input_fields = [p.get("name") for p in params if "name" in p]

            owner_param = None
            for p in ("user_id", "owner_id", "doc_id"):
                if f"{{{p}}}" in route_template:
                    owner_param = p
                    break

            is_debug = "debug" in route_template.lower() or "config" in route_template.lower()

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
                )
            )

    routes.sort(key=lambda r: (r.route_template, r.method))
    return routes
