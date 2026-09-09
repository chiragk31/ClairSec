"""
Integration and exit gate tests for Phase 6 Evaluator Agent.
(PHASES.md Phase 6, METHODOLOGY.md §4 & §9, DATA_MODEL.md §3, RULES.md §2).

EXIT GATE CRITERIA:
1. All three seeded vulnerabilities in vulnerable_fastapi_app reach `confirmed` with runtime evidence attached.
2. Zero findings from secure_fastapi_app reach `confirmed` (FP = 0).
3. Severity is reproducible from the stored CVSS inputs alone (proves the rubric isn't a black box).
4. Adversarial test: fabricated candidate finding (inconsistent evidence) is rejected with reason, not waved through.
5. Inconclusive on reproduction failure: candidates that fail to reproduce become inconclusive, never confirmed.
6. Duplicate detection: duplicate candidates in scan scope are rejected with duplicate_of populated.
"""
from __future__ import annotations

import uuid
from pathlib import Path
import pytest

from app.agents.attacker.attacker import AttackerAgent
from app.agents.attacker.repository import TestCaseRepository
from app.agents.attacker.schemas import CandidateFinding, TestCaseRecord
from app.agents.builder.builder import BuilderAgent
from app.agents.evaluator.cvss_scorer import calculate_cvss_score
from app.agents.evaluator.evaluator import EvaluatorAgent
from app.agents.evaluator.repository import FindingRepository
from app.agents.evaluator.schemas import (
    ConfidenceLevel,
    EvaluationStatus,
    EvaluatorEvidence,
    SeverityBand,
)
from app.targets.handle import LocalFixtureTargetHandle

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VULN_FIXTURE = FIXTURES_DIR / "vulnerable_fastapi_app"
SECURE_FIXTURE = FIXTURES_DIR / "secure_fastapi_app"


@pytest.mark.asyncio
async def test_evaluator_confirms_all_three_seeded_vulns_in_vulnerable_app():
    """
    Phase 6 Exit Gate: Evaluator independently reproduces and confirms all 3 seeded
    vulnerabilities in vulnerable_fastapi_app with runtime evidence attached.
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        # Step 1: Builder extracts context
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="vulnerable_fastapi_app",
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        # Step 2: Attacker generates candidates
        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_result = await attacker.run_scan(
            context=context,
            target_handle=handle,
        )
        assert len(attacker_result.findings) == 3

        # Step 3: Evaluator evaluates candidates independently
        finding_repo = FindingRepository()
        evaluator = EvaluatorAgent(
            test_case_repo=test_case_repo,
            finding_repo=finding_repo,
        )
        eval_result = await evaluator.evaluate_scan(
            candidates=attacker_result.findings,
            target_handle=handle,
            scan_id=scan_id,
        )

        # Exit gate counts
        assert eval_result.confirmed_count == 3, f"Expected 3 confirmed findings, got {eval_result.confirmed_count}"
        assert eval_result.rejected_count == 0, f"Expected 0 rejected findings, got {eval_result.rejected_count}"
        assert eval_result.inconclusive_count == 0, f"Expected 0 inconclusive findings, got {eval_result.inconclusive_count}"
        assert len(eval_result.findings) == 3

        # Verify each finding has confirmed status, runtime evidence, and valid CVSS
        categories = set()
        for f in eval_result.findings:
            categories.add(f.category)
            assert f.status == EvaluationStatus.CONFIRMED
            assert f.status_reason == "reproduced_and_verified"
            assert f.runtime_confirmed is True
            assert len(f.evidence_ids) >= 1, "Finding must have runtime evidence IDs attached"
            assert f.cvss.base_score > 0.0, "CVSS base score must be strictly positive"
            assert f.cvss.severity in (SeverityBand.MEDIUM, SeverityBand.HIGH, SeverityBand.CRITICAL)
            assert f.confidence.band == ConfidenceLevel.HIGH
            assert f.confidence.score == 1.0
            assert f.route_template.startswith("/")
            # Check provenance
            assert f.agent_provenance.get("evaluated_by") == "evaluator"
            assert f.agent_provenance.get("proposed_by") == "attacker"

        assert categories == {"BOLA", "BOPLA_MASS_ASSIGN", "SECURITY_MISCONFIG"}

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_evaluator_zero_findings_confirmed_on_secure_app():
    """
    Phase 6 Exit Gate: Evaluator confirms 0 findings against secure_fastapi_app (FP = 0).
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=SECURE_FIXTURE)
    await handle.start()

    try:
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="secure_fastapi_app",
            scan_id=scan_id,
            project_dir=SECURE_FIXTURE,
            target_handle=handle,
        )

        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_result = await attacker.run_scan(
            context=context,
            target_handle=handle,
        )
        assert len(attacker_result.findings) == 0

        evaluator = EvaluatorAgent(test_case_repo=test_case_repo)
        eval_result = await evaluator.evaluate_scan(
            candidates=attacker_result.findings,
            target_handle=handle,
            scan_id=scan_id,
        )

        assert eval_result.confirmed_count == 0
        assert eval_result.rejected_count == 0
        assert eval_result.inconclusive_count == 0
        assert len(eval_result.findings) == 0

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_evaluator_adversarial_fabricated_candidate_rejected():
    """
    Phase 6 Adversarial Test: Feed the Evaluator a deliberately fabricated candidate finding
    (oracle_result.fired is True, but response owner matches the requesting principal).
    Evaluator MUST reject it with a reason, not wave it through.
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        test_case_repo = TestCaseRepository()
        finding_repo = FindingRepository()
        evaluator = EvaluatorAgent(
            test_case_repo=test_case_repo,
            finding_repo=finding_repo,
        )

        # Fabricate evidence where owner_id matches requester_id (Alice requesting Alice's doc)
        fake_test_case = TestCaseRecord(
            scan_id=scan_id,
            category="BOLA",
            route_template="/documents/{doc_id}",
            method="GET",
            principal_id="usr_alice_01",
            request={
                "method": "GET",
                "url_path": "/documents/doc_alice_01",
                "headers": {"Authorization": "Bearer alice-token-123"},
                "body": None,
            },
            response={
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": '{"doc_id": "doc_alice_01", "owner_id": "usr_alice_01", "title": "Alice Secret"}',
                "elapsed_ms": 15,
            },
            oracle_result={
                "fired": True,  # Deliberately claimed to fire
                "rule_id": "BOLA_DISCRIMINATED_OBJECT",
                "rationale": "Fabricated BOLA claim",
                "evidence": {
                    "request_principal": "usr_alice_01",
                    "target_owner": "usr_alice_01",  # Inconsistent: matches requester
                },
            },
        )
        await test_case_repo.save(fake_test_case)

        # Fabricated candidate finding
        fabricated_candidate = CandidateFinding(
            scan_id=scan_id,
            project_id="vulnerable_fastapi_app",
            title="Fabricated BOLA Candidate",
            category="BOLA",
            cwe=["CWE-639"],
            route_template="/documents/{doc_id}",
            method="GET",
            description="Fabricated exploit claim where owner matches requester",
            impact="None",
            runtime_confirmed=True,
            oracle_rule_id="BOLA_DISCRIMINATED_OBJECT",
            evidence_ids=[fake_test_case.id],
            status="candidate",
        )

        evaluated = await evaluator.evaluate_candidate(
            candidate=fabricated_candidate,
            target_handle=handle,
            scan_id=scan_id,
        )

        # MUST be REJECTED, not confirmed
        assert evaluated.status == EvaluationStatus.REJECTED
        assert "matches requesting principal" in evaluated.status_reason
        assert evaluated.runtime_confirmed is False
        assert evaluated.confidence.band == ConfidenceLevel.ZERO
        assert evaluated.confidence.score == 0.0

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_evaluator_reproduction_failure_becomes_inconclusive():
    """
    Phase 6 Requirement: Candidate that cannot be reproduced becomes inconclusive, never confirmed.
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        test_case_repo = TestCaseRepository()
        finding_repo = FindingRepository()
        evaluator = EvaluatorAgent(
            test_case_repo=test_case_repo,
            finding_repo=finding_repo,
        )

        # Candidate points to a route that returns 404 on reproduction
        tc = TestCaseRecord(
            scan_id=scan_id,
            category="BOLA",
            route_template="/documents/{doc_id}",
            method="GET",
            principal_id="usr_alice_01",
            request={
                "method": "GET",
                "url_path": "/documents/non_existent_doc_999",
                "headers": {"Authorization": "Bearer alice-token-123"},
                "body": None,
            },
            response={
                "status": 200,
                "headers": {},
                "body": '{"doc_id": "doc_bob_02", "owner_id": "usr_bob_02"}',
                "elapsed_ms": 10,
            },
            oracle_result={
                "fired": True,
                "rule_id": "BOLA_DISCRIMINATED_OBJECT",
                "evidence": {
                    "request_principal": "usr_alice_01",
                    "target_owner": "usr_bob_02",
                },
            },
        )
        await test_case_repo.save(tc)

        candidate = CandidateFinding(
            scan_id=scan_id,
            project_id="vulnerable_fastapi_app",
            title="Unreproducible BOLA",
            category="BOLA",
            cwe=["CWE-639"],
            route_template="/documents/{doc_id}",
            method="GET",
            description="Unreproducible candidate test",
            impact="None",
            runtime_confirmed=True,
            oracle_rule_id="BOLA_DISCRIMINATED_OBJECT",
            evidence_ids=[tc.id],
            status="candidate",
        )

        evaluated = await evaluator.evaluate_candidate(
            candidate=candidate,
            target_handle=handle,
            scan_id=scan_id,
        )

        # MUST be INCONCLUSIVE, NEVER CONFIRMED
        assert evaluated.status == EvaluationStatus.INCONCLUSIVE
        assert "reproduction_failed" in evaluated.status_reason or "transport_error" in evaluated.status_reason
        assert evaluated.runtime_confirmed is False
        assert evaluated.confidence.band == ConfidenceLevel.ZERO

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_evaluator_duplicate_candidate_detection():
    """
    Phase 6 Requirement: Duplicate detection against already-confirmed findings in the same scan.
    Second identical candidate is rejected with duplicate_of pointing to the first finding.
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="vulnerable_fastapi_app",
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_result = await attacker.run_scan(context=context, target_handle=handle)

        misconfig_candidate = next(f for f in attacker_result.findings if f.category == "SECURITY_MISCONFIG")

        # Duplicate candidate
        duplicate_candidate = CandidateFinding(
            scan_id=scan_id,
            project_id="vulnerable_fastapi_app",
            title="Duplicate Security Misconfig",
            category=misconfig_candidate.category,
            cwe=misconfig_candidate.cwe,
            route_template=misconfig_candidate.route_template,
            method=misconfig_candidate.method,
            description="Duplicate candidate for the same route",
            impact=misconfig_candidate.impact,
            runtime_confirmed=True,
            oracle_rule_id=misconfig_candidate.oracle_rule_id,
            evidence_ids=misconfig_candidate.evidence_ids,
            status="candidate",
        )

        evaluator = EvaluatorAgent(test_case_repo=test_case_repo)
        eval_result = await evaluator.evaluate_scan(
            candidates=[misconfig_candidate, duplicate_candidate],
            target_handle=handle,
            scan_id=scan_id,
        )

        assert eval_result.confirmed_count == 1
        assert eval_result.rejected_count == 1
        assert eval_result.inconclusive_count == 0

        first_finding = eval_result.findings[0]
        second_finding = eval_result.findings[1]

        assert first_finding.status == EvaluationStatus.CONFIRMED
        assert second_finding.status == EvaluationStatus.REJECTED
        assert second_finding.duplicate_of == first_finding.id
        assert second_finding.status_reason == f"duplicate_of_{first_finding.id}"

    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_evaluator_severity_reproducible_from_stored_cvss_inputs():
    """
    Phase 6 Exit Gate: Severity is reproducible from the stored CVSS inputs alone.
    Proves the rubric isn't a black box.
    """
    scan_id = str(uuid.uuid4())
    handle = LocalFixtureTargetHandle(fixture_dir=VULN_FIXTURE)
    await handle.start()

    try:
        builder = BuilderAgent()
        context = await builder.build_context(
            project_id="vulnerable_fastapi_app",
            scan_id=scan_id,
            project_dir=VULN_FIXTURE,
            target_handle=handle,
        )

        test_case_repo = TestCaseRepository()
        attacker = AttackerAgent(test_case_repo=test_case_repo)
        attacker_result = await attacker.run_scan(context=context, target_handle=handle)

        evaluator = EvaluatorAgent(test_case_repo=test_case_repo)
        eval_result = await evaluator.evaluate_scan(
            candidates=attacker_result.findings,
            target_handle=handle,
            scan_id=scan_id,
        )

        assert eval_result.confirmed_count == 3

        for finding in eval_result.findings:
            stored_inputs = finding.cvss.inputs
            recomputed = calculate_cvss_score(stored_inputs)

            assert recomputed.base_score == finding.cvss.base_score, (
                f"Score mismatch for {finding.category}: stored={finding.cvss.base_score}, "
                f"recomputed={recomputed.base_score}"
            )
            assert recomputed.vector_string == finding.cvss.vector_string
            assert recomputed.severity == finding.cvss.severity

    finally:
        await handle.stop()


def test_structural_independence_evidence_model():
    """
    Phase 6 Requirement: Structural independence.
    EvaluatorEvidence excludes narrative, thoughts, and target source code.
    """
    evidence = EvaluatorEvidence(
        candidate_id="cand_123",
        category="BOLA",
        cwe=["CWE-639"],
        route_template="/documents/{doc_id}",
        method="GET",
        request={"method": "GET", "url_path": "/documents/doc_bob_02"},
        response={"status": 200, "body": "{}"},
        oracle_result={"fired": True},
    )
    # Ensure evidence model has no narrative or source fields
    fields = evidence.model_dump().keys()
    assert "narrative" not in fields
    assert "thought" not in fields
    assert "source_code" not in fields
    assert "attacker_reasoning" not in fields
