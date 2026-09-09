"""
Migration v001_initial: Initial schema groundwork (DATA_MODEL §1, §6).

Idempotent forward-only migration:
- Ensures all existing ProjectRecord documents carry schema_version=1.
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

MIGRATION_ID = "v001_initial"


async def upgrade(db: AsyncIOMotorDatabase) -> None:
    """Run migration v001_initial forward."""
    logger.info("Running migration %s...", MIGRATION_ID)
    projects_col = db["projects"]

    # Backfill schema_version=1 on any existing projects that lack it
    result = await projects_col.update_many(
        {"schema_version": {"$exists": False}},
        {"$set": {"schema_version": 1}},
    )
    logger.info(
        "Migration %s completed: updated %d projects without schema_version.",
        MIGRATION_ID,
        result.modified_count,
    )
