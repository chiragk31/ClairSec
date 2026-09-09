"""
Evidence capture, size capping, and redaction (DATA_MODEL.md §2, THREAT_MODEL C5.2).

Enforces:
1. Pre-persistence secret and canary token redaction.
2. 64 KB size limit per request/response body with SHA-256 digest on truncation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.llm.redaction import redact_secrets

MAX_BODY_BYTES = 64 * 1024  # 64 KB per DATA_MODEL.md §2


def sanitize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Sanitize sensitive headers before persistence."""
    if not headers:
        return {}

    sanitized: dict[str, str] = {}
    for k, v in headers.items():
        k_lower = k.lower()
        if k_lower in ("authorization", "x-api-key", "cookie", "set-cookie"):
            # If it is a synthetic test token like 'Bearer alice-token-123', preserve it
            # per DATA_MODEL.md §4 exception, but redact real JWTs / API keys
            sanitized[k] = redact_secrets(v)
        else:
            sanitized[k] = redact_secrets(v)
    return sanitized


def bound_and_redact_body(body: Any) -> tuple[Any, bool, str | None]:
    """
    Format, redact, and bound body to 64 KB.
    Returns: (bounded_body, truncated: bool, sha256_digest: str | None)
    """
    if body is None:
        return None, False, None

    if isinstance(body, (dict, list)):
        raw_str = json.dumps(body, default=str)
    elif isinstance(body, bytes):
        raw_str = body.decode("utf-8", errors="replace")
    else:
        raw_str = str(body)

    # Redact secrets
    scrubbed_str = redact_secrets(raw_str)
    encoded = scrubbed_str.encode("utf-8")

    if len(encoded) > MAX_BODY_BYTES:
        truncated = True
        digest = hashlib.sha256(encoded).hexdigest()
        bounded_body = encoded[:MAX_BODY_BYTES].decode("utf-8", errors="ignore")
        return bounded_body, truncated, digest

    # If it was originally JSON, try to return parsed dict/list for clean serialization
    if isinstance(body, (dict, list)):
        try:
            return json.loads(scrubbed_str), False, None
        except Exception:
            return scrubbed_str, False, None

    return scrubbed_str, False, None


def capture_request_evidence(
    method: str,
    url_path: str,
    headers: dict[str, str] | None,
    body: Any = None,
) -> dict[str, Any]:
    """Format request evidence record."""
    sanitized_headers = sanitize_headers(headers)
    bounded_body, truncated, digest = bound_and_redact_body(body)
    return {
        "method": method.upper(),
        "url_path": url_path,
        "headers": sanitized_headers,
        "body": bounded_body,
        "truncated": truncated,
        "sha256": digest,
    }


def capture_response_evidence(
    status_code: int,
    headers: dict[str, str] | None,
    body: Any,
    elapsed_ms: int,
) -> dict[str, Any]:
    """Format response evidence record."""
    sanitized_headers = sanitize_headers(headers)
    bounded_body, truncated, digest = bound_and_redact_body(body)
    return {
        "status": status_code,
        "headers": sanitized_headers,
        "body": bounded_body,
        "elapsed_ms": elapsed_ms,
        "truncated": truncated,
        "sha256": digest,
    }
