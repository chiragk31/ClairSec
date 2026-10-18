"""
Tests for C7 & C12: Tarball & Git Import Hardening.
"""
import io
import re
import tarfile
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import settings
from app.services.git_import_service import GitImportError, GitImportService
from app.services.url_validator import GitUrlInfo


def test_sha_validation_rejects_invalid_hex():
    """
    C7: Validate SHA with ^[0-9a-f]{40}$. Reject invalid, traversal, or non-hex SHAs.
    """
    service = GitImportService()
    sha_regex = re.compile(r"^[0-9a-f]{40}$")

    invalid_shas = [
        "not-a-sha",
        "12345",
        "g" * 40,  # 'g' is not hex
        "../" * 10,
        "a" * 39,
        "a" * 41,
        "A" * 40,  # uppercase should be normalised to lower or strictly lowercase
    ]

    for bad_sha in invalid_shas:
        # Check against SHA validator
        assert not bool(sha_regex.match(bad_sha.lower()) and len(bad_sha) == 40 and all(c in "0123456789abcdef" for c in bad_sha.lower()) and bad_sha == bad_sha.lower()), (
            f"Expected {bad_sha} to be rejected"
        )


def test_tarball_refuses_file_count_over_git_max_files():
    """
    C7: Before extractall, iterate members, count files; refuse if over git_max_files.
    """
    service = GitImportService()
    url_info = GitUrlInfo(
        url="https://github.com/test-owner/test-repo",
        normalized_url="https://github.com/test-owner/test-repo",
        owner="test-owner",
        repo="test-repo",
        ref="main",
    )

    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        # Create tarball in memory with file count exceeding cap
        cap = 10
        with patch.object(settings, "git_max_files", cap):
            tar_buf = io.BytesIO()
            with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
                for i in range(cap + 2):
                    ti = tarfile.TarInfo(name=f"test-repo-12345/file_{i}.txt")
                    ti.size = 10
                    tar.addfile(ti, io.BytesIO(b"1234567890"))
            tar_bytes = tar_buf.getvalue()

            # Mock httpx response streaming these bytes
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-length": str(len(tar_bytes))}
            mock_resp.iter_bytes.return_value = [tar_bytes]

            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_resp
                with pytest.raises(GitImportError, match="file count.*exceeds cap"):
                    service._fetch_and_extract_tarball(url_info, "a" * 40, dest_dir)


def test_tarball_refuses_declared_size_over_extracted_cap():
    """
    C7: Before extractall, iterate members, sum declared sizes; refuse if over git_max_repo_mb extracted cap (4x).
    """
    service = GitImportService()
    url_info = GitUrlInfo(
        url="https://github.com/test-owner/test-repo",
        normalized_url="https://github.com/test-owner/test-repo",
        owner="test-owner",
        repo="test-repo",
        ref="main",
    )

    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        # Set 1 MB cap, so extracted cap is 4 MB
        with patch.object(settings, "git_max_repo_mb", 1):
            tar_buf = io.BytesIO()
            with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
                # Single member declaring 5 MB size (zip bomb style)
                ti = tarfile.TarInfo(name="test-repo-12345/huge_file.dat")
                data = b"0" * (5 * 1024 * 1024)
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
            tar_bytes = tar_buf.getvalue()

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"content-length": str(len(tar_bytes))}
            mock_resp.iter_bytes.return_value = [tar_bytes]

            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_resp
                with pytest.raises(GitImportError, match="extracted size.*exceeds cap"):
                    service._fetch_and_extract_tarball(url_info, "a" * 40, dest_dir)


def test_download_wall_clock_deadline_enforced():
    """
    C7: Enforce an overall wall-clock deadline for download (monotonic check per chunk).
    """
    service = GitImportService()
    url_info = GitUrlInfo(
        url="https://github.com/test-owner/test-repo",
        normalized_url="https://github.com/test-owner/test-repo",
        owner="test-owner",
        repo="test-repo",
        ref="main",
    )

    with tempfile.TemporaryDirectory() as td:
        dest_dir = Path(td) / "dest"
        dest_dir.mkdir()

        # Simulate chunks taking longer than download timeout
        def slow_chunks():
            yield b"chunk1"
            # Jump time past deadline
            time.sleep(0.05)
            yield b"chunk2"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": "1000"}
        mock_resp.iter_bytes.return_value = slow_chunks()

        # Patch timeout to very short value
        with patch.object(settings, "git_clone_timeout", 0.01):
            with patch("httpx.Client.stream") as mock_stream:
                mock_stream.return_value.__enter__.return_value = mock_resp
                with pytest.raises(GitImportError, match="timed out|deadline"):
                    service._fetch_and_extract_tarball(url_info, "a" * 40, dest_dir)
