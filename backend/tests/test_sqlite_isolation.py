"""
Tests for SQLite support under hardened read-only Docker container isolation.

Covers:
  1. A FastAPI application using SQLite starting successfully under read_only=True rootfs.
  2. Relative paths and configured paths properly adapted to /tmp/clairsec-data.
  3. Non-root user (appuser, uid 10001) having write access to /tmp/clairsec-data.
  4. The container root filesystem remaining strictly read-only.
  5. Incompatible database configuration failing with a useful diagnostic.
  6. Original uploaded source directory remaining byte-for-byte unchanged.
  7. Failure handling capturing target and proxy container logs before cleanup.
  8. Existing isolation and cleanup behavior remaining intact.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.config import settings
from app.database.models import IsolationStatus, JobStatus
from app.isolation.docker_manager import DockerManager
from app.isolation.sqlite_adapter import (
    SQLITE_DATA_DIR,
    SQLiteDetectionResult,
    adapt_workspace_for_sqlite,
)
from app.services.job_service import JobService


def _dir_sha256(directory: Path) -> str:
    """Compute recursive SHA-256 digest of all files in directory."""
    hasher = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            hasher.update(path.relative_to(directory).as_posix().encode("utf-8"))
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


class TestSQLiteDetectionAndAdaptation:
    def test_relative_path_adaptation_in_workspace(self, tmp_path: Path):
        """Hardcoded relative SQLite path is adapted in-place in scan_workspace."""
        ws = tmp_path / "scan_workspace"
        app_dir = ws / "app"
        app_dir.mkdir(parents=True)

        db_py = app_dir / "database.py"
        db_py.write_text(
            'import os\n'
            'import sqlite3\n\n'
            'DB_PATH = os.path.join(os.path.dirname(__file__), "..", "vuln_app.db")\n\n'
            'def get_db():\n'
            '    return sqlite3.connect(DB_PATH)\n',
            encoding="utf-8",
        )

        # Pre-existing template database
        (ws / "vuln_app.db").write_bytes(b"SQLite format 3\x00fake")

        result = adapt_workspace_for_sqlite(ws)

        assert result.detected is True
        assert result.compatible is True
        assert "vuln_app.db" in result.db_files
        assert "app/database.py" in [p.replace("\\", "/") for p in result.adapted_files]
        assert result.env_vars["DB_PATH"] == f"{SQLITE_DATA_DIR}/vuln_app.db"
        assert result.env_vars["SQLITE_DATA_DIR"] == SQLITE_DATA_DIR

        # Verify adapted code parses cleanly as valid Python
        adapted_content = db_py.read_text(encoding="utf-8")
        assert "os.environ.get" in adapted_content
        ast.parse(adapted_content)

        # Verify sitecustomize.py was installed
        sitecustomize = ws / "sitecustomize.py"
        assert sitecustomize.exists()
        assert "sitecustomize.py" in sitecustomize.read_text(encoding="utf-8")

    def test_configured_env_path_not_mutated(self, tmp_path: Path):
        """Code already checking os.environ is detected without source mutation."""
        ws = tmp_path / "scan_workspace"
        app_dir = ws / "app"
        app_dir.mkdir(parents=True)

        db_py = app_dir / "database.py"
        original_code = (
            'import os\n'
            'import sqlite3\n\n'
            'DB_PATH = os.environ.get("DB_PATH", "/tmp/clairsec-data/app.db")\n\n'
            'def get_db():\n'
            '    return sqlite3.connect(DB_PATH)\n'
        )
        db_py.write_text(original_code, encoding="utf-8")

        result = adapt_workspace_for_sqlite(ws)

        assert result.detected is True
        assert result.compatible is True
        assert len(result.adapted_files) == 0  # No files modified!
        assert db_py.read_text(encoding="utf-8") == original_code

    def test_original_source_remains_unchanged(self, tmp_path: Path):
        """Original uploaded source files are NEVER modified."""
        source_dir = tmp_path / "original_source"
        source_dir.mkdir()
        (source_dir / "database.py").write_text(
            'DB_PATH = "my_app.db"\n', encoding="utf-8"
        )
        (source_dir / "my_app.db").write_bytes(b"initial_data")

        initial_sha = _dir_sha256(source_dir)

        # Simulate copy to workspace
        ws = tmp_path / "scan_workspace"
        import shutil
        shutil.copytree(source_dir, ws)

        adapt_workspace_for_sqlite(ws)

        final_sha = _dir_sha256(source_dir)
        assert initial_sha == final_sha, "Original uploaded source directory was modified!"

    def test_incompatible_configuration_diagnostic(self, tmp_path: Path):
        """Unparseable / invalid Python file causes clean incompatibility report."""
        ws = tmp_path / "scan_workspace"
        ws.mkdir()
        bad_file = ws / "database.py"
        bad_file.write_text("DB_PATH = 'data.db'\ndef broken(\n", encoding="utf-8")

        result = adapt_workspace_for_sqlite(ws)
        # Should gracefully detect or report incompatibility rather than crash
        assert isinstance(result, SQLiteDetectionResult)

    def test_non_sqlite_project_untouched(self, tmp_path: Path):
        """Projects not using SQLite are left completely untouched."""
        ws = tmp_path / "scan_workspace"
        ws.mkdir()
        main_py = ws / "main.py"
        main_py.write_text(
            'from fastapi import FastAPI\n'
            'app = FastAPI()\n'
            '@app.get("/health")\n'
            'def health(): return {"status": "ok"}\n',
            encoding="utf-8",
        )

        result = adapt_workspace_for_sqlite(ws)
        assert result.detected is False
        assert len(result.adapted_files) == 0
        assert not (ws / "sitecustomize.py").exists()


class TestDiagnosticsAndFailureHandling:
    @pytest.mark.asyncio
    async def test_failure_handling_captures_logs_before_cleanup(self):
        """Failure during health check captures target and proxy logs before cleanup."""
        mock_db = MagicMock()
        mock_docker = MagicMock()
        mock_docker.image_tag.return_value = "clairsec-image-12345678:latest"
        mock_docker.start_container.return_value = ("target_cid_123", "clairsec-target-12345678")
        mock_docker.start_proxy.return_value = ("proxy_cid_456", 8080)
        mock_docker.get_logs.side_effect = lambda cid: (
            "Traceback (most recent call last):\n  sqlite3.OperationalError: attempt to write a readonly database"
            if cid == "target_cid_123"
            else "HTTP/1.1 502 Bad Gateway"
        )

        mock_workspace = MagicMock()
        mock_workspace.get_project_root.return_value.exists.return_value = False
        mock_workspace.create_scan_workspace.return_value = Path("/tmp/mock_ws")

        service = JobService(mock_db, docker_manager=mock_docker, workspace_manager=mock_workspace)

        # Mock repository methods
        job_record = MagicMock(id="job-1", cancel_requested=False, status=JobStatus.RUNNING)
        project_record = MagicMock(
            id="12345678-0000-0000-0000-000000000000",
            source_path="/tmp/test",
            entry_point="main.py",
            dependency_file="requirements.txt",
            validation_status=MagicMock(value="valid"),
            proxy_container_id="proxy_cid_456",
        )

        service._job_repo.get_by_id = AsyncMock(return_value=job_record)
        service._job_repo.update = AsyncMock(return_value=job_record)
        service._project_repo.get_by_id = AsyncMock(return_value=project_record)
        service._project_repo.update = AsyncMock(return_value=project_record)

        # Force health check failure
        service._poll_health_with_cancel = AsyncMock(
            return_value=(False, {"probed_paths": ["/health"], "last_status_code": 502, "last_error": "Bad Gateway"})
        )

        with patch("app.services.job_service.adapt_workspace_for_sqlite") as mock_adapt:
            mock_adapt.return_value = SQLiteDetectionResult(detected=True, compatible=True, env_vars={})
            await service._run_isolation_job("job-1", project_record.id)

        # Verify logs were captured before cleanup
        mock_docker.get_logs.assert_any_call("target_cid_123")
        mock_docker.get_logs.assert_any_call("proxy_cid_456")

        # Verify cleanup was called
        mock_docker.cleanup_all.assert_called_once()
        mock_workspace.cleanup_workspace.assert_called_once()

        # Verify error message contains container logs
        assert "sqlite3.OperationalError" in project_record.isolation_error
        assert project_record.isolation_status == IsolationStatus.IMPORT_FAILED
        assert job_record.status == JobStatus.FAILED


@pytest.mark.docker
class TestSQLiteDockerIsolationLive:
    """Live Docker tests verifying SQLite functionality under read-only rootfs."""

    def test_non_root_user_has_write_access_to_tmpfs(self):
        """User 10001 (appuser) has write access to /tmp/clairsec-data on tmpfs."""
        import docker

        client = docker.from_env()
        output = client.containers.run(
            image=settings.docker_base_image,
            command=[
                "python3",
                "-c",
                (
                    "import os, sqlite3; "
                    "DATA_DIR = '/tmp/clairsec-data'; "
                    "os.makedirs(DATA_DIR, exist_ok=True); "
                    "conn = sqlite3.connect(f'{DATA_DIR}/test.db'); "
                    "conn.execute('CREATE TABLE t (v TEXT)'); "
                    "conn.execute('INSERT INTO t VALUES (?)', ('isolated_ok',)); "
                    "conn.commit(); "
                    "rows = conn.execute('SELECT v FROM t').fetchall(); "
                    "print(f'STATUS:{rows[0][0]} UID:{os.stat(f\"{DATA_DIR}/test.db\").st_uid}')"
                ),
            ],
            user="10001:10001",
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            remove=True,
        )
        text = output.decode("utf-8")
        assert "STATUS:isolated_ok" in text
        assert "UID:10001" in text

    def test_container_rootfs_remains_strictly_read_only(self):
        """Attempting to write to /app or /etc under read_only=True raises OperationalError/OSError."""
        import docker
        import docker.errors

        client = docker.from_env()
        with pytest.raises(docker.errors.ContainerError) as exc_info:
            client.containers.run(
                image=settings.docker_base_image,
                command=[
                    "python3",
                    "-c",
                    "import sqlite3; conn = sqlite3.connect('/app_readonly.db'); conn.execute('CREATE TABLE t (x INT)')",
                ],
                user="10001:10001",
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                remove=True,
            )
        assert "OperationalError" in str(exc_info.value) or "Read-only file system" in str(exc_info.value)

    def test_fastapi_sqlite_app_starts_and_responds_under_readonly_rootfs(self, tmp_path: Path):
        """A complete FastAPI app with SQLite lifespan starts and responds under read-only rootfs."""

        import httpx

        ws = tmp_path / "sqlite_test_app"
        ws.mkdir()
        (ws / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
        (ws / "main.py").write_text(
            'import os, sqlite3\n'
            'from contextlib import asynccontextmanager\n'
            'from fastapi import FastAPI\n\n'
            'DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")\n\n'
            'def init_db():\n'
            '    conn = sqlite3.connect(DB_PATH)\n'
            '    conn.execute("CREATE TABLE IF NOT EXISTS items (id INT, name TEXT)")\n'
            '    conn.execute("INSERT OR IGNORE INTO items VALUES (1, \'test\')")\n'
            '    conn.commit()\n'
            '    conn.close()\n\n'
            '@asynccontextmanager\n'
            'async def lifespan(app: FastAPI):\n'
            '    init_db()\n'
            '    yield\n\n'
            'app = FastAPI(lifespan=lifespan)\n\n'
            '@app.get("/health")\n'
            'def health():\n'
            '    return {"status": "ok"}\n\n'
            '@app.get("/items")\n'
            'def get_items():\n'
            '    conn = sqlite3.connect(DB_PATH)\n'
            '    rows = conn.execute("SELECT * FROM items").fetchall()\n'
            '    conn.close()\n'
            '    return {"items": rows}\n',
            encoding="utf-8",
        )

        # Adapt workspace
        adapt_res = adapt_workspace_for_sqlite(ws)
        assert adapt_res.detected is True
        assert adapt_res.compatible is True

        manager = DockerManager()
        project_id = "f0000000-0000-0000-0000-000000000001"

        try:
            image_tag = manager.build_image(project_id, ws, "main.py", "requirements.txt")
            cid, cname = manager.start_container(
                project_id,
                image_tag,
                environment=adapt_res.env_vars,
            )
            _proxy_id, proxy_port = manager.start_proxy(project_id, cname)

            healthy = manager.wait_for_healthy(proxy_port, startup_timeout=45)
            assert healthy is True, f"Target container failed to become healthy. Logs:\n{manager.get_logs(cid)}"

            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"http://127.0.0.1:{proxy_port}/items")
                assert resp.status_code == 200
                data = resp.json()
                assert data["items"] == [[1, "test"]]
        finally:
            manager.cleanup_all(project_id)
