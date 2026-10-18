"""
Live event backbone for agent activity and attack timeline (FEATURES.md F5, DATA_MODEL.md §3).

- Atomic per-scan monotonic sequence (safe under concurrency via MongoDB $inc).
- In-memory event broadcasting for active WebSocket subscribers.
- Backend static phrasebook (plain language, zero LLM).
- Pre-persistence redaction and 4 KB detail capping.
- Non-blocking emit that never raises into callers.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from app.database.client import get_database
from app.database.models import AgentEventRecord, EventKind
from app.llm.redaction import redact_secrets
from app.database.encoding import to_document

logger = logging.getLogger(__name__)

EVENT_PHRASEBOOK: dict[str, str] = {
    "stage_started": "Beginning stage: {title}.",
    "stage_finished": "Completed stage: {title}.",
    "endpoint_discovered": "Discovered API endpoint: {title}.",
    "test_planned": "Synthesized targeted security test: {title}.",
    "request_sent": "Sent test request: {title}.",
    "oracle_fired": "Security oracle triggered on {title}.",
    "oracle_clear": "Security oracle clear; no violation detected for {title}.",
    "finding_candidate": "Potential security issue detected: {title}.",
    "finding_confirmed": "Vulnerability confirmed by deterministic oracle: {title}.",
    "finding_rejected": "Potential issue rejected as false positive: {title}.",
    "finding_inconclusive": "Test produced inconclusive outcome: {title}.",
    "patch_proposed": "Fixer proposed code patch: {title}.",
    "patch_rejected": "Proposed patch failed pre-validation: {title}.",
    "verification_started": "Verifying remediation patch against original exploit: {title}.",
    "verification_result": "Remediation verification completed: {title}.",
    "budget": "Resource budget update: {title}.",
    "error": "Error encountered during execution: {title}.",
    "info": "{title}",
}


class EventBus:
    """
    Central event dispatcher and durable event logger.
    """

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._subscribers: dict[str, set[asyncio.Queue[AgentEventRecord]]] = defaultdict(set)
        # Thread/coroutine-safe fallback counters when DB is offline or in mock tests
        self._fallback_counters: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    def _get_db(self) -> AsyncIOMotorDatabase | None:
        if self._db is not None:
            return self._db
        try:
            return get_database()
        except Exception:
            return None

    async def seed_fallback_counter(self, scan_id: str, max_seq: int | None = None) -> None:
        """
        Seed the fallback counter from DB max seq or an explicit value (C10).
        """
        async with self._lock:
            if max_seq is not None:
                self._fallback_counters[scan_id] = max_seq
                return

            max_found = 0
            db = self._get_db()
            if db is not None:
                try:
                    cursor = db["agent_events"].find(
                        {"scan_id": scan_id},
                        projection={"seq": 1},
                    ).sort("seq", pymongo.DESCENDING).limit(1)
                    docs = await cursor.to_list(length=1)
                    if docs and "seq" in docs[0]:
                        max_found = int(docs[0]["seq"])
                except Exception as exc:
                    logger.debug("Failed querying agent_events for fallback seeding: %s", exc)
            self._fallback_counters[scan_id] = max_found

    async def _next_seq(self, scan_id: str) -> int:
        """
        Produce an atomic, strictly monotonic sequence number for this scan.
        Safe under arbitrary concurrency using MongoDB atomic $inc.
        """
        db = self._get_db()
        if db is not None:
            try:
                doc = await db["scan_counters"].find_one_and_update(
                    {"_id": f"event_seq_{scan_id}"},
                    {"$inc": {"seq": 1}},
                    upsert=True,
                    return_document=pymongo.ReturnDocument.AFTER,
                )
                if doc and "seq" in doc:
                    return int(doc["seq"])
            except Exception as exc:
                logger.warning("MongoDB atomic seq increment failed, falling back to lock: %s", exc)

        async with self._lock:
            if scan_id not in self._fallback_counters:
                max_found = 0
                if db is not None:
                    try:
                        cursor = db["agent_events"].find(
                            {"scan_id": scan_id},
                            projection={"seq": 1},
                        ).sort("seq", pymongo.DESCENDING).limit(1)
                        docs = await cursor.to_list(length=1)
                        if docs and "seq" in docs[0]:
                            max_found = int(docs[0]["seq"])
                    except Exception:
                        pass
                self._fallback_counters[scan_id] = max_found

            self._fallback_counters[scan_id] += 1
            return self._fallback_counters[scan_id]

    async def emit(
        self,
        scan_id: str,
        agent: str,
        kind: str,
        title: str,
        detail: str = "",
        plain: str | None = None,
        refs: dict[str, Any] | None = None,
        severity: str | None = None,
        budget: dict[str, Any] | None = None,
    ) -> AgentEventRecord | None:
        """
        Emit a new event. Persists to agent_events and notifies live subscribers.
        Never raises into caller.
        """
        try:
            # 1. Plain language generation via static phrasebook
            if not plain:
                template = EVENT_PHRASEBOOK.get(kind, "{title}")
                plain = template.format(title=title)

            # 2. Detail capping (4 KB) and redaction
            scrubbed_detail = redact_secrets(detail) if detail else ""
            if len(scrubbed_detail) > 4096:
                scrubbed_detail = scrubbed_detail[:4093] + "..."

            scrubbed_title = redact_secrets(title)
            scrubbed_plain = redact_secrets(plain)

            # 3. Monotonic sequence assignment
            seq = await self._next_seq(scan_id)

            event = AgentEventRecord(
                id=str(uuid.uuid4()),
                scan_id=scan_id,
                seq=seq,
                timestamp=datetime.now(tz=timezone.utc),
                agent=agent,
                kind=kind,
                title=scrubbed_title,
                detail=scrubbed_detail,
                plain=scrubbed_plain,
                severity=severity,
                refs=refs or {},
                budget=budget,
            )

            # 4. Durable persistence
            db = self._get_db()
            if db is not None:
                try:
                    await db["agent_events"].insert_one(to_document(event))
                except Exception as db_exc:
                    logger.warning("Failed to persist agent event to MongoDB: %s", db_exc)

            # 5. Live broadcast to active WebSocket subscribers
            self._broadcast(scan_id, event)

            return event
        except Exception as exc:
            logger.exception("EventBus.emit failed: %s", exc)
            return None

    def _broadcast(self, scan_id: str, event: AgentEventRecord) -> None:
        queues = self._subscribers.get(scan_id, set())
        for q in list(queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full for scan %s, dropping oldest", scan_id)
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("Failed to put event into subscriber queue: %s", exc)

    def subscribe(self, scan_id: str) -> asyncio.Queue[AgentEventRecord]:
        q: asyncio.Queue[AgentEventRecord] = asyncio.Queue(maxsize=1000)
        self._subscribers[scan_id].add(q)
        return q

    def unsubscribe(self, scan_id: str, q: asyncio.Queue[AgentEventRecord]) -> None:
        if scan_id in self._subscribers:
            self._subscribers[scan_id].discard(q)
            if not self._subscribers[scan_id]:
                del self._subscribers[scan_id]

    async def get_events(
        self,
        scan_id: str,
        after_seq: int = 0,
        limit: int = 500,
    ) -> list[AgentEventRecord]:
        """
        Read historical events for catch-up or polling.
        """
        db = self._get_db()
        if db is None:
            return []

        cursor = (
            db["agent_events"]
            .find({"scan_id": scan_id, "seq": {"$gt": after_seq}})
            .sort("seq", pymongo.ASCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [AgentEventRecord(**doc) for doc in docs]


# Global EventBus singleton
event_bus = EventBus()
