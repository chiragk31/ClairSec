"""
Mock LLM Provider implementing all scenarios in TESTING.md §3.
Enables end-to-end testing with zero credentials and zero network.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Sequence
from pydantic import BaseModel

from app.llm.models import (
    LLMRequest,
    LLMResponse,
    ModelDescriptor,
    TokenUsage,
)


class MockLLMProvider:
    """
    Simulates model responses across all required testing scenarios (TESTING.md §3).
    """

    def __init__(
        self,
        mode: str = "valid",
        custom_payload: dict[str, Any] | None = None,
        latency_ms: int = 10,
    ):
        self._mode = mode
        self._custom_payload = custom_payload
        self._latency_ms = latency_ms
        self._call_history: list[LLMRequest] = []
        self._attempts_count: dict[str, int] = {}
        self._descriptor = ModelDescriptor(
            provider="mock",
            model_id="claude-opus-5",
            max_output_tokens=8192,
            effort="high",
            thinking="adaptive",
        )

    @property
    def descriptor(self) -> ModelDescriptor:
        return self._descriptor

    @property
    def call_history(self) -> list[LLMRequest]:
        return list(self._call_history)

    def set_mode(self, mode: str, custom_payload: dict[str, Any] | None = None) -> None:
        self._mode = mode
        self._custom_payload = custom_payload

    async def complete(self, *, request: LLMRequest) -> LLMResponse:
        """Execute mock completion according to configured scenario mode."""
        self._call_history.append(request)
        call_key = f"{request.prompt_id}:{request.prompt_version}"
        attempt = self._attempts_count.get(call_key, 0) + 1
        self._attempts_count[call_key] = attempt

        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        schema = request.response_schema

        # Scenario 1: Timeout
        if self._mode == "timeout":
            raise asyncio.TimeoutError("Mock provider simulated request timeout.")

        # Scenario 2: Refusal
        if self._mode == "refusal":
            return LLMResponse(
                parsed=None,
                raw_text="I cannot fulfill this request due to safety policies.",
                usage=TokenUsage(input_tokens=150, output_tokens=12, total_tokens=162),
                latency_ms=self._latency_ms,
                attempts=1,
                finish_reason="refusal",
                descriptor=self._descriptor,
                malformed_output=False,
            )

        # Scenario 3: Oversized
        if self._mode == "oversized":
            huge_text = "A" * 500_000
            return LLMResponse(
                parsed=None,
                raw_text=huge_text,
                usage=TokenUsage(input_tokens=1000, output_tokens=120_000, total_tokens=121_000),
                latency_ms=self._latency_ms,
                attempts=1,
                finish_reason="length",
                descriptor=self._descriptor,
                malformed_output=True,
                malformed_error="Response exceeded token/size cap.",
            )

        # Scenario 4: Repaired on retry
        if self._mode == "repaired_on_retry":
            # If this is the initial attempt (no repair feedback in messages), fail schema validation
            is_repair_attempt = any("validation error" in m.content.lower() for m in request.messages)
            if not is_repair_attempt:
                return LLMResponse(
                    parsed=None,
                    raw_text="{'broken': 'invalid_schema_structure'}",
                    usage=TokenUsage(input_tokens=200, output_tokens=30, total_tokens=230),
                    latency_ms=self._latency_ms,
                    attempts=1,
                    finish_reason="stop",
                    descriptor=self._descriptor,
                    malformed_output=True,
                    malformed_error="Field required: missing expected schema keys.",
                )
            # Second attempt (repair retry) succeeds
            valid_obj = self._generate_valid_object(schema)
            return LLMResponse(
                parsed=valid_obj,
                raw_text=json.dumps(valid_obj.model_dump()),
                usage=TokenUsage(input_tokens=350, output_tokens=120, total_tokens=470),
                latency_ms=self._latency_ms,
                attempts=2,
                finish_reason="stop",
                descriptor=self._descriptor,
                malformed_output=False,
            )

        # Scenario 5: Schema violation failing twice / Malformed
        if self._mode in ("malformed", "schema_violation_failed_twice"):
            return LLMResponse(
                parsed=None,
                raw_text="MALFORMED_OUTPUT_NOT_JSON: <<garbled_tokens>>",
                usage=TokenUsage(input_tokens=200, output_tokens=20, total_tokens=220),
                latency_ms=self._latency_ms,
                attempts=2,
                finish_reason="stop",
                descriptor=self._descriptor,
                malformed_output=True,
                malformed_error="Failed to validate schema after repair retry.",
            )

        # Scenario 6: Hallucinated file path
        if self._mode == "hallucinated_file":
            payload = self._custom_payload or {"source_file": "app/nonexistent_phantom_file.py"}
            obj = self._populate_schema(schema, payload)
            return LLMResponse(
                parsed=obj,
                raw_text=json.dumps(payload),
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                latency_ms=self._latency_ms,
                attempts=1,
                finish_reason="stop",
                descriptor=self._descriptor,
            )

        # Scenario 7: Path traversal
        if self._mode == "path_traversal":
            payload = self._custom_payload or {"source_file": "../../../../etc/shadow"}
            obj = self._populate_schema(schema, payload)
            return LLMResponse(
                parsed=obj,
                raw_text=json.dumps(payload),
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                latency_ms=self._latency_ms,
                attempts=1,
                finish_reason="stop",
                descriptor=self._descriptor,
            )

        # Scenario 8: Injected instruction echo
        if self._mode == "injected_instruction_echo":
            payload = self._custom_payload or {
                "injected_command": "rm -rf /",
                "notes": "Echoing untrusted directive",
            }
            obj = self._populate_schema(schema, payload)
            return LLMResponse(
                parsed=obj,
                raw_text=json.dumps(payload),
                usage=TokenUsage(input_tokens=200, output_tokens=80, total_tokens=280),
                latency_ms=self._latency_ms,
                attempts=1,
                finish_reason="stop",
                descriptor=self._descriptor,
            )

        # Default / Valid mode
        valid_obj = self._generate_valid_object(schema)
        return LLMResponse(
            parsed=valid_obj,
            raw_text=json.dumps(valid_obj.model_dump()),
            usage=TokenUsage(input_tokens=250, output_tokens=100, total_tokens=350),
            latency_ms=self._latency_ms,
            attempts=1,
            finish_reason="stop",
            descriptor=self._descriptor,
            malformed_output=False,
        )

    def _populate_schema(self, schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        """Attempt to instantiate schema with payload, falling back to defaults for missing keys."""
        try:
            return schema.model_validate(payload)
        except Exception:
            base_obj = self._generate_valid_object(schema)
            for k, v in payload.items():
                if hasattr(base_obj, k):
                    try:
                        setattr(base_obj, k, v)
                    except Exception:
                        pass
            return base_obj

    def _generate_valid_object(self, schema: type[BaseModel]) -> BaseModel:
        """Create a minimally-valid default instance for a given Pydantic schema."""
        if self._custom_payload:
            try:
                return schema.model_validate(self._custom_payload)
            except Exception:
                pass

        sample_data: dict[str, Any] = {}
        for field_name, field_info in schema.model_fields.items():
            ann = field_info.annotation
            # Default values if available
            if field_info.default is not None and not str(field_info.default).startswith("PydanticUndefined"):
                sample_data[field_name] = field_info.default
            elif ann in (str, str | None):
                sample_data[field_name] = f"sample_{field_name}"
            elif ann in (int, int | None):
                sample_data[field_name] = 1
            elif ann in (float, float | None):
                sample_data[field_name] = 0.5
            elif ann in (bool, bool | None):
                sample_data[field_name] = True
            elif getattr(ann, "__origin__", None) in (list, Sequence):
                sample_data[field_name] = []
            elif getattr(ann, "__origin__", None) is dict:
                sample_data[field_name] = {}
            else:
                sample_data[field_name] = None

        try:
            return schema.model_validate(sample_data)
        except Exception:
            return schema.model_construct(**sample_data)
