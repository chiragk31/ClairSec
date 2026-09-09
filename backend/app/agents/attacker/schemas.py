"""
Schemas for the Attacker Agent (DATA_MODEL.md §3, VULN_TAXONOMY.md §4).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class TestCaseRecord(BaseModel):
    """
    Every executed test case, whether or not it fired (DATA_MODEL.md §3 test_cases).
    Denominator for tests executed and basis for replay.
    """
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    scan_id: str
    category: str
    route_template: str               # e.g. "/documents/{doc_id}", normalized
    method: str                       # GET, POST, PUT, etc.
    principal_id: str | None = None
    request: dict[str, Any]
    response: dict[str, Any]
    oracle_result: dict[str, Any]     # fired: bool, rule_id, rationale
    generated_by: dict[str, Any] = Field(
        default_factory=lambda: {
            "agent": "attacker",
            "prompt_id": "attacker_test_generator",
            "prompt_version": "v1.0",
            "llm_call_id": None,
        }
    )
    executed_at: str = Field(default_factory=_now_iso)


class CandidateFinding(BaseModel):
    """
    Candidate vulnerability emitted by the Attacker Agent before Evaluator triage.
    Matches DATA_MODEL.md §3 findings collection.
    """
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    scan_id: str
    project_id: str
    title: str
    category: str
    cwe: list[str]
    route_template: str               # Normalized template, never an instantiated id
    method: str
    description: str
    impact: str
    runtime_confirmed: bool = True
    oracle_rule_id: str
    cvss: Any | None = None
    confidence: Any | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reproduction_summary: str = ""
    source_locations: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "candidate"
    created_at: str = Field(default_factory=_now_iso)


class AttackerScanResult(BaseModel):
    """Container for tests executed and candidate findings produced during an Attacker scan."""
    model_config = ConfigDict(extra="ignore")

    scan_id: str
    project_id: str
    test_cases: list[TestCaseRecord]
    findings: list[CandidateFinding]
    counters: dict[str, int] = Field(default_factory=dict)


def normalize_route_path(path: str, known_routes: list[str]) -> str:
    """
    Match an instantiated path (e.g. /documents/doc_bob_02) against known route templates
    (e.g. /documents/{doc_id}) to return the canonical normalized route template.
    """
    clean_path = path.split("?")[0].rstrip("/") or "/"

    for tmpl in known_routes:
        clean_tmpl = tmpl.split("?")[0].rstrip("/") or "/"
        # Convert template {param} to regex ([^/]+)
        pattern = re.sub(r"\{[^}]+\}", r"[^/]+", clean_tmpl)
        if re.fullmatch(f"^{pattern}$", clean_path):
            return clean_tmpl

    return clean_path
