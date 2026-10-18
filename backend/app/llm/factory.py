"""
Single place that turns configuration into an LLMProvider (LLM.md §1).

Scans choose their provider per run (FEATURES.md F4): Demo-mode scans always get
the offline mock so no model-written code can reach the host; every other scan
gets the configured provider. Nothing here mutates global settings.
"""
from __future__ import annotations

from app.core.config import settings
from app.llm.provider import LLMProvider
from app.llm.providers.mock_provider import MockLLMProvider

OFFLINE_PROVIDERS = frozenset({"mock", "replay"})


def build_provider(name: str | None = None) -> LLMProvider:
    """Build the provider called `name` (defaults to settings.llm_provider)."""
    name = (name or settings.llm_provider or "mock").lower()
    if name == "anthropic":
        if not settings.llm_api_key.strip():
            raise ValueError("LLM_PROVIDER=anthropic requires LLM_API_KEY.")
        from app.llm.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings.llm_api_key, model_id=settings.llm_model_id)
    if name == "ollama":
        from app.llm.providers.ollama_provider import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_url, model_id=settings.ollama_model)
    return MockLLMProvider()


def provider_name_for_scan(project_origin: str | None) -> str:
    """Demo fixtures are always scanned with the offline provider."""
    if project_origin == "demo_fixture":
        return "mock"
    return (settings.llm_provider or "mock").lower()


def is_offline_provider(provider: LLMProvider | None) -> bool:
    if provider is None:
        return True
    return provider.descriptor.provider in OFFLINE_PROVIDERS
