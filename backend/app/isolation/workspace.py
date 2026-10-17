"""
Workspace manager — manages the scan workspace directory tree.

Directory convention (established in Phase 3, extended in Phase 7):

    {workspace_root}/
    └── {project_id}/
        ├── scan_workspace/     ← copy of original source (this phase)
        └── modified_workspace/ ← Fixer's patched copy (Phase 7)

SECURITY:
  - The original source_path is NEVER modified by this module.
  - All writes go to {workspace_root}/{project_id}/scan_workspace/.
  - We do not follow symlinks outside the workspace during copy (dirs_exist_ok=False
    for new projects; we fail if it already exists to prevent double-import).
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.core.config import settings
from app.isolation.errors import IsolationError

logger = logging.getLogger(__name__)

SCAN_WORKSPACE_SUBDIR = "scan_workspace"
MODIFIED_WORKSPACE_SUBDIR = "modified_workspace"  # reserved for Phase 7


class WorkspaceManager:
    def __init__(self, workspace_root: str | None = None) -> None:
        root = workspace_root or settings.workspace_root
        self._root = Path(root).expanduser().resolve()

    def get_project_root(self, project_id: str) -> Path:
        """Return the per-project workspace root (does not guarantee it exists)."""
        return self._root / project_id

    def get_scan_workspace_path(self, project_id: str) -> Path:
        """Return the scan_workspace/ path for this project."""
        return self.get_project_root(project_id) / SCAN_WORKSPACE_SUBDIR

    def get_modified_workspace_path(self, project_id: str) -> Path:
        """Return the modified_workspace/ path for this project (Phase 7)."""
        return self.get_project_root(project_id) / MODIFIED_WORKSPACE_SUBDIR

    def create_modified_workspace(self, project_id: str, reset: bool = True) -> Path:
        """
        Populate modified_workspace from scan_workspace (PHASES.md Phase 7).
        SECURITY: scan_workspace is strictly read-only and never modified.
        Copies with symlinks=False.

        If reset=True and dest exists, cleans up stale directory first.
        Validates copied contents against scan_workspace to ensure completeness.
        """
        scan_ws = self.get_scan_workspace_path(project_id)
        dest = self.get_modified_workspace_path(project_id)

        logger.info(
            "Creating modified workspace for project %s (from %s to %s, reset=%s)",
            project_id[:8],
            scan_ws,
            dest,
            reset,
            extra={"event": "workspace.modified.create.started"},
        )

        if not scan_ws.exists():
            logger.error(
                "Cannot create modified workspace: scan_workspace does not exist at %s",
                scan_ws,
                extra={"event": "workspace.modified.create.failed"},
            )
            raise IsolationError(
                f"Cannot create modified workspace: scan_workspace does not exist for project {project_id}: {scan_ws}"
            )

        if dest.exists():
            if not reset:
                # Validate that existing dest is complete and not empty/corrupted
                scan_files = {p.name for p in scan_ws.iterdir() if not p.name.startswith(".")}
                dest_files = {p.name for p in dest.iterdir() if not p.name.startswith(".")}
                missing = scan_files - dest_files
                if not missing:
                    logger.info(
                        "Modified workspace already exists and is complete for project %s at %s",
                        project_id[:8],
                        dest,
                        extra={"event": "workspace.modified.create.succeeded"},
                    )
                    return dest
                logger.warning(
                    "Existing modified workspace for project %s is incomplete (missing %s); refreshing from scan workspace.",
                    project_id[:8],
                    sorted(missing),
                )
            # Remove stale or incomplete modified workspace
            shutil.rmtree(dest, ignore_errors=True)

        t0 = time.perf_counter()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                src=scan_ws,
                dst=dest,
                symlinks=False,
                ignore_dangling_symlinks=True,
                dirs_exist_ok=False,
            )

            # Validate that the copy succeeded and contains expected files
            if not dest.exists():
                raise IsolationError(f"Modified workspace destination does not exist after copy: {dest}")

            scan_files = {p.name for p in scan_ws.iterdir() if not p.name.startswith(".")}
            dest_files = {p.name for p in dest.iterdir() if not p.name.startswith(".")}
            missing = scan_files - dest_files
            if missing:
                raise IsolationError(
                    f"Modified workspace copy incomplete for project {project_id}: "
                    f"missing expected files {sorted(missing)} in {dest}"
                )

            elapsed = time.perf_counter() - t0
            logger.info(
                "Created modified workspace for project %s in %.3fs: %s → %s",
                project_id[:8],
                elapsed,
                scan_ws,
                dest,
                extra={"event": "workspace.modified.create.succeeded"},
            )
            return dest
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Failed to create modified workspace for project %s after %.3fs: %s",
                project_id[:8],
                elapsed,
                exc,
                extra={"event": "workspace.modified.create.failed"},
            )
            raise IsolationError(
                f"Failed to create modified workspace for project {project_id}: {exc}"
            ) from exc

    def create_scan_workspace(self, project_id: str, source_path: str) -> Path:
        """
        Copy the original project into a fresh scan_workspace directory.

        SECURITY: source_path is treated as read-only. We copy using shutil.copytree
        with follow_symlinks=False to avoid following symlinks out of the source tree.

        Raises IsolationError if the workspace already exists or copy fails.
        """
        source = Path(source_path).resolve()
        dest = self.get_scan_workspace_path(project_id)

        logger.info(
            "Creating scan workspace for project %s from source '%s' (target: %s)",
            project_id[:8],
            source,
            dest,
            extra={"event": "workspace.scan.create.started"},
        )

        if dest.exists():
            logger.error(
                "Scan workspace already exists for project %s at %s",
                project_id[:8],
                dest,
                extra={"event": "workspace.scan.create.failed"},
            )
            raise IsolationError(
                f"Scan workspace already exists for project {project_id}: {dest}. "
                "Call cleanup_workspace() before re-importing."
            )

        t0 = time.perf_counter()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                src=source,
                dst=dest,
                symlinks=False,        # don't follow symlinks — treat source as untrusted
                ignore_dangling_symlinks=True,
                dirs_exist_ok=False,
            )
            elapsed = time.perf_counter() - t0
            logger.info(
                "Created scan workspace for project %s in %.3fs: %s → %s",
                project_id[:8],
                elapsed,
                source,
                dest,
                extra={"event": "workspace.scan.create.succeeded"},
            )
            return dest
        except shutil.Error as exc:
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Failed to copy project source into workspace for project %s after %.3fs: %s",
                project_id[:8],
                elapsed,
                exc,
                extra={"event": "workspace.scan.create.failed"},
            )
            raise IsolationError(
                f"Failed to copy project source into workspace: {exc}"
            ) from exc
        except OSError as exc:
            elapsed = time.perf_counter() - t0
            logger.exception(
                "Filesystem error creating workspace for project %s after %.3fs: %s",
                project_id[:8],
                elapsed,
                exc,
                extra={"event": "workspace.scan.create.failed"},
            )
            raise IsolationError(
                f"Filesystem error creating workspace: {exc}"
            ) from exc

    def cleanup_workspace(self, project_id: str) -> None:
        """
        Remove the entire per-project workspace directory (both scan and modified).
        Safe to call even if the directory does not exist.
        """
        project_root = self.get_project_root(project_id)
        logger.info(
            "Cleaning up workspace for project %s at %s",
            project_id[:8],
            project_root,
            extra={"event": "workspace.cleanup.started"},
        )
        if project_root.exists():
            try:
                shutil.rmtree(project_root)
                logger.info(
                    "Removed workspace for project %s: %s",
                    project_id[:8],
                    project_root,
                    extra={"event": "workspace.cleanup.succeeded"},
                )
            except OSError as exc:
                # Log but do not raise — cleanup should be best-effort
                logger.exception(
                    "Failed to remove workspace for project %s at %s: %s",
                    project_id[:8],
                    project_root,
                    exc,
                    extra={"event": "workspace.cleanup.failed"},
                )
        else:
            logger.debug(
                "No workspace directory exists to remove for project %s (%s)",
                project_id[:8],
                project_root,
                extra={"event": "workspace.cleanup.skipped"},
            )
