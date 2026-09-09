"""
Evaluator Agent (PHASES.md Phase 6, METHODOLOGY.md §4 & §9, RULES.md §2).

Responsibilities:
1. Structural Independence: Evaluates HTTP request/response evidence only,
   completely isolated from Attacker narrative and target source code.
2. Evidence Verification: Mechanically filters out internally inconsistent or
   adversarially fabricated candidate findings.
3. Duplicate Detection: Detects redundant findings in the same scan scope.
4. Independent Reproduction: Re-executes the test case via ScopeLockedHttpClient.
5. Deterministic Severity: Platform code calculates CVSS v3.1 vector and score.
6. Structured Confidence: Computed from verification attributes, never a model float.
"""
from __future__ import annotations

import json
import logging
from typing import Any
import uuid

from app.agents.attacker.repository import TestCaseRepository
from app.agents.attacker.schemas import CandidateFinding, normalize_route_path
from app.agents.evaluator.confidence import calculate_confidence
from app.agents.evaluator.cvss_scorer import calculate_cvss_score
from app.agents.evaluator.reproducer import TestReproducer
from app.agents.evaluator.repository import FindingRepository
from app.agents.evaluator.schemas import (
    AttackComplexity,
    AttackVector,
    ConfidenceInputs,
    ConfidenceLevel,
    ConfidenceResult,
    CvssInputs,
    CvssResult,
    EvaluatedFinding,
    EvaluationStatus,
    EvaluatorEvidence,
    EvaluatorScanResult,
    EvaluatorTriageResponse,
    ImpactLevel,
    PrivilegesRequired,
    Scope,
    SeverityBand,
    UserInteraction,
)
from app.agents.evaluator.verifier import EvidenceVerifier
from app.core.config import settings
from app.llm.models import AgentName, LLMRequest, TrustLevel
from app.llm.prompts.registry import PromptRegistry
from app.llm.provider import LLMProvider
from app.llm.providers.mock_provider import MockLLMProvider
from app.targets.handle import TargetHandle

logger = logging.getLogger(__name__)


def _default_cvss_for_category(category: str, evidence: EvaluatorEvidence) -> CvssInputs:
    """Deterministic default CVSS metric selection based on category and evidence."""
    cat = category.upper()
    req_headers = {k.lower(): str(v).lower() for k, v in (evidence.request.get("headers") or {}).items()}
    has_auth = "authorization" in req_headers

    if cat == "BOLA":
        return CvssInputs(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.LOW if has_auth else PrivilegesRequired.NONE,
            user_interaction=UserInteraction.NONE,
            scope=Scope.UNCHANGED,
            confidentiality=ImpactLevel.HIGH,
            integrity=ImpactLevel.NONE,
            availability=ImpactLevel.NONE,
            evidence_citations={
                "confidentiality": "Response leaked another user's resource",
                "privileges_required": "Authenticated bearer token present in request",
            },
        )

    if cat == "BOPLA_MASS_ASSIGN":
        return CvssInputs(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.LOW if has_auth else PrivilegesRequired.NONE,
            user_interaction=UserInteraction.NONE,
            scope=Scope.UNCHANGED,
            confidentiality=ImpactLevel.HIGH,
            integrity=ImpactLevel.HIGH,
            availability=ImpactLevel.NONE,
            evidence_citations={
                "integrity": "Injected privileged field persisted in resource state",
                "confidentiality": "Elevated access gained via mass assignment",
            },
        )

    if cat == "SECURITY_MISCONFIG":
        return CvssInputs(
            attack_vector=AttackVector.NETWORK,
            attack_complexity=AttackComplexity.LOW,
            privileges_required=PrivilegesRequired.NONE,
            user_interaction=UserInteraction.NONE,
            scope=Scope.UNCHANGED,
            confidentiality=ImpactLevel.HIGH,
            integrity=ImpactLevel.NONE,
            availability=ImpactLevel.NONE,
            evidence_citations={
                "confidentiality": "Debug keys or database credentials exposed without authentication",
                "privileges_required": "Unauthenticated endpoint",
            },
        )

    # Generic fallback
    return CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.NONE,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.LOW,
        integrity=ImpactLevel.NONE,
        availability=ImpactLevel.NONE,
        evidence_citations={"general": "Confirmed anomalous behavior"},
    )


class EvaluatorAgent:
    """
    Evaluates candidate security findings independently from the Attacker Agent.
    """

    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        test_case_repo: TestCaseRepository | None = None,
        finding_repo: FindingRepository | None = None,
        prompt_registry: PromptRegistry | None = None,
    ):
        self._provider = provider or MockLLMProvider()
        self._test_case_repo = test_case_repo or TestCaseRepository()
        self._finding_repo = finding_repo or FindingRepository()
        self._prompt_registry = prompt_registry or PromptRegistry()
        self._verifier = EvidenceVerifier()
        self._reproducer = TestReproducer(test_case_repo=self._test_case_repo)

    async def evaluate_candidate(
        self,
        *,
        candidate: CandidateFinding,
        target_handle: TargetHandle,
        scan_id: str,
        existing_confirmed: list[EvaluatedFinding] | None = None,
    ) -> EvaluatedFinding:
        """
        Adjudicate a single CandidateFinding through the full evaluation pipeline:
        1. Extract evidence container (structural independence).
        2. Evidence verification (filter out fabricated findings).
        3. Deduplication against already confirmed findings.
        4. Reproduction (re-execute via ScopeLockedHttpClient).
        5. Deterministic CVSS v3.1 scoring and structured confidence calculation.
        6. Persistence to the findings repository.
        """
        # Step 1: Structural Independence — isolate raw evidence
        evidence_req: dict[str, Any] = {}
        evidence_res: dict[str, Any] = {}
        evidence_oracle: dict[str, Any] = {}

        if candidate.evidence_ids:
            try:
                tc = await self._test_case_repo.get_by_id(candidate.evidence_ids[0])
                if tc:
                    evidence_req = tc.request
                    evidence_res = tc.response
                    evidence_oracle = tc.oracle_result
            except Exception as exc:
                logger.debug("Could not fetch test case %s: %s", candidate.evidence_ids[0], exc)

        evidence = EvaluatorEvidence(
            candidate_id=candidate.id,
            category=candidate.category,
            cwe=candidate.cwe,
            route_template=candidate.route_template,
            method=candidate.method,
            request=evidence_req,
            response=evidence_res,
            oracle_result=evidence_oracle,
        )

        default_cvss = _default_cvss_for_category(candidate.category, evidence)
        dummy_cvss_result = calculate_cvss_score(default_cvss)
        zero_confidence = calculate_confidence(
            ConfidenceInputs(
                runtime_confirmed=False,
                oracle_fired=False,
                reproduced_n_times=0,
                evidence_complete=False,
            )
        )

        # Step 2: Evidence Verification (Adversarial Inconsistency Filter)
        ver_res = self._verifier.verify_evidence(evidence)
        if not ver_res.is_valid:
            rejected_finding = EvaluatedFinding(
                scan_id=scan_id,
                project_id=candidate.project_id,
                title=f"{candidate.category} at {candidate.route_template}",
                category=candidate.category,
                cwe=candidate.cwe,
                route_template=candidate.route_template,
                method=candidate.method,
                description=f"Rejected candidate: {ver_res.rejection_reason}",
                impact="None (rejected)",
                runtime_confirmed=False,
                oracle_rule_id=candidate.oracle_rule_id,
                cvss=dummy_cvss_result,
                confidence=zero_confidence,
                evidence_ids=candidate.evidence_ids,
                status=EvaluationStatus.REJECTED,
                status_reason=ver_res.rejection_reason,
                agent_provenance={
                    "proposed_by": "attacker",
                    "evaluated_by": "evaluator",
                },
            )
            return await self._finding_repo.create(rejected_finding)

        # Step 3: Duplicate Detection in scan scope
        if existing_confirmed:
            for conf in existing_confirmed:
                if (
                    conf.category == candidate.category
                    and conf.route_template == candidate.route_template
                    and conf.method == candidate.method
                ):
                    dup_finding = EvaluatedFinding(
                        scan_id=scan_id,
                        project_id=candidate.project_id,
                        title=f"{candidate.category} at {candidate.route_template} (Duplicate)",
                        category=candidate.category,
                        cwe=candidate.cwe,
                        route_template=candidate.route_template,
                        method=candidate.method,
                        description=f"Duplicate of confirmed finding {conf.id}",
                        impact="Duplicate",
                        runtime_confirmed=True,
                        oracle_rule_id=candidate.oracle_rule_id,
                        cvss=conf.cvss,
                        confidence=conf.confidence,
                        evidence_ids=candidate.evidence_ids,
                        status=EvaluationStatus.REJECTED,
                        status_reason=f"duplicate_of_{conf.id}",
                        duplicate_of=conf.id,
                        agent_provenance={
                            "proposed_by": "attacker",
                            "evaluated_by": "evaluator",
                        },
                    )
                    return await self._finding_repo.create(dup_finding)

        # Step 4: Live Reproduction
        rep_res = await self._reproducer.reproduce(
            evidence=evidence,
            target_handle=target_handle,
            scan_id=scan_id,
        )

        if not rep_res.reproduced:
            inconclusive_finding = EvaluatedFinding(
                scan_id=scan_id,
                project_id=candidate.project_id,
                title=f"{candidate.category} at {candidate.route_template}",
                category=candidate.category,
                cwe=candidate.cwe,
                route_template=candidate.route_template,
                method=candidate.method,
                description=f"Candidate could not be reproduced: {rep_res.failure_reason}",
                impact="Unverified",
                runtime_confirmed=False,
                oracle_rule_id=candidate.oracle_rule_id,
                cvss=dummy_cvss_result,
                confidence=zero_confidence,
                evidence_ids=candidate.evidence_ids,
                status=EvaluationStatus.INCONCLUSIVE,
                status_reason=rep_res.failure_reason,
                agent_provenance={
                    "proposed_by": "attacker",
                    "evaluated_by": "evaluator",
                },
            )
            return await self._finding_repo.create(inconclusive_finding)

        # Step 5: Deterministic Severity (CVSS v3.1) and Structured Confidence
        # Obtain CVSS metric inputs
        cvss_inputs = default_cvss
        try:
            if settings.llm_provider != "mock":
                prompt_text = self._prompt_registry.get_prompt(
                    "evaluator.triage",
                    "v1",
                    category=candidate.category,
                    cwe=",".join(candidate.cwe),
                    route_template=candidate.route_template,
                    method=candidate.method,
                    request_json=json.dumps(rep_res.reproduced_request),
                    response_json=json.dumps(rep_res.reproduced_response),
                    oracle_result_json=json.dumps(rep_res.oracle_result),
                )
                llm_req = LLMRequest(
                    prompt_id="evaluator.triage",
                    prompt_version="v1",
                    system_prompt="You are an expert security evaluator. Select CVSS v3.1 base metrics.",
                    messages=[{"role": "user", "content": prompt_text}],
                    response_schema=EvaluatorTriageResponse,
                    trust_level=TrustLevel.QUARANTINED,
                )
                llm_resp = await self._provider.complete(request=llm_req)
                if llm_resp.parsed and isinstance(llm_resp.parsed, EvaluatorTriageResponse):
                    cvss_inputs = llm_resp.parsed.cvss_inputs
        except Exception as exc:
            logger.debug("Evaluator LLM triage call failed: %s; using deterministic baseline", exc)

        # Platform calculates score and vector (NEVER the model)
        cvss_result = calculate_cvss_score(cvss_inputs)

        # Calculate structured confidence
        conf_result = calculate_confidence(
            ConfidenceInputs(
                runtime_confirmed=True,
                oracle_fired=True,
                reproduced_n_times=1,
                evidence_complete=True,
            )
        )

        all_evidence_ids = list(candidate.evidence_ids)
        if rep_res.test_case_id and rep_res.test_case_id not in all_evidence_ids:
            all_evidence_ids.append(rep_res.test_case_id)

        confirmed_finding = EvaluatedFinding(
            scan_id=scan_id,
            project_id=candidate.project_id,
            title=f"{candidate.category} at {candidate.route_template}",
            category=candidate.category,
            cwe=candidate.cwe,
            route_template=candidate.route_template,
            method=candidate.method,
            description=(
                f"Confirmed {candidate.category} vulnerability on route {candidate.route_template} [{candidate.method}]. "
                f"Oracle {candidate.oracle_rule_id} fired and was independently reproduced."
            ),
            impact=f"CVSS v3.1 {cvss_result.base_score} ({cvss_result.severity.value}) - Vector: {cvss_result.vector_string}",
            runtime_confirmed=True,
            oracle_rule_id=candidate.oracle_rule_id,
            cvss=cvss_result,
            confidence=conf_result,
            evidence_ids=all_evidence_ids,
            reproduction_summary=f"Reproduced on {target_handle.base_url}: {rep_res.oracle_result.get('rationale', '')}",
            status=EvaluationStatus.CONFIRMED,
            status_reason="reproduced_and_verified",
            agent_provenance={
                "proposed_by": "attacker",
                "evaluated_by": "evaluator",
                "prompt_version": "v1.0",
            },
        )

        return await self._finding_repo.create(confirmed_finding)

    async def evaluate_scan(
        self,
        *,
        candidates: list[CandidateFinding],
        target_handle: TargetHandle,
        scan_id: str,
    ) -> EvaluatorScanResult:
        """
        Evaluate all candidate findings produced by the Attacker Agent.
        """
        project_id = candidates[0].project_id if candidates else "unknown"
        evaluated_findings: list[EvaluatedFinding] = []
        confirmed_list: list[EvaluatedFinding] = []

        confirmed_count = 0
        rejected_count = 0
        inconclusive_count = 0

        for cand in candidates:
            finding = await self.evaluate_candidate(
                candidate=cand,
                target_handle=target_handle,
                scan_id=scan_id,
                existing_confirmed=confirmed_list,
            )
            evaluated_findings.append(finding)

            if finding.status == EvaluationStatus.CONFIRMED:
                confirmed_count += 1
                confirmed_list.append(finding)
            elif finding.status == EvaluationStatus.REJECTED:
                rejected_count += 1
            elif finding.status == EvaluationStatus.INCONCLUSIVE:
                inconclusive_count += 1

        return EvaluatorScanResult(
            scan_id=scan_id,
            project_id=project_id,
            findings=evaluated_findings,
            confirmed_count=confirmed_count,
            rejected_count=rejected_count,
            inconclusive_count=inconclusive_count,
        )
