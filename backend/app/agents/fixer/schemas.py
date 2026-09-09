"""
Data models and schemas for Phase 7 Fixer Agent (DATA_MODEL.md §3 patches, PHASES.md Phase 7).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class PatchValidation(BaseModel):
    """
    Validation outcomes persisted as data (DATA_MODEL.md §3, THREAT_MODEL.md T8/C2.1).
    Ensures rejected patches are analysable rather than merely logged.
    """
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    ast_parsed: bool = False
    path_check_passed: bool = False
    size_ok: bool = False


class DiffStats(BaseModel):
    """Line and file counts for the unified diff."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    files: int = 0
    added: int = 0
    removed: int = 0


class FileDiff(BaseModel):
    """Single file unified diff proposal."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    path: str
    diff: str


class FixerProposal(BaseModel):
    """Structured LLM output for patch proposal (LLM.md §6 capability starvation)."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    root_cause: str
    rationale: str
    files: list[FileDiff] = Field(default_factory=list)


class PatchRecord(BaseModel):
    """
    Canonical record representing a proposed and evaluated patch in patches collection.
    (DATA_MODEL.md §3 patches).
    """
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    finding_id: str
    scan_id: str
    project_id: str = ""
    files: list[FileDiff] = Field(default_factory=list)
    diff_stats: DiffStats = Field(default_factory=DiffStats)
    rationale: str = ""
    root_cause: str = ""
    prompt_version: str = "v1.0"
    llm_call_id: str | None = None
    applied: bool = False
    applied_at: str | None = None
    apply_error: str | None = None
    workspace: str = "modified"
    validation: PatchValidation = Field(default_factory=PatchValidation)
    created_at: str = Field(default_factory=_now_iso)


class FixerResult(BaseModel):
    """Summary result of the Fixer Agent execution across confirmed findings."""
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    scan_id: str
    project_id: str
    patches: list[PatchRecord] = Field(default_factory=list)
    applied_count: int = 0
    rejected_count: int = 0
