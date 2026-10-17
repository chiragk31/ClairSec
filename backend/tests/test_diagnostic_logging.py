"""
Unit tests for ClairSec structured diagnostic logging.

Tests:
  - Contextvars ID propagation (request_id, project_id, job_id, scan_id, stage).
  - LogRecord enrichment by ClairSecLogFilter.
  - Secret redaction (passwords, tokens, Bearer, auth keys).
  - Untrusted input sanitization (newlines, control characters to prevent log injection).
  - Terminal formatter output formatting and exception tracebacks.
  - Stage boundary tracing (trace_stage helper).
  - DiagnosticLoggingMiddleware (request_id generation, polling noise reduction, error logging).
  - FastAPIValidator diagnostic logging for invalid paths and entrypoints.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.core.logging import (
    ClairSecLogFilter,
    ClairSecTerminalFormatter,
    clear_log_context,
    get_log_context,
    log_context,
    redact_secrets,
    sanitize_log_str,
    set_log_context,
    trace_stage,
)
from app.main import DiagnosticLoggingMiddleware
from app.services.fastapi_validator import validate_fastapi_project
from starlette.requests import Request
from starlette.responses import JSONResponse

# ─────────────────────────────────────────────────────────────────────────────
# 1. Contextvars & Log Filtering
# ─────────────────────────────────────────────────────────────────────────────

def test_set_and_get_log_context():
    clear_log_context()
    assert get_log_context() == {}

    set_log_context(
        request_id="req-123",
        project_id="proj-456",
        job_id="job-789",
        scan_id="scan-abc",
        stage="building",
    )
    ctx = get_log_context()
    assert ctx["request_id"] == "req-123"
    assert ctx["project_id"] == "proj-456"
    assert ctx["job_id"] == "job-789"
    assert ctx["scan_id"] == "scan-abc"
    assert ctx["stage"] == "building"

    clear_log_context()
    assert get_log_context() == {}


def test_log_context_manager():
    clear_log_context()
    set_log_context(request_id="outer-req")

    with log_context(project_id="inner-proj", stage="scan"):
        ctx = get_log_context()
        assert ctx["request_id"] == "outer-req"
        assert ctx["project_id"] == "inner-proj"
        assert ctx["stage"] == "scan"

    # Restored after context manager
    ctx_after = get_log_context()
    assert ctx_after.get("request_id") == "outer-req"
    assert "project_id" not in ctx_after
    clear_log_context()


def test_log_filter_enriches_record():
    clear_log_context()
    set_log_context(request_id="req-999", project_id="proj-888")

    flt = ClairSecLogFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message with token: secret123",
        args=(),
        exc_info=None,
    )

    result = flt.filter(record)
    assert result is True
    assert record.request_id == "req-999"
    assert record.project_id == "proj-888"
    assert not record.job_id
    assert not record.scan_id
    # Secret auto-redaction in filter
    assert "[REDACTED]" in record.msg
    assert "secret123" not in record.msg
    clear_log_context()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Secret Redaction & Log Sanitization
# ─────────────────────────────────────────────────────────────────────────────

def test_redact_secrets_in_dict():
    data = {
        "project_name": "my-app",
        "api_key": "sk-1234567890",
        "nested": {
            "password": "super-secret-pass",
            "safe_field": 42,
            "auth_token": "bearer xyz123",
        },
    }
    redacted = redact_secrets(data)
    assert redacted["project_name"] == "my-app"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["safe_field"] == 42
    assert redacted["nested"]["auth_token"] == "[REDACTED]"


def test_redact_secrets_in_string():
    raw_str = "Authorization: Bearer secret-token-value at https://api.internal/key: secretkey123"
    redacted = redact_secrets(raw_str)
    assert "secret-token-value" not in redacted
    assert "secretkey123" not in redacted
    assert "[REDACTED]" in redacted


def test_sanitize_log_str():
    # Newlines and carriage returns must be converted to spaces to prevent log injection
    evil_input = "first line\n[2026-01-01 INFO] INJECTED ADMIN LOG ENTRY\r\nthird line"
    sanitized = sanitize_log_str(evil_input)
    assert "\n" not in sanitized
    assert "\r" not in sanitized
    assert "INJECTED ADMIN LOG ENTRY" in sanitized


# ─────────────────────────────────────────────────────────────────────────────
# 3. Formatter & Traceback Output
# ─────────────────────────────────────────────────────────────────────────────

def test_terminal_formatter_output():
    formatter = ClairSecTerminalFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Isolation container started",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.project_id = "proj-2"
    record.event = "docker.container.started"

    formatted = formatter.format(record)
    assert "[INFO" in formatted
    assert "[app.test]" in formatted
    assert "req:req-1" in formatted
    assert "proj:proj-2" in formatted
    assert "[docker.container.started]" in formatted
    assert "Isolation container started" in formatted


def test_terminal_formatter_traceback():
    formatter = ClairSecTerminalFormatter()
    try:
        raise ValueError("Diagnostic failure reason")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="app.test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=10,
        msg="Pipeline stage crashed",
        args=(),
        exc_info=exc_info,
    )
    formatted = formatter.format(record)
    assert "Pipeline stage crashed" in formatted
    assert "ValueError: Diagnostic failure reason" in formatted
    assert "Traceback (most recent call last):" in formatted


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stage Tracing Context Manager
# ─────────────────────────────────────────────────────────────────────────────

def test_trace_stage_success(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test_trace")

    with trace_stage(logger, "unit_test_stage", "test.stage"):
        pass

    records = [r for r in caplog.records if r.name == "test_trace"]
    events = [getattr(r, "event", None) for r in records]
    assert "test.stage.started" in events
    assert "test.stage.succeeded" in events


def test_trace_stage_failure(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test_trace_fail")

    with (
        pytest.raises(RuntimeError, match="Stage exploded"),
        trace_stage(logger, "failing_stage", "test.stage"),
    ):
        raise RuntimeError("Stage exploded")

    records = [r for r in caplog.records if r.name == "test_trace_fail"]
    events = [getattr(r, "event", None) for r in records]
    assert "test.stage.started" in events
    assert "test.stage.failed" in events
    failed_record = next(r for r in records if getattr(r, "event", None) == "test.stage.failed")
    assert failed_record.exc_info is not None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Diagnostic Middleware
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_middleware_request_id_and_propagation():
    app_mock = MagicMock()
    middleware = DiagnosticLoggingMiddleware(app_mock)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/projects/p-12345/isolation-status",
        "headers": [(b"x-request-id", b"custom-req-id-123")],
        "query_string": b"",
    }
    request = Request(scope)

    captured_ctx = {}

    async def call_next(req):
        captured_ctx.update(get_log_context())
        return JSONResponse(status_code=200, content={"status": "ready"})

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "custom-req-id-123"
    assert captured_ctx.get("request_id") == "custom-req-id-123"
    assert captured_ctx.get("project_id") == "p-12345"


@pytest.mark.asyncio
async def test_middleware_polling_noise_reduction(caplog):
    caplog.set_level(logging.DEBUG, logger="app.api")
    logging.getLogger("app").setLevel(logging.DEBUG)
    logging.getLogger("app.api").setLevel(logging.DEBUG)
    app_mock = MagicMock()
    middleware = DiagnosticLoggingMiddleware(app_mock)

    # 1. Successful 200 polling -> logged at DEBUG
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)

    async def call_next_ok(req):
        return JSONResponse(status_code=200, content={"status": "ok"})

    caplog.clear()
    await middleware.dispatch(request, call_next_ok)
    records = [r for r in caplog.records if r.name == "app.api"]
    assert len(records) >= 1
    # Check that successful polling request is DEBUG level
    assert all(r.levelno == logging.DEBUG for r in records)

    # 2. Polling with 500 error -> logged at ERROR level
    async def call_next_err(req):
        return JSONResponse(status_code=500, content={"error": "db down"})

    caplog.clear()
    await middleware.dispatch(request, call_next_err)
    err_records = [r for r in caplog.records if r.name == "app.api"]
    assert any(r.levelno == logging.ERROR for r in err_records)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Validator Diagnostic Logging
# ─────────────────────────────────────────────────────────────────────────────

def test_validator_nonexistent_directory_diagnostics(tmp_path: Path, caplog):
    caplog.set_level(logging.DEBUG)
    missing_dir = tmp_path / "does_not_exist_subdir"

    result = validate_fastapi_project(str(missing_dir))

    assert result.is_valid is False
    assert any("does not exist" in err.lower() for err in result.errors)

    # Verify diagnostic logs recorded the missing path and candidates
    val_records = [r for r in caplog.records if r.name == "app.services.fastapi_validator"]
    assert any("does not exist" in r.message for r in val_records)


def test_validator_entrypoint_candidates_logging(tmp_path: Path, caplog):
    caplog.set_level(logging.DEBUG)
    # Create a project with python files but no FastAPI app
    app_dir = tmp_path / "no_app_project"
    app_dir.mkdir()
    (app_dir / "helper.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (app_dir / "utils.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")

    result = validate_fastapi_project(str(app_dir))

    assert result.is_valid is False
    assert result.entry_point is None

    # Verify that the diagnostic logs recorded checked candidates
    val_records = [r for r in caplog.records if r.name == "app.services.fastapi_validator"]
    events = [getattr(r, "event", None) for r in val_records]
    assert "entrypoint.not_found" in events
    not_found_rec = next(r for r in val_records if getattr(r, "event", None) == "entrypoint.not_found")
    assert "helper.py" in not_found_rec.message or "utils.py" in not_found_rec.message
