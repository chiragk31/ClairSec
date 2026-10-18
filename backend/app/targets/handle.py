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
import logging
from pathlib import Path
import socket
import sys
from typing import Any, Protocol
import uuid

import httpx
import uvicorn

from app.core.config import settings

logger = logging.getLogger(__name__)


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

    def __init__(self, fixture_dir: str | Path, app_module: str = "main:app"):
        resolved = Path(fixture_dir).resolve()
        # Security hard gate (Rule R5 & SECURITY.md)
        if not is_trusted_fixture_path(resolved):
            raise TargetAccessForbiddenError(
                f"LocalFixtureTargetHandle refused path outside fixtures root: {resolved} "
                f"(allowed root: {settings.trusted_fixtures_root})"
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


def resolve_workspace_entrypoint(
    workspace_dir: Path | str,
    entry_point: str | None = None,
    app_module: str = "main:app",
) -> tuple[Path, str, str]:
    """
    Resolve the absolute entrypoint Python file, module import path, and FastAPI app attribute name.

    Returns (resolved_file_path, module_name, app_attribute_name).
    Raises FileNotFoundError with bounded file list if the entrypoint cannot be resolved/found.
    """
    workspace_dir = Path(workspace_dir).resolve()

    def _get_bounded_py_files() -> list[str]:
        try:
            return [
                str(p.relative_to(workspace_dir)).replace("\\", "/")
                for p in sorted(workspace_dir.rglob("*.py"))
                if not any(part.startswith(".") for part in p.parts)
            ][:20]
        except Exception:  # noqa: BLE001
            return []

    # 1. If explicit entry_point is provided
    if entry_point:
        clean = str(entry_point).replace("\\", "/").strip("/")
        if ":" in clean:
            file_part, app_attr = clean.split(":", 1)
        else:
            file_part = clean
            app_attr = app_module.split(":")[1] if ":" in app_module else "app"

        if file_part.endswith(".py"):
            rel_file = Path(file_part)
            mod_name = file_part.removesuffix(".py").replace("/", ".")
        elif "." in file_part or "/" in file_part:
            rel_file = Path(*file_part.replace("/", ".").split(".")).with_suffix(".py")
            mod_name = file_part.replace("/", ".")
        else:
            rel_file = Path(f"{file_part}.py")
            mod_name = file_part

        resolved = (workspace_dir / rel_file).resolve()
        if resolved.exists() and resolved.is_file():
            return resolved, mod_name, app_attr

    # 2. If app_module is provided, check module path
    if app_module:
        mod_part, app_attr = app_module.split(":", 1) if ":" in app_module else (app_module, "app")
        clean_mod = mod_part.replace("\\", "/").strip("/")
        if clean_mod.endswith(".py"):
            rel_file = Path(clean_mod)
            mod_name = clean_mod.removesuffix(".py").replace("/", ".")
        elif "." in clean_mod or "/" in clean_mod:
            rel_file = Path(*clean_mod.replace("/", ".").split(".")).with_suffix(".py")
            mod_name = clean_mod.replace("/", ".")
        else:
            rel_file = Path(f"{clean_mod}.py")
            mod_name = clean_mod

        resolved = (workspace_dir / rel_file).resolve()
        if resolved.exists() and resolved.is_file():
            return resolved, mod_name, app_attr

    # 3. Check workspace_dir / "main.py"
    default_main = (workspace_dir / "main.py").resolve()
    if default_main.exists() and default_main.is_file():
        return default_main, "main", "app"

    # 4. Auto-discovery fallback: search for a file defining FastAPI()
    try:
        from app.services.fastapi_validator import validate_fastapi_project

        val_result = validate_fastapi_project(str(workspace_dir))
        if val_result.entry_point:
            clean_discovered = val_result.entry_point.replace("\\", "/").strip("/")
            discovered_path = (workspace_dir / clean_discovered).resolve()
            if discovered_path.exists() and discovered_path.is_file():
                mod_name = clean_discovered.removesuffix(".py").replace("/", ".")
                logger.info(
                    "Auto-discovered workspace entrypoint '%s' (%s)",
                    clean_discovered,
                    discovered_path,
                    extra={"event": "workspace.entrypoint.discovered"},
                )
                return discovered_path, mod_name, "app"
    except Exception as disc_err:  # noqa: BLE001
        logger.debug("Auto-discovery check encountered error: %s", disc_err)

    # 5. Missing entrypoint - log error with bounded file list and raise FileNotFoundError
    candidates = _get_bounded_py_files()
    attempted = str(entry_point or app_module or "main.py")
    logger.error(
        "Workspace entrypoint not found: '%s' in workspace root '%s'. Available Python files (%d): %s",
        attempted,
        workspace_dir,
        len(candidates),
        candidates,
        extra={
            "event": "workspace.entrypoint.not_found",
            "workspace_root": str(workspace_dir),
            "attempted_entrypoint": attempted,
            "files": candidates,
        },
    )
    raise FileNotFoundError(
        f"Workspace entrypoint not found: '{attempted}' in workspace {workspace_dir}. "
        f"Available Python files: {candidates}"
    )


def is_trusted_fixture_path(path: str | Path) -> bool:
    """Return True if the resolved path is contained within settings.trusted_fixtures_root."""
    try:
        resolved = Path(path).resolve()
        fixtures_root = Path(settings.trusted_fixtures_root).resolve()
        return resolved.is_relative_to(fixtures_root)
    except Exception:
        return False


class TrustedFixtureTargetHandle:
    """
    Target runner for trusted test fixtures (under settings.trusted_fixtures_root) with
    uvicorn on an ephemeral localhost port.
    Host execution of untrusted workspace code is strictly forbidden (FEATURES.md F0, C3).
    """

    def __init__(
        self,
        workspace_dir: str | Path,
        app_module: str = "main:app",
        entry_point: str | None = None,
        *,
        trusted_source_path: str | Path | None = None,
        project_workspace_root: str | Path | None = None,
    ):
        """
        Trust is decided only from values the caller passes explicitly (D5):

        - ``workspace_dir`` itself lies inside the trusted fixtures root, or
        - ``trusted_source_path`` (taken from the project's database record) lies
          inside the trusted fixtures root AND ``workspace_dir`` lies inside that
          project's own platform workspace root (``project_workspace_root``).

        Nothing is ever read from disk to decide trust: a marker file next to
        repository content could be planted by the repository itself.
        """
        resolved = Path(workspace_dir).resolve()
        trusted = is_trusted_fixture_path(resolved)
        if not trusted and trusted_source_path and project_workspace_root:
            ws_root = Path(project_workspace_root).resolve()
            if is_trusted_fixture_path(trusted_source_path) and resolved.is_relative_to(ws_root):
                trusted = True

        if not trusted:
            raise TargetAccessForbiddenError(
                f"TrustedFixtureTargetHandle refused non-fixture path: {resolved}. "
                f"Host execution is only permitted for test fixtures under {settings.trusted_fixtures_root}."
            )

        self._workspace_dir = resolved
        self._app_module = app_module
        self._entry_point = entry_point
        self._port: int | None = None
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("TrustedFixtureTargetHandle has not been started yet.")
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

        # Validate that the resolved entrypoint exists before attempting to start
        entry_path, module_name, app_attr = resolve_workspace_entrypoint(
            self._workspace_dir,
            entry_point=self._entry_point,
            app_module=self._app_module,
        )

        self._port = self._find_ephemeral_port()

        mod_key = f"workspace_{uuid.uuid4().hex[:8]}"
        spec = importlib.util.spec_from_file_location(mod_key, entry_path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not load module from {entry_path}")

        module = importlib.util.module_from_spec(spec)
        paths_to_remove = []
        if str(self._workspace_dir) not in sys.path:
            sys.path.insert(0, str(self._workspace_dir))
            paths_to_remove.append(str(self._workspace_dir))
        if str(entry_path.parent) not in sys.path:
            sys.path.insert(0, str(entry_path.parent))
            paths_to_remove.append(str(entry_path.parent))

        try:
            try:
                spec.loader.exec_module(module)
                app = getattr(module, app_attr, None)
                if app is None:
                    for attr in dir(module):
                        val = getattr(module, attr, None)
                        if val is not None and getattr(val, "__class__", None).__name__ == "FastAPI":
                            app = val
                            break
                if app is None:
                    raise AttributeError(f"Module '{module_name}' has no attribute '{app_attr}' or FastAPI instance")
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                    raise
                raise RuntimeError(f"Failed to load application module from {entry_path}: {exc}") from exc
        finally:
            for p in paths_to_remove:
                if p in sys.path:
                    sys.path.remove(p)

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
        for path in ("/health", "/", "/docs", "/openapi.json"):
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    r = await client.get(f"{self.base_url}{path}")
                    if 200 <= r.status_code < 500:
                        return True
            except Exception:  # noqa: BLE001
                continue
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

