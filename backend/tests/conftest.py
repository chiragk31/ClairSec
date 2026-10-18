"""
Shared test fixtures and configuration.

pytest_collection_modifyitems hook: Docker-marked tests are skipped (not failed)
when the Docker daemon is unreachable. This avoids false red signals on machines
without Docker Desktop running (OPERATIONS §4, TESTING §4).

Auto-authenticating TestClient: all tests that hit the API use `authed_client`
which automatically includes the per-launch bearer token. This was landed early
(Step 3) so subsequent tests are written once, not rewritten (correction #8).
"""
from __future__ import annotations

import os

# Configure test environment before importing application modules
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("WORKSPACE_ROOT", "~/.clairsec/test-workspaces")
os.environ.setdefault("LLM_API_KEY", "test-mock-key")

import pytest
from fastapi.testclient import TestClient


def _docker_daemon_reachable() -> bool:
    """Check whether the Docker daemon is reachable. Returns False on any error."""
    try:
        import docker
        client = docker.from_env(timeout=2)
        client.ping()
        return True
    except Exception:
        return False


def _github_reachable() -> bool:
    """Check whether github.com answers over HTTPS. Returns False on any error."""
    try:
        import httpx
        r = httpx.head("https://codeload.github.com", timeout=4.0, follow_redirects=False)
        return r.status_code < 600
    except Exception:
        return False


# Cache once per session — avoid re-probing on every test
_DOCKER_AVAILABLE: bool | None = None
_NETWORK_AVAILABLE: bool | None = None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip docker/network-marked tests when the dependency is absent, before any fixture runs."""
    global _DOCKER_AVAILABLE, _NETWORK_AVAILABLE
    wants_docker = any("docker" in item.keywords for item in items)
    wants_network = any("network" in item.keywords for item in items)
    if wants_docker and _DOCKER_AVAILABLE is None:
        _DOCKER_AVAILABLE = _docker_daemon_reachable()
    if wants_network and _NETWORK_AVAILABLE is None:
        _NETWORK_AVAILABLE = _github_reachable()

    skip_docker = pytest.mark.skip(reason="Docker daemon not available — skipping Docker tests")
    skip_network = pytest.mark.skip(reason="github.com not reachable — skipping network tests")
    for item in items:
        if "docker" in item.keywords and not _DOCKER_AVAILABLE:
            item.add_marker(skip_docker)
        if "network" in item.keywords and not _NETWORK_AVAILABLE:
            item.add_marker(skip_network)


@pytest.fixture(scope="session", autouse=True)
def _isolate_auth_token_path(tmp_path_factory):
    """
    Redirect the auth token file to a temporary path for the whole test session.

    Without this, initialize_auth() writes to the real AUTH_TOKEN_PATH
    (~/.clairsec/auth_token). Any running backend and any connected desktop
    client then start failing with 401, because the file no longer matches the
    token the live server generated at its own startup. Tests must never write
    to the developer's real home directory.
    """
    from app.core.config import settings

    original = settings.auth_token_path
    token_dir = tmp_path_factory.mktemp("clairsec_auth")
    settings.auth_token_path = str(token_dir / "auth_token")
    yield
    settings.auth_token_path = original


@pytest.fixture(scope="session")
def app(_isolate_auth_token_path):
    """Create a FastAPI app instance with auth and database mock initialized."""
    from unittest.mock import AsyncMock, MagicMock
    from app.main import create_app
    from app.core.auth import initialize_auth
    from app.database.client import get_database

    application = create_app()
    initialize_auth()

    # Provide a default mock db so non-db tests do not block attempting to reach MongoDB
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test"))
    mock_col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_col.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_col)
    application.dependency_overrides[get_database] = lambda: mock_db

    return application


@pytest.fixture()
def authed_client(app):
    """
    TestClient with the per-launch bearer token automatically included.

    Use this instead of creating a bare TestClient — it ensures every request
    passes auth (C7.2) and the Host header is 'testserver' which is in the
    allowed_hosts list (correction #8).
    """
    from app.core.auth import get_launch_token

    token = get_launch_token()
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        yield client


@pytest.fixture()
def auth_headers():
    """Return auth headers dict for use with httpx or manual requests."""
    from app.core.auth import get_launch_token

    token = get_launch_token()
    return {"Authorization": f"Bearer {token}"}

