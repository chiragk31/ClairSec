"""
LLMProvider Protocol definition (LLM.md §1).
No agent imports a vendor SDK; all agent interactions go through this protocol.
"""
from __future__ import annotations

from typing import Protocol
from app.llm.models import LLMRequest, LLMResponse, ModelDescriptor


class LLMProvider(Protocol):
    """Abstract interface implemented by AnthropicProvider and MockLLMProvider."""

    async def complete(self, *, request: LLMRequest) -> LLMResponse:
        """Execute completion with mandatory structured output validation."""
        ...

    @property
    def descriptor(self) -> ModelDescriptor:
        """Return the exact pinned model descriptor."""
        ...
