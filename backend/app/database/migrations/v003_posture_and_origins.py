"""
Migration v003_posture_and_origins: Setup project origin field and scan posture indexes (FEATURES.md F4, F6).
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

logger = logging.getLogger(__name__)

MIGRATION_ID = "v003_posture_and_origins"


async def upgrade(db: AsyncIOMotorDatabase) -> None:
    """Run migration v003_posture_and_origins forward."""
    logger.info("Running migration %s...", MIGRATION_ID)
    projects_col = db["projects"]
    scans_col = db["scans"]

    # Backfill origin="user_project" on projects without an origin field
    result = await projects_col.update_many(
        {"origin": {"$exists": False}},
        {"$set": {"origin": "user_project"}},
    )
    logger.info("Migration %s updated %d projects with default origin.", MIGRATION_ID, result.modified_count)

    # Ensure index on scan project_id and created_at for score trend queries
    await scans_col.create_index(
        [("project_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        name="idx_scans_project_created_posture",
    )
    logger.info("Migration %s completed: indexes and origins configured.", MIGRATION_ID)
