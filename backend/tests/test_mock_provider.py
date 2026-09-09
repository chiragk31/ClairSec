"""
Unit tests verifying MockLLMProvider implementation of all TESTING.md §3 scenarios.
Runs with zero API keys and zero network.
"""
import pytest
from pydantic import BaseModel
from app.llm.models import (
    AgentName,
    CallBudget,
    LLMRequest,
    Message,
    TrustLevel,
)
from app.llm.providers.mock_provider import MockLLMProvider


class SampleOutputSchema(BaseModel):
    summary: str
    confidence: float
    items: list[str] = []


def make_request(prompt_id: str = "builder.test") -> LLMRequest:
    return LLMRequest(
        prompt_id=prompt_id,
        prompt_version="v1",
        system="System prompt",
        messages=[Message(role="user", content="Analyze target")],
        response_schema=SampleOutputSchema,
        trust=TrustLevel.QUARANTINED,
        scan_id="scan-test-01",
        agent=AgentName.BUILDER,
        budget=CallBudget(),
    )


@pytest.mark.anyio
async def test_mock_provider_valid_scenario():
    provider = MockLLMProvider(mode="valid")
    resp = await provider.complete(request=make_request())

    assert resp.malformed_output is False
    assert resp.parsed is not None
    assert isinstance(resp.parsed, SampleOutputSchema)
    assert resp.attempts == 1
    assert resp.descriptor.model_id == "claude-opus-5"


@pytest.mark.anyio
async def test_mock_provider_refusal_scenario():
    provider = MockLLMProvider(mode="refusal")
    resp = await provider.complete(request=make_request())

    assert resp.parsed is None
    assert resp.finish_reason == "refusal"


@pytest.mark.anyio
async def test_mock_provider_timeout_scenario():
    provider = MockLLMProvider(mode="timeout")
    with pytest.raises(TimeoutError):
        await provider.complete(request=make_request())


@pytest.mark.anyio
async def test_mock_provider_oversized_scenario():
    provider = MockLLMProvider(mode="oversized")
    resp = await provider.complete(request=make_request())

    assert resp.malformed_output is True
    assert resp.finish_reason == "length"


@pytest.mark.anyio
async def test_mock_provider_repaired_on_retry_scenario():
    provider = MockLLMProvider(mode="repaired_on_retry")
    # Initial request -> fails schema validation
    req1 = make_request()
    resp1 = await provider.complete(request=req1)
    assert resp1.malformed_output is True
    assert resp1.parsed is None

    # Follow-up request with validation error feedback -> succeeds on repair attempt
    req2 = LLMRequest(
        prompt_id="builder.test",
        prompt_version="v1",
        system="System prompt",
        messages=[
            Message(role="user", content="Analyze target"),
            Message(role="assistant", content=resp1.raw_text),
            Message(role="user", content="Prior response had validation error: fix schema"),
        ],
        response_schema=SampleOutputSchema,
        trust=TrustLevel.QUARANTINED,
        scan_id="scan-test-01",
        agent=AgentName.BUILDER,
    )
    resp2 = await provider.complete(request=req2)
    assert resp2.malformed_output is False
    assert resp2.parsed is not None
    assert resp2.attempts == 2


@pytest.mark.anyio
async def test_mock_provider_malformed_failing_twice_scenario():
    provider = MockLLMProvider(mode="schema_violation_failed_twice")
    resp = await provider.complete(request=make_request())

    assert resp.malformed_output is True
    assert resp.parsed is None
    assert resp.attempts == 2
    assert "Schema violation failed twice" in resp.malformed_error or "repair retry" in resp.malformed_error
