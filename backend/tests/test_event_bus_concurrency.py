"""
Tests for C10: EventBus atomic sequence concurrency and fallback counter seeding.
"""
import asyncio
from typing import Any
import pytest
import pymongo

from app.services.event_bus import EventBus


class AtomicFakeCollection:
    """Fake Motor collection supporting atomic find_one_and_update with $inc."""

    def __init__(self):
        self._docs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def find_one_and_update(
        self,
        filter: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
        return_document: pymongo.ReturnDocument = pymongo.ReturnDocument.AFTER,
    ) -> dict[str, Any] | None:
        async with self._lock:
            doc_id = filter.get("_id")
            doc = self._docs.get(doc_id)
            if doc is None:
                if not upsert:
                    return None
                doc = {"_id": doc_id, "seq": 0}
                self._docs[doc_id] = doc

            if "$inc" in update:
                for k, v in update["$inc"].items():
                    doc[k] = doc.get(k, 0) + v

            return dict(doc)


class FakeDb:
    def __init__(self, counters_col):
        self._counters_col = counters_col

    def __getitem__(self, name: str):
        if name == "scan_counters":
            return self._counters_col
        raise KeyError(name)


@pytest.mark.asyncio
async def test_atomic_find_one_and_update_under_200_concurrent_emits():
    """
    C10: Test using a fake collection that implements find_one_and_update atomically
    under 200 concurrent emits.
    """
    fake_col = AtomicFakeCollection()
    fake_db = FakeDb(fake_col)
    bus = EventBus(db=fake_db)
    scan_id = "concurrent-scan-1"

    async def emit_task(i: int) -> int:
        return await bus._next_seq(scan_id)

    # Launch 200 concurrent emits
    tasks = [asyncio.create_task(emit_task(i)) for i in range(200)]
    results = await asyncio.gather(*tasks)

    # All 200 sequences must be unique and cover 1 to 200
    assert len(results) == 200
    assert len(set(results)) == 200
    assert set(results) == set(range(1, 201))


@pytest.mark.asyncio
async def test_fallback_counter_seeds_from_current_max_seq():
    """
    C10: Fallback counter seeds from the current max seq for the scan.
    """
    bus = EventBus(db=None)
    scan_id = "test-fallback-scan"

    # Pre-seed fallback counter with existing events by seeding logic
    # Suppose current max seq in DB for this scan is 42
    await bus.seed_fallback_counter(scan_id, max_seq=42)

    seq1 = await bus._next_seq(scan_id)
    seq2 = await bus._next_seq(scan_id)

    assert seq1 == 43
    assert seq2 == 44
