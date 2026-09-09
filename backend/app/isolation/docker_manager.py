"""
Docker manager — isolated target lifecycle.

SECURITY requirements enforced here:
  - No host environment variables are passed into the target container (env={}).
  - Target container is placed on an isolated bridge network, not the host network.
  - Resource limits (mem, cpu) are enforced on every container start.
  - Build and startup have hard timeouts to prevent hangs.
  - Container logs are size-limited before returning to the caller.
  - All Docker output/errors are treated as untrusted text (logged, never eval'd).
  - Cleanup is called on every failure path.

Generated Dockerfile design:
  - FROM python:3.11-slim (minimal, reproducible base)
  - COPY the scan_workspace content
  - pip install from the detected dependency manifest
  - EXPOSE the configured port
  - CMD: uvicorn {entry_module}:app
  The user's project does NOT need to provide a Dockerfile.

Container naming: clairsec-target-{project_id[:8]} — deterministic for lookup/cleanup.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import docker
import docker.errors
import httpx

from app.core.config import settings
from app.isolation.errors import IsolationError

logger = logging.getLogger(__name__)

_IMAGE_PREFIX = "clairsec-image"
_CONTAINER_PREFIX = "clairsec-target"

# Template Dockerfile — intentionally minimal.
# Security note: we never expose host env vars to this container.
_DOCKERFILE_TEMPLATE = """\
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY {dep_file} .
RUN pip install --no-cache-dir -r {dep_file}

# Copy the rest of the project
COPY . .

EXPOSE {port}

CMD ["uvicorn", "{entry_module}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""

_DOCKERFILE_PYPROJECT_TEMPLATE = """\
FROM python:3.11-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

EXPOSE {port}

CMD ["uvicorn", "{entry_module}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""


class DockerManager:
    def __init__(self) -> None:
        try:
            self._client = docker.from_env()
        except docker.errors.DockerException as exc:
            raise IsolationError(
                f"Cannot connect to Docker daemon. Is Docker running? Details: {exc}"
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Network
    # ─────────────────────────────────────────────────────────────────────────

    def ensure_network(self) -> None:
        """Create the isolated bridge network if it doesn't already exist."""
        net_name = settings.docker_network_name
        try:
            self._client.networks.get(net_name)
            logger.debug("Docker network '%s' already exists", net_name)
        except docker.errors.NotFound:
            self._client.networks.create(
                net_name,
                driver="bridge",
                # internal=False (default): allows the backend to reach the container
                # via mapped host ports for health checking and attack traffic.
                # A bridge network already isolates the container from the host LAN;
                # containers are only reachable through explicitly published ports.
                # Setting internal=True would block all host→container traffic,
                # including our own health check, which is not what we want.
                labels={"managed-by": "clairsec"},
            )
            logger.info("Created isolated Docker network '%s'", net_name)

    # ─────────────────────────────────────────────────────────────────────────
    # Naming helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def image_tag(project_id: str) -> str:
        return f"{_IMAGE_PREFIX}-{project_id[:8]}:latest"

    @staticmethod
    def container_name(project_id: str) -> str:
        return f"{_CONTAINER_PREFIX}-{project_id[:8]}"

    # ─────────────────────────────────────────────────────────────────────────
    # Dockerfile generation
    # ─────────────────────────────────────────────────────────────────────────

    def _write_dockerfile(
        self,
        workspace_path: Path,
        entry_point: str,
        dependency_file: str | None,
    ) -> None:
        """
        Write a generated Dockerfile into the workspace.

        The entry_point is a relative path like 'main.py' or 'src/app.py'.
        We convert it to a Python module path for uvicorn.
        """
        # Convert path like 'src/app.py' → 'src.app'
        entry_module = entry_point.replace("/", ".").replace("\\", ".").removesuffix(".py")
        port = str(settings.docker_target_port)

        if dependency_file and dependency_file.endswith(".txt"):
            content = _DOCKERFILE_TEMPLATE.format(
                dep_file=dependency_file,
                port=port,
                entry_module=entry_module,
            )
        else:
            # pyproject.toml or no dep file — fall back to pip install .
            content = _DOCKERFILE_PYPROJECT_TEMPLATE.format(
                port=port,
                entry_module=entry_module,
            )

        dockerfile_path = workspace_path / "Dockerfile"
        dockerfile_path.write_text(content, encoding="utf-8")
        logger.debug("Wrote generated Dockerfile to %s", dockerfile_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Image build
    # ─────────────────────────────────────────────────────────────────────────

    def build_image(
        self,
        project_id: str,
        workspace_path: Path,
        entry_point: str,
        dependency_file: str | None,
    ) -> str:
        """
        Write a Dockerfile into the workspace and build a Docker image.

        Returns the image tag on success.
        Raises IsolationError on build failure or timeout.

        Build output is treated as untrusted text — logged but not executed.
        """
        tag = self.image_tag(project_id)
        self._write_dockerfile(workspace_path, entry_point, dependency_file)

        logger.info("Building Docker image %s from %s", tag, workspace_path)
        try:
            _image, build_logs = self._client.images.build(
                path=str(workspace_path),
                tag=tag,
                rm=True,           # remove intermediate containers
                forcerm=True,
                timeout=settings.docker_build_timeout,
                buildargs={},      # no host secrets passed as build args
                # network_mode intentionally omitted during build so pip install works
            )
            # Log build output (treated as untrusted text — no eval)
            for chunk in build_logs:
                if "stream" in chunk:
                    line = str(chunk["stream"]).strip()
                    if line:
                        logger.debug("[build:%s] %s", project_id[:8], line)
            logger.info("Successfully built image %s", tag)
            return tag

        except docker.errors.BuildError as exc:
            # Capture a bounded amount of build output for the error message
            err_lines = []
            for log_entry in exc.build_log:
                if "stream" in log_entry:
                    err_lines.append(str(log_entry["stream"]).strip())
                if len(err_lines) >= 50:
                    err_lines.append("... (truncated)")
                    break
            build_output = "\n".join(filter(None, err_lines))
            raise IsolationError(
                f"Docker build failed for project {project_id}: {exc.msg}\n"
                f"Build output (last 50 lines):\n{build_output}"
            ) from exc

        except Exception as exc:  # noqa: BLE001
            raise IsolationError(
                f"Unexpected error building image for project {project_id}: {exc}"
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Container start / stop
    # ─────────────────────────────────────────────────────────────────────────

    def start_container(self, project_id: str, image_tag: str) -> tuple[str, str]:
        """
        Start an isolated container from the built image.

        Returns (container_id, container_name).

        Security properties:
          - env={}: no host environment variables passed to the container
          - network_mode=clairsec-net: isolated bridge, not host
          - mem_limit: per settings
          - nano_cpus: per settings
          - read_only=False: the app may need to write temp files, but the workspace
            is a copy — the original is safe
        """
        name = self.container_name(project_id)

        # Remove any stale container with the same name before starting
        self._remove_container_by_name(name)

        self.ensure_network()

        logger.info("Starting container %s from image %s", name, image_tag)
        try:
            container = self._client.containers.run(
                image=image_tag,
                name=name,
                detach=True,
                environment={},         # SECURITY: no host env vars
                network=settings.docker_network_name,
                mem_limit=settings.docker_mem_limit,
                nano_cpus=settings.docker_nano_cpus,
                labels={"managed-by": "clairsec", "project-id": project_id},
                # Port binding: bind container port to a random host port
                ports={f"{settings.docker_target_port}/tcp": None},
            )
            logger.info("Container %s started (id=%s)", name, container.id[:12])
            return container.id, name

        except docker.errors.ImageNotFound as exc:
            raise IsolationError(
                f"Image {image_tag} not found when starting container: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise IsolationError(
                f"Failed to start container for project {project_id}: {exc}"
            ) from exc

    def get_host_port(self, container_id: str) -> int | None:
        """Return the host port mapped to the target container's internal port."""
        try:
            container = self._client.containers.get(container_id)
            container.reload()
            ports = container.ports
            key = f"{settings.docker_target_port}/tcp"
            mappings = ports.get(key)
            if mappings:
                return int(mappings[0]["HostPort"])
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not get host port for container %s: %s", container_id[:12], exc)
            return None

    def stop_container(self, container_id: str) -> None:
        """Stop and remove a running container. Safe if already stopped."""
        try:
            container = self._client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove(force=True)
            logger.info("Stopped and removed container %s", container_id[:12])
        except docker.errors.NotFound:
            logger.debug("Container %s not found during stop — already removed", container_id[:12])
        except Exception as exc:  # noqa: BLE001
            logger.error("Error stopping container %s: %s", container_id[:12], exc)

    def _remove_container_by_name(self, name: str) -> None:
        """Remove an existing container by name if it exists (cleanup stale state)."""
        try:
            container = self._client.containers.get(name)
            container.remove(force=True)
            logger.debug("Removed stale container '%s'", name)
        except docker.errors.NotFound:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Health check
    # ─────────────────────────────────────────────────────────────────────────

    def wait_for_healthy(
        self,
        container_id: str,
        startup_timeout: int | None = None,
    ) -> bool:
        """
        Poll the container's health endpoint until it responds or times out.

        Tries GET /health first, then GET / as fallback.
        Returns True if the container is healthy within the timeout.
        """
        timeout = startup_timeout or settings.docker_startup_timeout
        host_port = self.get_host_port(container_id)

        if host_port is None:
            logger.warning("No host port found for container %s — cannot health-check", container_id[:12])
            return False

        base_url = f"http://127.0.0.1:{host_port}"
        deadline = time.monotonic() + timeout

        logger.info(
            "Waiting for container %s to become healthy at %s (timeout=%ds)",
            container_id[:12],
            base_url,
            timeout,
        )

        with httpx.Client(timeout=2.0) as client:
            while time.monotonic() < deadline:
                for path in ("/health", "/"):
                    try:
                        response = client.get(f"{base_url}{path}")
                        if response.status_code < 400:
                            logger.info(
                                "Container %s healthy (HTTP %d at %s%s)",
                                container_id[:12],
                                response.status_code,
                                base_url,
                                path,
                            )
                            return True
                    except httpx.HTTPError:
                        # ConnectError, TimeoutException, RemoteProtocolError, etc.
                        # All are expected while the container is starting up.
                        pass

                time.sleep(1)

        logger.warning(
            "Container %s did not become healthy within %d seconds",
            container_id[:12],
            timeout,
        )
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Logs
    # ─────────────────────────────────────────────────────────────────────────

    def get_logs(self, container_id: str) -> str:
        """
        Return size-limited container stdout/stderr as a string.

        Treated as untrusted text — returned as-is for display, never executed.
        """
        try:
            container = self._client.containers.get(container_id)
            raw: bytes = container.logs(
                stdout=True,
                stderr=True,
                tail=500,  # last 500 lines as a first guard
            )
            # Apply hard byte cap to prevent unbounded log data reaching callers
            if len(raw) > settings.docker_log_max_bytes:
                raw = raw[-settings.docker_log_max_bytes :]
                prefix = b"[logs truncated to last 100 KB]\n"
                raw = prefix + raw
            return raw.decode("utf-8", errors="replace")

        except docker.errors.NotFound:
            return f"Container {container_id[:12]} not found."
        except Exception as exc:  # noqa: BLE001
            logger.error("Error retrieving logs for container %s: %s", container_id[:12], exc)
            return f"Error retrieving logs: {exc}"

    # ─────────────────────────────────────────────────────────────────────────
    # Image cleanup
    # ─────────────────────────────────────────────────────────────────────────

    def remove_image(self, image_tag: str) -> None:
        """Remove a Docker image. Safe if already removed."""
        try:
            self._client.images.remove(image_tag, force=True)
            logger.info("Removed Docker image %s", image_tag)
        except docker.errors.ImageNotFound:
            logger.debug("Image %s not found during removal — already gone", image_tag)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error removing image %s: %s", image_tag, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Cleanup all
    # ─────────────────────────────────────────────────────────────────────────

    def cleanup_all(self, project_id: str, container_id: str | None = None) -> None:
        """
        Best-effort cleanup: stop container, remove image.
        Safe to call even if container or image don't exist.
        Workspace cleanup is handled separately by WorkspaceManager.
        """
        if container_id:
            self.stop_container(container_id)
        self.remove_image(self.image_tag(project_id))
        logger.info("Docker cleanup complete for project %s", project_id[:8])
