"""
Git & GitHub repository import service (FEATURES.md F2, THREAT_MODEL C2, C3).

Implements:
- Pure URL & ref validation
- Tarball-first fetch (httpx streaming with byte-cap and progress)
- Safe tar extraction with Python 3.11 tarfile.data_filter
- Hostile archive rejection (path traversal, absolute paths, device files, symlink escapes)
- Hardened git clone fallback (Git >= 2.45.1, hardened env, hook-free)
- Import pre-checks (install scripts, .pth, secrets, large binaries, editor hooks)
- Monorepo candidate discovery (up to depth 4)
- File tree generation (max 2,000 nodes, never file contents)
"""
from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import anyio
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.database.models import (
    JobRecord,
    JobStatus,
    ProjectRecord,
    ValidationStatus,
)
from app.database.repositories import JobRepository, ProjectRepository
from app.services.event_bus import event_bus
from app.services.fastapi_validator import (
    _ast_has_fastapi_instance,
    validate_fastapi_project,
)
from app.services.secret_scanner import scan_tree
from app.services.url_validator import GitUrlInfo, validate_github_url

from app.services.task_registry import task_registry

logger = logging.getLogger(__name__)

_SHA_REGEX = re.compile(r"^[0-9a-f]{40}$")

_SECRET_PATTERNS = [
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "service_account.json",
]


class GitImportError(Exception):
    """Raised when repository import or validation fails."""
    pass


class GitImportService:
    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._db = db
        self._project_repo = ProjectRepository(db)
        self._job_repo = JobRepository(db)
        self._active_tasks: dict[str, asyncio.Task] = {}

    def get_workspace_dir(self, project_id: str) -> Path:
        """Destination directory for imported git repository."""
        base = Path(settings.workspace_root or tempfile.gettempdir())
        return base / "imports" / project_id / "source"

    async def start_import(
        self,
        url: str,
        ref: str | None = None,
        subdir: str | None = None,
        name: str | None = None,
        authorization_affirmed: bool = False,
    ) -> tuple[JobRecord, ProjectRecord]:
        """
        Initiate an asynchronous git repository import.
        Returns (job_record, project_record) immediately.
        """
        # Authorization affirmation is mandatory per ETHICS.md §1
        if not authorization_affirmed:
            raise ValueError("authorization_affirmed must be True to import a repository.")

        url_info = validate_github_url(url, ref=ref)

        resolved_name = name or url_info.repo
        dest_dir = self.get_workspace_dir("pending")

        project = ProjectRecord(
            name=resolved_name,
            source_path="",  # will be populated once project ID is generated
            import_source="git",
            git_url=url_info.normalized_url,
            git_ref=url_info.ref,
            git_subdir=subdir,
            authorization_affirmed=True,
            authorization_affirmed_at=datetime.now(timezone.utc),
            validation_status=ValidationStatus.UNKNOWN,
        )
        created_project = await self._project_repo.create(project)

        # Update real source_path with project ID
        real_dest = self.get_workspace_dir(created_project.id)
        created_project.source_path = str(real_dest)
        await self._project_repo.update(created_project)

        # Create tracking job
        job = JobRecord(
            project_id=created_project.id,
            status=JobStatus.PENDING,
            stage="queued",
        )
        created_job = await self._job_repo.create(job)

        # Launch background worker
        task = asyncio.create_task(
            self._run_import_job(created_job.id, created_project.id, url_info, subdir)
        )
        self._active_tasks[created_job.id] = task
        task_registry.register(f"job-{created_job.id}", task)
        task_registry.register(f"import-{created_project.id}", task)

        return created_job, created_project

    async def _run_import_job(
        self,
        job_id: str,
        project_id: str,
        url_info: GitUrlInfo,
        subdir: str | None,
    ) -> None:
        """Background worker for git import."""
        dest_dir = self.get_workspace_dir(project_id)
        cancel_event = threading.Event()

        # Wire task_registry cancellation token to threading cancel_event
        token = task_registry.get_cancellation_token(f"job-{job_id}")

        async def _watch_cancel():
            if token:
                await token.wait()
                cancel_event.set()

        watcher_task = asyncio.create_task(_watch_cancel())

        try:
            await self._job_repo.update_status(job_id, JobStatus.RUNNING, stage="checking_url")
            await event_bus.emit(
                scan_id=f"job-{job_id}",
                agent="importer",
                kind="stage_started",
                title=f"Checking repository URL {url_info.normalized_url}",
                refs={"project_id": project_id, "job_id": job_id},
            )

            # Synchronous work in thread
            def _execute_import():
                return self._sync_fetch_and_verify(
                    job_id=job_id,
                    project_id=project_id,
                    url_info=url_info,
                    dest_dir=dest_dir,
                    subdir=subdir,
                    cancellation_flag=cancel_event,
                )

            project_updates = await anyio.to_thread.run_sync(_execute_import)

            # Update project in DB
            project = await self._project_repo.get_by_id(project_id)
            if project:
                for k, v in project_updates.items():
                    setattr(project, k, v)
                await self._project_repo.update(project)

            await self._job_repo.update_status(job_id, JobStatus.COMPLETED, stage="completed")
            await event_bus.emit(
                scan_id=f"job-{job_id}",
                agent="importer",
                kind="stage_finished",
                title="Repository import completed",
                refs={"project_id": project_id, "job_id": job_id},
            )

        except asyncio.CancelledError:
            cancel_event.set()
            await self._job_repo.update_status(job_id, JobStatus.CANCELLED, stage="cancelled")
            if dest_dir.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)
            await event_bus.emit(
                scan_id=f"job-{job_id}",
                agent="importer",
                kind="error",
                title="Repository import cancelled",
                refs={"project_id": project_id, "job_id": job_id},
            )
        except Exception as exc:
            cancel_event.set()
            logger.exception("Import failed for project %s: %s", project_id, exc)
            await self._job_repo.update_status(
                job_id,
                JobStatus.FAILED,
                stage="failed",
                error=str(exc),
            )
            # Mark project invalid with the error
            project = await self._project_repo.get_by_id(project_id)
            if project:
                project.validation_status = ValidationStatus.INVALID
                project.validation_errors = [str(exc)]
                await self._project_repo.update(project)

            await event_bus.emit(
                scan_id=f"job-{job_id}",
                agent="importer",
                kind="error",
                title=f"Repository import failed: {exc}",
                refs={"project_id": project_id, "job_id": job_id},
            )
        finally:
            watcher_task.cancel()
            task_registry.unregister(f"job-{job_id}")
            task_registry.unregister(f"import-{project_id}")

    def _validate_subdir(self, dest_dir: Path, subdir: str | None) -> Path:
        """
        Validate and resolve subdir (C8).
        Must be relative, no '..', resolves inside dest_dir, and is a directory.
        """
        if not subdir:
            return dest_dir

        sub_str = str(subdir).replace("\\", "/")
        if sub_str.startswith("/") or (len(sub_str) > 1 and sub_str[1] == ":"):
            raise GitImportError(f"Invalid subdir: '{subdir}' must be a relative path.")

        sub_p = Path(sub_str)
        if ".." in sub_p.parts:
            raise GitImportError(f"Invalid subdir: path traversal in '{subdir}' is refused.")

        resolved = (dest_dir / sub_p).resolve()
        dest_resolved = dest_dir.resolve()

        try:
            resolved.relative_to(dest_resolved)
        except ValueError:
            raise GitImportError(f"Invalid subdir: '{subdir}' resolves outside the repository root.")

        if not resolved.exists() or not resolved.is_dir():
            raise GitImportError(f"Invalid subdir: '{subdir}' does not exist or is not a directory.")

        return resolved

    def _finalize_import_metadata(
        self,
        dest_dir: Path,
        subdir: str | None,
        commit_sha: str | None,
        file_count: int,
        repo_size: int,
        notes: list[str],
        val_res: Any | None = None,
    ) -> dict[str, Any]:
        """Produce finalized project import metadata dictionary (C8)."""
        target_path = self._validate_subdir(dest_dir, subdir) if subdir else dest_dir
        if val_res is None:
            val_res = validate_fastapi_project(str(target_path))

        monorepo_candidates: list[dict] = []
        if not val_res.is_valid and not subdir:
            monorepo_candidates = self._discover_monorepo_candidates(dest_dir)

        return {
            "source_path": str(target_path),
            "commit_sha": commit_sha,
            "file_count": file_count,
            "repo_size_bytes": repo_size,
            "import_notes": notes,
            "monorepo_candidates": monorepo_candidates,
            "validation_status": ValidationStatus.VALID if val_res.is_valid else ValidationStatus.INVALID,
            "validation_errors": val_res.errors,
            "entry_point": val_res.entry_point,
            "dependency_file": val_res.dependency_file,
            "dependencies": val_res.dependencies,
            "isolation_ready": val_res.isolation_ready,
        }

    def _sync_fetch_and_verify(
        self,
        job_id: str,
        project_id: str,
        url_info: GitUrlInfo,
        dest_dir: Path,
        subdir: str | None,
        cancellation_flag: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Synchronous fetch, extract, sanitise, and validation steps."""
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.parent.mkdir(parents=True, exist_ok=True)

        commit_sha: str | None = None
        fetch_success = False

        # ── 1. Strategy: Tarball first for github.com ───────────────────────
        if "github.com" in url_info.normalized_url.lower():
            try:
                commit_sha = self._resolve_sha_github(url_info)
                if commit_sha:
                    self._fetch_and_extract_tarball(
                        url_info,
                        commit_sha,
                        dest_dir,
                        cancellation_flag=cancellation_flag,
                        job_id=job_id,
                    )
                    fetch_success = True
            except Exception as exc:
                logger.warning("Tarball fetch failed, falling back to git clone: %s", exc)
                # If hostile archive detected, do NOT fallback to clone — refuse immediately!
                if "Hostile archive" in str(exc) or "Symlink escapes" in str(exc):
                    raise
                fetch_success = False

        # ── 2. Strategy: Hardened Git Clone fallback ─────────────────────────
        if not fetch_success:
            commit_sha = self._hardened_git_clone(
                url_info,
                dest_dir,
                cancellation_flag=cancellation_flag,
                job_id=job_id,
            )

        # ── 3. Post-extract / post-clone security sanitisation ───────────────
        self._sanitize_extracted_tree(dest_dir)

        # ── 4. File count & size check ───────────────────────────────────────
        file_count, repo_size = self._check_limits(dest_dir)

        # ── 5. Import pre-checks (report, don't block) ───────────────────────
        notes = self._run_import_prechecks(dest_dir)
        secrets = scan_tree(dest_dir)
        if secrets:
            notes.insert(0, f"{len(secrets)} exposed secret(s) committed in this repository "
                            "(values masked; rotate them).")

        # ── 6. Monorepo & FastAPI application validation ─────────────────────
        result = self._finalize_import_metadata(
            dest_dir=dest_dir,
            subdir=subdir,
            commit_sha=commit_sha,
            file_count=file_count,
            repo_size=repo_size,
            notes=notes,
        )
        result["exposed_secrets"] = secrets
        return result

    def _resolve_sha_github(self, url_info: GitUrlInfo) -> str | None:
        """Resolve ref to commit SHA via git ls-remote or 40-char ref (C7)."""
        # Git refs are case-sensitive: never change the case of a branch/tag name.
        ref = (url_info.ref or "HEAD").strip()
        if _SHA_REGEX.match(ref.lower()):
            return ref.lower()

        # Try git ls-remote with hardened environment
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_file = Path(temp_dir) / "empty"
            empty_file.touch()
            env = {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(empty_file),
                "HOME": temp_dir,
                "PATH": os.environ.get("PATH", ""),
            }
            cmd = [
                "git",
                "-c", f"core.hooksPath={temp_dir}",
                "-c", "protocol.file.allow=never",
                "-c", "protocol.ext.allow=never",
                "ls-remote",
                "--exit-code",
                url_info.normalized_url,
                ref,
            ]
            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=15,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    # Format: "<sha>\t<ref>"
                    sha_cand = res.stdout.split()[0].strip().lower()
                    if _SHA_REGEX.match(sha_cand):
                        return sha_cand
            except Exception as e:
                logger.debug("git ls-remote failed: %s", e)

        # Fallback to GitHub public API
        try:
            api_url = f"https://api.github.com/repos/{url_info.owner}/{url_info.repo}/commits/{ref}"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(api_url, headers={"User-Agent": "ClairSec-Scanner"})
                if resp.status_code == 200:
                    data = resp.json()
                    sha_cand = (data.get("sha") or "").strip().lower()
                    if _SHA_REGEX.match(sha_cand):
                        return sha_cand
        except Exception as e:
            logger.debug("GitHub API commit resolve failed: %s", e)

        return None

    def _fetch_and_extract_tarball(
        self,
        url_info: GitUrlInfo,
        commit_sha: str,
        dest_dir: Path,
        cancellation_flag: threading.Event | None = None,
        job_id: str | None = None,
    ) -> None:
        """Download and extract tarball safely with byte limits, deadline, member limits, and data_filter."""
        if not _SHA_REGEX.match(commit_sha.lower()):
            raise GitImportError(f"Invalid commit SHA '{commit_sha}': must match ^[0-9a-f]{{40}}$")

        tar_url = f"https://codeload.github.com/{url_info.owner}/{url_info.repo}/tar.gz/{commit_sha}"
        max_bytes = settings.git_max_repo_mb * 1024 * 1024
        download_timeout = getattr(settings, "git_clone_timeout", 180)
        deadline = time.monotonic() + download_timeout

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_tar = Path(temp_dir) / "repo.tar.gz"
            total_read = 0

            with httpx.Client(timeout=float(download_timeout), follow_redirects=True) as client:
                with client.stream("GET", tar_url) as response:
                    if response.status_code != 200:
                        raise GitImportError(f"HTTP {response.status_code} fetching tarball from {tar_url}")

                    content_length_hdr = response.headers.get("content-length")
                    content_length = int(content_length_hdr) if content_length_hdr and content_length_hdr.isdigit() else None

                    with open(temp_tar, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if cancellation_flag and cancellation_flag.is_set():
                                raise asyncio.CancelledError("Import cancelled")
                            if time.monotonic() > deadline:
                                raise GitImportError(f"Download timed out: wall-clock deadline of {download_timeout}s exceeded.")

                            total_read += len(chunk)
                            if total_read > max_bytes:
                                raise GitImportError(
                                    f"Repository exceeds maximum size limit ({settings.git_max_repo_mb} MB)."
                                )
                            f.write(chunk)

            # Pre-extraction limits (C7)
            max_files = getattr(settings, "git_max_files", 20000)
            extracted_cap = getattr(settings, "git_max_repo_mb", 200) * 4 * 1024 * 1024

            extract_temp = Path(temp_dir) / "extracted"
            extract_temp.mkdir(parents=True, exist_ok=True)

            try:
                with tarfile.open(temp_tar, mode="r:gz") as tar:
                    member_count = 0
                    total_declared_size = 0
                    for m in tar.getmembers():
                        if cancellation_flag and cancellation_flag.is_set():
                            raise asyncio.CancelledError("Import cancelled")
                        member_count += 1
                        total_declared_size += m.size

                        if member_count > max_files:
                            raise GitImportError(
                                f"Hostile archive refused: file count ({member_count}) exceeds cap ({max_files})"
                            )
                        if total_declared_size > extracted_cap:
                            raise GitImportError(
                                f"Hostile archive refused: extracted size ({total_declared_size} bytes) exceeds cap ({extracted_cap} bytes)"
                            )

                        # Refuse absolute paths, traversal, or drive letters
                        clean_name = m.name.replace("\\", "/")
                        if clean_name.startswith("/") or (len(clean_name) > 1 and clean_name[1] == ":"):
                            raise GitImportError(f"Hostile archive refused: absolute path '{m.name}'")
                        if ".." in clean_name.split("/"):
                            raise GitImportError(f"Hostile archive refused: path traversal '{m.name}'")
                        if m.isdev() or m.ischr() or m.isblk() or m.isfifo():
                            raise GitImportError(f"Hostile archive refused: special device file '{m.name}'")

                    # Python 3.11.9 tarfile filter='data'
                    # Rejects absolute paths, .., device files, outside links
                    if hasattr(tarfile, "data_filter"):
                        tar.extractall(path=extract_temp, filter="data")
                    else:
                        tar.extractall(path=extract_temp)
            except (tarfile.FilterError, Exception) as exc:
                if isinstance(exc, (GitImportError, asyncio.CancelledError)):
                    raise
                raise GitImportError(f"Hostile archive refused: {exc}") from exc

            # GitHub tarballs unpack into an inner folder '<repo>-<sha>'
            inner_entries = list(extract_temp.iterdir())
            if len(inner_entries) == 1 and inner_entries[0].is_dir():
                inner_dir = inner_entries[0]
                dest_dir.mkdir(parents=True, exist_ok=True)
                for item in inner_dir.iterdir():
                    shutil.move(str(item), str(dest_dir / item.name))
            else:
                shutil.copytree(str(extract_temp), str(dest_dir), dirs_exist_ok=True)

    def _hardened_git_clone(
        self,
        url_info: GitUrlInfo,
        dest_dir: Path,
        cancellation_flag: threading.Event | None = None,
        job_id: str | None = None,
    ) -> str:
        """Run a hardened, cancellable git clone subprocess (F2 fallback path)."""
        # 1. Minimum git version check (>= 2.45.1)
        self._check_git_version()

        with tempfile.TemporaryDirectory() as temp_dir:
            empty_dir = Path(temp_dir) / "empty"
            empty_dir.mkdir(parents=True, exist_ok=True)
            empty_file = Path(temp_dir) / "empty_cfg"
            empty_file.touch()

            # Hardened environment per F2 specification — no host env passthrough
            env = {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(empty_file),
                "HOME": temp_dir,
                "PATH": os.environ.get("PATH", ""),
            }
            if os.name == "nt" and os.environ.get("SYSTEMROOT"):
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

            # Local file:// remotes are only reachable in the test suite.
            file_allow = "always" if settings.testing else "never"
            hardening = [
                "-c", f"core.hooksPath={empty_dir}",
                "-c", f"protocol.file.allow={file_allow}",
                "-c", "protocol.ext.allow=never",
                "-c", "core.symlinks=false",
                "-c", "submodule.recurse=false",
                "-c", "core.fsmonitor=false",
            ]
            cmd = ["git", *hardening, "clone", "--depth", "1", "--single-branch", "--no-tags"]
            if url_info.ref:
                cmd.extend(["--branch", url_info.ref])
            cmd.extend(["--progress", "--", url_info.url, str(dest_dir)])

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            deadline = time.monotonic() + settings.git_clone_timeout
            try:
                while True:
                    try:
                        _out, err = proc.communicate(timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        if cancellation_flag is not None and cancellation_flag.is_set():
                            proc.kill()
                            proc.communicate()
                            raise GitImportError("git clone cancelled by user request.")
                        if time.monotonic() > deadline:
                            proc.kill()
                            proc.communicate()
                            raise GitImportError(
                                f"git clone timed out after {settings.git_clone_timeout} seconds."
                            )
            finally:
                if proc.poll() is None:
                    proc.kill()
            if proc.returncode != 0:
                raise GitImportError(f"git clone failed: {(err or '').strip()[-2000:]}")

            # Remove .git/hooks if any
            hooks_dir = dest_dir / ".git" / "hooks"
            if hooks_dir.exists():
                shutil.rmtree(hooks_dir, ignore_errors=True)

            # Record commit sha (same hardening: no hooks, no fsmonitor)
            sha_res = subprocess.run(
                ["git", *hardening, "rev-parse", "HEAD"],
                cwd=str(dest_dir),
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            commit_sha = sha_res.stdout.strip().lower() if sha_res.returncode == 0 else ""
            if commit_sha and not _SHA_REGEX.match(commit_sha):
                commit_sha = ""
            return commit_sha

    def _check_git_version(self) -> None:
        """Verify host git is >= 2.45.1."""
        try:
            res = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
            out = res.stdout.strip()
            # e.g. "git version 2.52.0.windows.1"
            parts = out.replace("git version", "").strip().split(".")
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2].split()[0])
            min_parts = [int(p) for p in settings.git_min_version.split(".")]
            if (major, minor, patch) < tuple(min_parts):
                raise GitImportError(
                    f"Installed git version ({out}) is older than minimum required {settings.git_min_version}."
                )
        except (subprocess.SubprocessError, ValueError, IndexError) as exc:
            if isinstance(exc, GitImportError):
                raise
            logger.warning("Could not parse git version: %s", exc)

    def _sanitize_extracted_tree(self, dest_dir: Path) -> None:
        """Scan directory and refuse / remove any escaping symlinks."""
        resolved_root = dest_dir.resolve()
        for root, dirs, files in os.walk(dest_dir, followlinks=False):
            for entry in list(dirs) + list(files):
                p = Path(root) / entry
                if p.is_symlink():
                    try:
                        target = p.resolve()
                        if not target.is_relative_to(resolved_root):
                            p.unlink(missing_ok=True)
                            raise GitImportError(f"Symlink escapes repository root: {entry} -> {target}")
                    except (ValueError, OSError) as exc:
                        p.unlink(missing_ok=True)
                        raise GitImportError(f"Symlink escapes repository root: {exc}") from exc

    def _check_limits(self, dest_dir: Path) -> tuple[int, int]:
        """Enforce file-count and total size caps."""
        file_count = 0
        total_size = 0
        max_bytes = settings.git_max_repo_mb * 1024 * 1024

        for root, _, files in os.walk(dest_dir):
            file_count += len(files)
            if file_count > settings.git_max_files:
                raise GitImportError(f"File count exceeds maximum allowed ({settings.git_max_files}).")

            for f in files:
                fp = Path(root) / f
                try:
                    size = fp.stat().st_size
                    total_size += size
                    if total_size > max_bytes:
                        raise GitImportError(
                            f"Extracted repository size exceeds limit ({settings.git_max_repo_mb} MB)."
                        )
                except OSError:
                    pass

        return file_count, total_size

    def _run_import_prechecks(self, dest_dir: Path) -> list[str]:
        """Perform static pre-checks card inspection (FEATURES.md F2)."""
        notes: list[str] = []

        # 1. Flag install scripts and .pth files
        for root, _, files in os.walk(dest_dir):
            rel_root = Path(root).relative_to(dest_dir)
            if ".git" in rel_root.parts:
                continue

            for f in files:
                f_lower = f.lower()
                fp = Path(root) / f

                if f_lower in ("setup.py", "setup.cfg"):
                    notes.append(f"Install script detected: {rel_root / f}")
                elif f_lower.endswith(".pth"):
                    notes.append(f"Python path configuration file detected: {rel_root / f}")

                # 2. Suspected secrets
                for sec in _SECRET_PATTERNS:
                    if sec in f_lower:
                        notes.append(f"Suspected credential or configuration file: {rel_root / f}")
                        break

                # 3. Binaries > 5 MB
                try:
                    if fp.stat().st_size > 5 * 1024 * 1024:
                        size_mb = fp.stat().st_size / (1024 * 1024)
                        notes.append(f"Large binary file detected (> 5 MB): {rel_root / f} ({size_mb:.1f} MB)")
                except OSError:
                    pass

        # 4. Agent / editor hooks
        for hook in (".claude", ".vscode", ".github/workflows"):
            hook_path = dest_dir / hook
            if hook_path.exists():
                notes.append(f"Editor/automation hook folder detected: {hook}")

        return notes

    def _discover_monorepo_candidates(self, dest_dir: Path, max_depth: int = 4) -> list[dict]:
        """Discover candidate FastAPI applications in subdirectories up to max_depth."""
        candidates = []
        dest_resolved = dest_dir.resolve()

        for root, dirs, files in os.walk(dest_dir):
            rel_path = Path(root).resolve().relative_to(dest_resolved)
            if len(rel_path.parts) > max_depth or ".git" in rel_path.parts:
                continue

            for f in files:
                if f.endswith(".py"):
                    fp = Path(root) / f
                    try:
                        if fp.stat().st_size <= 1024 * 1024:
                            content = fp.read_text(encoding="utf-8", errors="replace")
                            if _ast_has_fastapi_instance(content):
                                rel_subdir = str(rel_path) if str(rel_path) != "." else ""
                                rel_entry = str(fp.relative_to(Path(root)))
                                has_dep = (
                                    (Path(root) / "requirements.txt").exists()
                                    or (Path(root) / "pyproject.toml").exists()
                                )
                                candidates.append({
                                    "subdir": rel_subdir,
                                    "entry_point": rel_entry,
                                    "has_dep_file": has_dep,
                                })
                    except Exception:
                        pass

        return candidates


def build_project_file_tree(
    project_root: Path,
    max_depth: int = 3,
    max_nodes: int = 2000,
) -> dict[str, Any]:
    """
    Build a safe, read-only file tree representation of project structure.
    Capped at max_nodes. NEVER returns file contents.
    """
    nodes_count = 0

    def _build_node(path: Path, current_depth: int) -> dict[str, Any] | None:
        nonlocal nodes_count
        if nodes_count >= max_nodes:
            return None

        nodes_count += 1
        is_dir = path.is_dir()
        size = 0
        try:
            if not is_dir:
                size = path.stat().st_size
        except OSError:
            pass

        node: dict[str, Any] = {
            "name": path.name,
            "type": "directory" if is_dir else "file",
            "size": size,
        }

        if is_dir and current_depth < max_depth:
            children = []
            try:
                entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                for child in entries:
                    if child.name.startswith(".git"):
                        continue
                    child_node = _build_node(child, current_depth + 1)
                    if child_node is not None:
                        children.append(child_node)
            except OSError:
                pass
            node["children"] = children

        return node

    tree = _build_node(project_root, 0)
    return tree or {"name": project_root.name, "type": "directory", "size": 0, "children": []}
