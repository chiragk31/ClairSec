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
from typing import Any

import docker
import docker.errors
import httpx
from requests.exceptions import ConnectionError as ReqConnectionError
from requests.exceptions import ReadTimeout

from app.core.config import settings
from app.isolation.errors import IsolationError

logger = logging.getLogger(__name__)

# How many trailing lines of a failed build to surface. The failure is always
# at the end, so this is a tail, never a head.
_BUILD_LOG_TAIL_LINES = 60

# Packages that only exist on Windows. A requirements.txt produced by
# `pip freeze` on Windows commonly contains these, and they can never install
# inside a Linux container — the single most frequent import failure for
# real-world projects.
_WINDOWS_ONLY_PACKAGES = (
    "pywin32",
    "pypiwin32",
    "pywinpty",
    "wincertstore",
    "win32-setctime",
    "windows-curses",
    "winshell",
)


def _diagnose_build_failure(log_lines: list[str]) -> str | None:
    """
    Produce a short, human-readable explanation of why a build failed.

    Matches on well-known pip/Docker failure signatures. Returns None when the
    cause is not recognised — an honest "no idea" is better than a confident
    wrong guess, and the raw log is shown either way.
    """
    blob = "\n".join(log_lines).lower()

    for pkg in _WINDOWS_ONLY_PACKAGES:
        if pkg in blob:
            return (
                f"the dependency list contains '{pkg}', which is a Windows-only "
                "package and cannot be installed inside a Linux container. This "
                "usually means requirements.txt was produced by 'pip freeze' on "
                "Windows. Remove the Windows-only entries and retry."
            )

    if "no matching distribution found" in blob or "could not find a version" in blob:
        return (
            "pip could not find a distribution matching one of the requested "
            "package versions. The package may not exist, may not support "
            "Python 3.11, or may not publish a Linux build."
        )

    if any(
        marker in blob
        for marker in (
            "gcc: command not found",
            "error: command 'gcc' failed",
            "unable to execute 'gcc'",
            "requires a c compiler",
            "python.h: no such file or directory",
        )
    ):
        return (
            "a dependency needs to be compiled from source, but the slim base "
            "image ships no C toolchain. Prefer a package version that publishes "
            "a prebuilt Linux wheel."
        )

    if "resolutionimpossible" in blob or "conflicting dependencies" in blob:
        return (
            "the dependency versions conflict with each other and pip could not "
            "resolve a compatible set."
        )

    if "killed" in blob and "pip" in blob:
        return (
            "the install process was killed, most likely by hitting the "
            "container memory limit while resolving a large dependency set."
        )

    if "failed to resolve reference" in blob or "manifest unknown" in blob:
        return (
            "the pinned base image digest could not be pulled. Re-resolve it "
            "with: docker pull python:3.11-slim && docker inspect "
            "--format='{{index .RepoDigests 0}}' python:3.11-slim"
        )

    return None

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
ENV PYTHONPATH=/app

WORKDIR /app

# Copy the project, then install from its manifest (as root). The whole tree is
# copied first so manifests that include others (`-r base.txt`) resolve.
COPY . .
RUN pip install --no-cache-dir -r {dep_file} && \
    (python -c "import uvicorn" 2>/dev/null || pip install --no-cache-dir "uvicorn[standard]")
{user_directive}
EXPOSE {port}

{cmd_directive}
"""

_DOCKERFILE_PYPROJECT_TEMPLATE = """\
FROM {base_image}

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir . && \
    (python -c "import uvicorn" 2>/dev/null || pip install --no-cache-dir "uvicorn[standard]")
{user_directive}
EXPOSE {port}

{cmd_directive}
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
                    "Cannot connect to the Docker daemon. Start Docker Desktop, wait "
                    "until the whale icon says 'Engine running', then retry. "
                    f"Details: {exc}"
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
    def patched_image_tag(project_id: str, patch_id: str) -> str:
        return f"{_IMAGE_PREFIX}-{project_id[:8]}-patched:{patch_id[:8]}"

    @staticmethod
    def container_name(project_id: str) -> str:
        """Deterministic name for target container."""
        return f"{_CONTAINER_PREFIX}-{project_id[:8]}"

    @staticmethod
    def patched_container_name(project_id: str, patch_id: str) -> str:
        """Deterministic name for patched target container."""
        return f"{_CONTAINER_PREFIX}-{project_id[:8]}-p-{patch_id[:8]}"

    @staticmethod
    def proxy_name(project_id: str) -> str:
        """Deterministic name for scanner proxy container."""
        return f"{_PROXY_PREFIX}-{project_id[:8]}"

    @staticmethod
    def patched_proxy_name(project_id: str, patch_id: str) -> str:
        """Deterministic name for scanner proxy container dedicated to patched target."""
        return f"{_PROXY_PREFIX}-{project_id[:8]}-p-{patch_id[:8]}"

    @staticmethod
    def patched_network_name(project_id: str, patch_id: str) -> str:
        """Deterministic name for internal network dedicated to patched target."""
        return f"cs-net-{project_id[:8]}-p-{patch_id[:8]}"

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
        Enforces non-root user, root pip install, POSIX path normalization,
        and --app-dir for nested entry points (C3.2, C9).
        """
        entry_posix = entry_point.replace("\\", "/").strip("/")
        dep_posix = dependency_file.replace("\\", "/").strip("/") if dependency_file else None
        port = str(settings.docker_target_port)
        base_image = settings.docker_base_image

        if "/" in entry_posix:
            app_dir, bare_filename = entry_posix.rsplit("/", 1)
            bare_module = bare_filename.removesuffix(".py")
            cmd_directive = f'CMD ["uvicorn", "{bare_module}:app", "--app-dir", "{app_dir}", "--host", "0.0.0.0", "--port", "{port}"]'
        else:
            bare_module = entry_posix.removesuffix(".py")
            cmd_directive = f'CMD ["uvicorn", "{bare_module}:app", "--host", "0.0.0.0", "--port", "{port}"]'

        user_directive = ""
        if settings.docker_non_root:
            user_directive = (
                "\n# Drop to non-root user (THREAT_MODEL C3.2)\n"
                "RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app\n"
                f"RUN mkdir -p {settings.docker_sqlite_data_dir} && "
                f"chown -R appuser:appuser {settings.docker_sqlite_data_dir} && "
                f"chmod 777 {settings.docker_sqlite_data_dir}\n"
                "USER appuser\n"
            )
        else:
            user_directive = (
                f"\nRUN mkdir -p {settings.docker_sqlite_data_dir} && "
                f"chmod 777 {settings.docker_sqlite_data_dir}\n"
            )

        # No usable manifest in the sandbox copy: infer one from the project's imports.
        if not dep_posix or not (workspace_path / dep_posix).is_file():
            dep_posix = write_inferred_requirements(workspace_path)

        if dep_posix and dep_posix.endswith(".txt"):
            content = _DOCKERFILE_TEMPLATE.format(
                base_image=base_image,
                dep_file=dep_posix,
                port=port,
                cmd_directive=cmd_directive,
                user_directive=user_directive,
            )
        else:
            content = _DOCKERFILE_PYPROJECT_TEMPLATE.format(
                base_image=base_image,
                port=port,
                cmd_directive=cmd_directive,
                user_directive=user_directive,
            )

        dockerfile_path = workspace_path / "Dockerfile"
        dockerfile_path.write_text(content, encoding="utf-8")
        logger.debug("Wrote generated Dockerfile to %s", dockerfile_path)

    # ─────────────────────────────────────────────────────────────────────────
    # Preflight / base image
    # ─────────────────────────────────────────────────────────────────────────

    def preflight(self) -> dict[str, Any]:
        """
        Report whether Docker is ready to build and run targets.

        Never raises: every failure is returned as data so the UI can show the
        user exactly what to fix instead of a stack trace.
        """
        report: dict[str, Any] = {
            "daemon_reachable": False,
            "server_version": None,
            "base_image": settings.docker_base_image,
            "base_image_present": False,
            "ready": False,
            "hint": None,
        }
        try:
            self._client.ping()
            report["daemon_reachable"] = True
            report["server_version"] = self._client.version().get("Version")
        except Exception as exc:  # noqa: BLE001
            report["hint"] = f"Docker daemon is not responding: {exc}"
            return report
        try:
            self._client.images.get(settings.docker_base_image)
            report["base_image_present"] = True
        except docker.errors.ImageNotFound:
            report["hint"] = (
                "Base image is not cached locally; it will be pulled on the "
                "first build (needs internet)."
            )
        except Exception as exc:  # noqa: BLE001
            report["hint"] = f"Could not inspect base image: {exc}"
        report["ready"] = report["daemon_reachable"]
        return report

    def ensure_base_image(self) -> None:
        """
        Pull the pinned base image if it is not cached, before the build starts.

        Without this the pull happens implicitly inside the build and is charged
        against the build timeout, so a slow first-time download looks like a
        hung or failed build.
        """
        image = settings.docker_base_image
        try:
            self._client.images.get(image)
            return
        except docker.errors.ImageNotFound:
            pass
        logger.info(
            "Base image %s not cached; pulling it now",
            image,
            extra={"event": "docker.base_image.pulling"},
        )
        try:
            self._client.images.pull(image)
        except Exception as exc:  # noqa: BLE001
            raise IsolationError(
                f"Could not pull base image {image}: {exc}\n"
                "\nCheck your internet connection and that Docker Desktop is "
                "signed in/online. If the pinned digest no longer exists, "
                "re-resolve it: docker pull python:3.11-slim && docker inspect "
                "--format='{{index .RepoDigests 0}}' python:3.11-slim, then set "
                "DOCKER_BASE_IMAGE in backend/.env."
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Image build
    # ─────────────────────────────────────────────────────────────────────────

    def build_image(
        self,
        project_id: str,
        workspace_path: Path,
        entry_point: str,
        dependency_file: str | None = None,
        tag: str | None = None,
    ) -> str:
        """
        Write a Dockerfile into the workspace and build a Docker image.
        Build runs on the default network mode (internet enabled for pip install).
        """
        tag = tag or self.image_tag(project_id)
        self.ensure_base_image()
        self._write_dockerfile(workspace_path, entry_point, dependency_file)
        dockerfile_path = workspace_path / "Dockerfile"

        t0 = time.perf_counter()
        logger.info(
            "Building Docker image %s from %s (dockerfile=%s, entrypoint=%s, timeout=%ds)",
            tag,
            workspace_path,
            dockerfile_path,
            entry_point,
            settings.docker_build_timeout,
            extra={"event": "docker.build.started"},
        )
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
            elapsed = time.perf_counter() - t0
            logger.info(
                "Successfully built image %s in %.3fs",
                tag,
                elapsed,
                extra={"event": "docker.build.succeeded"},
            )
            return tag

        except docker.errors.BuildError as exc:
            elapsed = time.perf_counter() - t0
            # Collect the whole stream, then keep the TAIL. The build failure is
            # always at the end; keeping the head (as this previously did) threw
            # away the only lines that explain why the build failed.
            all_lines = [
                str(entry["stream"]).rstrip()
                for entry in exc.build_log
                if isinstance(entry, dict) and "stream" in entry
            ]
            all_lines = [line for line in all_lines if line.strip()]

            tail = all_lines[-_BUILD_LOG_TAIL_LINES:]
            omitted = len(all_lines) - len(tail)
            build_output = "\n".join(tail)
            if omitted > 0:
                build_output = (
                    f"... ({omitted} earlier lines omitted)\n{build_output}"
                )

            diagnosis = _diagnose_build_failure(all_lines)
            logger.error(
                "Docker build failed for project %s (tag=%s, dockerfile=%s) after %.3fs: %s\n"
                "Likely cause: %s\nBuild output (tail):\n%s",
                project_id[:8],
                tag,
                dockerfile_path,
                elapsed,
                exc.msg,
                diagnosis or "None",
                build_output,
                extra={"event": "docker.build.failed"},
            )
            message = f"Docker build failed for project {project_id}: {exc.msg}\n"
            if diagnosis:
                message += f"\nLikely cause: {diagnosis}\n"
            message += (
                f"\nBuild output (last {len(tail)} lines):\n{build_output}"
            )
            raise IsolationError(message) from exc

        except (ReadTimeout, ReqConnectionError) as exc:
            elapsed = time.perf_counter() - t0
            logger.error(
                "Docker build timed out after %.3fs for project %s (tag=%s, dockerfile=%s, limit=%ds)",
                elapsed,
                project_id[:8],
                tag,
                dockerfile_path,
                settings.docker_build_timeout,
                extra={"event": "docker.build.timed_out"},
            )
            # The Docker SDK's `timeout` is an HTTP read timeout on the daemon
            # socket, so a slow build surfaces here as a transport error rather
            # than a BuildError. Without this branch it fell through to the
            # generic handler and reported a raw socket error, which gives no
            # indication that the real problem was simply "not enough time".
            raise IsolationError(
                f"Docker build timed out for project {project_id} after "
                f"{settings.docker_build_timeout}s.\n"
                "\nLikely cause: the project has a large dependency list and pip "
                "needs longer than the configured build timeout. This is a "
                "configuration limit, not a fault in the project.\n"
                "\nIncrease DOCKER_BUILD_TIMEOUT (seconds) in backend/.env and "
                "isolate again. Dependency-heavy projects can need several "
                "minutes on a first build; subsequent builds reuse Docker's "
                "layer cache and are much faster."
            ) from exc

        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Unexpected error building image %s for project %s after %.3fs: %s",
                tag,
                project_id[:8],
                elapsed,
                exc,
                extra={"event": "docker.build.failed"},
            )
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
        environment: dict[str, str] | None = None,
        container_name: str | None = None,
        network_name: str | None = None,
    ) -> tuple[str, str]:
        """
        Start the hardened, isolated target container on a per-scan internal network.

        Hardening enforced (THREAT_MODEL C3.1-C3.5):
          - cap_drop=["ALL"]
          - security_opt=["no-new-privileges"]
          - read_only rootfs + tmpfs on /tmp and /tmp/clairsec-data
          - pids_limit=256
          - memory and CPU limits
          - NO published ports (reachable only via proxy container on the internal net)
          - NO Docker socket or host volumes mounted
          - environment: target configuration only (no host secrets)
        """
        name = container_name or self.container_name(project_id)
        self._remove_container_by_name(name)

        if network_name:
            net = self.ensure_internal_network(network_name, project_id)
        else:
            net = self.ensure_target_network(project_id)

        tmpfs_config = {"/tmp": "rw,noexec,nosuid,size=64m"} if settings.docker_read_only else None

        container_env = dict(environment) if environment else {}
        env_keys = sorted(list(container_env.keys()))

        t0 = time.perf_counter()
        logger.info(
            "Starting hardened target container %s on network %s (image=%s, limits=[mem=%s, pids=%d, cpus=%d], "
            "read_only=%s, non_root=%s, env_keys=%s)",
            name,
            net.name,
            image_tag,
            settings.docker_mem_limit,
            settings.docker_pids_limit,
            settings.docker_nano_cpus,
            settings.docker_read_only,
            settings.docker_non_root,
            env_keys,
            extra={"event": "docker.container.starting"},
        )
        try:
            run_kwargs: dict[str, Any] = {
                "image": image_tag,
                "name": name,
                "detach": True,
                "environment": container_env,
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
            elapsed = time.perf_counter() - t0
            logger.info(
                "Target container %s started in %.3fs (id=%s)",
                name,
                elapsed,
                container.id[:12],
                extra={"event": "docker.container.started"},
            )
            return container.id, name

        except docker.errors.ImageNotFound as exc:
            elapsed = time.perf_counter() - t0
            logger.error(
                "Image %s not found when starting container %s after %.3fs: %s",
                image_tag,
                name,
                elapsed,
                exc,
                extra={"event": "docker.container.failed"},
            )
            raise IsolationError(
                f"Image {image_tag} not found when starting container: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Failed to start container %s after %.3fs: %s",
                name,
                elapsed,
                exc,
                extra={"event": "docker.container.failed"},
            )
            raise IsolationError(
                f"Failed to start container for project {project_id}: {exc}"
            ) from exc

    def ensure_internal_network(self, net_name: str, project_id: str) -> docker.models.networks.Network:
        """Create or retrieve an internal bridge network (internal=True, C3.3)."""
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

    # ─────────────────────────────────────────────────────────────────────────
    # Scanner-side HTTP proxy service (C3.3)
    # ─────────────────────────────────────────────────────────────────────────

    def start_proxy(
        self,
        project_id: str,
        target_container_name: str,
        proxy_name: str | None = None,
        target_net_name: str | None = None,
    ) -> tuple[str, int]:
        """
        Start a scanner-side HTTP proxy container dedicated to this target container.

        The proxy connects to:
          1. cs-scanner-net: publishes its port to 127.0.0.1 on the host.
          2. target's internal=True network (e.g. cs-net-{project_id[:8]}).

        Returns (proxy_container_id, host_port).
        """
        p_name = proxy_name or self.proxy_name(project_id)
        self._remove_container_by_name(p_name)

        scanner_net = self.ensure_scanner_network()
        t_net_name = target_net_name or self.target_network_name(project_id)

        target_base = f"http://{target_container_name}:{settings.docker_target_port}"
        t0 = time.perf_counter()
        logger.info(
            "Starting scanner proxy %s forwarding to %s",
            p_name,
            target_base,
            extra={"event": "docker.proxy.starting"},
        )

        try:
            proxy_container = self._client.containers.run(
                image=settings.docker_base_image,
                name=p_name,
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
            target_net = self._client.networks.get(t_net_name)
            target_net.connect(proxy_container)

            # Retrieve host port assigned to 8080
            proxy_container.reload()
            ports = proxy_container.ports
            key = "8080/tcp"
            mappings = ports.get(key)
            if not mappings:
                raise IsolationError(
                    f"Proxy container {p_name} started but no host port was mapped."
                )
            host_port = int(mappings[0]["HostPort"])
            elapsed = time.perf_counter() - t0
            logger.info(
                "Proxy container %s running at 127.0.0.1:%d -> %s in %.3fs (id=%s)",
                p_name,
                host_port,
                target_base,
                elapsed,
                proxy_container.id[:12],
                extra={"event": "docker.proxy.started"},
            )
            return proxy_container.id, host_port

        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Failed to start scanner proxy %s after %.3fs: %s",
                p_name,
                elapsed,
                exc,
                extra={"event": "docker.proxy.failed"},
            )
            raise IsolationError(
                f"Failed to start scanner proxy for project {project_id}: {exc}"
            ) from exc

    def start_patched_target(
        self,
        project_id: str,
        patch_id: str,
        image_tag: str,
        environment: dict[str, str] | None = None,
    ) -> tuple[str, str, int]:
        """
        Start a hardened patched target container and its dedicated proxy on an isolated internal network.
        Returns (target_container_id, proxy_container_id, proxy_port).
        """
        net_name = self.patched_network_name(project_id, patch_id)
        self.ensure_internal_network(net_name, project_id)

        target_name = self.patched_container_name(project_id, patch_id)
        target_id, _ = self.start_container(
            project_id=project_id,
            image_tag=image_tag,
            container_name=target_name,
            network_name=net_name,
            environment=environment,
        )

        proxy_name = self.patched_proxy_name(project_id, patch_id)
        proxy_id, proxy_port = self.start_proxy(
            project_id=project_id,
            target_container_name=target_name,
            proxy_name=proxy_name,
            target_net_name=net_name,
        )

        return target_id, proxy_id, proxy_port

    def cleanup_patched_target(self, project_id: str, patch_id: str) -> None:
        """Stop and tear down patched target container, proxy, network, and image."""
        self._remove_container_by_name(self.patched_proxy_name(project_id, patch_id))
        self._remove_container_by_name(self.patched_container_name(project_id, patch_id))
        self._remove_network(self.patched_network_name(project_id, patch_id))
        tag = self.patched_image_tag(project_id, patch_id)
        try:
            self._client.images.remove(tag, force=True)
            logger.debug("Removed patched image '%s'", tag)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not remove patched image '%s': %s", tag, exc)

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
        t0 = time.perf_counter()

        self._last_health_diagnostics = {
            "base_url": base_url,
            "probed_paths": ["/health", "/"],
            "last_status_code": None,
            "last_error": None,
            "attempts": 0,
        }

        logger.info(
            "Waiting for container to become healthy via proxy at %s (timeout=%ds)",
            base_url,
            timeout,
            extra={"event": "docker.health_check.started"},
        )

        with httpx.Client(timeout=2.0) as client:
            while time.monotonic() < deadline:
                for path in ("/health", "/"):
                    try:
                        self._last_health_diagnostics["attempts"] += 1
                        response = client.get(f"{base_url}{path}")
                        self._last_health_diagnostics["last_status_code"] = response.status_code
                        if response.status_code < 400:
                            elapsed = time.perf_counter() - t0
                            logger.info(
                                "Container healthy via proxy at %s%s (HTTP %d after %d attempt(s), took %.2fs)",
                                base_url,
                                path,
                                response.status_code,
                                self._last_health_diagnostics["attempts"],
                                elapsed,
                                extra={"event": "docker.health_check.succeeded"},
                            )
                            return True
                        logger.debug(
                            "Health probe attempt %d to %s%s returned HTTP %d",
                            self._last_health_diagnostics["attempts"],
                            base_url,
                            path,
                            response.status_code,
                            extra={"event": "docker.health_check.probing"},
                        )
                    except httpx.HTTPError as exc:
                        self._last_health_diagnostics["last_error"] = str(exc)
                        logger.debug(
                            "Health probe attempt %d to %s%s failed: %s",
                            self._last_health_diagnostics["attempts"],
                            base_url,
                            path,
                            exc,
                            extra={"event": "docker.health_check.probing"},
                        )

                time.sleep(1)

        elapsed = time.perf_counter() - t0
        logger.warning(
            "Target did not become healthy via proxy within %d seconds (elapsed=%.2fs, attempts=%d, diagnostics: %s)",
            timeout,
            elapsed,
            self._last_health_diagnostics["attempts"],
            self._last_health_diagnostics,
            extra={"event": "docker.health_check.failed"},
        )
        return False

    def get_last_health_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic details from the most recent health-check polling."""
        return getattr(self, "_last_health_diagnostics", {})

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
        logger.info(
            "Starting Docker teardown for project %s (container_id=%s)",
            project_id[:8],
            container_id[:12] if container_id else "None",
            extra={"event": "docker.cleanup.started"},
        )
        try:
            if container_id:
                self.stop_container(container_id)
            self._remove_container_by_name(self.container_name(project_id))
            self.stop_proxy(project_id)
            self._remove_network(self.target_network_name(project_id))
            self.remove_image(self.image_tag(project_id))
            logger.info(
                "Docker cleanup complete for project %s",
                project_id[:8],
                extra={"event": "docker.cleanup.succeeded"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Error during Docker cleanup for project %s: %s",
                project_id[:8],
                exc,
                extra={"event": "docker.cleanup.failed"},
            )


# Import name -> PyPI distribution for packages FastAPI projects commonly use.
_IMPORT_TO_DIST = {
    "fastapi": "fastapi", "uvicorn": "uvicorn[standard]", "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings", "starlette": "starlette", "sqlalchemy": "sqlalchemy",
    "sqlmodel": "sqlmodel", "alembic": "alembic", "jose": "python-jose[cryptography]", "jwt": "PyJWT",
    "passlib": "passlib[bcrypt]", "bcrypt": "bcrypt", "dotenv": "python-dotenv", "multipart": "python-multipart",
    "httpx": "httpx", "requests": "requests", "aiohttp": "aiohttp", "jinja2": "jinja2", "yaml": "PyYAML",
    "motor": "motor", "pymongo": "pymongo", "redis": "redis", "aiosqlite": "aiosqlite", "databases": "databases",
    "asyncpg": "asyncpg", "psycopg2": "psycopg2-binary", "psycopg": "psycopg[binary]", "pymysql": "PyMySQL",
    "slowapi": "slowapi", "email_validator": "email-validator", "orjson": "orjson", "ujson": "ujson",
    "cryptography": "cryptography", "itsdangerous": "itsdangerous", "aiofiles": "aiofiles",
    "beanie": "beanie", "tortoise": "tortoise-orm", "pandas": "pandas", "numpy": "numpy",
    "faker": "faker", "montydb": "montydb", "celery": "celery", "boto3": "boto3", "openai": "openai",
    "dateutil": "python-dateutil", "pytz": "pytz", "loguru": "loguru", "structlog": "structlog",
}
INFERRED_REQUIREMENTS = "requirements.clairsec.txt"


def write_inferred_requirements(workspace_path: Path) -> str:
    """
    Projects without requirements.txt / pyproject.toml / setup.py: read the top-level
    imports of every .py file statically (nothing is executed) and write a manifest into
    the SANDBOX COPY (never the user's original). Unknown imports are skipped; fastapi
    and uvicorn are always included.
    """
    import ast
    import os

    found: set[str] = {"fastapi", "uvicorn[standard]"}
    local = {p.stem for p in workspace_path.rglob("*.py")} | {p.name for p in workspace_path.iterdir() if p.is_dir()}
    for dirpath, dirnames, filenames in os.walk(workspace_path):
        dirnames[:] = [d for d in dirnames if d not in {".git", "venv", ".venv", "node_modules", "__pycache__"}]
        for f in filenames:
            if not f.endswith(".py"):
                continue
            try:
                tree = ast.parse(Path(dirpath, f).read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                for n in names:
                    top = n.split(".")[0]
                    if top in _IMPORT_TO_DIST and top not in local:
                        found.add(_IMPORT_TO_DIST[top])
    (workspace_path / INFERRED_REQUIREMENTS).write_text(
        "# Generated by ClairSec: this project has no dependency manifest.\n"
        + "\n".join(sorted(found)) + "\n",
        encoding="utf-8",
    )
    logger.info("Inferred %d dependency(ies) for %s: %s", len(found), workspace_path, sorted(found),
                extra={"event": "dependency.file.inferred"})
    return INFERRED_REQUIREMENTS
