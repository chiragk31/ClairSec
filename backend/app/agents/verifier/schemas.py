"""
Schemas for Phase 8 Re-test and Verification (DATA_MODEL.md §3 verification_results, METHODOLOGY.md §5).
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


class VerificationOutcome(str, Enum):
    """
    Verification states (PHASES.md Phase 8, METHODOLOGY.md §5).
    - FIXED: exploit blocked AND functional suite passes (Dual Criterion).
    - REGRESSED: exploit blocked BUT functional suite fails.
    - UNRESOLVED: exploit still succeeds after patch.
    - UNVERIFIED: target rebuild or restart failed.
    """
    FIXED = "fixed"
    REGRESSED = "regressed"
    UNRESOLVED = "unresolved"
    UNVERIFIED = "unverified"


class OriginalExploitResult(BaseModel):
    """Re-test outcome of the original candidate exploit."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    ran: bool = False
    exploited: bool = False
    rationale: str = ""


class FunctionalSuiteResult(BaseModel):
    """Execution outcome of the project's legitimate functional tests (Dual Criterion)."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    ran: bool = False
    passed: int = 0
    failed: int = 0
    newly_failing: list[str] = Field(default_factory=list)
    total: int = 0


class VariantAttackResult(BaseModel):
    """Execution outcome of an adapted attack variant (RESEARCH.md §5 post-fix robustness)."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    ran: bool = False
    exploited: bool = False
    variant_kind: str = ""
    rationale: str = ""


class VerificationRecord(BaseModel):
    """
    Canonical record representing re-test and verification outcome in verification_results.
    (DATA_MODEL.md §3 verification_results).
    """
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    finding_id: str
    patch_id: str
    scan_id: str
    rebuild_ok: bool
    original_exploit: OriginalExploitResult
    functional_suite: FunctionalSuiteResult
    variant_attack: VariantAttackResult
    outcome: VerificationOutcome
    outcome_reason: str = ""
    duration_s: float = 0.0
    created_at: str = Field(default_factory=_now_iso)


class VerificationScanSummary(BaseModel):
    """Aggregated verification results for all findings in a scan."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    scan_id: str
    records: list[VerificationRecord] = Field(default_factory=list)
    fixed_count: int = 0
    regressed_count: int = 0
    unresolved_count: int = 0
    unverified_count: int = 0
