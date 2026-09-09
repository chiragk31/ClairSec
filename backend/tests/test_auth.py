"""
Tests for local API authentication — THREAT_MODEL C7.1–C7.4.

Traceability:
    C7.1 — test_bind_localhost_only (config assertion)
    C7.2 — test_no_token_rejected, test_wrong_token_rejected, test_valid_token_accepted
    C7.3 — test_cors_deny_all_origins, test_host_header_validation
    C7.4 — WebSocket auth (deferred to Phase 9, WebSocket not yet implemented)
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.auth import initialize_auth, get_launch_token
from app.core.config import settings


class TestTokenAuth:
    """C7.2: Per-launch bearer token required on every authenticated endpoint."""

    def test_no_token_rejected(self, app):
        """Request without Authorization header gets 401."""
        with TestClient(app) as client:
            response = client.get("/api/projects")
            assert response.status_code == 401

    def test_wrong_token_rejected(self, app):
        """Request with an incorrect token gets 401."""
        with TestClient(app) as client:
            response = client.get(
                "/api/projects",
                headers={"Authorization": "Bearer wrong-token-value"},
            )
            assert response.status_code == 401

    def test_valid_token_accepted(self, authed_client):
        """Request with the correct per-launch token succeeds."""
        response = authed_client.get("/api/projects")
        # 200 or 500 (if Mongo is down) — but NOT 401
        assert response.status_code != 401

    def test_health_endpoint_no_auth(self, app):
        """Health endpoint is exempt from auth — Flutter needs it before reading token."""
        with TestClient(app) as client:
            response = client.get("/api/health")
            assert response.status_code == 200


class TestHostHeaderValidation:
    """C7.3: Host header must be in the allowlist."""

    def test_valid_host_accepted(self, authed_client):
        """testserver is in the allowlist — requests should work."""
        # TestClient sends Host: testserver by default
        response = authed_client.get("/api/health")
        assert response.status_code == 200

    def test_invalid_host_rejected(self, app):
        """A Host header not in the allowlist gets 400."""
        with TestClient(app, headers={"Host": "evil.example.com"}) as client:
            response = client.get("/api/health")
            assert response.status_code == 400

    def test_localhost_accepted(self, app):
        """localhost is in the allowlist."""
        initialize_auth()
        token = get_launch_token()
        with TestClient(app, headers={"Host": "localhost:8000"}) as client:
            response = client.get(
                "/api/projects",
                headers={"Authorization": f"Bearer {token}"},
            )
            # Not 400 (Host validation) — may be 401 if token changed, but not 400
            assert response.status_code != 400


class TestCors:
    """C7.3: CORS deny all origins."""

    def test_cors_deny_all_origins(self, app):
        """Preflight from any origin should be denied."""
        with TestClient(app) as client:
            response = client.options(
                "/api/projects",
                headers={
                    "Origin": "http://evil.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            # No Access-Control-Allow-Origin header should be present
            assert "access-control-allow-origin" not in response.headers


class TestBindConfig:
    """C7.1: Bind to 127.0.0.1 only."""

    def test_bind_localhost_only(self):
        """Config default is 127.0.0.1, never 0.0.0.0."""
        assert settings.api_host == "127.0.0.1"
