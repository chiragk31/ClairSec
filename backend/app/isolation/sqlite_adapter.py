"""
SQLite adapter for isolated container execution.

Enables compatible SQLite-backed benchmark and real-world applications to run
successfully inside ClairSec's hardened, read-only container root filesystem
(THREAT_MODEL C3.1, C3.2).

SECURITY INVARIANTS:
  - Container rootfs remains strictly read-only (read_only=True).
  - Writable storage is container-local, in-memory tmpfs (/tmp/clairsec-data) only.
  - Non-root user (appuser, uid 10001) owns and writes to /tmp/clairsec-data.
  - Original uploaded source files are NEVER modified; adaptations occur strictly
    within the isolated scan_workspace copy.
  - All file inspection is static (AST and defensive pattern matching); target code
    is never imported or executed on the host.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Standard container-local writable directory for SQLite data
SQLITE_DATA_DIR = "/tmp/clairsec-data"

# Extensions identifying SQLite database files
SQLITE_EXTENSIONS = (".db", ".sqlite", ".sqlite3")

# Common variable names used for SQLite database paths
_DB_PATH_VAR_NAMES = {
    "DB_PATH",
    "DATABASE_PATH",
    "SQLITE_PATH",
    "SQLITE_DB",
    "DATABASE_FILE",
    "DB_FILE",
    "SQLITE_DATABASE",
}

# Directories to skip when scanning workspace
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "venv",
    ".venv",
    "env",
    ".env",
    "build",
    "dist",
}

_SITECUSTOMIZE_TEMPLATE = '''\
"""
sitecustomize.py — ClairSec container runtime SQLite helper.
Auto-loaded by Python on startup inside the isolated container.

Ensures /tmp/clairsec-data exists, copies pre-existing database templates
from /app if not already present, and transparently redirects sqlite3
connections targeting read-only /app paths to /tmp/clairsec-data.
"""
import os
import shutil
import sqlite3

_DATA_DIR = os.environ.get("SQLITE_DATA_DIR", "/tmp/clairsec-data")

def _init_storage() -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
    except Exception:
        pass

    # If database files exist in /app, copy them to _DATA_DIR if not yet present
    app_dir = "/app"
    if os.path.isdir(app_dir):
        for root, dirs, files in os.walk(app_dir):
            if any(skip in root for skip in ("venv", ".venv", ".git", "__pycache__")):
                continue
            for f in files:
                if f.endswith((".db", ".sqlite", ".sqlite3")):
                    src = os.path.join(root, f)
                    dst = os.path.join(_DATA_DIR, f)
                    if not os.path.exists(dst):
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass

_init_storage()

# Hook sqlite3.connect to transparently redirect read-only /app or relative paths
_orig_connect = sqlite3.connect

def _clairsec_connect(database, *args, **kwargs):
    if isinstance(database, (str, bytes, os.PathLike)):
        db_str = os.fspath(database)
        if isinstance(db_str, bytes):
            db_str = db_str.decode("utf-8", errors="replace")
        if db_str.startswith("/tmp"):
            try:
                os.makedirs(os.path.dirname(db_str), exist_ok=True)
            except Exception:
                pass
            return _orig_connect(database, *args, **kwargs)
        if (
            db_str != ":memory:"
            and not db_str.startswith("file:")
            and not db_str.startswith(":")
        ):
            basename = os.path.basename(db_str)
            if basename:
                _init_storage()
                target = os.path.join(_DATA_DIR, basename)
                return _orig_connect(target, *args, **kwargs)
    return _orig_connect(database, *args, **kwargs)

sqlite3.connect = _clairsec_connect
'''


@dataclass
class SQLiteDetectionResult:
    """Outcome of SQLite detection and adaptation in a scan workspace."""

    detected: bool = False
    compatible: bool = True
    incompatibility_reason: str | None = None
    db_files: list[str] = field(default_factory=list)
    adapted_files: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)


def _find_existing_db_files(workspace_path: Path) -> list[str]:
    """Find any .db, .sqlite, .sqlite3 files in the workspace (excluding venv/git)."""
    db_files: list[str] = []
    try:
        for p in workspace_path.rglob("*"):
            if p.is_file() and p.suffix.lower() in SQLITE_EXTENSIONS:
                parts = p.relative_to(workspace_path).parts
                if not any(part in _SKIP_DIRS for part in parts):
                    db_files.append(p.name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Error scanning for db files: %s", exc)
    return sorted(set(db_files))


def _extract_db_filename_from_assignment(val_node: ast.AST) -> str | None:
    """Extract a database filename from an AST value node if discernible."""
    if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
        val = val_node.value
        if any(val.endswith(ext) for ext in SQLITE_EXTENSIONS):
            return Path(val).name
        if "sqlite:///" in val:
            path_part = val.split("sqlite:///")[-1]
            return Path(path_part).name

    # Check for os.path.join(..., "something.db")
    if isinstance(val_node, ast.Call):
        for arg in reversed(val_node.args):
            if (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and any(arg.value.endswith(ext) for ext in SQLITE_EXTENSIONS)
            ):
                return arg.value

    return None


def _check_uses_environ(node: ast.AST) -> bool:
    """Return True if node references os.environ or os.getenv."""
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr in ("environ", "getenv"):
            return True
        if isinstance(n, ast.Name) and n.id in ("environ", "getenv"):
            return True
    return False


def adapt_workspace_for_sqlite(workspace_path: Path) -> SQLiteDetectionResult:
    """
    Inspect scan_workspace for SQLite usage and configure container-local storage.

    Steps:
      1. Discover any existing .db files and Python files referencing SQLite.
      2. If SQLite is detected:
         a. Check if already configurable via environment variables.
         b. If hardcoded to a relative/local path, perform minimal targeted adaptation
            in the scan_workspace file to read from environment variable with fallback
            to /tmp/clairsec-data/<dbname>.
         c. Write sitecustomize.py into scan_workspace to ensure /tmp/clairsec-data
            exists, copies pre-existing data templates, and transparently redirects
            direct sqlite3.connect calls.
         d. Provide environment variables for container startup.
      3. If an incompatible configuration is encountered, mark compatible=False
         with an informative reason.

    SECURITY:
      - workspace_path MUST be a scan_workspace directory, NEVER the original source.
      - Target files are validated with ast.parse before and after changes.
    """
    workspace = Path(workspace_path).resolve()
    result = SQLiteDetectionResult()

    if not workspace.is_dir():
        return result

    existing_db_files = _find_existing_db_files(workspace)
    result.db_files = existing_db_files

    sqlite_referenced = bool(existing_db_files)
    detected_db_names: set[str] = set(existing_db_files)
    files_to_adapt: list[tuple[Path, str, str, str]] = []  # (path, var_name, old_line, db_filename)

    # Scan python files
    py_files = sorted(workspace.rglob("*.py"))
    for py_file in py_files:
        rel_parts = py_file.relative_to(workspace).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.debug("Could not read %s: %s", py_file, exc)
            continue

        if "sqlite" in content.lower() or any(ext in content.lower() for ext in SQLITE_EXTENSIONS):
            sqlite_referenced = True

        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            logger.debug("Syntax error parsing %s during SQLite detection: %s", py_file, exc)
            continue

        # Look for module-level or class-level assignments to database path variables
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        if var_name in _DB_PATH_VAR_NAMES or "DATABASE_URL" in var_name:
                            sqlite_referenced = True
                            db_name = _extract_db_filename_from_assignment(node.value)
                            if db_name:
                                detected_db_names.add(db_name)

                            already_uses_env = _check_uses_environ(node.value)
                            if not already_uses_env:
                                # Candidate for targeted adaptation
                                fallback_db = db_name or (existing_db_files[0] if existing_db_files else "app.db")
                                lines = content.splitlines()
                                lineno = node.lineno
                                if 1 <= lineno <= len(lines):
                                    old_line = lines[lineno - 1]
                                    files_to_adapt.append((py_file, var_name, old_line, fallback_db))

    logger.info(
        "Scanning workspace %s for SQLite references",
        workspace,
        extra={"event": "sqlite.adaptation.started"},
    )

    if not sqlite_referenced:
        logger.debug(
            "No SQLite usage detected in workspace %s",
            workspace,
            extra={"event": "sqlite.adaptation.skipped"},
        )
        return result

    result.detected = True

    # Determine primary database filename
    primary_db = "app.db"
    if detected_db_names:
        primary_db = min(detected_db_names)

    logger.info(
        "SQLite usage detected in workspace %s: db_files=%s, primary_db=%s, candidates_to_adapt=%d",
        workspace,
        existing_db_files,
        primary_db,
        len(files_to_adapt),
        extra={"event": "sqlite.detected"},
    )

    # Prepare environment variables to be passed to target container
    result.env_vars = {
        "SQLITE_DATA_DIR": SQLITE_DATA_DIR,
        "DB_PATH": f"{SQLITE_DATA_DIR}/{primary_db}",
        "CLAIRSEC_DB_PATH": f"{SQLITE_DATA_DIR}/{primary_db}",
        "DATABASE_URL": f"sqlite:///{SQLITE_DATA_DIR}/{primary_db}",
        "PYTHONPATH": "/app",
    }

    # Perform minimal, targeted adaptation on detected configuration assignments
    for py_file, var_name, old_line, db_name in files_to_adapt:
        try:
            file_text = py_file.read_text(encoding="utf-8")
            target_path = f"{SQLITE_DATA_DIR}/{db_name}"

            if "DATABASE_URL" in var_name:
                replacement_line = (
                    f'{var_name} = os.environ.get("{var_name}", '
                    f'f"sqlite:///{target_path}")'
                )
            else:
                replacement_line = (
                    f'{var_name} = os.environ.get("CLAIRSEC_DB_PATH", '
                    f'os.environ.get("{var_name}", "{target_path}"))'
                )

            # Ensure 'os' is imported if we introduce os.environ
            new_text = file_text
            if old_line in new_text:
                new_text = new_text.replace(old_line, replacement_line, 1)
                # Verify import os is present
                if "import os" not in new_text:
                    new_text = f"import os\n{new_text}"

                # Verify adapted code parses cleanly
                ast.parse(new_text)

                py_file.write_text(new_text, encoding="utf-8")
                rel_path = str(py_file.relative_to(workspace))
                result.adapted_files.append(rel_path)
                logger.info(
                    "Adapted SQLite config in %s: '%s' → '%s'",
                    rel_path,
                    old_line.strip(),
                    replacement_line,
                    extra={"event": "sqlite.file.adapted"},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not safely adapt SQLite configuration in %s: %s",
                py_file,
                exc,
                extra={"event": "sqlite.adaptation.incompatible"},
            )
            result.compatible = False
            result.incompatibility_reason = (
                f"Failed to adapt SQLite database path in {py_file.name}: {exc}"
            )
            return result

    # Install sitecustomize.py in the workspace root
    try:
        sitecustomize_path = workspace / "sitecustomize.py"
        sitecustomize_path.write_text(_SITECUSTOMIZE_TEMPLATE, encoding="utf-8")
        logger.info(
            "Installed ClairSec SQLite runtime helper in %s",
            sitecustomize_path,
            extra={"event": "sqlite.helper.installed"},
        )
    except OSError as exc:
        logger.warning(
            "Could not write sitecustomize.py in workspace: %s",
            exc,
            extra={"event": "sqlite.adaptation.incompatible"},
        )
        result.compatible = False
        result.incompatibility_reason = f"Could not install runtime SQLite helper: {exc}"
        return result

    logger.info(
        "SQLite adaptation succeeded for workspace %s (adapted=%s, env_vars=%s)",
        workspace,
        result.adapted_files,
        list(result.env_vars.keys()),
        extra={"event": "sqlite.adaptation.succeeded"},
    )
    return result
