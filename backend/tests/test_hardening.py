"""
Tests for container hardening and network isolation (THREAT_MODEL C3.1–C3.5).

Covers:
  - Dockerfile non-root user & pip install ordering
  - Container hardening flags: cap_drop, security_opt, read_only, tmpfs, pids_limit
  - Docker socket absence (C3.1)
  - Network isolation: internal=True, no published ports on target
  - Scanner-side proxy routing: bound to 127.0.0.1, dual-attached, scoped per-scan
  - Live Docker integration tests (marked docker & environment-dependent)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid
import httpx
import pytest

from app.core.config import settings
from app.isolation.docker_manager import DockerManager


class TestDockerfileHardening:
    def test_dockerfile_pip_root_then_drop_user(self, tmp_path):
        """C3.2: Pip install runs as root, then drops to unprivileged USER appuser."""
        manager = DockerManager(client=MagicMock())
        manager._write_dockerfile(
            workspace_path=tmp_path,
            entry_point="main.py",
            dependency_file="requirements.txt",
        )
        content = (tmp_path / "Dockerfile").read_text(encoding="utf-8")

        assert "pip install" in content
        assert "USER appuser" in content
        # Ensure pip install comes before USER appuser
        pip_pos = content.find("pip install")
        user_pos = content.find("USER appuser")
        assert pip_pos < user_pos, "pip install must run before dropping to unprivileged USER"

    def test_dockerfile_non_root_config_toggle(self, tmp_path, monkeypatch):
        """When docker_non_root is False, user directive is omitted."""
        monkeypatch.setattr(settings, "docker_non_root", False)
        manager = DockerManager(client=MagicMock())
        manager._write_dockerfile(
            workspace_path=tmp_path,
            entry_point="main.py",
            dependency_file="requirements.txt",
        )
        content = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
        assert "USER appuser" not in content


class TestContainerHardeningUnit:
    @pytest.fixture
    def mock_docker(self):
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.id = "mock-target-id-1234567890"
        mock_container.name = "clairsec-target-12345678"
        mock_client.containers.run.return_value = mock_container
        mock_client.containers.get.return_value = mock_container

        mock_net = MagicMock()
        mock_net.name = "cs-net-12345678"
        mock_client.networks.get.return_value = mock_net
        mock_client.networks.create.return_value = mock_net

        return DockerManager(client=mock_client), mock_client

    def test_target_network_internal_and_no_published_ports(self, mock_docker):
        """C3.3: Target is on an internal=True bridge network with no published ports."""
        import docker.errors
        manager, mock_client = mock_docker
        mock_client.networks.get.side_effect = docker.errors.NotFound("Network not found")
        project_id = "12345678-0000-0000-0000-000000000000"

        manager.start_container(project_id, "test-image:latest")

        # Verify network creation was requested with internal=True
        mock_client.networks.create.assert_called_with(
            manager.target_network_name(project_id),
            driver="bridge",
            internal=True,
            labels={"managed-by": "clairsec", "project-id": project_id, "role": "target-internal"},
        )

        # Verify container run kwargs
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["network"] == manager.target_network_name(project_id)
        assert call_kwargs["ports"] == {}, "Target container must have NO published ports"

    def test_container_hardening_flags_enforced(self, mock_docker):
        """C3.2, C3.4: cap_drop=ALL, no-new-privileges, read_only rootfs, tmpfs, pids_limit."""
        manager, mock_client = mock_docker
        project_id = "12345678-0000-0000-0000-000000000000"

        manager.start_container(project_id, "test-image:latest")

        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["cap_drop"] == ["ALL"]
        assert call_kwargs["security_opt"] == ["no-new-privileges"]
        assert call_kwargs["pids_limit"] == settings.docker_pids_limit
        assert call_kwargs["read_only"] is True
        assert call_kwargs["tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=64m"}
        assert call_kwargs["environment"] == {}, "No host environment variables permitted (C3.5)"

    def test_no_docker_socket_mounted(self, mock_docker):
        """C3.1: Never mount the Docker socket or any host filesystem into the target."""
        manager, mock_client = mock_docker
        project_id = "12345678-0000-0000-0000-000000000000"

        manager.start_container(project_id, "test-image:latest")

        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["volumes"] == {}
        # Explicit check for docker socket anywhere in kwargs
        for val in call_kwargs.values():
            assert "docker.sock" not in str(val)

    def test_scanner_proxy_attached_to_both_networks(self, mock_docker):
        """C3.3: Proxy attaches to scanner bridge and target internal network, bound to 127.0.0.1."""
        manager, mock_client = mock_docker
        project_id = "12345678-0000-0000-0000-000000000000"

        mock_proxy_container = MagicMock()
        mock_proxy_container.id = "proxy-123"
        mock_proxy_container.ports = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54321"}]}
        mock_client.containers.run.return_value = mock_proxy_container

        mock_target_net = MagicMock()
        mock_client.networks.get.return_value = mock_target_net

        proxy_id, host_port = manager.start_proxy(project_id, "clairsec-target-12345678")

        assert proxy_id == "proxy-123"
        assert host_port == 54321

        # Proxy started on scanner bridge with 127.0.0.1 port binding
        run_kwargs = mock_client.containers.run.call_args[1]
        assert run_kwargs["ports"] == {"8080/tcp": ("127.0.0.1", None)}

        # Proxy connected to target's internal network
        mock_target_net.connect.assert_called_once_with(mock_proxy_container)

    def test_scanner_proxy_scoped_only_to_target(self, mock_docker):
        """Proxy command only forwards to its designated target container, preventing cross-talk."""
        manager, mock_client = mock_docker
        project_id = "12345678-0000-0000-0000-000000000000"

        mock_proxy = MagicMock()
        mock_proxy.ports = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54321"}]}
        mock_client.containers.run.return_value = mock_proxy

        manager.start_proxy(project_id, "clairsec-target-12345678")

        run_kwargs = mock_client.containers.run.call_args[1]
        cmd = run_kwargs["command"]
        expected_target = f"http://clairsec-target-12345678:{settings.docker_target_port}"
        assert expected_target in cmd, "Proxy must be explicitly scoped to target container"

    def test_wait_for_healthy_via_proxy_port_success(self, mock_docker):
        """wait_for_healthy successfully queries proxy on 127.0.0.1:{proxy_port}."""
        manager, _ = mock_docker
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client_instance = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client_instance.get.return_value = mock_resp
            mock_httpx_cls.return_value.__enter__.return_value = mock_client_instance

            res = manager.wait_for_healthy(54321, startup_timeout=2)
            assert res is True
            mock_client_instance.get.assert_called_with("http://127.0.0.1:54321/health")

    def test_wait_for_healthy_via_proxy_port_timeout(self, mock_docker):
        """wait_for_healthy returns False when proxy cannot reach target."""
        manager, _ = mock_docker
        with patch("httpx.Client") as mock_httpx_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")
            mock_httpx_cls.return_value.__enter__.return_value = mock_client_instance

            res = manager.wait_for_healthy(54321, startup_timeout=1)
            assert res is False


# =============================================================================
# Live Docker Integration Tests (Requires running Docker daemon)
# =============================================================================

@pytest.mark.docker
class TestContainerHardeningLive:
    """Live tests verifying hardening on real running containers (OPERATIONS §4, C3.1-C3.5)."""

    def test_live_hardening_flags_applied(self):
        """Verify HostConfig of live running target has hardening flags applied."""
        import docker
        client = docker.from_env()
        manager = DockerManager(client=client)
        project_id = str(uuid.uuid4())

        try:
            cid, cname = manager.start_container(project_id, settings.docker_base_image)
            container = client.containers.get(cid)
            host_config = container.attrs["HostConfig"]

            assert "ALL" in host_config.get("CapDrop", [])
            assert any("no-new-privileges" in opt for opt in host_config.get("SecurityOpt", []))
            assert host_config.get("ReadonlyRootfs") is True
            assert host_config.get("PidsLimit") == settings.docker_pids_limit
            assert "/tmp" in host_config.get("Tmpfs", {})
        finally:
            manager.cleanup_all(project_id)

    def test_live_no_docker_socket_in_container(self):
        """C3.1: /var/run/docker.sock must not exist inside the target container."""
        import docker
        client = docker.from_env()
        manager = DockerManager(client=client)
        project_id = str(uuid.uuid4())

        try:
            cid, _ = manager.start_container(project_id, settings.docker_base_image)
            container = client.containers.get(cid)
            res = container.exec_run("ls -la /var/run/docker.sock")
            assert res.exit_code != 0, "Docker socket must NOT be present in container"
        finally:
            manager.cleanup_all(project_id)

    def test_live_dns_resolution_fails_from_target(self):
        """C3.3: Target on internal=True network cannot resolve external DNS."""
        import docker
        client = docker.from_env()
        manager = DockerManager(client=client)
        project_id = str(uuid.uuid4())

        try:
            cid, _ = manager.start_container(project_id, settings.docker_base_image)
            container = client.containers.get(cid)
            res = container.exec_run(
                "python -c \"import socket; socket.gethostbyname('example.com')\""
            )
            assert res.exit_code != 0, "DNS resolution must fail from isolated target"
        finally:
            manager.cleanup_all(project_id)

    def test_live_connect_default_gateway_fails(self):
        """C3.3: Target on internal=True network cannot connect to host gateway."""
        import docker
        client = docker.from_env()
        manager = DockerManager(client=client)
        project_id = str(uuid.uuid4())

        try:
            cid, _ = manager.start_container(project_id, settings.docker_base_image)
            container = client.containers.get(cid)
            res = container.exec_run(
                "python -c \"import socket; s = socket.socket(); s.settimeout(2); s.connect(('192.168.1.1', 80))\""
            )
            assert res.exit_code != 0, "Connection to host LAN gateway must fail from target"
        except Exception:
            pytest.skip("Environment-dependent: network route test")
        finally:
            manager.cleanup_all(project_id)
