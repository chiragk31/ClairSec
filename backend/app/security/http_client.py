"""
Scope-Locked HTTP Client (THREAT_MODEL.md T9, ETHICS.md §3, SECURITY.md §6).

Guarantees enforced in platform code:
1. Target Host Scope Lock (T9): Rejects any request targeting an IP/host/port other than
   the scan's designated target.
2. Cross-Host Redirect Rejection: Prevents redirects from escaping the target host.
3. Rate Limiting: Paces requests according to scan policy (default 20 req/s).
4. Request Ceiling: Enforces a hard budget ceiling on total requests per scan.
5. Non-Destructive Policy: Disallows destructive HTTP verbs (e.g. DELETE).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


class OffTargetRequestBlockedError(PermissionError):
    """Raised when an HTTP request attempts to reach a host/port outside the locked target (THREAT_MODEL T9)."""


class NonDestructivePolicyViolationError(PermissionError):
    """Raised when an HTTP request violates the non-destructive security testing policy (SECURITY.md §6)."""


class RequestCeilingExceededError(RuntimeError):
    """Raised when the maximum request budget per scan is exceeded (SECURITY.md §6)."""


class ScopeLockedHttpClient:
    """
    Scope-locked HTTP client wrapper enforcing host locking, rate limits, and non-destructive policies.
    """

    def __init__(
        self,
        base_url: str,
        *,
        rate_limit_rps: float = 20.0,
        max_requests: int = 100,
        timeout_seconds: float = 10.0,
    ):
        self._raw_base_url = base_url.rstrip("/")
        parsed = urlparse(self._raw_base_url)
        if not parsed.hostname:
            raise ValueError(f"Invalid target base_url: {base_url}")

        self._target_scheme = parsed.scheme or "http"
        self._target_hostname = parsed.hostname
        self._target_port = parsed.port or (80 if self._target_scheme == "http" else 443)

        self._rate_limit_rps = max(0.1, rate_limit_rps)
        self._min_interval = 1.0 / self._rate_limit_rps
        self._max_requests = max_requests
        self._timeout = timeout_seconds

        self._request_count = 0
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return self._raw_base_url

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def max_requests(self) -> int:
        return self._max_requests

    async def __aenter__(self) -> ScopeLockedHttpClient:
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _validate_scope(self, url: str) -> str:
        """
        Validate that the target URL is strictly within the allowed target scope.
        Returns the resolved absolute URL. Raises OffTargetRequestBlockedError on mismatch.
        """
        # If relative, resolve against target base_url
        if not url.startswith(("http://", "https://")):
            resolved = urljoin(f"{self._raw_base_url}/", url.lstrip("/"))
        else:
            resolved = url

        parsed = urlparse(resolved)
        parsed_port = parsed.port or (80 if parsed.scheme == "http" else 443)

        # Host matching (case-insensitive)
        if (parsed.hostname or "").lower() != self._target_hostname.lower() or parsed_port != self._target_port:
            raise OffTargetRequestBlockedError(
                f"Off-target request blocked: {resolved} is outside the allowed target scope "
                f"({self._target_hostname}:{self._target_port}). THREAT_MODEL T9 and ETHICS §3 enforced."
            )

        return resolved

    async def _enforce_rate_limit(self) -> None:
        """Enforce rate-limiting interval between requests."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        params: dict[str, Any] | None = None,
        max_redirects: int = 5,
    ) -> httpx.Response:
        """
        Execute an HTTP request within target scope with non-destructive policy and redirect checks.
        """
        norm_method = method.upper()

        # Non-destructive policy check (SECURITY.md §6)
        # DELETE is strictly prohibited to prevent irreversible data loss.
        # PUT/PATCH/POST are permitted because write-then-read verification is
        # required for oracles like BOPLA_MASS_ASSIGN (reproducing persistence).
        if norm_method == "DELETE":
            raise NonDestructivePolicyViolationError(
                "HTTP DELETE is prohibited by ClairSec non-destructive testing policy."
            )

        # Request ceiling check (SECURITY.md §6)
        if self._request_count >= self._max_requests:
            raise RequestCeilingExceededError(
                f"Request ceiling of {self._max_requests} requests reached for this scan."
            )

        resolved_url = self._validate_scope(url)

        if not self._client:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)

        current_url = resolved_url
        redirect_count = 0

        while True:
            await self._enforce_rate_limit()
            self._request_count += 1

            response = await self._client.request(
                method=norm_method,
                url=current_url,
                headers=headers,
                json=json,
                data=data,
                params=params,
            )

            # Check if response is a redirect (3xx)
            if response.is_redirect and "location" in response.headers:
                redirect_count += 1
                if redirect_count > max_redirects:
                    return response

                redirect_target = response.headers["location"]
                # Validate that redirect target stays strictly within target scope
                resolved_redirect = self._validate_scope(
                    urljoin(current_url, redirect_target)
                )
                current_url = resolved_redirect
                # Redirection for GET/HEAD; for 303 change to GET
                if response.status_code in (301, 302, 303):
                    norm_method = "GET"
                    json = None
                    data = None
                continue

            return response

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)
