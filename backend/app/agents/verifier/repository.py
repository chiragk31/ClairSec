"""
Repository for verification_results collection (DATA_MODEL.md §3 verification_results).
"""
from __future__ import annotations

import logging
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.verifier.schemas import VerificationRecord
from app.database.client import get_database

logger = logging.getLogger(__name__)

VERIFICATION_COLLECTION = "verification_results"
_REASON_MAX_BYTES = 2048


class VerificationRepository:
    """
    Manages persistence of canonical VerificationRecord documents.
    """
    __test__ = False

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._memory_store: dict[str, VerificationRecord] = {}

    def _get_collection(self):
        if self._db is not None:
            return self._db[VERIFICATION_COLLECTION]
        try:
            db = get_database()
            return db[VERIFICATION_COLLECTION]
        except Exception:
            return None

    async def create(self, record: VerificationRecord) -> VerificationRecord:
        """Persist a new VerificationRecord document."""
        data = record.model_dump()

        # Enforce size limits (DATA_MODEL.md §2)
        if data.get("outcome_reason") and len(data["outcome_reason"]) > _REASON_MAX_BYTES:
            data["outcome_reason"] = data["outcome_reason"][:_REASON_MAX_BYTES]

        self._memory_store[record.id] = record

        coll = self._get_collection()
        if coll is not None:
            try:
                doc = dict(data)
                doc["_id"] = doc["id"]
                await coll.insert_one(doc)
            except Exception as exc:
                logger.warning("MongoDB insert into verification_results failed: %s; memory stored", exc)

        return VerificationRecord.model_validate(data)

    save = create

    async def get_by_id(self, record_id: str) -> VerificationRecord | None:
        if record_id in self._memory_store:
            return self._memory_store[record_id]

        coll = self._get_collection()
        if coll is not None:
            try:
                doc = await coll.find_one({"id": record_id})
                if doc:
                    doc.pop("_id", None)
                    return VerificationRecord.model_validate(doc)
            except Exception as exc:
                logger.warning("MongoDB query on verification_results failed: %s", exc)

        return None

    async def list_by_scan(self, scan_id: str) -> list[VerificationRecord]:
        in_mem = [r for r in self._memory_store.values() if r.scan_id == scan_id]
        if in_mem:
            return in_mem

        coll = self._get_collection()
        if coll is not None:
            try:
                docs = await coll.find({"scan_id": scan_id}).to_list(length=1000)
                res = []
                for d in docs:
                    d.pop("_id", None)
                    res.append(VerificationRecord.model_validate(d))
                return res
            except Exception as exc:
                logger.warning("MongoDB query on verification_results failed: %s", exc)

        return []

    async def list_by_finding(self, finding_id: str) -> list[VerificationRecord]:
        in_mem = [r for r in self._memory_store.values() if r.finding_id == finding_id]
        if in_mem:
            return in_mem

        coll = self._get_collection()
        if coll is not None:
            try:
                docs = await coll.find({"finding_id": finding_id}).to_list(length=1000)
                res = []
                for d in docs:
                    d.pop("_id", None)
                    res.append(VerificationRecord.model_validate(d))
                return res
            except Exception as exc:
                logger.warning("MongoDB query on verification_results failed: %s", exc)

        return []
