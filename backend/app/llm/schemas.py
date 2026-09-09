"""
LLM output schemas — Pydantic models for validating structured LLM responses.

Per docs/RULES.md §3: validate all structured model output with schemas.
LLM output is treated as untrusted data and parsed defensively.

All schemas used by Builder (and later Attacker, Evaluator, Fixer) are defined here
so they can be shared and versioned independently of the agents.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Builder output schemas
# ─────────────────────────────────────────────────────────────────────────────


class RouteInfo(BaseModel):
    """A single discovered API route."""
    path: str
    methods: list[str] = Field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    # Security analysis fields (filled by Builder's LLM analysis)
    auth_required: bool | None = None
    """True if any auth mechanism is detected on this route. None = unknown."""
    auth_schemes: list[str] = Field(default_factory=list)
    """e.g. ['bearer', 'api_key']. Empty if auth_required is False or unknown."""


class AuthMechanism(BaseModel):
    """Detected authentication/authorization mechanism in the project."""
    kind: str
    """e.g. 'bearer_token', 'api_key_header', 'oauth2', 'cookie_session', 'none', 'unknown'"""
    details: str | None = None
    source_location: str | None = None
    """Relative path to the file where this was detected."""


class DependencyInfo(BaseModel):
    """A parsed dependency with optional security notes."""
    name: str
    version_spec: str | None = None
    """e.g. '>=0.100.0'. None if not specified."""
    notes: str | None = None
    """Any notable security or structural observation. Builder does NOT confirm vulnerabilities."""


class DatabaseAccessInfo(BaseModel):
    """Detected database/data-store access patterns."""
    kind: str
    """e.g. 'mongodb', 'postgresql', 'sqlite', 'redis', 'unknown'"""
    libraries: list[str] = Field(default_factory=list)
    """Detected ORM/driver library names."""
    notes: str | None = None


class BuilderAnalysis(BaseModel):
    """
    Structured output of the Builder agent.

    IMPORTANT: This record contains project inventory only.
    The Builder does NOT produce security findings or vulnerability confirmations.
    See docs/PRD.md §7 and docs/RULES.md §2.
    """
    entry_point: str | None = None
    """Relative path to the FastAPI application entry point."""

    openapi_source: str = "unknown"
    """How the OpenAPI schema was obtained: 'live' | 'static_fallback' | 'unavailable'"""

    routes: list[RouteInfo] = Field(default_factory=list)
    """All discovered API routes."""

    auth_mechanisms: list[AuthMechanism] = Field(default_factory=list)
    """Detected authentication/authorization mechanisms."""

    dependencies: list[DependencyInfo] = Field(default_factory=list)
    """Project dependencies parsed from the manifest."""

    database_access: list[DatabaseAccessInfo] = Field(default_factory=list)
    """Detected database or data-store access patterns."""

    configuration_notes: list[str] = Field(default_factory=list)
    """Notable configuration observations (no vulnerability claims)."""

    analysis_notes: str | None = None
    """Free-form summary from the Builder's LLM analysis — for human review only."""

    gaps: list[str] = Field(default_factory=list)
    """
    Explicit gaps in this analysis.
    Per docs/RULES.md §2: represent gaps honestly rather than guessing.
    Examples: 'OpenAPI schema unavailable', 'Could not parse entry point'.
    """
