"""
Tests for versioned prompt registry and digest stability (LLM.md §4).
"""
import pytest
from app.llm.prompts.registry import registry, PromptNotFoundError


def test_prompt_registry_loads_builder_prompts():
    prompts = registry.list_prompts()
    assert ("builder.route_extract", "v1") in prompts


def test_prompt_registry_digest_is_deterministic():
    digest1 = registry.digest
    assert len(digest1) == 64  # SHA-256 hex string

    # Re-computing digest should be identical
    assert registry.digest == digest1


def test_prompt_retrieval_and_formatting():
    content = registry.get_prompt("builder.route_extract", "v1")
    assert "Builder Agent" in content
    assert "RULES" in content


def test_missing_prompt_raises_not_found():
    with pytest.raises(PromptNotFoundError):
        registry.get_prompt("nonexistent.agent", "v99")
