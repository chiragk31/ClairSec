"""
Per-launch authentication, Host header validation, and CORS policy.

THREAT_MODEL C7.1–C7.4:
  C7.1: Bind to 127.0.0.1 only (enforced in config/uvicorn, not here)
  C7.2: Per-launch bearer token, written to an owner-readable local file
  C7.3: CORS: deny all origins (Flutter desktop doesn't send Origin headers);
        validate Host header against an allowlist
  C7.4: WebSocket connections require the same token

The token is generated at startup, written to AUTH_TOKEN_PATH, and required on
every request as `Authorization: Bearer <token>`.

On Windows, os.chmod(0o600) is a no-op. We attempt to set a restrictive ACL via
pywin32 if available; otherwise we document this as a residual risk.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sys
from pathlib import Path

from fastapi import Depends, HTTPException, Request, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Module-level token, set once at startup
_launch_token: str | None = None


def get_launch_token() -> str:
    """Return the current launch token. Raises if not yet initialized."""
    if _launch_token is None:
        raise RuntimeError("Auth token not initialized. Call initialize_auth() first.")
    return _launch_token


def initialize_auth(force: bool = False) -> str:
    """
    Generate a per-launch bearer token and write it to the auth token file.

    Called once during FastAPI lifespan startup. The Flutter client reads
    this file to authenticate its requests.

    Returns the generated token.
    """
    global _launch_token
    if _launch_token is not None and not force:
        return _launch_token

    _launch_token = secrets.token_hex(32)

    token_path = Path(settings.auth_token_path).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(_launch_token, encoding="utf-8")

    # Attempt to restrict file permissions
    _restrict_file_permissions(token_path)

    logger.info("Auth token written to %s", token_path)
    return _launch_token


def _restrict_file_permissions(path: Path) -> None:
    """
    Restrict token file to owner-only access.

    On POSIX: chmod 0o600.
    On Windows: attempt ACL via pywin32 if available, otherwise log the limitation.
    """
    if sys.platform == "win32":
        try:
            import ntsecuritycon as con
            import win32security

            # Get the current user's SID
            user_name = os.environ.get("USERNAME", "")
            sd = win32security.GetFileSecurity(
                str(path), win32security.DACL_SECURITY_INFORMATION
            )
            dacl = win32security.ACL()

            user_sid = win32security.LookupAccountName(None, user_name)[0]
            # Grant full control only to the current user
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                con.FILE_GENERIC_READ | con.FILE_GENERIC_WRITE,
                user_sid,
            )
            sd.SetSecurityDescriptorDacl(1, dacl, 0)
            win32security.SetFileSecurity(
                str(path), win32security.DACL_SECURITY_INFORMATION, sd
            )
            logger.debug("Set restrictive ACL on token file (Windows)")
        except ImportError:
            logger.warning(
                "pywin32 not available — cannot set restrictive ACL on auth token "
                "file %s. This is a documented residual risk on Windows (C7.2).",
                path,
            )
        except Exception as exc:
            logger.warning(
                "Failed to set ACL on auth token file %s: %s. "
                "Documented residual risk on Windows (C7.2).",
                path,
                exc,
            )
    else:
        # POSIX
        os.chmod(path, 0o600)


from starlette.requests import HTTPConnection


async def verify_token(
    conn: HTTPConnection,
) -> str:
    """
    FastAPI dependency that verifies the per-launch bearer token.

    Returns the token on success, raises 401 on failure for HTTP requests.
    WebSocket endpoints use explicit ws_auth dependency (C6, C7.4).
    """
    auth_header = conn.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:].strip()
    launch_token = get_launch_token()
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, launch_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


async def ws_auth(websocket: WebSocket) -> str:
    """
    FastAPI dependency that enforces WebSocket per-launch authentication (C5, C6, C7.4).
    Rejects query param tokens (do not log them).
    Accepts Sec-WebSocket-Protocol or first JSON auth message.
    """
    if "token" in websocket.query_params:
        logger.warning("Rejected WebSocket connection: auth token in query param is prohibited (C5)")
        # Note: Do NOT log the token value
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Query param token prohibited")

    launch_token = get_launch_token()

    # 1. Check Sec-WebSocket-Protocol header
    subprotocol_header = websocket.headers.get("sec-websocket-protocol")
    if subprotocol_header:
        parts = [p.strip() for p in subprotocol_header.split(",")]
        token_candidate = None
        selected_subprotocol = None
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token_candidate = parts[1]
            selected_subprotocol = parts[0]
        elif len(parts) == 1:
            token_candidate = parts[0]
            selected_subprotocol = parts[0]

        if token_candidate and secrets.compare_digest(token_candidate, launch_token):
            websocket.state.subprotocol = selected_subprotocol
            return token_candidate

        logger.warning("WebSocket handshake rejected: invalid Sec-WebSocket-Protocol token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")

    # 2. Accept and await first JSON auth message
    await websocket.accept()
    websocket.state.accepted = True
    try:
        msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        if isinstance(msg, dict) and msg.get("type") == "auth":
            client_tok = msg.get("token", "")
            if client_tok and secrets.compare_digest(client_tok, launch_token):
                if "after_seq" in msg:
                    websocket.state.after_seq = int(msg["after_seq"])
                return client_tok
    except Exception:
        pass

    logger.warning("WebSocket handshake rejected: unauthorized first message")
    raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")


def validate_host_header(request: Request) -> None:
    """
    Validate the Host header against an allowlist.

    Rejects requests not directed at localhost to prevent DNS rebinding
    attacks (THREAT_MODEL C7.3).

    The Starlette Host-header bypass class of vulnerability makes this
    concrete rather than theoretical.
    """
    allowed_hosts = settings.allowed_hosts
    host = request.headers.get("host", "")
    # Strip port
    host_without_port = host.split(":")[0].lower()

    if host_without_port not in allowed_hosts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Host header: {host}",
        )
