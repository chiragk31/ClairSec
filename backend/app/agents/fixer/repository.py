"""
Repository for patches collection (DATA_MODEL.md §3 patches, §2 size limits).
Supports async MongoDB persistence with in-memory buffering.
"""
from __future__ import annotations

import logging
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.fixer.schemas import PatchRecord
from app.database.client import get_database

logger = logging.getLogger(__name__)

PATCHES_COLLECTION = "patches"
_ERROR_MAX_BYTES = 2048


class PatchRepository:
    """
    Manages persistence of canonical PatchRecord documents.
    """
    __test__ = False

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._memory_store: dict[str, PatchRecord] = {}

    def _get_collection(self):
        if self._db is not None:
            return self._db[PATCHES_COLLECTION]
        try:
            db = get_database()
            return db[PATCHES_COLLECTION]
        except Exception:
            return None

    async def create(self, record: PatchRecord) -> PatchRecord:
        """Persist a new PatchRecord document."""
        data = record.model_dump()

        # Enforce size limits (DATA_MODEL.md §2)
        if data.get("apply_error") and len(data["apply_error"]) > _ERROR_MAX_BYTES:
            data["apply_error"] = data["apply_error"][:_ERROR_MAX_BYTES]

        self._memory_store[record.id] = record

        coll = self._get_collection()
        if coll is not None:
            try:
                doc = dict(data)
                doc["_id"] = doc["id"]
                await coll.insert_one(doc)
            except Exception as exc:
                logger.warning("MongoDB insert into patches failed: %s; memory stored", exc)

        return PatchRecord.model_validate(data)

    save = create

    async def get_by_id(self, patch_id: str) -> PatchRecord | None:
        if patch_id in self._memory_store:
            return self._memory_store[patch_id]

        coll = self._get_collection()
        if coll is not None:
            try:
                doc = await coll.find_one({"id": patch_id})
                if doc:
                    doc.pop("_id", None)
                    return PatchRecord.model_validate(doc)
            except Exception as exc:
                logger.warning("MongoDB query on patches failed: %s", exc)

        return None

    async def list_by_scan(self, scan_id: str) -> list[PatchRecord]:
        in_mem = [p for p in self._memory_store.values() if p.scan_id == scan_id]
        if in_mem:
            return in_mem

        coll = self._get_collection()
        if coll is not None:
            try:
                docs = await coll.find({"scan_id": scan_id}).to_list(length=1000)
                res = []
                for d in docs:
                    d.pop("_id", None)
                    res.append(PatchRecord.model_validate(d))
                return res
            except Exception as exc:
                logger.warning("MongoDB query on patches failed: %s", exc)

        return []

    async def list_by_finding(self, finding_id: str) -> list[PatchRecord]:
        in_mem = [p for p in self._memory_store.values() if p.finding_id == finding_id]
        if in_mem:
            return in_mem

        coll = self._get_collection()
        if coll is not None:
            try:
                docs = await coll.find({"finding_id": finding_id}).to_list(length=1000)
                res = []
                for d in docs:
                    d.pop("_id", None)
                    res.append(PatchRecord.model_validate(d))
                return res
            except Exception as exc:
                logger.warning("MongoDB query on patches failed: %s", exc)

        return []
