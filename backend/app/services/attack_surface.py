"""
Attack Surface Builder (FEATURES.md F10).
Extracts route nodes and tree hierarchy from Builder inventory, findings, and test cases.
"""
from __future__ import annotations

from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.scoring.posture import _resolve_severity as severity_band

SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "informational": 0,
}


def _worst_severity(severities: list[str]) -> str | None:
    valid = [s.lower() for s in severities if s and s.lower() in SEVERITY_ORDER]
    if not valid:
        return None
    return max(valid, key=lambda s: SEVERITY_ORDER[s])


def build_surface_from_inventory(
    routes: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
    test_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build attack surface tree (nodes and edges) from inventory routes, findings, and test cases.
    """
    findings = findings or []
    test_cases = test_cases or []

    # Map findings by route/path
    findings_by_path: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        f_path = f.get("route_template") or f.get("path")
        if f_path:
            findings_by_path.setdefault(f_path, []).append(f)

    # Map test count by route/path
    tests_by_path: dict[str, int] = {}
    for tc in test_cases:
        tc_path = tc.get("route_template") or (tc.get("request") or {}).get("path") or ""
        # Match normalized path template
        if tc_path:
            tests_by_path[tc_path] = tests_by_path.get(tc_path, 0) + 1

    # Ensure root route exists
    paths_seen: set[str] = set()
    node_map: dict[str, dict[str, Any]] = {}

    # Always ensure "/" root node exists
    paths_seen.add("/")
    node_map["/"] = {
        "id": "node-root",
        "path": "/",
        "methods": [],
        "auth": "public",
        "worst_severity": None,
        "finding_ids": [],
        "tests_run": 0,
    }

    for r in routes:
        path = r.get("route_template") or r.get("path") or "/"
        method = (r.get("method") or "GET").upper()
        requires_auth = bool(r.get("requires_auth"))
        is_debug = bool(r.get("is_debug_or_internal"))
        auth_dep = str(r.get("auth_dependency") or "").lower()

        if is_debug or "admin" in auth_dep:
            auth_level = "admin"
        elif requires_auth:
            auth_level = "login"
        else:
            auth_level = "public"

        if path not in node_map:
            node_map[path] = {
                "id": f"node-{path.strip('/').replace('/', '-').replace('{', '').replace('}', '') or 'root'}",
                "path": path,
                "methods": [method],
                "auth": auth_level,
                "worst_severity": None,
                "finding_ids": [],
                "tests_run": tests_by_path.get(path, 0),
            }
        else:
            if method not in node_map[path]["methods"]:
                node_map[path]["methods"].append(method)
            # Upgrade auth level if higher
            if auth_level == "admin":
                node_map[path]["auth"] = "admin"
            elif auth_level == "login" and node_map[path]["auth"] == "public":
                node_map[path]["auth"] = "login"

        paths_seen.add(path)

    # Attach findings to nodes
    for path, p_findings in findings_by_path.items():
        # Match node by direct path or path parameter normalization
        target_node = node_map.get(path)
        if not target_node:
            for k in node_map:
                if k.split("?")[0] == path.split("?")[0]:
                    target_node = node_map[k]
                    break

        if target_node:
            confirmed_findings = [f for f in p_findings if str(f.get("status", "")).lower() == "confirmed"]
            severities = [severity_band(f) for f in confirmed_findings]
            target_node["worst_severity"] = _worst_severity(severities)
            target_node["finding_ids"] = [f.get("id") for f in p_findings if f.get("id")]

    # Build hierarchical edges by path segments
    nodes = list(node_map.values())
    edges: list[dict[str, str]] = []

    # Sort paths by segment depth
    sorted_paths = sorted([n["path"] for n in nodes if n["path"] != "/"], key=lambda p: (len(p.strip("/").split("/")), p))

    for p in sorted_paths:
        child_id = node_map[p]["id"]
        # Find closest parent prefix
        segments = p.strip("/").split("/")
        parent_found = False
        for i in range(len(segments) - 1, 0, -1):
            parent_candidate = "/" + "/".join(segments[:i])
            if parent_candidate in node_map:
                edges.append({"from": node_map[parent_candidate]["id"], "to": child_id})
                parent_found = True
                break
        if not parent_found:
            edges.append({"from": node_map["/"]["id"], "to": child_id})

    return {
        "nodes": nodes,
        "edges": edges,
    }


async def get_scan_attack_surface(scan_id: str, db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """Retrieve or assemble the attack surface map for a scan."""
    scans_col = db["scans"]
    findings_col = db["findings"]
    test_cases_col = db["test_cases"]

    scan = await scans_col.find_one({"id": scan_id})
    if not scan:
        raise ValueError(f"Scan '{scan_id}' not found.")

    routes = scan.get("routes", [])
    findings = await findings_col.find({"scan_id": scan_id}).to_list(1000)
    test_cases = await test_cases_col.find({"scan_id": scan_id}).to_list(5000)

    # If routes not stored on scan, build from findings and test cases
    if not routes:
        path_set = set()
        for f in findings:
            p = f.get("route_template") or f.get("path")
            if p:
                path_set.add(p)
        for tc in test_cases:
            p = tc.get("route_template") or (tc.get("request") or {}).get("path")
            if p:
                path_set.add(p)

        routes = [{"route_template": p, "method": "GET", "requires_auth": False} for p in path_set]

    surface = build_surface_from_inventory(routes, findings, test_cases)
    surface["scan_id"] = scan_id
    return surface
