from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api import projects
from app.core.config import settings
from app.database.client import init_client, close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the MongoDB client lifecycle."""
    await init_client()
    yield
    await close_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(projects.router, prefix="/api", tags=["projects"])

    return app


app = create_app()
