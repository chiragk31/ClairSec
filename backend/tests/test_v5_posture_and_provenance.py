"""
Tests for V5 Trust & Score (FEATURES.md F6, F7, F10, PLAN.md V5).

Exit Gates:
- Posture score formula table tests incl. edge cases (no findings + low coverage,
  all fixed, regressed counts against after, inconclusive penalty cap).
- Grep test verifying the string "Secure" (as a verdict) appears nowhere in UI strings
  or backend report templates / phrasebook.
- Provenance endpoint tests (includes oracle record, CVSS vector, and 6-step custody chain).
- Surface builder unit test from fixture inventory (nodes, methods, auth, hierarchy edges).
- Glossary key-parity unit test between Python backend and Dart desktop.
"""
from __future__ import annotations

from pathlib import Path
import re
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from app.core.glossary import get_glossary_keys, GLOSSARY_ENTRIES
from app.scoring.posture import compute_posture, POSTURE_VERSION
from app.services.attack_surface import build_surface_from_inventory
from app.services.provenance_service import assemble_finding_provenance


# ── 1. Posture Score Formula Table Tests (F6) ──────────────────────────────────

def test_posture_score_formula_table_cases():
    """
    Test CVSS band penalties and posture scoring formula:
      critical: 30, high: 18, medium: 9, low: 3, informational: 0.
      inconclusive: 2 each, capped at 10 total.
      grade: A >= 90, B >= 80, C >= 70, D >= 55, F < 55.
    """
    # Case 1: 1 critical + 1 high confirmed finding
    # Penalties: 30 + 18 = 48. Score before = 100 - 48 = 52 (Grade F, since < 55)
    findings = [
        {"id": "f1", "status": "confirmed", "severity": "critical", "category": "INJECTION"},
        {"id": "f2", "status": "confirmed", "severity": "high", "category": "BOLA"},
    ]
    test_cases = [{"category": "INJECTION"}, {"category": "BOLA"}, {"category": "BROKEN_AUTH"}, {"category": "BFLA"}]
    posture = compute_posture(findings=findings, test_cases=test_cases, categories_applicable=8)
    assert posture["version"] == POSTURE_VERSION
    assert posture["before"] == 52
    assert posture["grade_before"] == "F"
    assert posture["coverage"] == 0.5  # 4 of 8 categories tested
    assert posture["limited_coverage"] is False

    # Case 2: All findings fixed
    # score_after must be 100 and Grade A
    findings_fixed = [
        {"id": "f1", "status": "confirmed", "severity": "critical", "verification_outcome": "fixed", "category": "INJECTION"},
        {"id": "f2", "status": "confirmed", "severity": "high", "verification_outcome": "fixed", "category": "BOLA"},
    ]
    posture_fixed = compute_posture(findings=findings_fixed, test_cases=test_cases, categories_applicable=8)
    assert posture_fixed["before"] == 52
    assert posture_fixed["after"] == 100
    assert posture_fixed["grade_after"] == "A"

    # Case 3: Regressed finding still counts against score_after
    findings_regressed = [
        {"id": "f1", "status": "confirmed", "severity": "critical", "verification_outcome": "fixed", "category": "INJECTION"},
        {"id": "f2", "status": "confirmed", "severity": "high", "verification_outcome": "regressed", "category": "BOLA"},
    ]
    posture_reg = compute_posture(findings=findings_regressed, test_cases=test_cases, categories_applicable=8)
    assert posture_reg["before"] == 52
    assert posture_reg["after"] == 82  # 100 - 18
    assert posture_reg["grade_after"] == "B"

    # Case 4: Inconclusive cap (10 inconclusive findings -> capped at 10 penalty, not 20)
    inconclusive_findings = [
        {"id": f"inc-{i}", "status": "inconclusive", "category": "BROKEN_AUTH"}
        for i in range(10)
    ]
    posture_inc = compute_posture(findings=inconclusive_findings, test_cases=[], categories_applicable=8)
    assert posture_inc["inputs"]["inconclusive_count"] == 10
    assert posture_inc["inputs"]["inconclusive_penalty"] == 10
    assert posture_inc["before"] == 90
    assert posture_inc["grade_before"] == "A"

    # Case 5: No findings + low coverage (< 50%) -> limited_coverage flag True
    posture_low_cov = compute_posture(findings=[], test_cases=[{"category": "BOLA"}], categories_applicable=8)
    assert posture_low_cov["before"] == 100
    assert posture_low_cov["coverage"] == 0.12  # 1/8
    assert posture_low_cov["limited_coverage"] is True

    # Case 6: Grade threshold D >= 55
    findings_d = [
        {"id": "f1", "status": "confirmed", "severity": "critical", "category": "INJECTION"},  # -30
        {"id": "f2", "status": "confirmed", "severity": "medium", "category": "BOLA"},         # -9
        {"id": "f3", "status": "inconclusive", "category": "BFLA"},                            # -2
        {"id": "f4", "status": "inconclusive", "category": "BROKEN_AUTH"},                     # -2
        # Total penalty: 43 -> score 57 -> Grade D
    ]
    posture_d = compute_posture(findings=findings_d, test_cases=test_cases, categories_applicable=8)
    assert posture_d["before"] == 57
    assert posture_d["grade_before"] == "D"


# ── 2. Grep Test for "Secure" Prohibition ──────────────────────────────────────

def test_grep_prohibits_secure_as_verdict_or_status():
    """
    Exit Gate: The word "Secure" must NEVER appear as a verdict, status, or report outcome.
    A zero-finding scan does not mean the app is "Secure"; it means no tested vulnerabilities were confirmed.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    desktop_lib = repo_root / "desktop" / "lib"
    backend_app = repo_root / "backend" / "app"

    forbidden_patterns = [
        re.compile(r'["\']status["\']\s*:\s*["\']secure["\']', re.IGNORECASE),
        re.compile(r'["\']verdict["\']\s*:\s*["\']secure["\']', re.IGNORECASE),
        re.compile(r'outcome\s*==\s*["\']secure["\']', re.IGNORECASE),
        re.compile(r'label\s*:\s*["\']secure["\']', re.IGNORECASE),
        re.compile(r'grade\s*:\s*["\']secure["\']', re.IGNORECASE),
        re.compile(r'verdict\s*:\s*["\']secure["\']', re.IGNORECASE),
    ]

    violations = []

    # Check desktop dart files
    if desktop_lib.exists():
        for dart_file in desktop_lib.rglob("*.dart"):
            # Exclude tests and fixtures
            if "test" in str(dart_file) or "fixtures" in str(dart_file):
                continue
            text = dart_file.read_text(encoding="utf-8", errors="ignore")
            for pat in forbidden_patterns:
                if pat.search(text):
                    violations.append(f"{dart_file}: matches forbidden pattern {pat.pattern}")

    # Check backend python files
    if backend_app.exists():
        for py_file in backend_app.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for pat in forbidden_patterns:
                if pat.search(text):
                    violations.append(f"{py_file}: matches forbidden pattern {pat.pattern}")

    assert not violations, f"Forbidden 'Secure' verdict found in codebase:\n" + "\n".join(violations)


# ── 3. Provenance Endpoint Unit Tests (F7) ────────────────────────────────────

@pytest.mark.asyncio
async def test_provenance_built_from_real_record_shapes():
    """
    Provenance for a confirmed finding reads the REAL stored shapes (EvaluatedFinding,
    TestCase with oracle_result, captured response evidence) — fixtures are built from
    the Pydantic models so they cannot drift from what the pipeline actually stores.
    """
    from mongomock_motor import AsyncMongoMockClient

    from app.agents.attacker.schemas import TestCaseRecord as TestCase
    from app.agents.evaluator.schemas import (
        ConfidenceInputs, ConfidenceLevel, ConfidenceResult, CvssInputs, CvssResult,
        EvaluatedFinding, SeverityBand,
    )

    db = AsyncMongoMockClient()["prov"]
    scan_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
    tc = TestCase(
        scan_id=scan_id, category="BOLA", route_template="/documents/{doc_id}", method="GET",
        request={"method": "GET", "path": "/documents/2"},
        response={"status": 200, "headers": {}, "body": "{}", "elapsed_ms": 15.2, "truncated": False},
        oracle_result={"fired": True, "rule_id": "ORACLE-BOLA-01",
                       "rationale": "Object owned by user B accessed by user A"},
    )
    finding = EvaluatedFinding(
        scan_id=scan_id, project_id=project_id, title="BOLA on documents", category="BOLA",
        cwe=["CWE-639"], route_template="/documents/{doc_id}", method="GET",
        description="d", impact="i", runtime_confirmed=True, oracle_rule_id="ORACLE-BOLA-01",
        cvss=CvssResult(inputs=CvssInputs(), vector_string="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
                        base_score=8.1, severity=SeverityBand.HIGH),
        confidence=ConfidenceResult(
            inputs=ConfidenceInputs(runtime_confirmed=True, oracle_fired=True,
                                    reproduced_n_times=3, evidence_complete=True),
            band=ConfidenceLevel.HIGH, score=0.9),
        evidence_ids=[tc.id],
    )
    await db.test_cases.insert_one(tc.model_dump(mode="json"))
    await db.findings.insert_one(finding.model_dump(mode="json"))
    await db.verification_results.insert_one({"id": "ver-1", "finding_id": finding.id, "outcome": "fixed",
                                              "outcome_reason": "exploit blocked; suite 6/6"})

    prov = await assemble_finding_provenance(finding_id=finding.id, db=db)
    assert prov["has_oracle_evidence"] is True
    assert prov["lane"] == "confirmed"
    assert prov["badge"] == "Runtime-confirmed · oracle-verified"
    steps = prov["steps"]
    assert len(steps) == 6
    assert steps[0]["who"] == "AI proposal"
    assert steps[1]["title"] == "HTTP 200" and "15 ms" in steps[1]["detail"]
    assert steps[2]["title"] == "Oracle ORACLE-BOLA-01 fired"
    assert steps[3]["title"] == "Reproduced 3 time(s)"
    assert steps[4]["title"] == "CVSS 8.1 (HIGH)" and "AV:N" in steps[4]["detail"]
    assert steps[5]["title"] == "Fix status: Fixed"


@pytest.mark.asyncio
async def test_provenance_never_invents_missing_evidence():
    """Missing records produce 'not recorded' — never a default 200 / 3/3 / CVSS 7.5 / 'fired'."""
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["prov2"]
    await db.findings.insert_one({"id": "f-bare", "scan_id": "s", "category": "BOLA", "status": "confirmed"})
    prov = await assemble_finding_provenance(finding_id="f-bare", db=db)
    text = " ".join(f"{s['title']} {s['detail']}" for s in prov["steps"])
    for invented in ("HTTP 200", "3/3", "7.5", "fired", "AV:N/AC:L"):
        assert invented not in text, (invented, text)
    assert "not recorded" in text
    # No oracle record ⇒ never the confirmed badge, even if status says confirmed.
    assert prov["badge"] == "Source suspicion — not confirmed"
    assert prov["lane"] == "candidates"


# ── 4. Attack Surface Builder Unit Test (F10) ──────────────────────────────────

def test_attack_surface_builder_unit():
    """
    Test: Attack-surface builder constructs tree nodes with methods, auth levels,
    worst severity, and hierarchical edges.
    """
    routes = [
        {"route_template": "/", "method": "GET", "requires_auth": False},
        {"route_template": "/users", "method": "GET", "requires_auth": True},
        {"route_template": "/users", "method": "POST", "requires_auth": True},
        {"route_template": "/users/{id}", "method": "GET", "requires_auth": True},
        {"route_template": "/admin/metrics", "method": "GET", "requires_auth": True, "auth_dependency": "get_admin_user"},
    ]
    findings = [
        {"route_template": "/users/{id}", "status": "confirmed", "severity": "high", "id": "f-1"},
    ]
    test_cases = [
        {"route_template": "/users/{id}", "id": "tc-1"},
    ]

    surface = build_surface_from_inventory(routes=routes, findings=findings, test_cases=test_cases)
    nodes = {n["path"]: n for n in surface["nodes"]}
    edges = surface["edges"]

    # Assert nodes
    assert "/" in nodes
    assert "/users" in nodes
    assert "/users/{id}" in nodes
    assert "/admin/metrics" in nodes

    # Assert methods
    assert "GET" in nodes["/users"]["methods"]
    assert "POST" in nodes["/users"]["methods"]

    # Assert auth level
    assert nodes["/"]["auth"] == "public"
    assert nodes["/users"]["auth"] == "login"
    assert nodes["/admin/metrics"]["auth"] == "admin"

    # Assert worst severity on /users/{id}
    assert nodes["/users/{id}"]["worst_severity"] == "high"
    assert "f-1" in nodes["/users/{id}"]["finding_ids"]

    # Assert edges
    # There should be an edge from root to /users and /admin/metrics
    assert any(e["to"] == nodes["/users"]["id"] for e in edges)
    # Edge from /users to /users/{id}
    assert any(e["from"] == nodes["/users"]["id"] and e["to"] == nodes["/users/{id}"]["id"] for e in edges)


# ── 5. Glossary Key Parity Unit Test (F6, F7, §9) ──────────────────────────────

def test_glossary_key_parity_python_and_dart():
    """
    Exit Gate: Verify exact key parity between Python backend glossary
    (backend/app/core/glossary.py) and Dart frontend glossary (desktop/lib/core/glossary/glossary.dart).
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    dart_glossary_path = repo_root / "desktop" / "lib" / "core" / "glossary" / "glossary.dart"
    assert dart_glossary_path.exists(), f"Dart glossary file missing: {dart_glossary_path}"

    dart_content = dart_glossary_path.read_text(encoding="utf-8")
    # Extract keys like 'builder_agent': GlossaryEntry(
    dart_keys = set(re.findall(r"'([a-zA-Z0-9_]+)':\s*GlossaryEntry\(", dart_content))

    python_keys = set(get_glossary_keys())

    assert len(python_keys) == 20, f"Expected 20 glossary keys, got {len(python_keys)}"
    assert dart_keys == python_keys, (
        f"Glossary key mismatch between Python and Dart:\n"
        f"In Python only: {python_keys - dart_keys}\n"
        f"In Dart only: {dart_keys - python_keys}"
    )
