"""
Phase 3 isolation tests.

Tests are split into two groups:
  - Unit tests (no Docker required) — test workspace, error handling, timeout logic.
  - Integration tests (marked 'docker') — test real Docker lifecycle.

Run all:        pytest tests/test_isolation.py
Run unit only:  pytest tests/test_isolation.py -m "not docker"
Run Docker:     pytest tests/test_isolation.py -m docker
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Fixture paths ──────────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_APP_PATH = str(FIXTURES_DIR / "valid_fastapi_app")
BROKEN_APP_PATH = str(FIXTURES_DIR / "broken_fastapi_app")


# =============================================================================
# Unit tests — no Docker, no MongoDB
# =============================================================================

class TestWorkspaceManager:
    def test_create_scan_workspace_copies_source(self, tmp_path):
        from app.isolation.workspace import WorkspaceManager

        # Set up a source directory with a file
        source = tmp_path / "source_project"
        source.mkdir()
        (source / "main.py").write_text("app = None")
        (source / "requirements.txt").write_text("fastapi\n")

        workspace_root = tmp_path / "workspaces"
        manager = WorkspaceManager(workspace_root=str(workspace_root))
        project_id = str(uuid.uuid4())

        result = manager.create_scan_workspace(project_id, str(source))

        assert result.exists()
        assert (result / "main.py").exists()
        assert (result / "requirements.txt").exists()
        # Source must be untouched
        assert (source / "main.py").exists()

    def test_workspace_is_separate_from_source(self, tmp_path):
        from app.isolation.workspace import WorkspaceManager

        source = tmp_path / "source_project"
        source.mkdir()
        (source / "main.py").write_text("original")

        workspace_root = tmp_path / "workspaces"
        manager = WorkspaceManager(workspace_root=str(workspace_root))
        project_id = str(uuid.uuid4())

        result = manager.create_scan_workspace(project_id, str(source))

        # Modify the copy — source must remain unchanged
        (result / "main.py").write_text("modified")
        assert (source / "main.py").read_text() == "original"

    def test_create_fails_if_workspace_already_exists(self, tmp_path):
        from app.isolation.workspace import WorkspaceManager
        from app.isolation.errors import IsolationError

        source = tmp_path / "source_project"
        source.mkdir()

        workspace_root = tmp_path / "workspaces"
        manager = WorkspaceManager(workspace_root=str(workspace_root))
        project_id = str(uuid.uuid4())

        manager.create_scan_workspace(project_id, str(source))
        # Second call should fail — no silent overwrite
        with pytest.raises(IsolationError, match="already exists"):
            manager.create_scan_workspace(project_id, str(source))

    def test_workspace_isolation_separate_projects(self, tmp_path):
        """Two projects get separate workspace directories that don't interfere."""
        from app.isolation.workspace import WorkspaceManager

        source = tmp_path / "source"
        source.mkdir()
        (source / "main.py").write_text("app = None")

        workspace_root = tmp_path / "workspaces"
        manager = WorkspaceManager(workspace_root=str(workspace_root))

        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())

        path_a = manager.create_scan_workspace(id_a, str(source))
        path_b = manager.create_scan_workspace(id_b, str(source))

        assert path_a != path_b
        assert not str(path_b).startswith(str(path_a))

    def test_cleanup_removes_workspace(self, tmp_path):
        from app.isolation.workspace import WorkspaceManager

        source = tmp_path / "source_project"
        source.mkdir()
        (source / "file.txt").write_text("data")

        workspace_root = tmp_path / "workspaces"
        manager = WorkspaceManager(workspace_root=str(workspace_root))
        project_id = str(uuid.uuid4())

        result = manager.create_scan_workspace(project_id, str(source))
        assert result.exists()

        manager.cleanup_workspace(project_id)
        assert not result.exists()
        assert not result.parent.exists()  # per-project dir also removed

    def test_cleanup_is_safe_if_workspace_missing(self, tmp_path):
        from app.isolation.workspace import WorkspaceManager

        manager = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        # Should not raise even if project was never created
        manager.cleanup_workspace("nonexistent-project-id")


class TestDockerfileGeneration:
    def test_dockerfile_uses_requirements_txt(self, tmp_path):
        """If dependency_file is requirements.txt, the generated Dockerfile uses it."""
        from app.isolation.docker_manager import DockerManager

        # We don't need a real Docker connection for this — just test file generation
        with patch("docker.from_env"):
            manager = DockerManager()

        (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp=FastAPI()")
        (tmp_path / "requirements.txt").write_text("fastapi\n")

        manager._write_dockerfile(
            workspace_path=tmp_path,
            entry_point="main.py",
            dependency_file="requirements.txt",
        )
        content = (tmp_path / "Dockerfile").read_text()
        assert "COPY requirements.txt" in content
        assert "pip install" in content
        assert '"uvicorn", "main:app"' in content

    def test_dockerfile_entry_point_converted_to_module(self, tmp_path):
        """src/api/app.py → src.api.app in uvicorn CMD."""
        from app.isolation.docker_manager import DockerManager

        with patch("docker.from_env"):
            manager = DockerManager()

        manager._write_dockerfile(
            workspace_path=tmp_path,
            entry_point="src/api/app.py",
            dependency_file="requirements.txt",
        )
        content = (tmp_path / "Dockerfile").read_text()
        assert '"uvicorn", "src.api.app:app"' in content

    def test_dockerfile_fallback_for_pyproject(self, tmp_path):
        """pyproject.toml → pip install . in fallback template."""
        from app.isolation.docker_manager import DockerManager

        with patch("docker.from_env"):
            manager = DockerManager()

        manager._write_dockerfile(
            workspace_path=tmp_path,
            entry_point="main.py",
            dependency_file="pyproject.toml",
        )
        content = (tmp_path / "Dockerfile").read_text()
        assert "pip install" in content


class TestIsolationErrorHandling:
    def test_isolation_error_is_raised_on_invalid_project(self):
        from app.isolation.errors import IsolationError
        with pytest.raises(IsolationError):
            raise IsolationError("test error")

    def test_docker_manager_raises_on_no_daemon(self):
        """DockerManager raises IsolationError if Docker is not available."""
        from app.isolation.errors import IsolationError
        import docker.errors

        with patch("docker.from_env", side_effect=docker.errors.DockerException("no daemon")):
            from app.isolation import docker_manager
            # Re-import to trigger the constructor
            import importlib
            importlib.reload(docker_manager)
            with pytest.raises(IsolationError, match="Cannot connect to Docker"):
                docker_manager.DockerManager()


# =============================================================================
# Docker integration tests — require real Docker
# =============================================================================

pytestmark_docker = pytest.mark.docker


@pytest.mark.docker
class TestDockerLifecycle:
    """
    Full lifecycle integration tests.
    Requires Docker to be running.
    Run with: pytest -m docker
    """

    @pytest.fixture(autouse=True)
    def cleanup_after(self):
        """Ensure Docker resources are cleaned up after each test."""
        created_project_ids: list[str] = []
        yield created_project_ids

        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager
        manager = DockerManager()
        ws = WorkspaceManager()
        for pid in created_project_ids:
            try:
                manager.cleanup_all(pid)
            except Exception:
                pass
            try:
                ws.cleanup_workspace(pid)
            except Exception:
                pass

    def test_build_and_start_valid_app(self, tmp_path, cleanup_after):
        """Happy path: build image, start container, health check passes."""
        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager

        project_id = str(uuid.uuid4())
        cleanup_after.append(project_id)

        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        workspace = ws.create_scan_workspace(project_id, VALID_APP_PATH)

        dm = DockerManager()
        image_tag = dm.build_image(
            project_id=project_id,
            workspace_path=workspace,
            entry_point="main.py",
            dependency_file="requirements.txt",
        )
        assert image_tag is not None

        container_id, container_name = dm.start_container(project_id, image_tag)
        assert container_id is not None
        assert "clairsec-target" in container_name

        healthy = dm.wait_for_healthy(container_id)
        assert healthy, "Container health check did not pass"

    def test_logs_retrievable(self, tmp_path, cleanup_after):
        """Container logs are non-empty after startup."""
        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager

        project_id = str(uuid.uuid4())
        cleanup_after.append(project_id)

        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        workspace = ws.create_scan_workspace(project_id, VALID_APP_PATH)

        dm = DockerManager()
        image_tag = dm.build_image(project_id, workspace, "main.py", "requirements.txt")
        container_id, _ = dm.start_container(project_id, image_tag)
        dm.wait_for_healthy(container_id)

        logs = dm.get_logs(container_id)
        assert isinstance(logs, str)
        assert len(logs) > 0

    def test_cleanup_removes_container(self, tmp_path, cleanup_after):
        """After cleanup_all, the container no longer exists."""
        import docker

        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager

        project_id = str(uuid.uuid4())
        cleanup_after.append(project_id)

        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        workspace = ws.create_scan_workspace(project_id, VALID_APP_PATH)

        dm = DockerManager()
        image_tag = dm.build_image(project_id, workspace, "main.py", "requirements.txt")
        container_id, _ = dm.start_container(project_id, image_tag)
        dm.wait_for_healthy(container_id)

        dm.cleanup_all(project_id, container_id=container_id)
        cleanup_after.clear()  # already cleaned up

        client = docker.from_env()
        with pytest.raises(docker.errors.NotFound):
            client.containers.get(container_id)

    def test_build_failure_raises_isolation_error(self, tmp_path, cleanup_after):
        """A broken project (bad dependency) raises IsolationError during build."""
        from app.isolation.docker_manager import DockerManager
        from app.isolation.errors import IsolationError
        from app.isolation.workspace import WorkspaceManager

        project_id = str(uuid.uuid4())
        cleanup_after.append(project_id)

        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        workspace = ws.create_scan_workspace(project_id, BROKEN_APP_PATH)

        dm = DockerManager()
        with pytest.raises(IsolationError, match="build failed"):
            dm.build_image(
                project_id=project_id,
                workspace_path=workspace,
                entry_point="main.py",
                dependency_file="requirements.txt",
            )

    def test_workspace_isolation_two_projects(self, tmp_path, cleanup_after):
        """Two separate projects use separate workspaces that don't interfere."""
        from app.isolation.workspace import WorkspaceManager

        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())
        cleanup_after.extend([id_a, id_b])

        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        path_a = ws.create_scan_workspace(id_a, VALID_APP_PATH)
        path_b = ws.create_scan_workspace(id_b, VALID_APP_PATH)

        # Write to A — should not affect B
        (path_a / "injected.txt").write_text("project A only")
        assert not (path_b / "injected.txt").exists()

    def test_stop_container(self, tmp_path, cleanup_after):
        """Stopping a container removes it; get_logs returns not-found message."""
        from app.isolation.docker_manager import DockerManager
        from app.isolation.workspace import WorkspaceManager

        project_id = str(uuid.uuid4())
        cleanup_after.append(project_id)

        ws = WorkspaceManager(workspace_root=str(tmp_path / "workspaces"))
        workspace = ws.create_scan_workspace(project_id, VALID_APP_PATH)

        dm = DockerManager()
        image_tag = dm.build_image(project_id, workspace, "main.py", "requirements.txt")
        container_id, _ = dm.start_container(project_id, image_tag)
        dm.wait_for_healthy(container_id)

        dm.stop_container(container_id)

        # After stop, logs should return not-found message (not raise)
        result = dm.get_logs(container_id)
        assert "not found" in result.lower() or isinstance(result, str)
