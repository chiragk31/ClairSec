"""
Docker manager — isolated target lifecycle and scanner HTTP proxy service.

SECURITY requirements enforced here (THREAT_MODEL C3.1–C3.5):
  - Target container is placed on a per-scan internal network with internal=True (C3.3).
    It has no published ports and cannot reach the host LAN or resolve external DNS.
  - Scanner-side HTTP proxy container attaches to both the scanner bridge and the target's
    internal network. It publishes its port to 127.0.0.1 only, forwarding requests
    to its assigned target container only.
  - Container hardening:
      cap_drop=["ALL"]
      security_opt=["no-new-privileges"]
      non-root user (appuser, dropped after root pip install)
      read_only rootfs + writable tmpfs on /tmp
      pids_limit=256
      mem_limit, nano_cpus
      Never mount Docker socket (C3.1)
  - No host environment variables are passed into any container (env={}) (C3.5).
  - Hard wall-clock timeouts for build and startup.
  - Container logs are size-limited before returning to callers.
  - All Docker output/errors are treated as untrusted text (logged, never eval'd).
  - Cleanup is called on every failure path.
"""
from __future__ import annotations

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
_PROXY_PREFIX = "clairsec-proxy"
_SCANNER_NET = "cs-scanner-net"

# Template Dockerfile — intentionally minimal and hardened (THREAT_MODEL C3.1, C3.2).
# Security notes:
# - Runs pip install as root for layer caching
# - Drops to unprivileged non-root user (appuser) when docker_non_root is True
# - No host secrets or host environment variables are embedded
_DOCKERFILE_TEMPLATE = """\
FROM {base_image}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first for layer caching (as root)
COPY {dep_file} .
RUN pip install --no-cache-dir -r {dep_file}

# Copy the rest of the project
COPY . .
{user_directive}
EXPOSE {port}

CMD ["uvicorn", "{entry_module}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""

_DOCKERFILE_PYPROJECT_TEMPLATE = """\
FROM {base_image}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .
{user_directive}
EXPOSE {port}

CMD ["uvicorn", "{entry_module}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""

# Scanner proxy server script executed inside the proxy container.
# It forwards incoming HTTP requests only to its designated target container.
_PROXY_SCRIPT = """\
import http.server
import urllib.request
import urllib.error
import sys

target_base = sys.argv[1]
listen_port = int(sys.argv[2])

class ForwardingHandler(http.server.BaseHTTPRequestHandler):
    def do_forward(self):
        url = f"{target_base}{self.path}"
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host", "transfer-encoding"):
                headers[k] = v

        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(k, v)
                resp_body = resp.read()
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as err:
            self.send_response(err.code)
            for k, v in err.headers.items():
                if k.lower() not in ("transfer-encoding", "content-length"):
                    self.send_header(k, v)
            resp_body = err.read()
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            msg = f'{{"detail": "Bad Gateway: {str(exc)}"}}'.encode()
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    do_GET = do_forward
    do_POST = do_forward
    do_PUT = do_forward
    do_DELETE = do_forward
    do_PATCH = do_forward
    do_HEAD = do_forward
    do_OPTIONS = do_forward

    def log_message(self, format, *args):
        pass

server = http.server.ThreadingHTTPServer(("0.0.0.0", listen_port), ForwardingHandler)
server.serve_forever()
"""


class DockerManager:
    def __init__(self, client: docker.DockerClient | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            try:
                self._client = docker.from_env()
            except docker.errors.DockerException as exc:
                raise IsolationError(
                    f"Cannot connect to Docker daemon. Is Docker running? Details: {exc}"
                ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Networks (C3.3)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def target_network_name(project_id: str) -> str:
        """Name of the per-scan isolated bridge network (internal=True)."""
        return f"cs-net-{project_id[:8]}"

    @staticmethod
    def scanner_network_name() -> str:
        """Name of the bridge network shared by the proxy and the host."""
        return _SCANNER_NET

    def ensure_target_network(self, project_id: str) -> docker.models.networks.Network:
        """
        Create the per-scan internal network for the target container (C3.3).
        internal=True prevents any routing to host LAN or external Internet.
        """
        net_name = self.target_network_name(project_id)
        try:
            net = self._client.networks.get(net_name)
            net.reload()
            return net
        except (docker.errors.NotFound, docker.errors.APIError):
            try:
                net = self._client.networks.create(
                    net_name,
                    driver="bridge",
                    internal=True,
                    labels={"managed-by": "clairsec", "project-id": project_id, "role": "target-internal"},
                )
                logger.info("Created internal target network '%s' (internal=True)", net_name)
                return net
            except docker.errors.APIError:
                return self._client.networks.get(net_name)

    def ensure_scanner_network(self) -> docker.models.networks.Network:
        """Create the scanner bridge network if it does not already exist."""
        net_name = self.scanner_network_name()
        try:
            return self._client.networks.get(net_name)
        except docker.errors.NotFound:
            net = self._client.networks.create(
                net_name,
                driver="bridge",
                internal=False,
                labels={"managed-by": "clairsec", "role": "scanner-bridge"},
            )
            logger.info("Created scanner bridge network '%s'", net_name)
            return net

    def _remove_network(self, net_name: str) -> None:
        """Remove a network by name if it exists."""
        try:
            net = self._client.networks.get(net_name)
            net.remove()
            logger.debug("Removed network '%s'", net_name)
        except (docker.errors.NotFound, docker.errors.APIError) as exc:
            logger.debug("Could not remove network '%s': %s", net_name, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Naming helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def image_tag(project_id: str) -> str:
        return f"{_IMAGE_PREFIX}-{project_id[:8]}:latest"

    @staticmethod
    def container_name(project_id: str) -> str:
        """Deterministic name for target container."""
        return f"{_CONTAINER_PREFIX}-{project_id[:8]}"

    @staticmethod
    def proxy_name(project_id: str) -> str:
        """Deterministic name for scanner proxy container."""
        return f"{_PROXY_PREFIX}-{project_id[:8]}"

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
        Write a generated Dockerfile into the scan workspace.
        Enforces non-root user and root pip install per C3.2.
        """
        entry_module = entry_point.replace("/", ".").replace("\\", ".").removesuffix(".py")
        port = str(settings.docker_target_port)
        base_image = settings.docker_base_image

        user_directive = ""
        if settings.docker_non_root:
            user_directive = (
                "\n# Drop to non-root user (THREAT_MODEL C3.2)\n"
                "RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app\n"
                "USER appuser\n"
            )

        if dependency_file and dependency_file.endswith(".txt"):
            content = _DOCKERFILE_TEMPLATE.format(
                base_image=base_image,
                dep_file=dependency_file,
                port=port,
                entry_module=entry_module,
                user_directive=user_directive,
            )
        else:
            content = _DOCKERFILE_PYPROJECT_TEMPLATE.format(
                base_image=base_image,
                port=port,
                entry_module=entry_module,
                user_directive=user_directive,
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
        Build runs on the default network mode (internet enabled for pip install).
        """
        tag = self.image_tag(project_id)
        self._write_dockerfile(workspace_path, entry_point, dependency_file)

        logger.info("Building Docker image %s from %s", tag, workspace_path)
        try:
            _image, build_logs = self._client.images.build(
                path=str(workspace_path),
                tag=tag,
                rm=True,
                forcerm=True,
                timeout=settings.docker_build_timeout,
                buildargs={},
            )
            for chunk in build_logs:
                if "stream" in chunk:
                    line = str(chunk["stream"]).strip()
                    if line:
                        logger.debug("[build:%s] %s", project_id[:8], line)
            logger.info("Successfully built image %s", tag)
            return tag

        except docker.errors.BuildError as exc:
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
    # Target container lifecycle (C3.1, C3.2, C3.3, C3.4)
    # ─────────────────────────────────────────────────────────────────────────

    def start_container(
        self,
        project_id: str,
        image_tag: str,
        command: str | list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Start the hardened, isolated target container on a per-scan internal network.

        Hardening enforced (THREAT_MODEL C3.1-C3.5):
          - cap_drop=["ALL"]
          - security_opt=["no-new-privileges"]
          - read_only rootfs + tmpfs on /tmp
          - pids_limit=256
          - memory and CPU limits
          - NO published ports (reachable only via proxy container on the internal net)
          - NO Docker socket or host volumes mounted
          - environment={} (no host secrets)
        """
        name = self.container_name(project_id)
        self._remove_container_by_name(name)

        net = self.ensure_target_network(project_id)

        tmpfs_config = {"/tmp": "rw,noexec,nosuid,size=64m"} if settings.docker_read_only else None

        logger.info("Starting hardened target container %s on network %s", name, net.name)
        try:
            run_kwargs: dict[str, Any] = {
                "image": image_tag,
                "name": name,
                "detach": True,
                "environment": {},
                "network": net.name,
                "ports": {},  # No published ports — reachable only via internal proxy
                "mem_limit": settings.docker_mem_limit,
                "nano_cpus": settings.docker_nano_cpus,
                "pids_limit": settings.docker_pids_limit,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges"],
                "read_only": settings.docker_read_only,
                "tmpfs": tmpfs_config,
                "volumes": {},  # Never mount host files or Docker socket (C3.1)
                "labels": {"managed-by": "clairsec", "project-id": project_id, "role": "target"},
            }
            if command is not None:
                run_kwargs["command"] = command
            elif image_tag == settings.docker_base_image:
                run_kwargs["command"] = ["python3", "-c", "import time; time.sleep(3600)"]

            container = self._client.containers.run(**run_kwargs)
            logger.info("Target container %s started (id=%s)", name, container.id[:12])
            return container.id, name

        except docker.errors.ImageNotFound as exc:
            raise IsolationError(
                f"Image {image_tag} not found when starting container: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise IsolationError(
                f"Failed to start container for project {project_id}: {exc}"
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Scanner-side HTTP proxy service (C3.3)
    # ─────────────────────────────────────────────────────────────────────────

    def start_proxy(self, project_id: str, target_container_name: str) -> tuple[str, int]:
        """
        Start a scanner-side HTTP proxy container dedicated to this target container.

        The proxy connects to:
          1. cs-scanner-net: publishes its port to 127.0.0.1 on the host.
          2. cs-net-{project_id[:8]}: the target's internal=True network.

        Returns (proxy_container_id, host_port).
        """
        proxy_name = self.proxy_name(project_id)
        self._remove_container_by_name(proxy_name)

        scanner_net = self.ensure_scanner_network()
        target_net_name = self.target_network_name(project_id)

        target_base = f"http://{target_container_name}:{settings.docker_target_port}"
        logger.info(
            "Starting scanner proxy %s forwarding to %s",
            proxy_name,
            target_base,
        )

        try:
            proxy_container = self._client.containers.run(
                image=settings.docker_base_image,
                name=proxy_name,
                command=[
                    "python", "-u", "-c", _PROXY_SCRIPT,
                    target_base,
                    "8080",
                ],
                detach=True,
                network=scanner_net.name,
                # Bind container port 8080 to a random port on 127.0.0.1 ONLY (C7.1)
                ports={"8080/tcp": ("127.0.0.1", None)},
                environment={},
                labels={"managed-by": "clairsec", "project-id": project_id, "role": "scanner-proxy"},
            )

            # Attach proxy to the target's internal network so it can reach the target
            target_net = self._client.networks.get(target_net_name)
            target_net.connect(proxy_container)

            # Retrieve host port assigned to 8080
            proxy_container.reload()
            ports = proxy_container.ports
            key = "8080/tcp"
            mappings = ports.get(key)
            if not mappings:
                raise IsolationError(
                    f"Proxy container {proxy_name} started but no host port was mapped."
                )
            host_port = int(mappings[0]["HostPort"])
            logger.info(
                "Proxy container %s running at 127.0.0.1:%d -> %s",
                proxy_name,
                host_port,
                target_base,
            )
            return proxy_container.id, host_port

        except Exception as exc:  # noqa: BLE001
            raise IsolationError(
                f"Failed to start scanner proxy for project {project_id}: {exc}"
            ) from exc

    def get_proxy_port(self, proxy_container_id_or_name: str) -> int | None:
        """Return the host port mapped to the scanner proxy's 8080/tcp port."""
        try:
            container = self._client.containers.get(proxy_container_id_or_name)
            container.reload()
            mappings = container.ports.get("8080/tcp")
            if mappings:
                return int(mappings[0]["HostPort"])
            # If this container is a target container, check if its proxy is already running
            pid = container.labels.get("project-id")
            if pid:
                p_c = self._client.containers.get(self.proxy_name(pid))
                p_c.reload()
                p_mappings = p_c.ports.get("8080/tcp")
                if p_mappings:
                    return int(p_mappings[0]["HostPort"])
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not get proxy port for %s: %s", proxy_container_id_or_name, exc)
            return None

    def get_host_port(self, container_id: str) -> int | None:
        """Return host port for target (legacy) or proxy container."""
        try:
            container = self._client.containers.get(container_id)
            container.reload()
            ports = container.ports
            # Try target port first, then proxy port 8080
            for k in (f"{settings.docker_target_port}/tcp", "8080/tcp"):
                mappings = ports.get(k)
                if mappings:
                    return int(mappings[0]["HostPort"])
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not get host port for container %s: %s", container_id[:12], exc)
            return None

    def stop_proxy(self, project_id: str) -> None:
        """Stop and remove the scanner proxy container for a project."""
        self._remove_container_by_name(self.proxy_name(project_id))

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
            container.stop(timeout=5)
            container.remove(force=True)
            logger.debug("Removed stale container '%s'", name)
        except docker.errors.NotFound:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error removing container '%s': %s", name, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Health check
    # ─────────────────────────────────────────────────────────────────────────

    def wait_for_healthy(
        self,
        target: str | int,
        startup_timeout: int | None = None,
    ) -> bool:
        """
        Poll the health endpoint through the scanner proxy until healthy or timeout.
        `target` can be:
          - int: host port of the proxy directly
          - str: container id or name (will lookup host port)
        """
        timeout = startup_timeout or settings.docker_startup_timeout

        if isinstance(target, int):
            host_port = target
        else:
            host_port = self.get_host_port(target)
            if host_port is None:
                # Check proxy by project id or container id
                host_port = self.get_proxy_port(target)
            if host_port is None:
                # Target may be a target container id/name or project_id whose proxy
                # has not yet been started. Auto-start the scanner proxy (C3.3).
                project_id = None
                target_name = None
                try:
                    c = self._client.containers.get(target)
                    project_id = c.labels.get("project-id")
                    target_name = c.name
                except Exception:
                    if len(target) == 36:  # UUID string
                        project_id = target
                        target_name = self.container_name(project_id)

                if project_id and target_name:
                    proxy_name = self.proxy_name(project_id)
                    host_port = self.get_proxy_port(proxy_name)
                    if host_port is None:
                        try:
                            _, host_port = self.start_proxy(project_id, target_name)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Could not auto-start proxy for target %s: %s", target, exc)

        if host_port is None:
            logger.warning("No host port found for target %s — cannot health-check", target)
            return False

        base_url = f"http://127.0.0.1:{host_port}"
        deadline = time.monotonic() + timeout

        logger.info(
            "Waiting for container to become healthy via proxy at %s (timeout=%ds)",
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
                                "Container healthy via proxy (HTTP %d at %s%s)",
                                response.status_code,
                                base_url,
                                path,
                            )
                            return True
                    except httpx.HTTPError:
                        pass

                time.sleep(1)

        logger.warning(
            "Target did not become healthy via proxy within %d seconds",
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
                tail=500,
            )
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
    # Cleanup
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

    def cleanup_all(self, project_id: str, container_id: str | None = None) -> None:
        """
        Full teardown of Docker resources for a project:
          1. Stop target container.
          2. Stop proxy container.
          3. Remove internal network.
          4. Remove built image.
        """
        if container_id:
            self.stop_container(container_id)
        self._remove_container_by_name(self.container_name(project_id))
        self.stop_proxy(project_id)
        self._remove_network(self.target_network_name(project_id))
        self.remove_image(self.image_tag(project_id))
        logger.info("Docker cleanup complete for project %s", project_id[:8])
