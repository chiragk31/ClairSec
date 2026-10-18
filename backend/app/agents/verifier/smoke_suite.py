"""
Auto-generated functional smoke suite (FEATURES.md F9, "App still works").

Real-world projects rarely ship a test suite ClairSec can run, and the demo
fixture's hand-written suite is meaningless against them. This module builds a
deterministic, read-only check set from the target's own OpenAPI schema:

  * only GET operations (non-destructive policy, RULES.md / SECURITY.md section 6),
  * path parameters filled from schema examples/defaults, else a fixed "1",
  * recorded once against the ORIGINAL target (the baseline) and replayed
    against the PATCHED target.

A regression is a case that answered 2xx/3xx before the fix and does not now, or
any case that newly answers 5xx. The finding's own route is excluded: changing
that route's behaviour is the point of the fix. Labelled "auto-generated" in the
UI and reports because it is a weaker guarantee than a real test suite.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.agents.builder.ast_extractor import normalize_route_template
from app.agents.verifier.schemas import FunctionalSuiteResult
from app.security.http_client import ScopeLockedHttpClient

logger = logging.getLogger(__name__)

MAX_CASES = 40
_PARAM = re.compile(r"\{([^}/]+)\}")


class SmokeCase(BaseModel):
    id: str
    method: str = "GET"
    route_template: str
    path: str


class SmokeBaseline(BaseModel):
    """Pre-fix observations: case id -> HTTP status (None = transport error)."""

    cases: list[SmokeCase] = Field(default_factory=list)
    statuses: dict[str, int | None] = Field(default_factory=dict)


def _example_for(param: dict[str, Any]) -> str:
    schema = param.get("schema") or {}
    for key in ("example", "default"):
        if param.get(key) is not None:
            return str(param[key])
        if schema.get(key) is not None:
            return str(schema[key])
    if schema.get("enum"):
        return str(schema["enum"][0])
    return "1"


def cases_from_openapi(spec: dict[str, Any]) -> list[SmokeCase]:
    """Deterministically derive read-only smoke cases from an OpenAPI document."""
    cases: list[SmokeCase] = []
    for raw_path in sorted((spec.get("paths") or {}).keys()):
        item = spec["paths"][raw_path] or {}
        op = item.get("get")
        if not isinstance(op, dict):
            continue
        params = {
            p.get("name"): p
            for p in [*(item.get("parameters") or []), *(op.get("parameters") or [])]
            if isinstance(p, dict) and p.get("in") == "path"
        }
        concrete = _PARAM.sub(lambda m: _example_for(params.get(m.group(1), {})), raw_path)
        template = normalize_route_template(raw_path)
        cases.append(SmokeCase(id=f"GET {template}", route_template=template, path=concrete))
        if len(cases) >= MAX_CASES:
            break
    return cases


async def _observe(base_url: str, cases: list[SmokeCase]) -> dict[str, int | None]:
    statuses: dict[str, int | None] = {}
    async with ScopeLockedHttpClient(base_url=base_url) as client:
        for case in cases:
            try:
                resp = await client.request(method="GET", url=case.path)
                statuses[case.id] = resp.status_code
            except Exception as exc:  # noqa: BLE001 - a dead target is data, not a crash
                logger.debug("Smoke case %s failed: %s", case.id, exc)
                statuses[case.id] = None
    return statuses


async def record_baseline(base_url: str) -> SmokeBaseline | None:
    """Fetch /openapi.json from the ORIGINAL target and record every case's status."""
    try:
        async with ScopeLockedHttpClient(base_url=base_url) as client:
            resp = await client.request(method="GET", url="/openapi.json")
            if resp.status_code != 200:
                return None
            spec = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.info("No OpenAPI schema for smoke baseline: %s", exc)
        return None
    cases = cases_from_openapi(spec)
    if not cases:
        return None
    return SmokeBaseline(cases=cases, statuses=await _observe(base_url, cases))


def _ok(status: int | None) -> bool:
    return status is not None and 200 <= status < 400


def compare(
    baseline: SmokeBaseline,
    after: dict[str, int | None],
    exclude_route: tuple[str, str] | None = None,
    exclude_routes: list[tuple[str, str]] | None = None,
) -> FunctionalSuiteResult:
    """
    Pure comparison of baseline vs post-fix observations (unit-testable).

    Every route fixed in this scan is excluded: all patches live in one modified
    workspace, so a route another fix deliberately locked down (e.g. /debug/config
    now 401) must not count as a regression of this fix. Those routes are judged
    by their own exploit re-tests.
    """
    excluded_ids = {
        f"{m.upper()} {normalize_route_template(r)}"
        for r, m in ([exclude_route] if exclude_route else []) + list(exclude_routes or [])
    }
    considered = [c for c in baseline.cases if c.id not in excluded_ids and _ok(baseline.statuses.get(c.id))]
    newly_failing: list[str] = []
    for c in considered:
        now = after.get(c.id)
        if not _ok(now):
            newly_failing.append(f"{c.id} ({baseline.statuses.get(c.id)} -> {now})")
    # A brand-new server error anywhere is also a regression.
    for c in baseline.cases:
        before, now = baseline.statuses.get(c.id), after.get(c.id)
        if c.id not in excluded_ids and now is not None and now >= 500 and (before is None or before < 500):
            label = f"{c.id} ({before} -> {now})"
            if label not in newly_failing:
                newly_failing.append(label)
    total = len(considered)
    if total == 0:
        return FunctionalSuiteResult(
            ran=False,
            total=0,
            source="auto_smoke",
            detail="No read-only endpoint answered successfully before the fix, so there is nothing to compare.",
        )
    failed = len(newly_failing)
    return FunctionalSuiteResult(
        ran=True,
        passed=max(0, total - failed),
        failed=failed,
        total=total,
        newly_failing=newly_failing,
        source="auto_smoke",
        detail=f"{total} auto-generated read-only checks from the app's OpenAPI schema.",
    )


async def run_against(
    base_url: str,
    baseline: SmokeBaseline,
    exclude_route: tuple[str, str] | None = None,
    exclude_routes: list[tuple[str, str]] | None = None,
) -> FunctionalSuiteResult:
    return compare(baseline, await _observe(base_url, baseline.cases), exclude_route, exclude_routes)
