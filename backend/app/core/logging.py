"""
ClairSec Structured Diagnostic Logging System.

Provides consistent, end-to-end observable logging throughout the platform:
  - Contextual propagation via contextvars (request_id, project_id, job_id, scan_id, stage).
  - Secret redaction and input sanitization to prevent log injection and credential leaks.
  - Event-based stage boundary tracking (pipeline.stage.started, succeeded, failed).
  - Terminal-friendly structured formatting without duplicate log records.
  - Routine polling suppression to keep high-frequency health checks from drowning out logs.
"""
from __future__ import annotations

import contextvars
import logging
import re
import sys
import time
from contextlib import contextmanager
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Context variables for asynchronous request and pipeline tracing
# ---------------------------------------------------------------------------

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_project_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("project_id", default="")
_job_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="")
_scan_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("scan_id", default="")
_stage_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("stage", default="")


def set_log_context(
    *,
    request_id: str | None = None,
    project_id: str | None = None,
    job_id: str | None = None,
    scan_id: str | None = None,
    stage: str | None = None,
) -> None:
    """Set logging context variables for the current async task / thread."""
    if request_id is not None:
        _request_id_ctx.set(request_id)
    if project_id is not None:
        _project_id_ctx.set(project_id)
    if job_id is not None:
        _job_id_ctx.set(job_id)
    if scan_id is not None:
        _scan_id_ctx.set(scan_id)
    if stage is not None:
        _stage_ctx.set(stage)


def get_log_context() -> dict[str, str]:
    """Return a dictionary of the active logging context identifiers."""
    ctx = {
        "request_id": _request_id_ctx.get(),
        "project_id": _project_id_ctx.get(),
        "job_id": _job_id_ctx.get(),
        "scan_id": _scan_id_ctx.get(),
        "stage": _stage_ctx.get(),
    }
    return {k: v for k, v in ctx.items() if v}


def clear_log_context() -> None:
    """Reset all logging context variables to empty strings."""
    _request_id_ctx.set("")
    _project_id_ctx.set("")
    _job_id_ctx.set("")
    _scan_id_ctx.set("")
    _stage_ctx.set("")


@contextmanager
def log_context(
    *,
    request_id: str | None = None,
    project_id: str | None = None,
    job_id: str | None = None,
    scan_id: str | None = None,
    stage: str | None = None,
) -> Generator[None, None, None]:
    """Context manager to temporarily set log context and restore previous values on exit."""
    tokens = []
    if request_id is not None:
        tokens.append((_request_id_ctx, _request_id_ctx.set(request_id)))
    if project_id is not None:
        tokens.append((_project_id_ctx, _project_id_ctx.set(project_id)))
    if job_id is not None:
        tokens.append((_job_id_ctx, _job_id_ctx.set(job_id)))
    if scan_id is not None:
        tokens.append((_scan_id_ctx, _scan_id_ctx.set(scan_id)))
    if stage is not None:
        tokens.append((_stage_ctx, _stage_ctx.set(stage)))

    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


# ---------------------------------------------------------------------------
# Security: Secret Redaction and Log Input Sanitization
# ---------------------------------------------------------------------------

_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|bearer|authorization|auth_token|cookie)",
    re.IGNORECASE,
)

_BEARER_TOKEN_PATTERN = re.compile(
    r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*",
    re.IGNORECASE,
)

_INLINE_SECRET_PATTERN = re.compile(
    r"((?:password|passwd|secret|token|api[_-]?key|key)\s*[:=]\s*)([^\s,;&]+)",
    re.IGNORECASE,
)


def sanitize_log_str(val: Any) -> str:
    """
    Sanitize untrusted user string inputs for logs:
    - Removes newlines and carriage returns to prevent log injection.
    - Truncates excessively long values.
    """
    if val is None:
        return "None"
    s = str(val)
    # Replace control characters to prevent log injection
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if len(s) > 1000:
        return s[:997] + "..."
    return s


def redact_secrets(data: Any) -> Any:
    """
    Recursively redact sensitive keys and values (passwords, tokens, keys)
    from dictionaries, lists, or header mappings.
    """
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            key_str = str(k)
            if _SENSITIVE_KEY_PATTERNS.search(key_str):
                redacted[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                redacted[k] = redact_secrets(v)
            elif isinstance(v, str):
                redacted[k] = redact_secrets(v)
            else:
                redacted[k] = v
        return redacted
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, str):
        s = _BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", data)
        return _INLINE_SECRET_PATTERN.sub(r"\1[REDACTED]", s)
    return data


# ---------------------------------------------------------------------------
# Log Filter: Injects context variables and event metadata into LogRecords
# ---------------------------------------------------------------------------

class ClairSecLogFilter(logging.Filter):
    """
    Enriches each LogRecord with:
      - req_id / request_id: current request identifier
      - proj_id / project_id: current project identifier
      - job_id: current job identifier
      - scan_id: current scan identifier
      - stage: current processing stage
      - event: structured event name if supplied via extra={'event': ...}
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Contextvars
        record.req_id = getattr(record, "req_id", None) or _request_id_ctx.get()
        record.request_id = record.req_id
        record.project_id = getattr(record, "project_id", None) or _project_id_ctx.get()
        record.job_id = getattr(record, "job_id", None) or _job_id_ctx.get()
        record.scan_id = getattr(record, "scan_id", None) or _scan_id_ctx.get()
        record.stage = getattr(record, "stage", None) or _stage_ctx.get()
        record.event = getattr(record, "event", None) or getattr(record, "event_name", None)

        # Redact secrets in raw messages
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)

        return True


# ---------------------------------------------------------------------------
# Structured Terminal Formatter
# ---------------------------------------------------------------------------

class ClairSecTerminalFormatter(logging.Formatter):
    """
    Clean, human-readable structured formatter designed for terminal output.

    Format:
      YYYY-MM-DD HH:MM:SS.mmm [LEVEL] [logger] [tags] [event=...] Message
    """

    def format(self, record: logging.LogRecord) -> str:
        # Format timestamp with milliseconds
        created_sec = int(record.created)
        msec = int(record.msecs)
        t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_sec))
        timestamp = f"{t_str}.{msec:03d}"

        level = record.levelname.ljust(5)
        logger_name = record.name

        # Tags
        tags: list[str] = []
        req_id = getattr(record, "req_id", "") or getattr(record, "request_id", "")
        if req_id:
            tags.append(f"req:{req_id[:8]}")

        proj_id = getattr(record, "project_id", "") or getattr(record, "proj_id", "")
        if proj_id:
            tags.append(f"proj:{proj_id[:8]}")

        job_id = getattr(record, "job_id", "")
        if job_id:
            tags.append(f"job:{job_id[:8]}")

        scan_id = getattr(record, "scan_id", "")
        if scan_id:
            tags.append(f"scan:{scan_id[:8]}")

        stage = getattr(record, "stage", "")
        if stage:
            tags.append(f"stage:{stage}")

        tags_str = f" [{' '.join(tags)}]" if tags else ""

        event = getattr(record, "event", None)
        event_str = f" [{event}]" if event else ""

        # Format message
        record.message = record.getMessage()

        base = f"{timestamp} [{level}] [{logger_name}]{tags_str}{event_str} {record.message}"

        # Traceback formatting for exceptions
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                base = f"{base}\n{record.exc_text}"

        if record.stack_info:
            base = f"{base}\n{self.formatStack(record.stack_info)}"

        return base


# ---------------------------------------------------------------------------
# Stage Tracing Helper
# ---------------------------------------------------------------------------

@contextmanager
def trace_stage(
    logger: logging.Logger,
    stage_name: str,
    event_prefix: str,
    inputs: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager to trace a pipeline stage boundary.
    Logs:
      - <event_prefix>.started on entry with sanitized inputs
      - <event_prefix>.succeeded on exit with elapsed duration
      - <event_prefix>.failed on exception with traceback and elapsed duration
    """
    t0 = time.perf_counter()
    with log_context(stage=stage_name):
        input_desc = ""
        if inputs:
            sanitized_inputs = redact_secrets(inputs)
            input_desc = f" | inputs: {sanitized_inputs}"

        logger.info(
            "Stage %s started%s",
            stage_name,
            input_desc,
            extra={"event": f"{event_prefix}.started"},
        )
        try:
            yield
            elapsed_sec = time.perf_counter() - t0
            logger.info(
                "Stage %s succeeded (took %.3fs)",
                stage_name,
                elapsed_sec,
                extra={"event": f"{event_prefix}.succeeded"},
            )
        except Exception as exc:
            elapsed_sec = time.perf_counter() - t0
            logger.exception(
                "Stage %s failed after %.3fs: %s",
                stage_name,
                elapsed_sec,
                exc,
                extra={"event": f"{event_prefix}.failed"},
            )
            raise


# ---------------------------------------------------------------------------
# Setup logging configuration
# ---------------------------------------------------------------------------

_logging_configured = False


def setup_logging(log_level: int = logging.INFO) -> None:
    """
    Configure application logging uniformly:
      - Installs ClairSecLogFilter and ClairSecTerminalFormatter.
      - Ensures log records propagate without duplicate prints.
      - Applied to root logger and app loggers.
    """
    global _logging_configured
    if _logging_configured:
        return

    root_logger = logging.getLogger()
    app_logger = logging.getLogger("app")

    # If root logger has existing StreamHandlers (e.g. from uvicorn or basicConfig),
    # update their formatter and add the ClairSec filter.
    formatter = ClairSecTerminalFormatter()
    log_filter = ClairSecLogFilter()

    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(log_filter)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
            handler.addFilter(log_filter)

    # Attach filter to root logger
    root_logger.addFilter(log_filter)
    app_logger.addFilter(log_filter)

    root_logger.setLevel(log_level)
    app_logger.setLevel(log_level)

    _logging_configured = True
