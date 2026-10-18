"""
Evidence Chain of Custody & Provenance Assembler (FEATURES.md F7).

Assembles the 6-step chain strictly from stored database records. When a record
or field is missing the step says so ("not recorded") — it never substitutes a
plausible default. A provenance panel that invents an HTTP status, a CVSS score
or a reproduction count is exactly the failure F7 exists to prevent.
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

NOT_RECORDED = "not recorded"


def _val(x: Any) -> Any:
    """Unwrap enum members from documents written before values were normalised."""
    return getattr(x, "value", x)


def _get(d: dict[str, Any] | None, *path: str) -> Any:
    cur: Any = d or {}
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


async def assemble_finding_provenance(
    finding_id: str,
    db: AsyncIOMotorDatabase,
) -> dict[str, Any]:
    findings_col = db["findings"]
    test_cases_col = db["test_cases"]
    patches_col = db["patches"]
    verification_col = db["verification_results"]

    finding = await findings_col.find_one({"id": finding_id})
    if not finding:
        raise ValueError(f"Finding '{finding_id}' not found.")

    # The originating test case: first evidence id, else any test case linked to the finding.
    evidence_ids = finding.get("evidence_ids") or []
    test_case = None
    for tc_id in [finding.get("test_case_id"), *evidence_ids]:
        if tc_id:
            test_case = await test_cases_col.find_one({"id": tc_id, "kind": {"$ne": "replay"}}) or \
                await test_cases_col.find_one({"id": tc_id})
            if test_case:
                break

    patch = await patches_col.find_one({"finding_id": finding_id})
    verification = await verification_col.find_one({"finding_id": finding_id})

    status = str(_val(finding.get("status")) or "").lower()
    is_confirmed = status in ("confirmed", "runtime_confirmed")
    oracle = (test_case or {}).get("oracle_result") or {}
    conf_inputs = _get(finding, "confidence", "inputs") or {}
    oracle_fired = bool(oracle.get("fired")) if oracle else bool(conf_inputs.get("oracle_fired"))
    has_oracle_record = bool(oracle) or "oracle_fired" in conf_inputs

    steps: list[dict[str, Any]] = []

    # 1 — AI proposal (the attacker planned the test)
    req = (test_case or {}).get("request") or {}
    method = (test_case or {}).get("method") or finding.get("method")
    route = (test_case or {}).get("route_template") or finding.get("route_template")
    gen = (test_case or {}).get("generated_by") or {}
    steps.append({
        "step_number": 1,
        "who": "AI proposal",
        "action": "Attacker proposed the test",
        "title": f"Planned {finding.get('category', 'security')} probe",
        "status": "completed" if test_case else "unknown",
        "timestamp": (test_case or {}).get("created_at") or (test_case or {}).get("executed_at"),
        "record_id": (test_case or {}).get("id"),
        "record_type": "test_case",
        "detail": f"Target: {method or '?'} {route or '?'}"
        + (f" · prompt {gen.get('prompt_id')} {gen.get('prompt_version')}" if gen.get("prompt_id") else ""),
    })

    # 2 — Platform sent the request
    resp = (test_case or {}).get("response") or {}
    http_status = resp.get("status") if resp.get("status") is not None else resp.get("status_code")
    elapsed = resp.get("elapsed_ms")
    steps.append({
        "step_number": 2,
        "who": "Platform code",
        "action": "Platform sent the HTTP request (scope-locked client)",
        "title": f"HTTP {http_status}" if http_status is not None else f"HTTP status {NOT_RECORDED}",
        "status": "completed" if http_status is not None else "unknown",
        "timestamp": (test_case or {}).get("executed_at"),
        "record_id": (test_case or {}).get("id"),
        "record_type": "http_exchange",
        "detail": f"{req.get('method', method or '?')} {req.get('path') or req.get('url') or route or '?'}"
        + (f" · {float(elapsed):.0f} ms" if isinstance(elapsed, (int, float)) else ""),
    })

    # 3 — Oracle verdict (platform code, never the LLM)
    rule = oracle.get("rule_id") or finding.get("oracle_rule_id")
    steps.append({
        "step_number": 3,
        "who": "Platform code",
        "action": f"Oracle {rule or NOT_RECORDED} evaluated",
        "title": (f"Oracle {rule} fired" if oracle_fired else f"Oracle {rule} clear")
        if has_oracle_record else f"Oracle result {NOT_RECORDED}",
        "status": ("completed" if oracle_fired else "failed") if has_oracle_record else "unknown",
        "timestamp": (test_case or {}).get("executed_at"),
        "record_id": (test_case or {}).get("id"),
        "record_type": "oracle_result",
        "detail": oracle.get("rationale") or NOT_RECORDED,
    })

    # 4 — Independent reproduction by the evaluator
    reproduced = conf_inputs.get("reproduced_n_times")
    steps.append({
        "step_number": 4,
        "who": "Platform code",
        "action": "Evaluator re-ran the attack independently",
        "title": f"Reproduced {reproduced} time(s)" if reproduced is not None else f"Reproduction {NOT_RECORDED}",
        "status": "completed" if (reproduced or 0) > 0 else ("unknown" if reproduced is None else "failed"),
        "timestamp": finding.get("created_at"),
        "record_id": finding_id,
        "record_type": "evaluator_reproduction",
        "detail": finding.get("reproduction_summary") or finding.get("status_reason") or NOT_RECORDED,
    })

    # 5 — Severity computed by platform code from CVSS inputs
    base_score = _get(finding, "cvss", "base_score")
    vector = _get(finding, "cvss", "vector_string")
    band = _val(_get(finding, "cvss", "severity"))
    steps.append({
        "step_number": 5,
        "who": "Platform code",
        "action": "CVSS inputs → computed score",
        "title": f"CVSS {base_score} ({str(band).upper()})" if base_score is not None else f"CVSS {NOT_RECORDED}",
        "status": "completed" if base_score is not None else "unknown",
        "timestamp": finding.get("created_at"),
        "record_id": finding_id,
        "record_type": "cvss_calculation",
        "detail": f"Vector: {vector}" if vector else NOT_RECORDED,
    })

    # 6 — Fix verification
    v_outcome = _val((verification or {}).get("outcome"))
    steps.append({
        "step_number": 6,
        "who": "Platform code",
        "action": "Fix re-tested",
        "title": f"Fix status: {str(v_outcome).replace('_', ' ').title()}" if v_outcome
        else ("Patch proposed — not yet verified" if patch else "No fix yet"),
        "status": "completed" if v_outcome == "fixed"
        else ("failed" if v_outcome in ("regressed", "unresolved") else "unverified"),
        "timestamp": (verification or {}).get("created_at"),
        "record_id": (verification or {}).get("id") or (patch or {}).get("id"),
        "record_type": "verification_result",
        "detail": (verification or {}).get("outcome_reason") or NOT_RECORDED,
    })

    # The confirmed badge requires an actual oracle record that fired.
    show_confirmed = is_confirmed and has_oracle_record and oracle_fired
    return {
        "finding_id": finding_id,
        "scan_id": finding.get("scan_id"),
        "category": finding.get("category"),
        "status": finding.get("status"),
        "is_confirmed": is_confirmed,
        "has_oracle_evidence": has_oracle_record and oracle_fired,
        "lane": "confirmed" if show_confirmed else "candidates",
        "badge": "Runtime-confirmed · oracle-verified" if show_confirmed else "Source suspicion — not confirmed",
        "steps": steps,
    }
