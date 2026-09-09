"""
Typed request/response envelopes and domain models for the LLM Layer.
Implements LLM.md §1, §2, §6, and §7.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Type
from pydantic import BaseModel, ConfigDict, Field


class TrustLevel(str, Enum):
    """Trust levels enforced by the type system (LLM.md §6)."""
    PRIVILEGED = "PRIVILEGED"      # Plans, decides, or authorizes; cannot contain raw Untrusted data
    QUARANTINED = "QUARANTINED"    # Extracts structured data from raw target text; no tools, narrow schema


class AgentName(str, Enum):
    """The four research agents."""
    BUILDER = "BUILDER"
    ATTACKER = "ATTACKER"
    EVALUATOR = "EVALUATOR"
    FIXER = "FIXER"


class ModelDescriptor(BaseModel):
    """
    Metadata for the model invocation recorded per call and per experiment record (LLM.md §1).
    Pinned to claude-opus-5 by default. temperature/top_p/seed are omitted for this model.
    """
    model_config = ConfigDict(frozen=True)

    provider: str                      # "anthropic" | "mock"
    model_id: str                      # "claude-opus-5", exact pinned string
    api_version: str | None = None
    max_output_tokens: int = 8192
    effort: str | None = "high"        # Anthropic: output_config.effort
    thinking: str | None = "adaptive"  # Anthropic: "adaptive" | "disabled" | None
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None


class TokenUsage(BaseModel):
    """Token consumption and estimated USD accounting (LLM.md §2, §9)."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class CallBudget(BaseModel):
    """Per-call resource and retry bounds (LLM.md §7)."""
    max_attempts: int = 3
    timeout_s: int = 120
    max_input_tokens: int = 100_000
    max_output_tokens: int = 8_000


class Message(BaseModel):
    """Message in the LLM conversation."""
    role: str  # "user" | "assistant" | "system"
    content: str


class Untrusted(BaseModel):
    """
    Anything derived from the target: source code, README, logs, HTTP responses.
    Implements LLM.md §6 and THREAT_MODEL.md C1.1.
    """
    content: str
    origin: str  # e.g. "file:app/main.py", "http:GET /documents/1", "container:logs"


class LLMRequest(BaseModel):
    """
    Strongly-typed request envelope for all agent LLM calls (LLM.md §2).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    prompt_id: str                          # e.g. "builder.route_extract"
    prompt_version: str                     # e.g. "v1"
    system: str                             # Loaded from versioned registry
    messages: list[Message]
    response_schema: Type[BaseModel]        # Mandatory structured output schema
    trust: TrustLevel
    scan_id: str
    agent: AgentName
    budget: CallBudget = Field(default_factory=CallBudget)


class LLMResponse(BaseModel):
    """
    Strongly-typed response envelope returning validated structured output (LLM.md §2).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parsed: BaseModel | None = None         # Populated if schema validation succeeds
    raw_text: str = ""                      # Retained for debugging/audit
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = 0
    attempts: int = 1
    finish_reason: str = "stop"
    descriptor: ModelDescriptor
    cache_hit: bool = False
    malformed_output: bool = False          # True if all attempts failed schema validation
    malformed_error: str | None = None
