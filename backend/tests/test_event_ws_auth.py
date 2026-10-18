"""
WebSocket authentication tests for event stream (THREAT_MODEL C7.4, FEATURES.md F5, V2 exit gate).
Exit gate: "WS rejects missing/invalid token".
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.auth import initialize_auth
from app.main import app


@pytest.fixture
def auth_token() -> str:
    return initialize_auth(force=True)


def test_ws_rejects_missing_or_invalid_token(auth_token: str) -> None:
    client = TestClient(app)

    # 1. Connect with invalid token in query
    with pytest.raises(Exception):
        with client.websocket_connect("/api/scans/scan-auth-test/events/ws?token=invalid_token") as ws:
            pass

    # 2. Connect with invalid token in first auth message
    with pytest.raises(WebSocketDisconnect) as exc_info2:
        with client.websocket_connect("/api/scans/scan-auth-test/events/ws") as ws:
            ws.send_json({"type": "auth", "token": "wrong_token"})
            ws.receive_json()
    assert exc_info2.value.code == 1008


def test_ws_rejects_token_in_query_per_c5(auth_token: str) -> None:
    """Per C5: Query param tokens are prohibited even if valid."""
    client = TestClient(app)

    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/scans/scan-auth-test/events/ws?token={auth_token}") as ws:
            pass


def test_ws_accepts_valid_token_in_sec_websocket_protocol(auth_token: str) -> None:
    """Per C5: Desktop sends token via Sec-WebSocket-Protocol."""
    client = TestClient(app)

    with client.websocket_connect(
        "/api/scans/scan-auth-test/events/ws",
        subprotocols=[auth_token],
    ) as ws:
        assert ws is not None


def test_ws_accepts_valid_token_in_first_message(auth_token: str) -> None:
    client = TestClient(app)

    with client.websocket_connect("/api/scans/scan-auth-test/events/ws") as ws:
        ws.send_json({"type": "auth", "token": auth_token})
        # Stays open and connected without throwing
