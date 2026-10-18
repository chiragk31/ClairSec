"""
V6 / F9: the three proofs behind "Fix verified".

1. Exploit blocked      — existing retester (covered in test_verifier_agent.py)
2. App still works      — fixture suite, or auto-generated smoke suite vs baseline
3. Endpoint preserved   — static route table of the patched workspace

These run the real verifier against the real vulnerable fixture on the trusted
host handle (Docker unavailable here); nothing inside the verifier is mocked.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.agents.evaluator.repository import FindingRepository
from app.agents.fixer.schemas import FileDiff, PatchRecord, PatchValidation
from app.agents.verifier.endpoint_check import check_endpoint_preserved
from app.agents.verifier.schemas import VerificationOutcome
from app.agents.verifier.smoke_suite import SmokeBaseline, SmokeCase, cases_from_openapi, compare
from app.agents.verifier.verifier import VerifierAgent
from app.database.models import ProjectRecord
from app.isolation.workspace import WorkspaceManager

FIXTURES = Path(__file__).parent / "fixtures"
VULN = FIXTURES / "vulnerable_fastapi_app"


# ── smoke suite logic (pure) ──────────────────────────────────────────────────


def _baseline(statuses: dict[str, int | None]) -> SmokeBaseline:
    cases = [SmokeCase(id=k, route_template=k.split(" ", 1)[1], path=k.split(" ", 1)[1]) for k in statuses]
    return SmokeBaseline(cases=cases, statuses=statuses)


def test_smoke_cases_are_read_only_and_deterministic():
    spec = {"paths": {
        "/items/{item_id}": {"get": {"parameters": [{"name": "item_id", "in": "path", "schema": {"example": 7}}]},
                             "delete": {}},
        "/health": {"get": {}},
        "/users": {"post": {}},
    }}
    cases = cases_from_openapi(spec)
    assert [c.id for c in cases] == ["GET /health", "GET /items/{item_id}"]
    assert cases[1].path == "/items/7"
    assert cases_from_openapi(spec) == cases


def test_smoke_compare_detects_regressions_and_ignores_the_fixed_route():
    base = _baseline({"GET /health": 200, "GET /items": 200, "GET /docs/{id}": 200, "GET /broken": 404})
    after = {"GET /health": 200, "GET /items": 500, "GET /docs/{id}": 403, "GET /broken": 404}
    res = compare(base, after, exclude_route=("/docs/{id}", "GET"))
    assert res.ran and res.source == "auto_smoke"
    assert res.total == 2  # /health and /items (the fixed route and the already-broken one are excluded)
    assert res.failed == 1 and "GET /items" in res.newly_failing[0]


def test_smoke_compare_with_nothing_working_before_is_not_a_pass():
    res = compare(_baseline({"GET /a": 404}), {"GET /a": 404})
    assert res.ran is False and res.total == 0


# ── endpoint preserved (static) ───────────────────────────────────────────────


def test_endpoint_check_detects_deleted_route(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/documents/{document_id}')\ndef d(document_id: str):\n    return {}\n"
    )
    ok = check_endpoint_preserved(tmp_path, "/documents/{doc_id}", "GET")
    assert ok.ran and ok.preserved  # renamed parameter still counts as the same endpoint
    gone = check_endpoint_preserved(tmp_path, "/documents/{doc_id}", "DELETE")
    assert gone.ran and not gone.preserved


# ── verifier integration on the real fixture ─────────────────────────────────


async def _setup(tmp_path: Path, mutate):
    scan_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
    ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
    ws.create_scan_workspace(project_id, str(VULN))
    mod_ws = ws.create_modified_workspace(project_id)
    mutate(mod_ws / "main.py")
    from tests.test_verifier_agent import _make_dummy_finding  # same finding shape as Phase 8 tests

    finding = await FindingRepository().create(_make_dummy_finding(
        scan_id=scan_id, project_id=project_id, category="BOLA",
        route_template="/documents/{doc_id}", method="GET", oracle_rule_id="ORACLE_BOLA_001",
    ))
    patch = PatchRecord(
        id=str(uuid.uuid4()), finding_id=finding.id, scan_id=scan_id, project_id=project_id,
        files=[FileDiff(path="main.py", diff="--- test")], applied=True,
        applied_at="2026-10-18T00:00:00Z", workspace="modified",
        validation=PatchValidation(ast_parsed=True, path_check_passed=True, size_ok=True),
    )
    project = ProjectRecord(id=project_id, name="v", source_path=str(VULN), entry_point="main.py",
                            origin="demo_fixture")
    return VerifierAgent(workspace_manager=ws, provider_name="mock"), finding, patch, scan_id, mod_ws, project


@pytest.mark.asyncio
async def test_delete_the_route_patch_is_regressed_by_endpoint_proof(tmp_path: Path):
    """Removing the vulnerable route 'blocks' the exploit — the third proof must reject it."""
    def delete_route(main: Path):
        src = main.read_text(encoding="utf-8")
        src = src.replace('@app.get("/documents/{doc_id}"', '@app.get("/documents-removed/{doc_id}"')
        main.write_text(src, encoding="utf-8")

    verifier, finding, patch, scan_id, mod_ws, project = await _setup(tmp_path, delete_route)
    rec = await verifier.verify_finding(finding=finding, patch=patch, scan_id=scan_id,
                                        modified_workspace=mod_ws, project=project)
    assert rec.endpoint_preserved.ran is True
    assert rec.endpoint_preserved.preserved is False
    assert rec.outcome in (VerificationOutcome.REGRESSED,), rec.outcome_reason
    assert rec.outcome != VerificationOutcome.FIXED


@pytest.mark.asyncio
async def test_user_project_without_baseline_is_never_fixed(tmp_path: Path, monkeypatch):
    """No runnable suite and no baseline → 'unverified', never 'fixed' (dual criterion)."""
    verifier, finding, patch, scan_id, mod_ws, project = await _setup(tmp_path, lambda p: None)
    # Treat the project as a user project for suite selection, while the target stays the fixture.
    user_like = project.model_copy(update={"source_path": str(tmp_path / "user_src")})
    res = await verifier._run_functional_check(handle=None, finding=finding, project=user_like,
                                               functional_baseline=None)
    assert res.ran is False and res.source == "none"


def test_smoke_compare_ignores_routes_fixed_by_other_patches_in_the_scan():
    """Found in the live Docker run: all patches share one workspace, so the misconfig fix
    (GET /debug/config 200 -> 401) was wrongly counted as a regression of the BOLA fix."""
    base = _baseline({"GET /health": 200, "GET /debug/config": 200, "GET /documents/{doc_id}": 200})
    after = {"GET /health": 200, "GET /debug/config": 401, "GET /documents/{doc_id}": 403}
    scan_routes = [("/documents/{doc_id}", "GET"), ("/debug/config", "GET")]
    res = compare(base, after, exclude_route=("/documents/{doc_id}", "GET"), exclude_routes=scan_routes)
    assert res.ran and res.failed == 0 and res.total == 1
    # Without the scan-wide exclusion the same data would be a (false) regression.
    assert compare(base, after, exclude_route=("/documents/{doc_id}", "GET")).failed == 1
