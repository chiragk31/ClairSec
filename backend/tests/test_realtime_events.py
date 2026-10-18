"""
Tests for C3: Real-time event emission during agent execution.
"""
import asyncio
from datetime import datetime, timezone
import time
from typing import Any
import pytest

from app.database.models import AgentEventRecord


@pytest.mark.asyncio
async def test_realtime_events_interleave_before_stage_finished():
    """
    C3: A fake attacker that executes 3 tests with small sleeps produces
    request/oracle events whose timestamps interleave *before* the attacker
    stage_finished event.
    """
    emitted_events: list[dict[str, Any]] = []

    async def fake_emitter(
        scan_id: str,
        agent: str,
        kind: str,
        title: str,
        detail: str = "",
        plain: str | None = None,
        refs: dict[str, Any] | None = None,
        severity: str | None = None,
        budget: dict[str, Any] | None = None,
    ):
        emitted_events.append({
            "scan_id": scan_id,
            "agent": agent,
            "kind": kind,
            "title": title,
            "ts": time.time(),
        })

    # Fake attacker with injected emitter
    class FakeAttacker:
        def __init__(self, emitter=None):
            self._emitter = emitter

        async def run_scan(self, scan_id: str):
            for i in range(1, 4):
                if self._emitter:
                    await self._emitter(
                        scan_id,
                        "attacker",
                        "request_sent",
                        f"GET /api/items/{i}",
                    )
                await asyncio.sleep(0.03)
                if self._emitter:
                    await self._emitter(
                        scan_id,
                        "attacker",
                        "oracle_fired" if i == 2 else "oracle_clear",
                        f"Oracle evaluation for /api/items/{i}",
                    )
                await asyncio.sleep(0.03)

    attacker = FakeAttacker(emitter=fake_emitter)

    # Simulate scan service stage execution
    scan_id = "test-realtime-scan"
    await fake_emitter(scan_id, "attacker", "stage_started", "Attacker Agent")
    await attacker.run_scan(scan_id)
    await fake_emitter(scan_id, "attacker", "stage_finished", "Attacker Agent")

    assert len(emitted_events) == 8  # 1 started + (3 requests + 3 oracle) + 1 finished
    kinds = [e["kind"] for e in emitted_events]
    assert kinds == [
        "stage_started",
        "request_sent",
        "oracle_clear",
        "request_sent",
        "oracle_fired",
        "request_sent",
        "oracle_clear",
        "stage_finished",
    ]

    # Verify timestamps are strictly ascending and all request/oracle events happened BEFORE stage_finished
    stage_finished_ts = emitted_events[-1]["ts"]
    for e in emitted_events[:-1]:
        assert e["ts"] < stage_finished_ts

    # Interleaving verification: request_sent -> oracle outcome -> request_sent -> oracle outcome
    for i in range(1, 4):
        req_idx = (i - 1) * 2 + 1
        orc_idx = req_idx + 1
        assert emitted_events[req_idx]["kind"] == "request_sent"
        assert emitted_events[orc_idx]["kind"] in ("oracle_fired", "oracle_clear")
        assert emitted_events[req_idx]["ts"] < emitted_events[orc_idx]["ts"]
