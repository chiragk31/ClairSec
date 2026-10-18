"""
Async MongoDB client managed via FastAPI lifespan.

Storage modes (FEATURES.md F4, Round 3 audit D3):
  - "mongodb": a real MongoDB server answered the startup ping.
  - "memory":  MongoDB was unreachable, so the app runs on an in-memory database
               (mongomock-motor) behind the same Motor interface. Everything works,
               but nothing survives a restart — the UI shows a TEMPORARY STORAGE badge.

Usage:
    from app.database.client import get_database
"""
from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Any = None
_storage_mode: str = "mongodb"
_fallback_reason: str | None = None


def get_client() -> Any:
    """Return the shared client. Must be initialized before calling."""
    if _client is None:
        raise RuntimeError("MongoDB client has not been initialized. Call init_client() first.")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongodb_db]


def storage_mode() -> str:
    """'mongodb' or 'memory'."""
    return _storage_mode


def storage_fallback_reason() -> str | None:
    return _fallback_reason


def _memory_client() -> Any:
    from mongomock_motor import AsyncMongoMockClient

    return AsyncMongoMockClient()


async def init_client() -> None:
    """Open the database. Falls back to in-memory storage when MongoDB is unreachable."""
    global _client, _storage_mode, _fallback_reason
    timeout_ms = 500 if settings.testing else settings.mongodb_connect_timeout_ms
    client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=timeout_ms)
    try:
        await client.admin.command("ping")
        _client = client
        _storage_mode = "mongodb"
        _fallback_reason = None
        return
    except Exception as exc:  # noqa: BLE001
        client.close()
        if not settings.memory_storage_fallback:
            # Keep the old behaviour available: a client that fails on first use.
            _client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=timeout_ms)
            _storage_mode = "mongodb"
            _fallback_reason = None
            return
        _fallback_reason = f"MongoDB is not reachable at startup: {exc}"
        logger.warning(
            "%s — falling back to TEMPORARY in-memory storage; results will not survive a restart.",
            _fallback_reason,
            extra={"event": "database.fallback.memory"},
        )
        _client = _memory_client()
        _storage_mode = "memory"


async def close_client() -> None:
    """Close the database client. Called during FastAPI lifespan shutdown."""
    global _client
    if _client is not None:
        close = getattr(_client, "close", None)
        if callable(close):
            close()
        _client = None
