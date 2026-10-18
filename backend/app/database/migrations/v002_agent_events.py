"""
Migration v002_agent_events: Setup agent_events collection and indexes (FEATURES.md F5).
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

logger = logging.getLogger(__name__)

MIGRATION_ID = "v002_agent_events"


async def upgrade(db: AsyncIOMotorDatabase) -> None:
    """Run migration v002_agent_events forward."""
    logger.info("Running migration %s...", MIGRATION_ID)
    events_col = db["agent_events"]

    # Ensure unique index on (scan_id, seq)
    await events_col.create_index(
        [("scan_id", pymongo.ASCENDING), ("seq", pymongo.ASCENDING)],
        unique=True,
        name="idx_agent_events_scan_seq_unique",
    )
    logger.info("Migration %s completed: agent_events index created.", MIGRATION_ID)
