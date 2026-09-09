"""
Phase 4 repositories — ScanRepository, AgentEventRepository, AgentContextRepository.

Per docs/RULES.md §7:
  - Use indexes for frequently queried fields.
  - Always correlate records with scan_id.
  - Avoid storing enormous raw payloads without size limits.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.models import (
    AgentContextRecord,
    AgentEvent,
    ScanRecord,
    ScanStatus,
)

_MAX_EVENT_DATA_BYTES = 10_240  # 10 KB cap on event data payload


class ScanRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["scans"]

    async def create(self, record: ScanRecord) -> ScanRecord:
        doc = record.model_dump()
        doc["_id"] = doc["id"]
        await self._col.insert_one(doc)
        return record

    async def get_by_id(self, scan_id: str) -> ScanRecord | None:
        doc = await self._col.find_one({"id": scan_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return ScanRecord.model_validate(doc)

    async def list_by_project(self, project_id: str) -> list[ScanRecord]:
        docs = await self._col.find({"project_id": project_id}).to_list(length=100)
        return [ScanRecord.model_validate({**d, "_id": None} if "_id" in d else d) for d in docs]

    async def update(self, record: ScanRecord) -> ScanRecord:
        record.updated_at = datetime.now(tz=timezone.utc)
        doc = record.model_dump()
        doc.pop("_id", None)
        await self._col.update_one({"id": record.id}, {"$set": doc})
        return record


class AgentEventRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["agent_events"]

    async def emit(self, event: AgentEvent) -> AgentEvent:
        """Persist an agent event. The data payload is size-limited."""
        import json
        doc = event.model_dump()
        # Guard against unbounded event data payloads
        serialized = json.dumps(doc.get("data", {}))
        if len(serialized) > _MAX_EVENT_DATA_BYTES:
            doc["data"] = {"truncated": True, "note": "Event data exceeded size limit"}
        doc["_id"] = doc["id"]
        await self._col.insert_one(doc)
        return event

    async def list_by_scan(self, scan_id: str) -> list[AgentEvent]:
        docs = await self._col.find({"scan_id": scan_id}).sort("timestamp", 1).to_list(length=1000)
        result = []
        for d in docs:
            d.pop("_id", None)
            result.append(AgentEvent.model_validate(d))
        return result


class AgentContextRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["agent_context"]

    async def save(self, record: AgentContextRecord) -> AgentContextRecord:
        doc = record.model_dump()
        doc["_id"] = doc["id"]
        await self._col.insert_one(doc)
        return record

    async def get_by_scan_and_agent(
        self, scan_id: str, agent: str
    ) -> AgentContextRecord | None:
        doc = await self._col.find_one({"scan_id": scan_id, "agent": agent})
        if doc is None:
            return None
        doc.pop("_id", None)
        return AgentContextRecord.model_validate(doc)

    async def list_by_scan(self, scan_id: str) -> list[AgentContextRecord]:
        docs = await self._col.find({"scan_id": scan_id}).to_list(length=100)
        result = []
        for d in docs:
            d.pop("_id", None)
            result.append(AgentContextRecord.model_validate(d))
        return result
