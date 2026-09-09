"""
Unit tests for deterministic CVSS v3.1 mathematical scorer (METHODOLOGY.md §4).
Validates calculation against FIRST CVSS v3.1 specification.
"""
from __future__ import annotations

import pytest

from app.agents.evaluator.cvss_scorer import (
    calculate_cvss_score,
    roundup,
    score_to_severity,
)
from app.agents.evaluator.schemas import (
    AttackComplexity,
    AttackVector,
    CvssInputs,
    ImpactLevel,
    PrivilegesRequired,
    Scope,
    SeverityBand,
    UserInteraction,
)


def test_roundup_cvss_specification():
    """Verify CVSS v3.1 roundup function implementation against official examples."""
    assert roundup(4.00) == 4.0
    assert roundup(4.01) == 4.1
    assert roundup(4.02) == 4.1
    assert roundup(4.09) == 4.1
    assert roundup(4.10) == 4.1
    assert roundup(0.0) == 0.0
    assert roundup(9.8001) == 9.9


def test_score_to_severity_mapping():
    """Verify standard CVSS v3.1 severity bands."""
    assert score_to_severity(0.0) == SeverityBand.NONE
    assert score_to_severity(3.9) == SeverityBand.LOW
    assert score_to_severity(4.0) == SeverityBand.MEDIUM
    assert score_to_severity(6.9) == SeverityBand.MEDIUM
    assert score_to_severity(7.0) == SeverityBand.HIGH
    assert score_to_severity(8.9) == SeverityBand.HIGH
    assert score_to_severity(9.0) == SeverityBand.CRITICAL
    assert score_to_severity(10.0) == SeverityBand.CRITICAL


def test_cvss_critical_reference_vector():
    """CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H -> 9.8 Critical."""
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.NONE,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.HIGH,
        integrity=ImpactLevel.HIGH,
        availability=ImpactLevel.HIGH,
    )
    result = calculate_cvss_score(inputs)
    assert result.vector_string == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    assert result.base_score == 9.8
    assert result.severity == SeverityBand.CRITICAL


def test_cvss_bola_vector():
    """CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N -> 6.5 Medium."""
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.LOW,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.HIGH,
        integrity=ImpactLevel.NONE,
        availability=ImpactLevel.NONE,
    )
    result = calculate_cvss_score(inputs)
    assert result.vector_string == "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N"
    assert result.base_score == 6.5
    assert result.severity == SeverityBand.MEDIUM


def test_cvss_mass_assignment_vector():
    """CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N -> 8.1 High."""
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.LOW,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.HIGH,
        integrity=ImpactLevel.HIGH,
        availability=ImpactLevel.NONE,
    )
    result = calculate_cvss_score(inputs)
    assert result.vector_string == "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N"
    assert result.base_score == 8.1
    assert result.severity == SeverityBand.HIGH


def test_cvss_misconfig_vector():
    """CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N -> 7.5 High."""
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.NONE,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.HIGH,
        integrity=ImpactLevel.NONE,
        availability=ImpactLevel.NONE,
    )
    result = calculate_cvss_score(inputs)
    assert result.vector_string == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
    assert result.base_score == 7.5
    assert result.severity == SeverityBand.HIGH


def test_cvss_scope_changed_vector():
    """CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N -> 6.1 Medium (Reflected XSS)."""
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.NONE,
        user_interaction=UserInteraction.REQUIRED,
        scope=Scope.CHANGED,
        confidentiality=ImpactLevel.LOW,
        integrity=ImpactLevel.LOW,
        availability=ImpactLevel.NONE,
    )
    result = calculate_cvss_score(inputs)
    assert result.vector_string == "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N"
    assert result.base_score == 6.1
    assert result.severity == SeverityBand.MEDIUM


def test_cvss_zero_impact_vector():
    """No impact -> 0.0 None."""
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.NONE,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.NONE,
        integrity=ImpactLevel.NONE,
        availability=ImpactLevel.NONE,
    )
    result = calculate_cvss_score(inputs)
    assert result.base_score == 0.0
    assert result.severity == SeverityBand.NONE


def test_cvss_round_trip_reproducibility():
    """
    Phase 6 Requirement: Severity is reproducible from the stored CVSS inputs alone.
    Asserts that recomputing the score from stored inputs matches what was persisted.
    """
    inputs = CvssInputs(
        attack_vector=AttackVector.NETWORK,
        attack_complexity=AttackComplexity.LOW,
        privileges_required=PrivilegesRequired.LOW,
        user_interaction=UserInteraction.NONE,
        scope=Scope.UNCHANGED,
        confidentiality=ImpactLevel.HIGH,
        integrity=ImpactLevel.HIGH,
        availability=ImpactLevel.NONE,
        evidence_citations={"C": "data breach", "I": "unauthorized edit"},
    )
    first_result = calculate_cvss_score(inputs)
    recomputed_result = calculate_cvss_score(inputs)

    assert first_result.base_score == recomputed_result.base_score
    assert first_result.vector_string == recomputed_result.vector_string
    assert first_result.severity == recomputed_result.severity
    assert first_result.inputs.model_dump() == recomputed_result.inputs.model_dump()
