"""
Target access abstractions exposing a base_url for scanner agents.
Implements Rule R5:
  1. ContainerTargetHandle: production path wrapping isolated Docker container via proxy.
  2. LocalFixtureTargetHandle: TEST-ONLY seam running our own fixtures on an ephemeral localhost port.
     Hard-gated to the tests/fixtures directory; refuses any external path.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import socket
import sys
from typing import Any, Protocol
import uuid

import httpx
import uvicorn


class TargetAccessForbiddenError(PermissionError):
    """Raised when LocalFixtureTargetHandle is asked to run code outside tests/fixtures/."""


class TargetHandle(Protocol):
    """Protocol for interacting with a target under test."""

    @property
    def base_url(self) -> str:
        """Target HTTP base URL, e.g. 'http://127.0.0.1:49210'."""
        ...

    async def is_healthy(self) -> bool:
        """Return True if the target responds 2xx on /health."""
        ...

    async def stop(self) -> None:
        """Clean up and terminate the running target."""
        ...


class ContainerTargetHandle:
    """Production target handle backed by a hardened Docker container and scanner proxy."""

    def __init__(self, proxy_port: int, container_id: str, docker_manager: Any = None):
        self._proxy_port = proxy_port
        self._container_id = container_id
        self._docker_manager = docker_manager

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._proxy_port}"

    async def is_healthy(self) -> bool:
        health_url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(health_url)
                return 200 <= r.status_code < 300
        except Exception:
            return False

    async def stop(self) -> None:
        if self._docker_manager and self._container_id:
            await asyncio.to_thread(self._docker_manager.stop_container, self._container_id)


class LocalFixtureTargetHandle:
    """
    TEST-ONLY target runner starting a ClairSec fixture with uvicorn on ephemeral localhost.
    Enforces Rule R5: strictly hard-gated to backend/tests/fixtures/.
    """

    ALLOWED_FIXTURE_ROOT = (
        Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    ).resolve()

    def __init__(self, fixture_dir: str | Path, app_module: str = "main:app"):
        resolved = Path(fixture_dir).resolve()
        # Security hard gate (Rule R5 & SECURITY.md)
        try:
            resolved.relative_to(self.ALLOWED_FIXTURE_ROOT)
        except ValueError:
            raise TargetAccessForbiddenError(
                f"LocalFixtureTargetHandle refused path outside fixtures root: {resolved} "
                f"(allowed root: {self.ALLOWED_FIXTURE_ROOT})"
            )

        self._fixture_dir = resolved
        self._app_module = app_module
        self._port: int | None = None
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("LocalFixtureTargetHandle has not been started yet.")
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @staticmethod
    def _find_ephemeral_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    async def start(self) -> str:
        """Start the fixture application on an ephemeral port."""
        if self._server_task and not self._server_task.done():
            return self.base_url

        self._port = self._find_ephemeral_port()

        # Dynamically load the FastAPI app from the fixture directory
        module_name, app_attr = self._app_module.split(":")
        main_py = self._fixture_dir / f"{module_name}.py"
        if not main_py.exists():
            raise FileNotFoundError(f"Fixture entrypoint not found: {main_py}")

        spec = importlib.util.spec_from_file_location(
            f"fixture_{self._fixture_dir.name}", main_py
        )
        if not spec or not spec.loader:
            raise ImportError(f"Could not load module from {main_py}")

        module = importlib.util.module_from_spec(spec)
        # Temporarily ensure fixture dir is on path for relative imports if any
        sys_path_inserted = False
        if str(self._fixture_dir) not in sys.path:
            sys.path.insert(0, str(self._fixture_dir))
            sys_path_inserted = True

        try:
            spec.loader.exec_module(module)
            app = getattr(module, app_attr)
        finally:
            if sys_path_inserted:
                sys.path.remove(str(self._fixture_dir))

        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)

        # Launch server in async task
        self._server_task = asyncio.create_task(self._server.serve())

        # Wait until server is listening / healthy
        for _ in range(50):  # up to 5 seconds
            if await self.is_healthy():
                return self.base_url
            await asyncio.sleep(0.1)

        raise TimeoutError(f"Local fixture failed to start healthy at {self.base_url}")

    async def is_healthy(self) -> bool:
        if self._port is None:
            return False
        health_url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                r = await client.get(health_url)
                return 200 <= r.status_code < 300
        except Exception:
            return False

    async def stop(self) -> None:
        """Stop the local fixture server."""
        if self._server:
            self._server.should_exit = True
        if self._server_task:
            try:
                await asyncio.wait_for(self._server_task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._server_task.cancel()
            self._server_task = None
        self._server = None
        self._port = None


class LocalWorkspaceTargetHandle:
    """
    Target runner starting a target from modified_workspace/ (or a scan workspace)
    with uvicorn on an ephemeral localhost port.
    Enforces that workspace_dir is a workspace directory under a modified_workspace/ tree.
    """

    def __init__(self, workspace_dir: str | Path, app_module: str = "main:app"):
        resolved = Path(workspace_dir).resolve()
        if not (
            resolved.name == "modified_workspace"
            or "workspaces" in resolved.parts
            or "modified_workspace" in resolved.parts
        ):
            raise TargetAccessForbiddenError(
                f"LocalWorkspaceTargetHandle refused non-workspace path: {resolved}"
            )

        self._workspace_dir = resolved
        self._app_module = app_module
        self._port: int | None = None
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("LocalWorkspaceTargetHandle has not been started yet.")
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @staticmethod
    def _find_ephemeral_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    async def start(self) -> str:
        """Start the modified workspace application on an ephemeral port."""
        if self._server_task and not self._server_task.done():
            return self.base_url

        self._port = self._find_ephemeral_port()

        module_name, app_attr = self._app_module.split(":")
        main_py = self._workspace_dir / f"{module_name}.py"
        if not main_py.exists():
            raise FileNotFoundError(f"Workspace entrypoint not found: {main_py}")

        mod_key = f"workspace_{uuid.uuid4().hex[:8]}"
        spec = importlib.util.spec_from_file_location(mod_key, main_py)
        if not spec or not spec.loader:
            raise ImportError(f"Could not load module from {main_py}")

        module = importlib.util.module_from_spec(spec)
        sys_path_inserted = False
        if str(self._workspace_dir) not in sys.path:
            sys.path.insert(0, str(self._workspace_dir))
            sys_path_inserted = True

        try:
            try:
                spec.loader.exec_module(module)
                app = getattr(module, app_attr)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                    raise
                raise RuntimeError(f"Failed to load application module from {main_py}: {exc}") from exc
        finally:
            if sys_path_inserted:
                sys.path.remove(str(self._workspace_dir))

        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())

        for _ in range(50):
            if await self.is_healthy():
                return self.base_url
            await asyncio.sleep(0.1)

        raise TimeoutError(f"Workspace target failed to start healthy at {self.base_url}")

    async def is_healthy(self) -> bool:
        if self._port is None:
            return False
        health_url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                r = await client.get(health_url)
                return 200 <= r.status_code < 300
        except Exception:
            return False

    async def stop(self) -> None:
        """Stop the workspace target server."""
        if self._server:
            self._server.should_exit = True
        if self._server_task:
            try:
                await asyncio.wait_for(self._server_task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._server_task.cancel()
            self._server_task = None
        self._server = None
        self._port = None
