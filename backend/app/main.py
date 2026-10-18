import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import health, isolation, jobs, pipelines, projects, scans, system
from app.core.auth import initialize_auth, validate_host_header, verify_token
from app.core.config import settings
from app.core.logging import log_context, setup_logging
from app.database.client import close_client, get_database, init_client
from app.database.indexes import ensure_indexes
from app.database.migrations.runner import run_migrations
from app.services.job_service import JobService

logger = logging.getLogger("app.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown: config check, MongoDB client, auth token, indexes, migrations, job reconciliation."""
    setup_logging()
    settings.check_required_settings()
    initialize_auth()
    await init_client()
    try:
        db = get_database()
        await run_migrations(db)
        await ensure_indexes(db)
        job_service = JobService(db)
        await job_service.reconcile_startup()
        from app.services.task_registry import reconcile_stale_tasks
        await reconcile_stale_tasks(db)
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


class DiagnosticLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured diagnostic logging for every API request:
    - Injects request_id and route context identifiers into log_context.
    - Suppresses repetitive 200 polls to DEBUG level so the console is readable.
    - Logs start, completion duration, and full traceback on unhandled exceptions.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:8]}"
        path = request.url.path
        method = request.method

        # Extract IDs from path
        project_id = ""
        job_id = ""
        scan_id = ""
        parts = path.strip("/").split("/")
        if "projects" in parts:
            idx = parts.index("projects")
            if idx + 1 < len(parts) and parts[idx + 1] not in ("", "search"):
                project_id = parts[idx + 1]
        if "jobs" in parts:
            idx = parts.index("jobs")
            if idx + 1 < len(parts):
                job_id = parts[idx + 1]
        if "scans" in parts:
            idx = parts.index("scans")
            if idx + 1 < len(parts):
                scan_id = parts[idx + 1]

        is_polling = (
            method == "GET"
            and any(p in path for p in ("/status", "/isolation-status", "/api/health"))
            or (method == "GET" and "/api/jobs/" in path and len(parts) == 3)
        )

        with log_context(
            request_id=req_id,
            project_id=project_id,
            job_id=job_id,
            scan_id=scan_id,
            stage="api",
        ):
            if is_polling:
                logger.debug(
                    "%s %s (poll)",
                    method,
                    path,
                    extra={"event": "api.poll.received"},
                )
            else:
                logger.info(
                    "%s %s received",
                    method,
                    path,
                    extra={"event": "api.request.received"},
                )

            t0 = time.perf_counter()
            try:
                response = await call_next(request)
                duration_ms = (time.perf_counter() - t0) * 1000
                response.headers["X-Request-ID"] = req_id

                if is_polling and response.status_code < 400:
                    logger.debug(
                        "%s %s -> HTTP %d (took %.1fms)",
                        method,
                        path,
                        response.status_code,
                        duration_ms,
                        extra={"event": "api.poll.completed"},
                    )
                else:
                    log_fn = (
                        logger.info
                        if response.status_code < 400
                        else (logger.error if response.status_code >= 500 else logger.warning)
                    )
                    log_fn(
                        "%s %s -> HTTP %d (took %.1fms)",
                        method,
                        path,
                        response.status_code,
                        duration_ms,
                        extra={"event": "api.request.completed"},
                    )
                return response
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                logger.exception(
                    "%s %s -> UNHANDLED EXCEPTION after %.1fms: %s",
                    method,
                    path,
                    duration_ms,
                    exc,
                    extra={"event": "api.request.failed"},
                )
                raise


def create_app() -> FastAPI:
    setup_logging()
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

    # ── Diagnostic logging middleware (observability) ───────────────────────
    app.add_middleware(DiagnosticLoggingMiddleware)

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
    app.include_router(
        scans.ws_router,
        prefix="/api",
        tags=["scans"],
    )

    app.include_router(
        system.router,
        prefix="/api",
        tags=["system"],
        dependencies=[Depends(verify_token)],
    )

    app.include_router(
        pipelines.router,
        prefix="/api",
        tags=["pipelines"],
        dependencies=[Depends(verify_token)],
    )

    from app.api import assistant, bundles, findings, reports
    app.include_router(
        bundles.router,
        prefix="/api",
        tags=["bundles"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        findings.router,
        prefix="/api",
        tags=["findings"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        reports.router,
        prefix="/api",
        tags=["reports"],
        dependencies=[Depends(verify_token)],
    )
    app.include_router(
        assistant.router,
        prefix="/api",
        tags=["assistant"],
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

