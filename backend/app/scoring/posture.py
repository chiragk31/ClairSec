"""
Security Posture Score (FEATURES.md F6).
Platform code only, unit-tested, versioned posture_v1.

Never uses the word "Secure" as a verdict.
A high score means tested problems were not confirmed — not that none exist.
"""
from __future__ import annotations

from typing import Any

POSTURE_VERSION = "posture_v1"

CVSS_BAND_PENALTIES: dict[str, int] = {
    "critical": 30,
    "high": 18,
    "medium": 9,
    "low": 3,
    "informational": 0,
}

# A confirmed finding whose CVSS band is missing or unknown is never silently
# treated as "medium": it lands in an explicit "unscored" bucket with this
# conservative penalty, recorded in posture.inputs and shown in the breakdown (D6).
UNSCORED_BAND = "unscored"
UNSCORED_PENALTY = 9

INCONCLUSIVE_UNIT_PENALTY = 2
MAX_INCONCLUSIVE_PENALTY = 10

IN_SCOPE_CATEGORIES: list[str] = [
    "BOLA",
    "BROKEN_AUTH",
    "BOPLA_MASS_ASSIGN",
    "BOPLA_DATA_EXPOSURE",
    "BFLA",
    "RESOURCE_CONSUMPTION",
    "INJECTION",
    "SECURITY_MISCONFIG",
]


def _cvss_score_to_band(cvss: float | None) -> str:
    if cvss is None:
        return UNSCORED_BAND
    if cvss >= 9.0:
        return "critical"
    if cvss >= 7.0:
        return "high"
    if cvss >= 4.0:
        return "medium"
    if cvss > 0.0:
        return "low"
    return "informational"


def _resolve_severity(finding: dict[str, Any]) -> str:
    """Normalize finding severity to a canonical CVSS band.

    Reads the stored EvaluatedFinding shape (``cvss.severity`` / ``cvss.base_score``)
    as well as flattened API shapes (``severity`` / ``cvss_score``).
    """
    cvss = finding.get("cvss") if isinstance(finding.get("cvss"), dict) else {}
    sev = finding.get("severity") or finding.get("cvss_severity") or cvss.get("severity")
    if hasattr(sev, "value"):
        sev = sev.value
    if isinstance(sev, str):
        sev_clean = sev.strip().lower()
        if sev_clean in CVSS_BAND_PENALTIES:
            return sev_clean
    score = finding.get("cvss_score")
    if score is None:
        score = cvss.get("base_score")
    if score is not None:
        try:
            return _cvss_score_to_band(float(score))
        except (ValueError, TypeError):
            pass
    return UNSCORED_BAND


def _grade_from_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 55:
        return "D"
    return "F"


def compute_posture(
    findings: list[dict[str, Any]],
    test_cases: list[dict[str, Any]] | None = None,
    categories_applicable: int = 8,
) -> dict[str, Any]:
    """
    Compute Security Posture Score before and after verification (FEATURES.md F6).
    Formula:
      confirmed penalties: critical 30, high 18, medium 9, low 3, informational 0
      inconclusive penalties: 2 each, capped at 10 total
      score_before = max(0, 100 - sum(confirmed_penalties + inconclusive_penalties))
      score_after = same formula, excluding findings whose verification outcome == "fixed"
    """
    confirmed_findings: list[dict[str, Any]] = []
    inconclusive_findings: list[dict[str, Any]] = []

    for f in findings:
        raw_status = f.get("status") or ""
        # model_dump() keeps enum members (EvaluationStatus.CONFIRMED) — use their value.
        status = str(getattr(raw_status, "value", raw_status)).lower()
        # Accept 'confirmed' or 'evaluated' with confirmed oracle
        if status in ("confirmed", "runtime_confirmed"):
            confirmed_findings.append(f)
        elif status in ("inconclusive", "candidate", "suspicion"):
            inconclusive_findings.append(f)

    # Compute categories tested
    tested_cats: set[str] = set()
    if test_cases:
        for tc in test_cases:
            cat = tc.get("category")
            if cat:
                tested_cats.add(str(cat).upper())
    for f in findings:
        cat = f.get("category")
        if cat:
            tested_cats.add(str(cat).upper())

    categories_tested_count = len(tested_cats) if tested_cats else min(len(findings), categories_applicable)
    categories_app = max(1, categories_applicable)
    coverage = round(min(1.0, categories_tested_count / categories_app), 2)
    tests_count = len(test_cases) if test_cases is not None else len(findings)

    # Inconclusive penalty
    inconclusive_penalty = min(MAX_INCONCLUSIVE_PENALTY, len(inconclusive_findings) * INCONCLUSIVE_UNIT_PENALTY)

    # Confirmed penalties before
    confirmed_penalty_before = 0
    confirmed_penalty_after = 0
    confirmed_counts_by_severity: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "informational": 0,
        UNSCORED_BAND: 0,
    }

    what_moved: list[dict[str, Any]] = []

    for cf in confirmed_findings:
        band = _resolve_severity(cf)
        pen = UNSCORED_PENALTY if band == UNSCORED_BAND else CVSS_BAND_PENALTIES[band]
        confirmed_penalty_before += pen
        confirmed_counts_by_severity[band] = confirmed_counts_by_severity.get(band, 0) + 1

        raw_outcome = (
            cf.get("verification_outcome")
            or (cf.get("verification") or {}).get("outcome")
            or ""
        )
        v_outcome = str(getattr(raw_outcome, "value", raw_outcome)).lower()

        is_fixed = v_outcome == "fixed"
        if not is_fixed:
            confirmed_penalty_after += pen

        what_moved.append({
            "finding_id": cf.get("id"),
            "title": cf.get("title") or cf.get("category") or "Vulnerability finding",
            "category": cf.get("category"),
            "severity": band,
            "penalty": pen,
            "verification_outcome": v_outcome or "unverified",
            "is_fixed": is_fixed,
        })

    # Scores (clamped to 0..100)
    score_before = max(0, 100 - (confirmed_penalty_before + inconclusive_penalty))
    score_after = max(0, 100 - (confirmed_penalty_after + inconclusive_penalty))

    grade_before = _grade_from_score(score_before)
    grade_after = _grade_from_score(score_after)

    limited_coverage = coverage < 0.50

    basis = (
        f"Based on {tests_count} tests across {categories_tested_count} of "
        f"{categories_app} categories. A high score means we did not find these problems — "
        f"not that none exist."
    )

    return {
        "version": POSTURE_VERSION,
        "before": score_before,
        "after": score_after,
        "grade_before": grade_before,
        "grade_after": grade_after,
        "coverage": coverage,
        "limited_coverage": limited_coverage,
        "basis": basis,
        "inputs": {
            "confirmed_counts": confirmed_counts_by_severity,
            "unscored_count": confirmed_counts_by_severity[UNSCORED_BAND],
            "unscored_penalty_each": UNSCORED_PENALTY,
            "inconclusive_count": len(inconclusive_findings),
            "inconclusive_penalty": inconclusive_penalty,
            "penalties_before": confirmed_penalty_before + inconclusive_penalty,
            "penalties_after": confirmed_penalty_after + inconclusive_penalty,
            "categories_tested": categories_tested_count,
            "categories_applicable": categories_app,
            "tests_count": tests_count,
        },
        "what_moved": what_moved,
    }
