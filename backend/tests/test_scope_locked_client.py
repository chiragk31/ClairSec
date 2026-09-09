"""
Unit and integration tests for ScopeLockedHttpClient (THREAT_MODEL T9, ETHICS §3, SECURITY §6).
"""
from __future__ import annotations

import asyncio
import pytest
import httpx

from app.security.http_client import (
    NonDestructivePolicyViolationError,
    OffTargetRequestBlockedError,
    RequestCeilingExceededError,
    ScopeLockedHttpClient,
)


@pytest.mark.asyncio
async def test_off_target_absolute_url_refused_t9():
    """T9: Request to off-target host/port is rejected without network traffic."""
    target_base = "http://127.0.0.1:49210"
    client = ScopeLockedHttpClient(target_base)

    # 1. Foreign domain
    with pytest.raises(OffTargetRequestBlockedError, match="outside the allowed target scope"):
        await client.get("https://example.com/api/steal")

    # 2. Localhost but different port
    with pytest.raises(OffTargetRequestBlockedError, match="outside the allowed target scope"):
        await client.get("http://127.0.0.1:8080/admin")

    # 3. Different host
    with pytest.raises(OffTargetRequestBlockedError, match="outside the allowed target scope"):
        await client.get("http://192.168.1.1:49210/target")


@pytest.mark.asyncio
async def test_non_destructive_policy_blocks_delete():
    """SECURITY.md §6: Non-destructive policy blocks HTTP DELETE."""
    target_base = "http://127.0.0.1:49210"
    client = ScopeLockedHttpClient(target_base)

    with pytest.raises(NonDestructivePolicyViolationError, match="DELETE is prohibited"):
        await client.request("DELETE", "/documents/doc_01")


@pytest.mark.asyncio
async def test_request_ceiling_enforced():
    """SECURITY.md §6: Scan request ceiling terminates testing when budget exhausted."""
    target_base = "http://127.0.0.1:49210"
    client = ScopeLockedHttpClient(target_base, max_requests=3, rate_limit_rps=100.0)

    # Mock internal client to avoid needing a live server
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200)))

    # Requests 1, 2, 3 succeed
    await client.get("/test1")
    await client.get("/test2")
    await client.get("/test3")
    assert client.request_count == 3

    # Request 4 exceeds ceiling
    with pytest.raises(RequestCeilingExceededError, match="ceiling of 3 requests reached"):
        await client.get("/test4")


@pytest.mark.asyncio
async def test_cross_host_redirect_blocked_by_scope_lock():
    """T9 & ETHICS §3: Redirect attempting to escape target host is blocked."""
    target_base = "http://127.0.0.1:49210"
    client = ScopeLockedHttpClient(target_base)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        # Returns 302 redirecting to off-target domain
        return httpx.Response(302, headers={"Location": "https://evil.attacker.com/sink"})

    client._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), follow_redirects=False)

    with pytest.raises(OffTargetRequestBlockedError, match="outside the allowed target scope"):
        await client.get("/redirect-me")
