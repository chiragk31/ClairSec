"""
Typed data schemas for the Builder Agent and AgentContext (LLM.md §1, DATA_MODEL.md §1).
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RouteItem(BaseModel):
    """Normalized route description in the project inventory."""
    model_config = ConfigDict(extra="ignore")

    route_template: str               # e.g. "/documents/{doc_id}", normalized
    method: str                       # "GET", "POST", "PUT", "DELETE", "PATCH"
    handler_name: str
    source_file: str
    source_line_range: tuple[int, int]
    requires_auth: bool = False
    auth_dependency: str | None = None
    resource_owner_param: str | None = None
    input_fields: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    extra_fields_allowed: bool = False
    is_debug_or_internal: bool = False


class AuthSemanticInventory(BaseModel):
    """Narrow schema for quarantined LLM extraction turn (LLM.md §6)."""
    route_template: str
    method: str
    requires_auth: bool
    auth_type: str | None = None
    resource_owner_param: str | None = None
    extra_fields_allowed: bool = False
    is_debug_or_internal: bool = False


class RouteSemanticBatch(BaseModel):
    """Batch schema emitted by the quarantined LLM call."""
    routes: list[AuthSemanticInventory] = Field(default_factory=list)


class TestPrincipal(BaseModel):
    """Test identity used for authenticated security testing."""
    user_id: str
    username: str
    token: str
    display_name: str = ""
    role: str = "member"
    is_admin: bool = False


class AgentContext(BaseModel):
    """
    Typed context document produced by the Builder Agent for downstream agents.
    Provides verified route table, auth schemes, and test identities.
    """
    model_config = ConfigDict(extra="ignore")

    project_id: str
    scan_id: str
    routes: list[RouteItem]
    auth_schemes: list[str] = Field(default_factory=list)
    principals: list[TestPrincipal] = Field(default_factory=list)
    canary_clean: bool = True
    created_at: str = ""
