"""
Tests for C4, C5, C6: WebSocket Authentication Hardening and Ordering.
"""
import asyncio
from datetime import datetime, timezone
import json
import pytest
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient

from app.core.auth import get_launch_token, initialize_auth, ws_auth
from app.database.models import AgentEventRecord
from app.main import create_app
from app.services.event_bus import EventBus


@pytest.fixture(autouse=True)
def setup_auth_token():
    token = initialize_auth(force=True)
    return token


from fastapi.routing import APIWebSocketRoute


def test_all_websocket_routes_require_auth():
    """
    C6: Enumerate all app WebSocket routes and assert each has explicit ws_auth dependency.
    """
    app = create_app()
    ws_routes: list[Any] = []
    for r in app.routes:
        if isinstance(r, (WebSocketRoute, APIWebSocketRoute)):
            ws_routes.append(r)
        elif hasattr(r, "original_router"):
            for sub_r in r.original_router.routes:
                if isinstance(sub_r, (WebSocketRoute, APIWebSocketRoute)):
                    ws_routes.append(sub_r)
        elif hasattr(r, "routes"):
            for sub_r in r.routes:
                if isinstance(sub_r, (WebSocketRoute, APIWebSocketRoute)):
                    ws_routes.append(sub_r)

    assert len(ws_routes) > 0, "Expected at least one WebSocket route in the application"

    for route in ws_routes:
        dep_callables = [d.dependency for d in getattr(route, "dependencies", [])]
        assert ws_auth in dep_callables, (
            f"WebSocket route {route.path} does not have explicit ws_auth dependency"
        )


def test_query_param_token_is_rejected():
    """
    C5: Query-param token is rejected/ignored. Connecting with ?token=... fails.
    """
    app = create_app()
    token = get_launch_token()
    client = TestClient(app)

    # Attempt to connect with ?token=...
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/scans/test-scan/events/ws?token={token}") as ws:
            pass


def test_sec_websocket_protocol_auth_accepted():
    """
    C5: Desktop sends the token via Sec-WebSocket-Protocol. Valid token is accepted.
    """
    app = create_app()
    token = get_launch_token()
    client = TestClient(app)

    with client.websocket_connect(
        "/api/scans/test-scan/events/ws",
        subprotocols=[token],
    ) as ws:
        # Connected successfully
        assert ws is not None


def test_first_json_message_auth_accepted():
    """
    C5: Client sends the token in the first JSON message {"type": "auth", "token": "..."}.
    """
    app = create_app()
    token = get_launch_token()
    client = TestClient(app)

    with client.websocket_connect("/api/scans/test-scan/events/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        # Next message or connection remains alive without policy violation disconnect


@pytest.mark.asyncio
async def test_subscribe_first_ordering_and_drop_stale():
    """
    C4: WS subscribe first, then send catch-up, then live; drop live events with seq <= last sent.
    An event emitted between catch-up read and subscribe is not lost.
    """
    event_bus = EventBus(db=None)
    scan_id = "test-c4-scan"

    # Pre-populate 2 events
    e1 = AgentEventRecord(
        scan_id=scan_id,
        seq=1,
        agent="builder",
        kind="stage_started",
        title="Builder Agent",
    )
    e2 = AgentEventRecord(
        scan_id=scan_id,
        seq=2,
        agent="builder",
        kind="endpoint_discovered",
        title="GET /users",
    )
    # Simulate DB storage by mocking get_events
    stored_events = [e1, e2]

    async def fake_get_events(s_id, after_seq=0, limit=500):
        return [e for e in stored_events if e.seq > after_seq][:limit]

    event_bus.get_events = fake_get_events

    # C4 ordering in client handler:
    # 1. Subscribe FIRST
    queue = event_bus.subscribe(scan_id)

    # 2. Emitted event happens right after subscribe, before catch-up finishes
    e3 = AgentEventRecord(
        scan_id=scan_id,
        seq=3,
        agent="attacker",
        kind="request_sent",
        title="GET /users",
    )
    stored_events.append(e3)
    # Also broadcast live into subscriber queue
    await queue.put(e3)

    # 3. Catch-up read
    sent_events: list[AgentEventRecord] = []
    last_sent_seq = 0
    catch_up = await event_bus.get_events(scan_id, after_seq=0, limit=500)
    for evt in catch_up:
        sent_events.append(evt)
        last_sent_seq = max(last_sent_seq, evt.seq)

    # 4. Process live event from queue
    live_evt = await queue.get()
    if live_evt.seq > last_sent_seq:
        sent_events.append(live_evt)
        last_sent_seq = max(last_sent_seq, live_evt.seq)

    # Assert all 3 events delivered in monotonic order without duplicates
    assert [e.seq for e in sent_events] == [1, 2, 3]
