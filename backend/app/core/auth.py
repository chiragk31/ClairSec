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

import logging
import os
import secrets
import sys
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
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


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """
    FastAPI dependency that verifies the per-launch bearer token.

    Returns the token on success, raises 401 on failure.
    Used as a global dependency on the app.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = get_launch_token()
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(credentials.credentials, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials


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
