"""
Pydantic models for MongoDB persistence.

These are the canonical typed schemas for all data stored in MongoDB.
API request/response schemas (in app/api/) may differ; they import from here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ValidationStatus(str, Enum):
    """Result of static inspection of an imported project."""
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class IsolationStatus(str, Enum):
    """
    Tracks the Docker lifecycle state of an imported project.

    Transitions:
        pending → building → ready (health check passed)
        ready   → running  (scan has started using this container)
        running → stopped  (scan completed or user stopped)
        any     → import_failed (build/startup/health check failed)
    """
    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"       # Container healthy, awaiting scan
    RUNNING = "running"   # Scan is actively using this container
    STOPPED = "stopped"   # Container stopped, workspace still present
    IMPORT_FAILED = "import_failed"  # Could not build / start / health-check


class JobStatus(str, Enum):
    """Lifecycle status of a background job (OPERATIONS §5, RULES §5a)."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class JobRecord(BaseModel):
    """Persisted record of an asynchronous background job."""
    id: str = Field(default_factory=_new_id)
    project_id: str
    status: JobStatus = JobStatus.PENDING
    stage: str = "queued"
    cancel_requested: bool = False
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    model_config = {"populate_by_name": True}


class ProjectRecord(BaseModel):
    """
    Persisted record of an imported FastAPI project.

    This is the single source of truth for what has been imported.
    The original source_path is never modified; it is treated as immutable input.
    """
    id: str = Field(default_factory=_new_id)
    schema_version: int = 1
    name: str
    source_path: str
    """Absolute path to the user's original project directory. Never modified."""

    # ── Phase 2 fields ────────────────────────────────────────────────────────
    validation_status: ValidationStatus = ValidationStatus.UNKNOWN
    validation_errors: list[str] = Field(default_factory=list)
    """Human-readable list of reasons why validation failed (if status=invalid)."""

    entry_point: str | None = None
    """Relative path within the project to the detected FastAPI entry module."""

    dependency_file: str | None = None
    """Relative path to the dependency manifest (requirements.txt / pyproject.toml)."""

    dependencies: list[str] = Field(default_factory=list)
    """Parsed top-level dependency names from the manifest."""

    isolation_ready: bool = False
    """
    Static assessment: True if the project appears ready for isolation.
    Does NOT mean Docker has run. Actual Docker lifecycle tracked by isolation_status.
    """

    # ── Phase 3 fields ────────────────────────────────────────────────────────
    isolation_status: IsolationStatus = IsolationStatus.PENDING
    """Current Docker lifecycle state of this project."""

    workspace_path: str | None = None
    """
    Absolute path to the scan workspace (a copy of source_path).
    Never the same as source_path. Created by WorkspaceManager in Phase 3.
    """

    container_id: str | None = None
    """Docker container ID, set when the container is running."""

    container_name: str | None = None
    """Docker container name, deterministic: clairsec-target-{project_id[:8]}."""

    proxy_container_id: str | None = None
    """Docker scanner proxy container ID."""

    proxy_port: int | None = None
    """Host port bound to 127.0.0.1 for scanner proxy traffic to this target."""

    isolation_error: str | None = None
    """
    Human-readable reason for import_failed status.
    Treated as untrusted text (may come from Docker build output).
    """

    # ── Phase V3 fields: Git & GitHub import (FEATURES.md F2) ─────────────────
    commit_sha: str | None = None
    authorization_affirmed: bool = False
    authorization_affirmed_at: datetime | None = None
    import_source: str = "local"  # "local" | "git"
    git_url: str | None = None
    git_ref: str | None = None
    git_subdir: str | None = None
    import_notes: list[str] = Field(default_factory=list)
    # Credentials found committed in the imported code: type/file/line + masked preview only.
    exposed_secrets: list[dict] = Field(default_factory=list)
    monorepo_candidates: list[dict] = Field(default_factory=list)
    file_count: int = 0
    repo_size_bytes: int = 0
    origin: str = "user_project"  # "user_project" | "demo_fixture" (FEATURES.md F4)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _detect_origin(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "origin" not in data or data["origin"] is None:
                source_p = data.get("source_path")
                if source_p:
                    try:
                        from app.targets.handle import is_trusted_fixture_path
                        if is_trusted_fixture_path(source_p):
                            data["origin"] = "demo_fixture"
                    except Exception:
                        pass
        return data


class ScanRecord(BaseModel):
    """
    Persisted record of a security scan run (DATA_MODEL.md §3).
    """
    id: str = Field(default_factory=_new_id)
    project_id: str
    project_name: str = ""
    arm: str = "multi_agent"
    mode: str = "live"  # "live", "live_local_ai", "live_offline_ai", "demo", "recorded" (FEATURES.md F4)
    state: str = "queued"  # "queued", "running", "completed", "failed", "cancelled"
    stage: str = "queued"  # "queued", "builder", "attacker", "evaluator", "fixer", "verifier", "completed", "failed"
    created_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cancel_requested: bool = False
    terminal_reason: str | None = None
    error: str | None = None
    findings_confirmed: int = 0
    # Which model produced the AI proposals in this scan (recorded for reports, LLM.md §1).
    llm: dict | None = None  # {provider, model_id, prompt_registry_digest}
    posture: dict | None = None  # {version: "posture_v1", before, after, grade_before, grade_after, coverage, inputs} (FEATURES.md F6)
    counters: dict[str, int] = Field(default_factory=lambda: {
        "endpoints_discovered": 0,
        "tests_generated": 0,
        "tests_executed": 0,
        "tests_skipped_policy": 0,
        "tests_failed_error": 0,
        "candidates": 0,
        "confirmed": 0,
        "rejected": 0,
        "inconclusive": 0,
        "fixes_proposed": 0,
        "fixes_applied": 0,
        "fixes_verified": 0,
    })
    stage_durations: dict[str, float] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class EventKind(str, Enum):
    """Closed enum of allowed agent event kinds (FEATURES.md F5)."""
    STAGE_STARTED = "stage_started"
    STAGE_FINISHED = "stage_finished"
    ENDPOINT_DISCOVERED = "endpoint_discovered"
    TEST_PLANNED = "test_planned"
    REQUEST_SENT = "request_sent"
    ORACLE_FIRED = "oracle_fired"
    ORACLE_CLEAR = "oracle_clear"
    FINDING_CANDIDATE = "finding_candidate"
    FINDING_CONFIRMED = "finding_confirmed"
    FINDING_REJECTED = "finding_rejected"
    FINDING_INCONCLUSIVE = "finding_inconclusive"
    PATCH_PROPOSED = "patch_proposed"
    PATCH_REJECTED = "patch_rejected"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_RESULT = "verification_result"
    BUDGET = "budget"
    ERROR = "error"
    INFO = "info"


class AgentEventRecord(BaseModel):
    """
    Persisted record of an agent event (DATA_MODEL.md §3, FEATURES.md F5).
    """
    id: str = Field(default_factory=_new_id)
    scan_id: str
    seq: int
    timestamp: datetime = Field(default_factory=_now)
    agent: str
    kind: str
    title: str
    detail: str = ""  # capped at 4 KB
    plain: str = ""
    severity: str | None = None
    refs: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] | None = None
    schema_version: int = 1

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Phase V3 models: Autopilot & Pipelines (FEATURES.md F3)
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStage(str, Enum):
    IMPORT = "import"
    ISOLATE = "isolate"
    SCAN = "scan"
    REPORT = "report"


class PipelineStageInfo(BaseModel):
    status: str = "pending"  # pending, running, completed, failed, cancelled, skipped
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_s: float = 0.0
    line: str = ""
    error: str | None = None
    fix_hint: str | None = None


class PipelineRecord(BaseModel):
    id: str = Field(default_factory=_new_id)
    project_id: str | None = None
    report_id: str | None = None
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage = PipelineStage.IMPORT
    stages: dict[str, PipelineStageInfo] = Field(default_factory=dict)
    import_job_id: str | None = None
    # The GitHub import request, kept so a resumed pipeline can redo the import.
    git_import: dict | None = None
    isolation_job_id: str | None = None
    scan_id: str | None = None
    error: str | None = None
    fix_hint: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    model_config = {"populate_by_name": True}


