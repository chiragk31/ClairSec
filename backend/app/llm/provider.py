"""
LLM provider abstraction.

Per docs/ARCHITECTURE.md §2 and docs/RULES.md §3:
  - Do not couple the product to one LLM vendor.
  - Treat LLM output as untrusted data; validate with Pydantic schemas.
  - Record model/provider information for research reproducibility.
  - Handle malformed responses gracefully with bounded retries.
  - Never expose environment variables or credentials to the model.

Provider selection is controlled by settings.llm_provider:
  "gemini"      → GeminiProvider (Google Generative AI SDK)
  "mock"        → MockProvider   (deterministic, for tests — no real calls)

To add a new provider, implement BaseLLMProvider and register it in get_provider().
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LLMResponse:
    """
    Typed container for a raw LLM response.

    raw_text: the string returned by the provider (treated as untrusted).
    provider: provider name for reproducibility logging.
    model: model identifier for reproducibility logging.
    prompt_version: the prompt template version used (for research reproducibility).
    """
    raw_text: str
    provider: str
    model: str
    prompt_version: str


@dataclass(frozen=True)
class ProviderInfo:
    """Metadata about the active provider for reproducibility records."""
    provider: str
    model: str


# ─────────────────────────────────────────────────────────────────────────────
# Abstract interface
# ─────────────────────────────────────────────────────────────────────────────


class BaseLLMProvider(ABC):
    """
    Interface that all LLM providers must implement.

    generate() is the only required method. It takes a prompt string and returns
    an LLMResponse. The caller is responsible for parsing and validating the text.

    SECURITY:
      - Implementations must NOT forward host environment variables to the model.
      - Implementations must NOT log the full prompt content at INFO level
        (prompts may contain project source excerpts treated as untrusted).
    """

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return provider/model metadata for reproducibility recording."""

    @abstractmethod
    def generate(self, prompt: str, prompt_version: str) -> LLMResponse:
        """
        Send the prompt to the LLM and return a raw LLMResponse.

        Args:
            prompt: the complete prompt string (already assembled by the caller).
            prompt_version: a stable identifier for the prompt template used,
                            stored alongside any output for research reproducibility.

        Returns:
            LLMResponse with the raw text and metadata.

        Raises:
            LLMProviderError: on unrecoverable API or network error.
        """


class LLMProviderError(Exception):
    """Raised when the LLM provider returns an unrecoverable error."""


# ─────────────────────────────────────────────────────────────────────────────
# Mock provider — deterministic, no network calls, used in tests
# ─────────────────────────────────────────────────────────────────────────────


class MockProvider(BaseLLMProvider):
    """
    Test-only provider. Returns a pre-set response without making any real calls.

    Usage:
        provider = MockProvider(response_text='{"key": "value"}')
    """

    def __init__(self, response_text: str = "{}") -> None:
        self._response = response_text

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(provider="mock", model="mock")

    def generate(self, prompt: str, prompt_version: str) -> LLMResponse:
        logger.debug("MockProvider returning canned response (prompt_version=%s)", prompt_version)
        return LLMResponse(
            raw_text=self._response,
            provider="mock",
            model="mock",
            prompt_version=prompt_version,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Gemini provider — Google Generative AI SDK
# ─────────────────────────────────────────────────────────────────────────────


class GeminiProvider(BaseLLMProvider):
    """
    Concrete provider using Google Generative AI (Gemini).

    Requires GEMINI_API_KEY in the environment or .env file.
    Model is configurable via settings.llm_model.
    """

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMProviderError(
                "Gemini API key is not configured. "
                "Set GEMINI_API_KEY in your .env file or environment."
            )
        try:
            import google.generativeai as genai  # type: ignore[import]
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(model)
            self._model_name = model
        except ImportError as exc:
            raise LLMProviderError(
                "google-generativeai is not installed. "
                "Run: pip install google-generativeai"
            ) from exc

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(provider="gemini", model=self._model_name)

    def generate(self, prompt: str, prompt_version: str) -> LLMResponse:
        """
        Call Gemini and return the response text.

        SECURITY: The prompt is logged only at DEBUG level (may contain
        untrusted project content). The response is returned as-is — callers
        must validate against a Pydantic schema before using.
        """
        logger.debug(
            "GeminiProvider: calling model=%s prompt_version=%s prompt_len=%d",
            self._model_name,
            prompt_version,
            len(prompt),
        )
        try:
            response = self._model.generate_content(prompt)
            raw = response.text
            logger.debug(
                "GeminiProvider: response received len=%d", len(raw)
            )
            return LLMResponse(
                raw_text=raw,
                provider="gemini",
                model=self._model_name,
                prompt_version=prompt_version,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"Gemini API call failed: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────


def get_provider() -> BaseLLMProvider:
    """
    Return the configured LLM provider instance.

    Provider is selected by settings.llm_provider. This is the single place
    that couples the rest of the codebase to a concrete provider.
    """
    from app.core.config import settings  # local import to avoid circular deps

    name = settings.llm_provider.lower()
    if name == "mock":
        return MockProvider()
    elif name == "gemini":
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.llm_model,
        )
    else:
        raise LLMProviderError(
            f"Unknown LLM provider '{name}'. "
            "Supported values: gemini, mock. "
            "Set LLM_PROVIDER in your .env file."
        )
