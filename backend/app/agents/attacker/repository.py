"""
Repositories for test_cases and findings collections (DATA_MODEL.md §3).
Supports both in-memory buffering and async MongoDB persistence.
"""
from __future__ import annotations

from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.attacker.schemas import CandidateFinding, TestCaseRecord

TEST_CASES_COLLECTION = "test_cases"
FINDINGS_COLLECTION = "findings"


class TestCaseRepository:
    """Repository for persisting and querying test case execution records."""
    __test__ = False

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._memory_store: dict[str, TestCaseRecord] = {}

    async def save(self, record: TestCaseRecord) -> TestCaseRecord:
        self._memory_store[record.id] = record
        if self._db is not None:
            doc = record.model_dump()
            doc["_id"] = doc["id"]
            await self._db[TEST_CASES_COLLECTION].insert_one(doc)
        return record

    create = save

    async def get_by_id(self, test_case_id: str) -> TestCaseRecord | None:
        if test_case_id in self._memory_store:
            return self._memory_store[test_case_id]
        if self._db is not None:
            doc = await self._db[TEST_CASES_COLLECTION].find_one({"id": test_case_id})
            if doc:
                doc.pop("_id", None)
                return TestCaseRecord.model_validate(doc)
        return None

    async def list_by_scan(self, scan_id: str) -> list[TestCaseRecord]:
        in_mem = [tc for tc in self._memory_store.values() if tc.scan_id == scan_id]
        if in_mem:
            return in_mem
        if self._db is not None:
            docs = await self._db[TEST_CASES_COLLECTION].find({"scan_id": scan_id}).to_list(length=1000)
            res = []
            for d in docs:
                d.pop("_id", None)
                res.append(TestCaseRecord.model_validate(d))
            return res
        return []


class FindingRepository:
    """Repository for persisting and querying candidate and confirmed findings."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._memory_store: dict[str, CandidateFinding] = {}

    async def save(self, finding: CandidateFinding) -> CandidateFinding:
        self._memory_store[finding.id] = finding
        if self._db is not None:
            doc = finding.model_dump()
            doc["_id"] = doc["id"]
            await self._db[FINDINGS_COLLECTION].insert_one(doc)
        return finding

    create = save

    async def get_by_id(self, finding_id: str) -> CandidateFinding | None:
        if finding_id in self._memory_store:
            return self._memory_store[finding_id]
        if self._db is not None:
            doc = await self._db[FINDINGS_COLLECTION].find_one({"id": finding_id})
            if doc:
                doc.pop("_id", None)
                return CandidateFinding.model_validate(doc)
        return None

    async def list_by_scan(self, scan_id: str) -> list[CandidateFinding]:
        in_mem = [f for f in self._memory_store.values() if f.scan_id == scan_id]
        if in_mem:
            return in_mem
        if self._db is not None:
            docs = await self._db[FINDINGS_COLLECTION].find({"scan_id": scan_id}).to_list(length=1000)
            res = []
            for d in docs:
                d.pop("_id", None)
                res.append(CandidateFinding.model_validate(d))
            return res
        return []
