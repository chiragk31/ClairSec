"""
Tests for C8 & C9: Subdir validation and Dockerfile POSIX path normalization.
"""
from pathlib import Path
import tempfile
import pytest

from app.isolation.docker_manager import DockerManager
from app.services.fastapi_validator import validate_fastapi_project
from app.services.git_import_service import GitImportError, GitImportService


def test_subdir_traversal_refused():
    """
    C8: Validate subdir (relative, no .., no absolute, resolves inside the clone, is a directory).
    Refuse traversal or invalid subdirs.
    """
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()
        (dest_dir / "valid_dir").mkdir()

        # Valid subdir
        validated = service._validate_subdir(dest_dir, "valid_dir")
        assert validated == dest_dir / "valid_dir"

        # Traversal with ..
        with pytest.raises(GitImportError, match="traversal|relative|invalid"):
            service._validate_subdir(dest_dir, "../outside")

        # Nested traversal
        with pytest.raises(GitImportError, match="traversal|relative|invalid"):
            service._validate_subdir(dest_dir, "valid_dir/../../etc")

        # Absolute path
        with pytest.raises(GitImportError, match="traversal|relative|invalid"):
            service._validate_subdir(dest_dir, "/absolute/path")

        # Not a directory (file or non-existent)
        (dest_dir / "some_file.txt").write_text("hello")
        with pytest.raises(GitImportError, match="directory|not exist"):
            service._validate_subdir(dest_dir, "some_file.txt")


def test_monorepo_import_source_path_is_subdir():
    """
    C8: When subdir is used, the project's app root (source_path for building) is the subdir.
    """
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()
        sub = dest_dir / "backend_service"
        sub.mkdir()
        (sub / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
        (sub / "requirements.txt").write_text("fastapi\n")

        res = service._finalize_import_metadata(
            dest_dir=dest_dir,
            subdir="backend_service",
            commit_sha="a" * 40,
            file_count=2,
            repo_size=100,
            notes=[],
        )
        assert res["source_path"] == str(sub.resolve()) or res["source_path"] == str(sub)
        assert res["validation_status"].value == "valid"


from unittest.mock import MagicMock


def test_dockerfile_nested_entrypoint_posix_and_app_dir():
    """
    C9: Dockerfile for entry `docker-images\\app\\main.py` + dep `docker-images\\requirements.txt`
    contains only forward slashes and a valid uvicorn command with --app-dir.
    """
    manager = DockerManager(client=MagicMock())
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        entry_point = "docker-images\\app\\main.py"
        dep_file = "docker-images\\requirements.txt"
        (ws / "docker-images").mkdir()
        (ws / "docker-images" / "requirements.txt").write_text("fastapi\n")

        manager._write_dockerfile(
            workspace_path=ws,
            entry_point=entry_point,
            dependency_file=dep_file,
        )

        dockerfile = (ws / "Dockerfile").read_text(encoding="utf-8")

        # 1. Must contain ONLY forward slashes in path references, NO backslashes
        assert "\\" not in dockerfile, f"Dockerfile contains backslashes: {dockerfile}"

        # 2. Must contain forward-slash dependency copy/install
        assert "docker-images/requirements.txt" in dockerfile

        # 3. Must use uvicorn with --app-dir and bare module
        assert "--app-dir" in dockerfile
        assert "docker-images/app" in dockerfile
        assert "main:app" in dockerfile
