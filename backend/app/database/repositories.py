"""
Project repository — typed async access to the 'projects' MongoDB collection.
"""
from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.client import get_database
from app.database.models import JobRecord, ProjectRecord, ScanRecord

COLLECTION = "projects"


class ProjectRepository:
    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._memory_store: dict[str, ProjectRecord] = {}

    def _get_collection(self):
        if self._db is not None:
            return self._db[COLLECTION]
        try:
            db = get_database()
            return db[COLLECTION]
        except Exception:
            return None

    async def create(self, record: ProjectRecord) -> ProjectRecord:
        self._memory_store[record.id] = record
        coll = self._get_collection()
        if coll is not None:
            doc = record.model_dump()
            # MongoDB stores _id; we use our own string 'id' field.
            doc["_id"] = doc["id"]
            await coll.insert_one(doc)
        return record

    async def list_all(self) -> list[ProjectRecord]:
        coll = self._get_collection()
        if coll is not None:
            docs = await coll.find({}).to_list(length=1000)
            return [_from_doc(d) for d in docs]
        return list(self._memory_store.values())

    async def get_by_id(self, project_id: str) -> ProjectRecord | None:
        if project_id in self._memory_store:
            return self._memory_store[project_id]
        coll = self._get_collection()
        if coll is not None:
            doc = await coll.find_one({"id": project_id})
            if doc is None:
                return None
            return _from_doc(doc)
        return None

    async def update(self, record: ProjectRecord) -> ProjectRecord:
        """Update an existing document by its id field."""
        record.updated_at = datetime.now(tz=timezone.utc)
        self._memory_store[record.id] = record
        coll = self._get_collection()
        if coll is not None:
            doc = record.model_dump()
            doc.pop("_id", None)  # never overwrite Mongo _id
            await coll.update_one(
                {"id": record.id},
                {"$set": doc},
            )
        return record


def _from_doc(doc: dict) -> ProjectRecord:
    doc.pop("_id", None)
    return ProjectRecord.model_validate(doc)


JOBS_COLLECTION = "jobs"


class JobRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[JOBS_COLLECTION]

    async def create(self, record: JobRecord) -> JobRecord:
        doc = record.model_dump()
        doc["_id"] = doc["id"]
        await self._col.insert_one(doc)
        return record

    async def get_by_id(self, job_id: str) -> JobRecord | None:
        doc = await self._col.find_one({"id": job_id})
        if doc is None:
            return None
        return _from_job_doc(doc)

    async def update(self, record: JobRecord) -> JobRecord:
        record.updated_at = datetime.now(tz=timezone.utc)
        doc = record.model_dump()
        doc.pop("_id", None)
        await self._col.update_one(
            {"id": record.id},
            {"$set": doc},
        )
        return record

    async def get_active_jobs(self) -> list[JobRecord]:
        """Return jobs in 'pending' or 'running' state."""
        docs = await self._col.find(
            {"status": {"$in": ["pending", "running"]}}
        ).to_list(length=1000)
        return [_from_job_doc(d) for d in docs]


def _from_job_doc(doc: dict) -> JobRecord:
    doc.pop("_id", None)
    return JobRecord.model_validate(doc)


SCANS_COLLECTION = "scans"


class ScanRepository:
    """
    Manages persistence of canonical ScanRecord documents.
    """
    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._memory_store: dict[str, ScanRecord] = {}

    def _get_collection(self):
        if self._db is not None:
            return self._db[SCANS_COLLECTION]
        try:
            db = get_database()
            return db[SCANS_COLLECTION]
        except Exception:
            return None

    async def create(self, record: ScanRecord) -> ScanRecord:
        self._memory_store[record.id] = record
        coll = self._get_collection()
        if coll is not None:
            doc = record.model_dump()
            doc["_id"] = doc["id"]
            await coll.insert_one(doc)
        return record

    async def get_by_id(self, scan_id: str) -> ScanRecord | None:
        if scan_id in self._memory_store:
            return self._memory_store[scan_id]
        coll = self._get_collection()
        if coll is not None:
            doc = await coll.find_one({"id": scan_id})
            if doc:
                doc.pop("_id", None)
                return ScanRecord.model_validate(doc)
        return None

    async def list_all(self) -> list[ScanRecord]:
        coll = self._get_collection()
        if coll is not None:
            docs = await coll.find({}).sort("created_at", -1).to_list(length=1000)
            res = []
            for d in docs:
                d.pop("_id", None)
                res.append(ScanRecord.model_validate(d))
            return res
        return sorted(self._memory_store.values(), key=lambda s: s.created_at, reverse=True)

    async def list_by_project(self, project_id: str) -> list[ScanRecord]:
        coll = self._get_collection()
        if coll is not None:
            docs = await coll.find({"project_id": project_id}).sort("created_at", -1).to_list(length=1000)
            res = []
            for d in docs:
                d.pop("_id", None)
                res.append(ScanRecord.model_validate(d))
            return res
        return [s for s in self._memory_store.values() if s.project_id == project_id]

    async def update(self, record: ScanRecord) -> ScanRecord:
        self._memory_store[record.id] = record
        coll = self._get_collection()
        if coll is not None:
            doc = record.model_dump()
            doc.pop("_id", None)
            await coll.update_one({"id": record.id}, {"$set": doc})
        return record

