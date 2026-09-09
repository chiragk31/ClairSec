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


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class ProjectRecord(BaseModel):
    """
    Persisted record of an imported FastAPI project.

    This is the single source of truth for what has been imported.
    The original source_path is never modified; it is treated as immutable input.
    """
    id: str = Field(default_factory=_new_id)
    name: str
    source_path: str
    """Absolute path to the user's original project directory. Never modified."""

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
    Does NOT mean Docker has run. Actual Docker lifecycle is Phase 3.
    """

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    model_config = {"populate_by_name": True}
