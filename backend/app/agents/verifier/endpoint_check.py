"""
Third proof (FEATURES.md F9): "Endpoint preserved".

A patch that deletes or renames the vulnerable route blocks the exploit
perfectly and may slip past a thin functional suite. This check reads the
patched workspace's route table with the same static AST extractor the Builder
uses and requires the finding's route + method to still be there.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.agents.builder.ast_extractor import extract_routes_from_project, normalize_route_template
from app.agents.verifier.schemas import EndpointPreservedResult


def _shape(template: str) -> str:
    """Compare templates by shape so a renamed path parameter still matches."""
    return re.sub(r"\{[^}/]+\}", "{}", normalize_route_template(template))


def check_endpoint_preserved(workspace: Path, route_template: str, method: str) -> EndpointPreservedResult:
    method = (method or "").upper()
    try:
        routes = extract_routes_from_project(workspace)
    except Exception as exc:  # noqa: BLE001
        return EndpointPreservedResult(
            ran=False, route=route_template, method=method,
            detail=f"Could not read routes from the patched code: {exc}",
        )
    if not routes:
        return EndpointPreservedResult(
            ran=False, route=route_template, method=method,
            detail="No routes could be extracted statically from the patched code.",
        )
    wanted = _shape(route_template)
    present = any(_shape(r.route_template) == wanted and r.method.upper() == method for r in routes)
    return EndpointPreservedResult(
        ran=True,
        preserved=present,
        route=route_template,
        method=method,
        detail=(
            f"{method} {route_template} is still defined in the patched code."
            if present
            else f"{method} {route_template} no longer exists in the patched code: the fix removed the endpoint."
        ),
    )
