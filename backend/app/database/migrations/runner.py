"""
Migration runner for forward-only, idempotent schema migrations (DATA_MODEL §1, §6).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.migrations import v001_initial

logger = logging.getLogger(__name__)

MIGRATIONS = [
    (v001_initial.MIGRATION_ID, v001_initial.upgrade),
]


async def run_migrations(db: AsyncIOMotorDatabase) -> None:
    """
    Run all pending forward-only migrations.
    Idempotent: migrations recorded in 'schema_migrations' collection are skipped.
    """
    migrations_col = db["schema_migrations"]
    applied_cursor = migrations_col.find({}, {"name": 1})
    applied_docs = await applied_cursor.to_list(length=1000)
    applied_names = {doc["name"] for doc in applied_docs}

    for migration_id, upgrade_func in MIGRATIONS:
        if migration_id in applied_names:
            logger.debug("Migration %s already applied, skipping.", migration_id)
            continue

        logger.info("Applying migration %s...", migration_id)
        await upgrade_func(db)
        await migrations_col.insert_one({
            "name": migration_id,
            "applied_at": datetime.now(tz=timezone.utc),
        })
        logger.info("Migration %s successfully recorded.", migration_id)
