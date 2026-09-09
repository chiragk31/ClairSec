"""
Database index definitions and assertions (DATA_MODEL §1, §6, RULES §7).

Indexes are declared in code, never created by hand. Startup asserts every
declared index exists (create_index is idempotent in MongoDB).
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

logger = logging.getLogger(__name__)

# Declared indexes per collection (DATA_MODEL §3, §6)
PROJECTS_INDEXES = [
    pymongo.IndexModel([("id", pymongo.ASCENDING)], unique=True, name="idx_projects_id_unique"),
    pymongo.IndexModel([("isolation_status", pymongo.ASCENDING)], name="idx_projects_isolation_status"),
]

JOBS_INDEXES = [
    pymongo.IndexModel([("id", pymongo.ASCENDING)], unique=True, name="idx_jobs_id_unique"),
    pymongo.IndexModel([("status", pymongo.ASCENDING)], name="idx_jobs_status"),
]


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Ensure all declared indexes exist in MongoDB and assert their presence.
    Called at lifespan startup.
    """
    logger.info("Ensuring database indexes...")
    # 1. Projects collection
    projects_col = db["projects"]
    created_names = await projects_col.create_indexes(PROJECTS_INDEXES)
    logger.debug("Ensured projects indexes: %s", created_names)

    # Assert projects indexes exist
    existing_indexes = await projects_col.index_information()
    assert "idx_projects_id_unique" in existing_indexes, "Required index 'idx_projects_id_unique' missing from projects collection"
    assert "idx_projects_isolation_status" in existing_indexes, "Required index 'idx_projects_isolation_status' missing from projects collection"

    # 2. Jobs collection
    jobs_col = db["jobs"]
    created_jobs_names = await jobs_col.create_indexes(JOBS_INDEXES)
    logger.debug("Ensured jobs indexes: %s", created_jobs_names)

    # Assert jobs indexes exist
    existing_jobs_indexes = await jobs_col.index_information()
    assert "idx_jobs_id_unique" in existing_jobs_indexes, "Required index 'idx_jobs_id_unique' missing from jobs collection"
    assert "idx_jobs_status" in existing_jobs_indexes, "Required index 'idx_jobs_status' missing from jobs collection"

    logger.info("Database index assertion passed.")
