"""
Async MongoDB client managed via FastAPI lifespan.

Usage:
    from app.database.client import get_db

    @app.get("/example")
    async def handler(db=Depends(get_db)):
        ...
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Return the shared Motor client. Must be initialized before calling."""
    if _client is None:
        raise RuntimeError("MongoDB client has not been initialized. Call init_client() first.")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongodb_db]


async def init_client() -> None:
    """Open the MongoDB connection. Called during FastAPI lifespan startup."""
    global _client
    _client = AsyncIOMotorClient(settings.mongodb_url)


async def close_client() -> None:
    """Close the MongoDB connection. Called during FastAPI lifespan shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
