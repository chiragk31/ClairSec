"""
Deterministic CVSS v3.1 Mathematical Scorer (METHODOLOGY.md §4).

Implements the official FIRST CVSS v3.1 Base Metric equations.
An LLM never emits the final CVSS score, vector, or severity band;
platform code strictly calculates them from closed-enum metric inputs.
"""
from __future__ import annotations

import math
from app.agents.evaluator.schemas import (
    AttackComplexity,
    AttackVector,
    CvssInputs,
    CvssResult,
    ImpactLevel,
    PrivilegesRequired,
    Scope,
    SeverityBand,
    UserInteraction,
)


def roundup(val: float) -> float:
    """
    CVSS v3.1 roundup function per FIRST specification:
    The smallest number, specified to one decimal place, that is equal to or higher than its input.
    E.g.: roundup(4.00) -> 4.0, roundup(4.02) -> 4.1
    """
    int_val = round(val * 100_000)
    if int_val % 10_000 == 0:
        return int_val / 100_000
    return math.ceil(int_val / 10_000) / 10.0


# ─────────────────────────────────────────────────────────────────────────────
# CVSS v3.1 Metric Weight Tables
# ─────────────────────────────────────────────────────────────────────────────

_AV_WEIGHTS = {
    AttackVector.NETWORK: 0.85,
    AttackVector.ADJACENT: 0.62,
    AttackVector.LOCAL: 0.55,
    AttackVector.PHYSICAL: 0.20,
}

_AC_WEIGHTS = {
    AttackComplexity.LOW: 0.77,
    AttackComplexity.HIGH: 0.44,
}

_PR_WEIGHTS_UNCHANGED = {
    PrivilegesRequired.NONE: 0.85,
    PrivilegesRequired.LOW: 0.62,
    PrivilegesRequired.HIGH: 0.27,
}

_PR_WEIGHTS_CHANGED = {
    PrivilegesRequired.NONE: 0.85,
    PrivilegesRequired.LOW: 0.68,
    PrivilegesRequired.HIGH: 0.50,
}

_UI_WEIGHTS = {
    UserInteraction.NONE: 0.85,
    UserInteraction.REQUIRED: 0.62,
}

_IMPACT_WEIGHTS = {
    ImpactLevel.NONE: 0.0,
    ImpactLevel.LOW: 0.22,
    ImpactLevel.HIGH: 0.56,
}


def score_to_severity(score: float) -> SeverityBand:
    """Map CVSS 3.1 base score to its standard severity band."""
    if score == 0.0:
        return SeverityBand.NONE
    if score < 4.0:
        return SeverityBand.LOW
    if score < 7.0:
        return SeverityBand.MEDIUM
    if score < 9.0:
        return SeverityBand.HIGH
    return SeverityBand.CRITICAL


def format_vector_string(inputs: CvssInputs) -> str:
    """Format the canonical CVSS:3.1 vector string."""
    return (
        f"CVSS:3.1/AV:{inputs.attack_vector.value}"
        f"/AC:{inputs.attack_complexity.value}"
        f"/PR:{inputs.privileges_required.value}"
        f"/UI:{inputs.user_interaction.value}"
        f"/S:{inputs.scope.value}"
        f"/C:{inputs.confidentiality.value}"
        f"/I:{inputs.integrity.value}"
        f"/A:{inputs.availability.value}"
    )


def calculate_cvss_score(inputs: CvssInputs) -> CvssResult:
    """
    Deterministically calculate CVSS v3.1 base score and vector from inputs.
    Strictly adheres to FIRST CVSS v3.1 specification.
    """
    av = _AV_WEIGHTS[inputs.attack_vector]
    ac = _AC_WEIGHTS[inputs.attack_complexity]
    ui = _UI_WEIGHTS[inputs.user_interaction]

    if inputs.scope == Scope.CHANGED:
        pr = _PR_WEIGHTS_CHANGED[inputs.privileges_required]
    else:
        pr = _PR_WEIGHTS_UNCHANGED[inputs.privileges_required]

    c = _IMPACT_WEIGHTS[inputs.confidentiality]
    i = _IMPACT_WEIGHTS[inputs.integrity]
    a = _IMPACT_WEIGHTS[inputs.availability]

    # Impact Sub-Score (ISS)
    iss = 1.0 - ((1.0 - c) * (1.0 - i) * (1.0 - a))

    # Exploitability Sub-Score
    exploitability = 8.22 * av * ac * pr * ui

    # Impact
    if inputs.scope == Scope.CHANGED:
        impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
    else:
        impact = 6.42 * iss

    # Base Score
    if impact <= 0:
        base_score = 0.0
    else:
        if inputs.scope == Scope.CHANGED:
            base_score = roundup(min(1.08 * (impact + exploitability), 10.0))
        else:
            base_score = roundup(min(impact + exploitability, 10.0))

    vector = format_vector_string(inputs)
    severity = score_to_severity(base_score)

    return CvssResult(
        inputs=inputs,
        vector_string=vector,
        base_score=base_score,
        severity=severity,
    )
