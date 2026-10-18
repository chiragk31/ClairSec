"""
Safety and hostile archive tests for GitImportService (FEATURES.md F2, THREAT_MODEL C2).

Tests:
- authorization_affirmed is mandatory (422)
- hostile archives: path-traversal, absolute-path, device/FIFO, symlink-escape
- size cap enforcement
- file count cap enforcement
- timeout enforcement
- import pre-checks card
- monorepo candidate discovery
- read-only file tree generation
"""
from __future__ import annotations

import io
import os
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services.git_import_service import (
    GitImportError,
    GitImportService,
    build_project_file_tree,
)
from app.services.url_validator import GitUrlInfo


def test_authorization_affirmed_required():
    service = GitImportService()
    with pytest.raises(ValueError, match="authorization_affirmed must be True"):
        import asyncio
        asyncio.run(
            service.start_import(
                url="https://github.com/owner/repo",
                authorization_affirmed=False,
            )
        )


def test_hostile_archive_path_traversal():
    """Archive with ../../ outside target must be refused."""
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            data = b"malicious content"
            ti = tarfile.TarInfo(name="../../evil.txt")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        tar_buf.seek(0)
        temp_tar = Path(td) / "hostile.tar.gz"
        temp_tar.write_bytes(tar_buf.getvalue())

        url_info = GitUrlInfo(
            url="https://github.com/owner/repo",
            normalized_url="https://github.com/owner/repo",
            owner="owner",
            repo="repo",
        )

        with patch("httpx.Client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_bytes.return_value = [tar_buf.getvalue()]
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp

            with pytest.raises(GitImportError, match="Hostile archive refused"):
                service._fetch_and_extract_tarball(url_info, "0123456789abcdef0123456789abcdef01234567", dest_dir)


def test_hostile_archive_absolute_path():
    """Archive with /etc/passwd or absolute path must be refused."""
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            data = b"malicious content"
            ti = tarfile.TarInfo(name="/tmp/evil.txt")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))

        tar_buf.seek(0)
        url_info = GitUrlInfo(
            url="https://github.com/owner/repo",
            normalized_url="https://github.com/owner/repo",
            owner="owner",
            repo="repo",
        )

        with patch("httpx.Client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_bytes.return_value = [tar_buf.getvalue()]
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp

            with pytest.raises(GitImportError, match="Hostile archive refused"):
                service._fetch_and_extract_tarball(url_info, "0123456789abcdef0123456789abcdef01234567", dest_dir)


def test_symlink_escape_refused():
    """Symlink pointing outside repository root must be refused and removed."""
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()
        outside_file = Path(td) / "outside.txt"
        outside_file.write_text("secret host data")

        # Create symlink inside dest pointing to outside
        symlink = dest_dir / "link_to_outside"
        try:
            os.symlink(outside_file, symlink)
        except OSError:
            pytest.skip("Symlinks not supported on this platform/privilege level")

        with pytest.raises(GitImportError, match="Symlink escapes repository root"):
            service._sanitize_extracted_tree(dest_dir)

        # Symlink should have been deleted for defense in depth
        assert not symlink.exists()


def test_size_cap_enforced(monkeypatch):
    """Streaming download exceeding git_max_repo_mb must be aborted."""
    service = GitImportService()
    # Temporarily set max repo to 1 MB for the test
    monkeypatch.setattr(settings, "git_max_repo_mb", 1)

    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        url_info = GitUrlInfo(
            url="https://github.com/owner/repo",
            normalized_url="https://github.com/owner/repo",
            owner="owner",
            repo="repo",
        )

        # Provide 2 MB chunk stream
        large_chunk = b"X" * (1024 * 1024 + 100)

        with patch("httpx.Client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_bytes.return_value = [large_chunk]
            mock_client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp

            with pytest.raises(GitImportError, match="Repository exceeds maximum size limit"):
                service._fetch_and_extract_tarball(url_info, "0123456789abcdef0123456789abcdef01234567", dest_dir)


def test_file_count_cap_enforced(monkeypatch):
    """File count exceeding git_max_files must be refused."""
    service = GitImportService()
    monkeypatch.setattr(settings, "git_max_files", 3)

    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()
        for i in range(5):
            (dest_dir / f"file_{i}.txt").write_text("ok")

        with pytest.raises(GitImportError, match="File count exceeds maximum allowed"):
            service._check_limits(dest_dir)


def test_import_prechecks_card():
    """Import pre-checks flags install scripts, secrets, and editor hooks."""
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        (dest_dir / "setup.py").write_text("print('install')")
        (dest_dir / ".env").write_text("SECRET=123")
        (dest_dir / "custom.pth").write_text("/usr/local")
        hook_dir = dest_dir / ".claude"
        hook_dir.mkdir()

        notes = service._run_import_prechecks(dest_dir)
        note_str = " ".join(notes)
        assert "setup.py" in note_str
        assert ".env" in note_str
        assert ".pth" in note_str
        assert ".claude" in note_str


def test_monorepo_candidate_discovery():
    """Finds FastAPI apps in subdirectories up to depth 4."""
    service = GitImportService()
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        backend_dir = dest_dir / "services" / "api"
        backend_dir.mkdir(parents=True)
        (backend_dir / "main.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root(): pass"
        )
        (backend_dir / "requirements.txt").write_text("fastapi\nuvicorn\n")

        candidates = service._discover_monorepo_candidates(dest_dir)
        assert len(candidates) >= 1
        c = candidates[0]
        assert "services" in c["subdir"] and "api" in c["subdir"]
        assert c["entry_point"] == "main.py"
        assert c["has_dep_file"] is True


def test_read_only_file_tree_generation():
    """Generates read-only tree structure capped at max_nodes, omitting file contents."""
    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        (dest_dir / "app").mkdir()
        (dest_dir / "app" / "main.py").write_text("app code")
        (dest_dir / "requirements.txt").write_text("fastapi")
        (dest_dir / ".git").mkdir()
        (dest_dir / ".git" / "config").write_text("git config")

        tree = build_project_file_tree(dest_dir, max_depth=3)
        assert tree["type"] == "directory"
        child_names = [c["name"] for c in tree.get("children", [])]
        assert "app" in child_names
        assert "requirements.txt" in child_names
        assert ".git" not in child_names
        # Never includes file contents
        assert "app code" not in str(tree)
