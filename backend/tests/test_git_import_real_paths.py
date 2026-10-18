"""
D1 regression tests: the GitHub import must work through its REAL call chain.

Round 3 shipped two bugs that mocked tests hid: the ref was lower-cased
(HEAD -> head, which git cannot resolve) and the clone fallback was called with
a keyword its signature did not accept. These tests do not mock any internal
GitImportService method; only the remote (a local bare repo, or github.com
itself in the network test) differs from production.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.git_import_service import GitImportService
from app.services.url_validator import GitUrlInfo, validate_github_url

APP_SRC = (
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n\n"
    "@app.get('/health')\n"
    "def health():\n"
    "    return {'ok': True}\n"
)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture()
def bare_repo(tmp_path: Path) -> Path:
    """A local bare repo with a FastAPI app on a mixed-case branch 'Feature-X'."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "main.py").write_text(APP_SRC)
    (work / "requirements.txt").write_text("fastapi\nuvicorn\n")
    _git("init", "-q", "-b", "Feature-X", cwd=work)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "add", ".", cwd=work)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init", cwd=work)
    bare = tmp_path / "remote.git"
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    return bare


@pytest.fixture()
def file_protocol_allowed(monkeypatch):
    monkeypatch.setattr(settings, "testing", True)


def test_ref_case_is_preserved_for_ls_remote(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, *a, **kw):
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="")

    import app.services.git_import_service as mod

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.httpx, "Client", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    svc = GitImportService(db=None)
    for ref in (None, "Feature-X"):
        seen.clear()
        info = GitUrlInfo(url="https://github.com/o/r", normalized_url="https://github.com/o/r",
                          owner="o", repo="r", ref=ref)
        assert svc._resolve_sha_github(info) is None
        ls = [c for c in seen if "ls-remote" in c][0]
        assert ls[-1] == (ref or "HEAD"), ls


def test_tarball_failure_falls_back_to_real_hardened_clone(bare_repo, tmp_path, file_protocol_allowed, monkeypatch):
    svc = GitImportService(db=None)
    # Force the tarball strategy to fail at the network boundary only.
    monkeypatch.setattr(svc, "_resolve_sha_github", lambda info: None)
    info = GitUrlInfo(url=bare_repo.as_uri(), normalized_url="https://github.com/o/r",
                      owner="o", repo="r", ref="Feature-X")
    dest = tmp_path / "dest" / "source"
    result = svc._sync_fetch_and_verify("job", "00000000-0000-4000-8000-000000000000", info, dest, None)
    assert (dest / "main.py").exists()
    assert len(result["commit_sha"]) == 40
    assert str(result["validation_status"]).endswith("VALID")
    assert result["entry_point"] == "main.py"
    assert not (dest / ".git" / "hooks").exists()


def test_hardened_clone_honours_cancellation(tmp_path, monkeypatch):
    """A clone that never finishes is killed promptly once the flag is set."""
    import threading
    import time

    import app.services.git_import_service as mod
    from app.services.git_import_service import GitImportError

    killed = threading.Event()

    class HangingProc:
        returncode = None

        def communicate(self, timeout=None):
            if killed.is_set():
                self.returncode = -9
                return "", ""
            time.sleep(timeout or 0)
            raise subprocess.TimeoutExpired("git", timeout)

        def kill(self):
            killed.set()

        def poll(self):
            return self.returncode

    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: HangingProc())
    monkeypatch.setattr(GitImportService, "_check_git_version", lambda self: None)
    flag = threading.Event()
    threading.Timer(0.3, flag.set).start()
    info = GitUrlInfo(url="https://github.com/o/r", normalized_url="https://github.com/o/r",
                      owner="o", repo="r", ref=None)
    t0 = time.monotonic()
    with pytest.raises(GitImportError, match="cancelled"):
        GitImportService(db=None)._hardened_git_clone(info, tmp_path / "c", cancellation_flag=flag)
    assert killed.is_set()
    assert time.monotonic() - t0 < 5


@pytest.mark.network
def test_real_github_import():
    info = validate_github_url("https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / "source"
        result = GitImportService(db=None)._sync_fetch_and_verify(
            "job", "00000000-0000-4000-8000-000000000000", info, dest, None
        )
        assert len(result["commit_sha"]) == 40
        assert result["file_count"] > 0
        assert result["entry_point"] == "docker-images/app/main.py"
        assert "\\" not in (result["dependency_file"] or "")
