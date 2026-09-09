"""
MongoDB Repository for the findings collection (DATA_MODEL.md §2 & §3).
"""
from __future__ import annotations

import logging
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.evaluator.schemas import EvaluatedFinding
from app.database.client import get_database

logger = logging.getLogger(__name__)

_REASON_MAX_BYTES = 2048


class FindingRepository:
    """
    Manages persistence of canonical EvaluatedFinding records.
    Enforces append-only semantics and size caps.
    """

    def __init__(self, db: AsyncIOMotorDatabase | None = None):
        self._db = db
        self._memory_store: list[dict[str, Any]] = []

    def _get_collection(self):
        if self._db is not None:
            return self._db["findings"]
        try:
            db = get_database()
            return db["findings"]
        except Exception:
            return None

    async def create(self, finding: EvaluatedFinding | dict[str, Any]) -> EvaluatedFinding:
        """Persist a new EvaluatedFinding document."""
        if hasattr(finding, "model_dump"):
            data = finding.model_dump()
        elif isinstance(finding, dict):
            data = dict(finding)
        else:
            raise TypeError(f"Expected EvaluatedFinding or dict, got {type(finding).__name__}")

        # Enforce size limits (DATA_MODEL.md §2)
        if len(data.get("status_reason", "")) > _REASON_MAX_BYTES:
            data["status_reason"] = data["status_reason"][:_REASON_MAX_BYTES]

        coll = self._get_collection()
        if coll is not None:
            try:
                await coll.insert_one(data)
            except Exception as exc:
                logger.warning("MongoDB insert into findings failed: %s; falling back to memory", exc)
                self._memory_store.append(data)
        else:
            self._memory_store.append(data)

        return EvaluatedFinding.model_validate(data)

    async def list_by_scan(self, scan_id: str) -> list[EvaluatedFinding]:
        """Return all findings recorded for a scan_id."""
        coll = self._get_collection()
        if coll is not None:
            try:
                cursor = coll.find({"scan_id": scan_id})
                docs = await cursor.to_list(length=1000)
                return [EvaluatedFinding.model_validate(d) for d in docs]
            except Exception as exc:
                logger.warning("MongoDB query on findings failed: %s; using memory", exc)

        return [
            EvaluatedFinding.model_validate(d)
            for d in self._memory_store
            if d.get("scan_id") == scan_id
        ]

    async def list_by_project(self, project_id: str) -> list[EvaluatedFinding]:
        """Return all findings recorded for a project_id."""
        coll = self._get_collection()
        if coll is not None:
            try:
                cursor = coll.find({"project_id": project_id})
                docs = await cursor.to_list(length=1000)
                return [EvaluatedFinding.model_validate(d) for d in docs]
            except Exception as exc:
                logger.warning("MongoDB query on findings failed: %s; using memory", exc)

        return [
            EvaluatedFinding.model_validate(d)
            for d in self._memory_store
            if d.get("project_id") == project_id
        ]
