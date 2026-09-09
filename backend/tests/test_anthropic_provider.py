"""
Unit tests for AnthropicProvider using mock responses.
Verifies claude-opus-5 parameters and mandatory structured output repair behavior.
Runs with zero API keys and zero network.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import BaseModel

from app.llm.models import (
    AgentName,
    CallBudget,
    LLMRequest,
    Message,
    TrustLevel,
)
from app.llm.providers.anthropic_provider import AnthropicProvider


class SampleSchema(BaseModel):
    name: str
    count: int


def make_test_request() -> LLMRequest:
    return LLMRequest(
        prompt_id="builder.test",
        prompt_version="v1",
        system="Test system",
        messages=[Message(role="user", content="Test input")],
        response_schema=SampleSchema,
        trust=TrustLevel.QUARANTINED,
        scan_id="scan-anthropic-01",
        agent=AgentName.BUILDER,
        budget=CallBudget(),
    )


def make_mock_message_response(text: str, stop_reason: str = "stop") -> MagicMock:
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp.content = [block]
    return resp


def test_anthropic_provider_descriptor_pinned_to_opus5():
    provider = AnthropicProvider(api_key="test-key")
    desc = provider.descriptor

    assert desc.provider == "anthropic"
    assert desc.model_id == "claude-opus-5"
    assert desc.effort == "high"
    assert desc.thinking == "adaptive"
    # Temperature and seed MUST be None on claude-opus-5
    assert desc.temperature is None
    assert desc.top_p is None
    assert desc.seed is None


@pytest.mark.anyio
async def test_anthropic_provider_valid_structured_output():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=make_mock_message_response('{"name": "test_app", "count": 42}')
    )

    provider = AnthropicProvider(api_key="test-key", client=mock_client)
    resp = await provider.complete(request=make_test_request())

    assert resp.malformed_output is False
    assert resp.parsed is not None
    assert resp.parsed.name == "test_app"
    assert resp.parsed.count == 42
    assert resp.attempts == 1

    # Verify parameters sent to messages.create
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-opus-5"
    assert call_kwargs["thinking"] == {"type": "adaptive"}
    assert call_kwargs["output_config"]["effort"] == "high"
    assert "temperature" not in call_kwargs
    assert "seed" not in call_kwargs


@pytest.mark.anyio
async def test_anthropic_provider_repair_retry_on_schema_violation():
    mock_client = MagicMock()
    # Call 1 fails validation (missing 'count'), Call 2 provides valid schema
    mock_client.messages.create = AsyncMock(
        side_effect=[
            make_mock_message_response('{"name": "missing_count_field"}'),
            make_mock_message_response('{"name": "repaired_name", "count": 10}'),
        ]
    )

    provider = AnthropicProvider(api_key="test-key", client=mock_client)
    resp = await provider.complete(request=make_test_request())

    assert resp.malformed_output is False
    assert resp.parsed is not None
    assert resp.parsed.name == "repaired_name"
    assert resp.parsed.count == 10
    assert resp.attempts == 2
    assert mock_client.messages.create.call_count == 2


@pytest.mark.anyio
async def test_anthropic_provider_schema_violation_failing_twice_records_malformed():
    mock_client = MagicMock()
    # Both calls return invalid schema
    mock_client.messages.create = AsyncMock(
        side_effect=[
            make_mock_message_response('{"invalid": "data"}'),
            make_mock_message_response('{"still_invalid": "data"}'),
        ]
    )

    provider = AnthropicProvider(api_key="test-key", client=mock_client)
    resp = await provider.complete(request=make_test_request())

    assert resp.malformed_output is True
    assert resp.parsed is None
    assert resp.attempts == 2
    assert "MalformedOutput" in resp.malformed_error


@pytest.mark.anyio
async def test_refusal_handled_distinctly():
    """Fix 3: A model refusal is handled as a refusal, not a schema violation."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=make_mock_message_response("I cannot fulfill this request.", stop_reason="refusal")
    )

    provider = AnthropicProvider(api_key="test-key", client=mock_client)
    resp = await provider.complete(request=make_test_request())

    assert resp.finish_reason == "refusal"
    assert resp.malformed_output is False
    assert resp.parsed is None
    assert resp.attempts == 1
    # Verify no repair retry was attempted
    assert mock_client.messages.create.call_count == 1


@pytest.mark.anyio
async def test_double_failure_accumulates_tokens():
    """Fix 4: Token usage is counted across both calls on double failure."""
    mock_client = MagicMock()
    resp1 = make_mock_message_response('{"invalid": "data"}')
    resp1.usage.input_tokens = 100
    resp1.usage.output_tokens = 50
    resp2 = make_mock_message_response('{"still_invalid": "data"}')
    resp2.usage.input_tokens = 150
    resp2.usage.output_tokens = 80

    mock_client.messages.create = AsyncMock(side_effect=[resp1, resp2])

    provider = AnthropicProvider(api_key="test-key", client=mock_client)
    resp = await provider.complete(request=make_test_request())

    assert resp.malformed_output is True
    assert resp.usage.input_tokens == 250  # 100 + 150
    assert resp.usage.output_tokens == 130  # 50 + 80
    assert resp.usage.total_tokens == 380


@pytest.mark.anyio
async def test_transport_error_retried(monkeypatch):
    """Fix 2: Transport/rate-limit errors are retried with backoff."""
    import anthropic
    # Fast-forward sleep so test does not wait
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[
            anthropic.RateLimitError(
                message="Rate limit hit",
                response=MagicMock(status_code=429, headers={}),
                body={"error": {"message": "Rate limit hit"}},
            ),
            make_mock_message_response('{"name": "success_after_429", "count": 1}'),
        ]
    )

    provider = AnthropicProvider(api_key="test-key", client=mock_client)
    resp = await provider.complete(request=make_test_request())

    assert resp.malformed_output is False
    assert resp.parsed.name == "success_after_429"
    assert mock_client.messages.create.call_count == 2

