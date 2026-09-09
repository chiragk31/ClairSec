"""
Structured Confidence Calculator (METHODOLOGY.md §4).

Computes a deterministic confidence band from verifiable runtime attributes:
runtime_confirmed, oracle_fired, reproduced_n_times, evidence_complete.
An LLM never emits a bare ungrounded float.
"""
from __future__ import annotations

from app.agents.evaluator.schemas import (
    ConfidenceInputs,
    ConfidenceLevel,
    ConfidenceResult,
)


def calculate_confidence(inputs: ConfidenceInputs) -> ConfidenceResult:
    """
    Deterministically derive structured confidence score and level.
    """
    if not inputs.runtime_confirmed or not inputs.oracle_fired:
        return ConfidenceResult(
            inputs=inputs,
            band=ConfidenceLevel.ZERO,
            score=0.0,
        )

    if inputs.reproduced_n_times >= 1 and inputs.evidence_complete:
        return ConfidenceResult(
            inputs=inputs,
            band=ConfidenceLevel.HIGH,
            score=1.0,
        )

    if inputs.reproduced_n_times >= 1 and not inputs.evidence_complete:
        return ConfidenceResult(
            inputs=inputs,
            band=ConfidenceLevel.MEDIUM,
            score=0.7,
        )

    # Runtime confirmed but not independently reproduced in current pass
    return ConfidenceResult(
        inputs=inputs,
        band=ConfidenceLevel.LOW,
        score=0.4,
    )
