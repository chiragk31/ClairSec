"""
Ollama provider (FEATURES.md F4 "Live · local AI").

Runs a local model through the Ollama HTTP API with JSON-schema constrained
output. Same contract as every other provider (LLM.md §1, §3): typed request,
mandatory structured output, one repair attempt, never raises on a malformed
answer — returns malformed_output=True instead.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.llm.models import LLMRequest, LLMResponse, ModelDescriptor, TokenUsage


class OllamaProvider:
    def __init__(self, base_url: str, model_id: str, client: httpx.AsyncClient | None = None):
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._client = client
        self._descriptor = ModelDescriptor(
            provider="ollama",
            model_id=model_id,
            max_output_tokens=8192,
            effort=None,
            thinking=None,
            temperature=0.0,
            seed=7,
        )

    @property
    def descriptor(self) -> ModelDescriptor:
        return self._descriptor

    async def _chat(self, payload: dict[str, Any], timeout_s: int) -> dict[str, Any]:
        if self._client is not None:
            resp = await self._client.post(f"{self._base_url}/api/chat", json=payload, timeout=timeout_s)
        else:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def complete(self, *, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        schema = request.response_schema
        messages = [{"role": "system", "content": request.system}] + [
            {"role": m.role, "content": m.content} for m in request.messages
        ]
        usage = TokenUsage()
        last_error: str | None = None
        raw = ""
        for attempt in (1, 2):
            payload = {
                "model": self._model_id,
                "messages": messages,
                "stream": False,
                "format": schema.model_json_schema(),
                "options": {"temperature": 0, "seed": 7,
                            "num_predict": request.budget.max_output_tokens},
            }
            data = await self._chat(payload, request.budget.timeout_s)
            raw = (data.get("message") or {}).get("content", "") or ""
            usage.input_tokens += int(data.get("prompt_eval_count") or 0)
            usage.output_tokens += int(data.get("eval_count") or 0)
            usage.total_tokens = usage.input_tokens + usage.output_tokens
            try:
                parsed = schema.model_validate(json.loads(raw))
                return LLMResponse(
                    parsed=parsed, raw_text=raw, usage=usage,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                    attempts=attempt, descriptor=self._descriptor,
                )
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)[:500]
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Your previous reply did not match the JSON schema: "
                     f"{last_error}. Reply again with only valid JSON for the schema."},
                ]
        return LLMResponse(
            parsed=None, raw_text=raw, usage=usage,
            latency_ms=int((time.perf_counter() - start) * 1000), attempts=2,
            descriptor=self._descriptor, malformed_output=True, malformed_error=last_error,
        )
