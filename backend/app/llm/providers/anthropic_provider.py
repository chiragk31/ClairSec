"""
Anthropic SDK adapter for claude-opus-5 (LLM.md §1, §3, §5, §7).
This is the ONLY file in the repository that imports the anthropic SDK.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any
import anthropic
from pydantic import BaseModel, ValidationError

from app.llm.models import (
    LLMRequest,
    LLMResponse,
    Message,
    ModelDescriptor,
    TokenUsage,
)


def _is_retryable_transport_error(err: Exception) -> bool:
    """
    Determine if an exception is a transient network, rate limit, or 5xx error (LLM.md §7).
    Never retries schema violations, refusals, or client errors (e.g. 400, 401).
    """
    if isinstance(
        err,
        (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
            asyncio.TimeoutError,
        ),
    ):
        return True
    if isinstance(err, anthropic.APIStatusError) and err.status_code in (429, 500, 502, 503, 504, 529):
        return True
    return False


class AnthropicProvider:
    """
    Official Anthropic SDK implementation pinned to claude-opus-5.
    Sends effort + adaptive thinking; omits temperature, top_p, and seed.
    Mandatory structured output with single repair retry on validation error.
    Exponential backoff with full jitter on transport/rate-limit errors.
    """

    def __init__(
        self,
        api_key: str,
        model_id: str = "claude-opus-5",
        client: anthropic.AsyncAnthropic | None = None,
    ):
        self._api_key = api_key
        self._model_id = model_id
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)
        self._descriptor = ModelDescriptor(
            provider="anthropic",
            model_id=self._model_id,
            api_version="2023-06-01",
            max_output_tokens=8192,
            effort="high",
            thinking="adaptive",
            temperature=None,
            top_p=None,
            seed=None,
        )

    @property
    def descriptor(self) -> ModelDescriptor:
        return self._descriptor

    async def _create_message_with_backoff(
        self, call_kwargs: dict[str, Any], max_attempts: int
    ) -> Any:
        """Execute client.messages.create with exponential backoff and full jitter (LLM.md §7)."""
        max_retries = max(1, max_attempts)
        for attempt in range(1, max_retries + 1):
            try:
                return await self._client.messages.create(**call_kwargs)
            except Exception as exc:
                if _is_retryable_transport_error(exc) and attempt < max_retries:
                    # Exponential backoff with full jitter: base 1s, cap 30s
                    base_backoff = min(30.0, 1.0 * (2 ** (attempt - 1)))
                    jittered_sleep = random.uniform(0.0, base_backoff)
                    await asyncio.sleep(jittered_sleep)
                    continue
                raise

    async def complete(self, *, request: LLMRequest) -> LLMResponse:
        """
        Execute request with native structured output parsing and 1 repair retry on failure.
        """
        start_time = time.perf_counter()
        schema = request.response_schema

        # Build message history
        anthropic_messages = [{"role": m.role, "content": m.content} for m in request.messages]

        # Call 1: Initial Attempt
        try:
            call_kwargs: dict[str, Any] = {
                "model": self._model_id,
                "max_tokens": request.budget.max_output_tokens,
                "system": request.system,
                "messages": anthropic_messages,
                "thinking": {"type": "adaptive"},
                "output_config": {
                    "effort": "high",
                    "format": {
                        "type": "json_schema",
                        "schema": schema.model_json_schema(),
                    },
                },
            }

            resp = await self._create_message_with_backoff(
                call_kwargs, request.budget.max_attempts
            )

            # Fix 3: Handle model refusal distinctly BEFORE attempting schema validation
            if getattr(resp, "stop_reason", "") == "refusal":
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                return LLMResponse(
                    parsed=None,
                    raw_text=self._extract_text(resp),
                    usage=TokenUsage(
                        input_tokens=resp.usage.input_tokens,
                        output_tokens=resp.usage.output_tokens,
                        total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
                    ),
                    latency_ms=latency_ms,
                    attempts=1,
                    finish_reason="refusal",
                    descriptor=self._descriptor,
                    malformed_output=False,
                )

            raw_text = self._extract_text(resp)
            parsed_obj = schema.model_validate_json(raw_text)

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return LLMResponse(
                parsed=parsed_obj,
                raw_text=raw_text,
                usage=TokenUsage(
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
                ),
                latency_ms=latency_ms,
                attempts=1,
                finish_reason=resp.stop_reason or "stop",
                descriptor=self._descriptor,
                malformed_output=False,
            )

        except (ValidationError, json.JSONDecodeError) as initial_val_err:
            # ONE repair retry feeding back the validation error verbatim (LLM.md §3)
            repair_feedback = (
                f"The prior response failed schema validation:\n"
                f"{str(initial_val_err)}\n"
                f"Please fix the schema violation and return valid JSON adhering strictly to the schema."
            )
            retry_messages = list(anthropic_messages)
            retry_messages.append({"role": "assistant", "content": raw_text if 'raw_text' in locals() else ""})
            retry_messages.append({"role": "user", "content": repair_feedback})

            try:
                retry_kwargs = dict(call_kwargs)
                retry_kwargs["messages"] = retry_messages
                retry_resp = await self._create_message_with_backoff(
                    retry_kwargs, request.budget.max_attempts
                )
                retry_raw_text = self._extract_text(retry_resp)
                retry_parsed = schema.model_validate_json(retry_raw_text)

                latency_ms = int((time.perf_counter() - start_time) * 1000)
                tot_in = resp.usage.input_tokens + retry_resp.usage.input_tokens
                tot_out = resp.usage.output_tokens + retry_resp.usage.output_tokens

                return LLMResponse(
                    parsed=retry_parsed,
                    raw_text=retry_raw_text,
                    usage=TokenUsage(input_tokens=tot_in, output_tokens=tot_out, total_tokens=tot_in + tot_out),
                    latency_ms=latency_ms,
                    attempts=2,
                    finish_reason=retry_resp.stop_reason or "stop",
                    descriptor=self._descriptor,
                    malformed_output=False,
                )

            except Exception as second_err:
                # Fix 4: Count tokens from both attempts even on double-failure
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                tot_in = resp.usage.input_tokens
                tot_out = resp.usage.output_tokens
                if 'retry_resp' in locals() and hasattr(retry_resp, "usage") and retry_resp.usage:
                    tot_in += getattr(retry_resp.usage, "input_tokens", 0)
                    tot_out += getattr(retry_resp.usage, "output_tokens", 0)

                return LLMResponse(
                    parsed=None,
                    raw_text=retry_raw_text if 'retry_raw_text' in locals() else "",
                    usage=TokenUsage(
                        input_tokens=tot_in,
                        output_tokens=tot_out,
                        total_tokens=tot_in + tot_out,
                    ),
                    latency_ms=latency_ms,
                    attempts=2,
                    finish_reason="schema_failure",
                    descriptor=self._descriptor,
                    malformed_output=True,
                    malformed_error=f"MalformedOutput: Schema violation failed twice. Initial: {initial_val_err}. Second: {second_err}",
                )

        except Exception as err:
            # Fatal provider transport or refusal exception
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return LLMResponse(
                parsed=None,
                raw_text="",
                usage=TokenUsage(),
                latency_ms=latency_ms,
                attempts=1,
                finish_reason="error",
                descriptor=self._descriptor,
                malformed_output=True,
                malformed_error=str(err),
            )

    def _extract_text(self, resp: Any) -> str:
        """Extract text blocks from Anthropic response content."""
        text_parts = []
        for block in getattr(resp, "content", []):
            if getattr(block, "type", "") == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts).strip()
