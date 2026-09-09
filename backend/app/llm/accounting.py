"""
Token and cost accounting ledger for LLM calls (LLM.md §9, DATA_MODEL.md §7).
Every call is recorded with latency, tokens, cost, and research metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.llm.models import (
    AgentName,
    LLMRequest,
    LLMResponse,
    ModelDescriptor,
    TokenUsage,
    TrustLevel,
)

# Token rates per million tokens (LLM.md §9, current claude-opus-5 pricing)
PRICING_PER_MILLION = {
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "mock": {"input": 0.00, "output": 0.00},
}


def calculate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING_PER_MILLION.get(model_id, {"input": 5.00, "output": 25.00})
    cost_in = (input_tokens / 1_000_000.0) * rates["input"]
    cost_out = (output_tokens / 1_000_000.0) * rates["output"]
    return round(cost_in + cost_out, 6)


class LLMCallRecord(BaseModel):
    """
    Append-only record stored in the llm_calls collection (DATA_MODEL.md §7).
    """
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scan_id: str
    agent: AgentName
    prompt_id: str
    prompt_version: str
    trust_level: TrustLevel
    model_descriptor: ModelDescriptor
    usage: TokenUsage
    cost_usd: float
    latency_ms: int
    attempts: int
    finish_reason: str
    schema_valid: bool
    cache_hit: bool = False
    cache_key: str = ""
    injection_attempt_detected: bool = False
    truncation_applied: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMCallLedger:
    """In-memory and persistent accounting ledger."""

    def __init__(self, db: Any = None):
        self._db = db
        self._records: list[LLMCallRecord] = []

    @property
    def records(self) -> list[LLMCallRecord]:
        return list(self._records)

    async def record_call(
        self,
        *,
        request: LLMRequest,
        response: LLMResponse,
        injection_detected: bool = False,
        truncation_applied: bool = False,
        cache_key: str = "",
    ) -> LLMCallRecord:
        """Create and persist an LLMCallRecord."""
        cost_usd = calculate_cost_usd(
            response.descriptor.model_id,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        response.usage.estimated_cost_usd = cost_usd

        rec = LLMCallRecord(
            scan_id=request.scan_id,
            agent=request.agent,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            trust_level=request.trust,
            model_descriptor=response.descriptor,
            usage=response.usage,
            cost_usd=cost_usd,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
            finish_reason=response.finish_reason,
            schema_valid=not response.malformed_output,
            cache_hit=response.cache_hit,
            cache_key=cache_key,
            injection_attempt_detected=injection_detected,
            truncation_applied=truncation_applied,
        )

        self._records.append(rec)

        if self._db is not None:
            try:
                await self._db.llm_calls.insert_one(rec.model_dump(mode="json"))
            except Exception:
                # Never crash on auxiliary ledger write failure
                pass

        return rec

    def get_scan_totals(self, scan_id: str) -> dict[str, Any]:
        """Aggregate token and cost metrics for a given scan."""
        scan_records = [r for r in self._records if r.scan_id == scan_id]
        total_in = sum(r.usage.input_tokens for r in scan_records)
        total_out = sum(r.usage.output_tokens for r in scan_records)
        total_tokens = sum(r.usage.total_tokens for r in scan_records)
        total_cost = sum(r.cost_usd for r in scan_records)
        total_calls = len(scan_records)
        malformed = sum(1 for r in scan_records if not r.schema_valid)

        return {
            "scan_id": scan_id,
            "calls_count": total_calls,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "malformed_calls_count": malformed,
        }
