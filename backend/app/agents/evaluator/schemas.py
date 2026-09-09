"""
Schemas for the Evaluator Agent (PHASES.md Phase 6, DATA_MODEL.md §3, METHODOLOGY.md §4).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class EvaluationStatus(str, Enum):
    """Lifecycle status of a finding after Evaluator adjudication."""
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


# ─────────────────────────────────────────────────────────────────────────────
# CVSS v3.1 Closed Enums & Models (METHODOLOGY.md §4)
# ─────────────────────────────────────────────────────────────────────────────

class AttackVector(str, Enum):
    NETWORK = "N"
    ADJACENT = "A"
    LOCAL = "L"
    PHYSICAL = "P"


class AttackComplexity(str, Enum):
    LOW = "L"
    HIGH = "H"


class PrivilegesRequired(str, Enum):
    NONE = "N"
    LOW = "L"
    HIGH = "H"


class UserInteraction(str, Enum):
    NONE = "N"
    REQUIRED = "R"


class Scope(str, Enum):
    UNCHANGED = "U"
    CHANGED = "C"


class ImpactLevel(str, Enum):
    NONE = "N"
    LOW = "L"
    HIGH = "H"


class SeverityBand(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CvssInputs(BaseModel):
    """
    Closed-enum base metrics selected by the Evaluator, each citing specific evidence.
    Platform code calculates the numeric score and vector; the model never does.
    """
    model_config = ConfigDict(extra="ignore")

    attack_vector: AttackVector = AttackVector.NETWORK
    attack_complexity: AttackComplexity = AttackComplexity.LOW
    privileges_required: PrivilegesRequired = PrivilegesRequired.NONE
    user_interaction: UserInteraction = UserInteraction.NONE
    scope: Scope = Scope.UNCHANGED
    confidentiality: ImpactLevel = ImpactLevel.NONE
    integrity: ImpactLevel = ImpactLevel.NONE
    availability: ImpactLevel = ImpactLevel.NONE
    evidence_citations: dict[str, str] = Field(
        default_factory=dict,
        description="Citations mapping metric keys to specific evidence fields",
    )


class CvssResult(BaseModel):
    """Platform-computed CVSS v3.1 vector, score, and severity band."""
    model_config = ConfigDict(extra="ignore")

    inputs: CvssInputs
    vector_string: str
    base_score: float
    severity: SeverityBand


# ─────────────────────────────────────────────────────────────────────────────
# Confidence Scoring Models (METHODOLOGY.md §4)
# ─────────────────────────────────────────────────────────────────────────────

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ZERO = "ZERO"


class ConfidenceInputs(BaseModel):
    """
    Mechanical inputs for confidence derivation.
    Never an ungrounded model float.
    """
    model_config = ConfigDict(extra="ignore")

    runtime_confirmed: bool
    oracle_fired: bool
    reproduced_n_times: int
    evidence_complete: bool


class ConfidenceResult(BaseModel):
    """Structured confidence computation."""
    model_config = ConfigDict(extra="ignore")

    inputs: ConfidenceInputs
    band: ConfidenceLevel
    score: float


# ─────────────────────────────────────────────────────────────────────────────
# Structural Independence & Evidence Isolation (RULES.md §2, METHODOLOGY.md §9)
# ─────────────────────────────────────────────────────────────────────────────

class EvaluatorEvidence(BaseModel):
    """
    Strict evidence container stripped of Attacker narrative, reasoning, and target source.
    Ensures genuine independent adjudication and resistance to prompt injection.
    """
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    category: str
    cwe: list[str]
    route_template: str
    method: str
    request: dict[str, Any]
    response: dict[str, Any]
    oracle_result: dict[str, Any]


class EvaluatorTriageResponse(BaseModel):
    """Structured output expected from Evaluator model triage."""
    model_config = ConfigDict(extra="ignore")

    cvss_inputs: CvssInputs
    rationale: str


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Finding Record (DATA_MODEL.md §3 findings)
# ─────────────────────────────────────────────────────────────────────────────

class EvaluatedFinding(BaseModel):
    """
    Complete finding record as specified in DATA_MODEL.md §3 findings collection.
    """
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    scan_id: str
    project_id: str
    title: str
    category: str
    cwe: list[str]
    route_template: str               # Normalized template, e.g. /documents/{doc_id}
    method: str
    description: str
    impact: str
    runtime_confirmed: bool
    oracle_rule_id: str
    cvss: CvssResult
    confidence: ConfidenceResult
    evidence_ids: list[str] = Field(default_factory=list)
    reproduction_summary: str = ""
    source_locations: list[dict[str, Any]] = Field(default_factory=list)
    status: EvaluationStatus = EvaluationStatus.CONFIRMED
    status_reason: str = ""
    agent_provenance: dict[str, Any] = Field(default_factory=dict)
    duplicate_of: str | None = None
    superseded_by: str | None = None
    created_at: str = Field(default_factory=_now_iso)


class EvaluatorScanResult(BaseModel):
    """Aggregated output from an Evaluator triage run."""
    model_config = ConfigDict(extra="ignore")

    scan_id: str
    project_id: str
    findings: list[EvaluatedFinding]
    confirmed_count: int = 0
    rejected_count: int = 0
    inconclusive_count: int = 0
