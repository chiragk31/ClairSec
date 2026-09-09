"""
Pydantic models for MongoDB persistence.

These are the canonical typed schemas for all data stored in MongoDB.
API request/response schemas (in app/api/) may differ; they import from here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


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

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    model_config = {"populate_by_name": True}


class ScanRecord(BaseModel):
    """
    Persisted record of a security scan run (DATA_MODEL.md §3).
    """
    id: str = Field(default_factory=_new_id)
    project_id: str
    project_name: str = ""
    arm: str = "multi_agent"
    state: str = "queued"  # "queued", "running", "completed", "failed", "cancelled"
    stage: str = "queued"  # "queued", "builder", "attacker", "evaluator", "fixer", "verifier", "completed", "failed"
    created_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cancel_requested: bool = False
    terminal_reason: str | None = None
    error: str | None = None
    findings_confirmed: int = 0
    counters: dict[str, int] = Field(default_factory=lambda: {
        "tests_executed": 0,
        "candidates": 0,
        "confirmed": 0,
        "rejected": 0,
        "inconclusive": 0,
        "fixes_proposed": 0,
        "fixes_applied": 0,
        "fixes_verified": 0,
    })

    model_config = {"populate_by_name": True}
