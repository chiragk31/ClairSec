"""
Project repository — typed async access to the 'projects' MongoDB collection.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.models import ProjectRecord

COLLECTION = "projects"


class ProjectRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db[COLLECTION]

    async def create(self, record: ProjectRecord) -> ProjectRecord:
        doc = record.model_dump()
        # MongoDB stores _id; we use our own string 'id' field.
        doc["_id"] = doc["id"]
        await self._col.insert_one(doc)
        return record

    async def list_all(self) -> list[ProjectRecord]:
        docs = await self._col.find({}).to_list(length=1000)
        return [_from_doc(d) for d in docs]

    async def get_by_id(self, project_id: str) -> ProjectRecord | None:
        doc = await self._col.find_one({"id": project_id})
        if doc is None:
            return None
        return _from_doc(doc)


def _from_doc(doc: dict) -> ProjectRecord:
    doc.pop("_id", None)
    return ProjectRecord.model_validate(doc)
