from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import health, projects, isolation, jobs, scans
from app.core.auth import initialize_auth, validate_host_header, verify_token
from app.core.config import settings
from app.database.client import init_client, close_client, get_database
from app.database.indexes import ensure_indexes
from app.database.migrations.runner import run_migrations
from app.services.job_service import JobService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown: config check, MongoDB client, auth token, indexes, migrations, job reconciliation."""
    settings.check_required_settings()
    initialize_auth()
    await init_client()
    try:
        db = get_database()
        await run_migrations(db)
        await ensure_indexes(db)
        job_service = JobService(db)
        await job_service.reconcile_startup()
    except Exception:
        if not settings.testing:
            raise
    yield
    await close_client()


class HostValidationMiddleware(BaseHTTPMiddleware):
    """
    Reject requests whose Host header is not in the allowlist (C7.3).

    This prevents DNS rebinding attacks — the Starlette Host-header bypass
    class of vulnerability makes this concrete rather than theoretical.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            validate_host_header(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )

    # ── CORS: deny all origins (C7.3) ──────────────────────────────────────
    # Flutter desktop doesn't send Origin headers — an empty allow_origins
    # is both stronger and simpler than trying to enumerate localhost variants.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],          # deny all
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization"],
    )

    # ── Host header validation (C7.3) ──────────────────────────────────────
    app.add_middleware(HostValidationMiddleware)

    # ── Health route: no auth (Flutter needs it before it reads the token) ──
    app.include_router(health.router, prefix="/api", tags=["health"])

    # ── Authenticated routes (C7.2) ────────────────────────────────────────
    app.include_router(
        projects.router,
        prefix="/api",
        tags=["projects"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        isolation.router,
        prefix="/api",
        tags=["isolation"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        jobs.router,
        prefix="/api",
        tags=["jobs"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        scans.router,
        prefix="/api",
        tags=["scans"],
        dependencies=[Depends(verify_token)],
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc)},
        )

    return app


app = create_app()

