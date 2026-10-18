"""
Reconnect and gap-fill tests for event stream (FEATURES.md F5, V2 exit gate).
Exit gate: "reconnect gap-fill test".
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.database.models import AgentEventRecord
from app.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_reconnect_gap_fill_retrieval() -> None:
    """
    Simulate a client that previously saw up to seq=2, reconnects with after_seq=2,
    and receives missed events (seq 3, 4, 5) followed by new live events.
    """
    mock_db = MagicMock()
    stored_events: list[dict] = []

    # Mock MongoDB insert_one, find, and find_one_and_update
    async def mock_insert_one(doc):
        stored_events.append(doc)
        return MagicMock()

    counter = 0

    async def mock_find_one_and_update(filter, update, **kwargs):
        nonlocal counter
        inc = update.get("$inc", {}).get("seq", 1)
        counter += inc
        return {"seq": counter}

    def mock_find(query):
        scan_id = query.get("scan_id")
        after_seq = query.get("seq", {}).get("$gt", 0)
        filtered = [
            e for e in stored_events
            if e.get("scan_id") == scan_id and e.get("seq", 0) > after_seq
        ]
        filtered.sort(key=lambda x: x.get("seq", 0))

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor

        async def to_list(length=500):
            return filtered[:length]

        mock_cursor.to_list = to_list
        return mock_cursor

    collections: dict[str, Any] = {
        "agent_events": MagicMock(insert_one=mock_insert_one, find=mock_find),
        "scan_counters": MagicMock(find_one_and_update=mock_find_one_and_update),
    }
    mock_db.__getitem__.side_effect = lambda name: collections.get(name, MagicMock())

    bus = EventBus(db=mock_db)
    scan_id = "test-scan-gap-fill"

    # Emit initial 5 events
    for i in range(1, 6):
        await bus.emit(
            scan_id=scan_id,
            agent="builder",
            kind="info",
            title=f"Event {i}",
        )

    assert len(stored_events) == 5

    # Client reconnects with after_seq=2
    missed_events = await bus.get_events(scan_id=scan_id, after_seq=2, limit=500)
    assert len(missed_events) == 3
    assert [e.seq for e in missed_events] == [3, 4, 5]
    assert [e.title for e in missed_events] == ["Event 3", "Event 4", "Event 5"]

    # Subscribe for live events
    live_q = bus.subscribe(scan_id)
    try:
        # Emit event 6
        await bus.emit(
            scan_id=scan_id,
            agent="attacker",
            kind="info",
            title="Event 6",
        )

        live_event = await asyncio.wait_for(live_q.get(), timeout=2.0)
        assert live_event.seq == 6
        assert live_event.title == "Event 6"
    finally:
        bus.unsubscribe(scan_id, live_q)
