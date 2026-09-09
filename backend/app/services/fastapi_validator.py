"""
FastAPI project validator.

SECURITY: This module ONLY inspects files statically. It never:
  - executes any imported project code
  - imports any module from the target project
  - spawns subprocesses to run target code
  - calls eval() or exec() on target content

All file reads are treated as untrusted input and parsed defensively.
"""
from __future__ import annotations

import ast
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    is_valid: bool
    entry_point: str | None = None
    """Relative path to the file containing the FastAPI() instantiation."""
    dependency_file: str | None = None
    """Relative path to requirements.txt or pyproject.toml."""
    dependencies: list[str] = field(default_factory=list)
    isolation_ready: bool = False
    errors: list[str] = field(default_factory=list)


def validate_fastapi_project(project_path: str) -> ValidationResult:
    """
    Statically inspect a directory and determine if it looks like a FastAPI project.

    Returns a ValidationResult with findings. Never raises; errors are captured
    in ValidationResult.errors.
    """
    path = Path(project_path)

    # --- Basic directory checks ---
    if not path.exists():
        return ValidationResult(
            is_valid=False,
            errors=[f"Path does not exist: {project_path}"],
        )
    if not path.is_dir():
        return ValidationResult(
            is_valid=False,
            errors=[f"Path is not a directory: {project_path}"],
        )

    errors: list[str] = []
    entry_point: str | None = None
    dep_file: str | None = None
    dependencies: list[str] = []

    # --- Detect entry point (FastAPI() instantiation) ---
    entry_point = _find_fastapi_entry(path, errors)

    if entry_point is None:
        errors.append(
            "No FastAPI application instance found. "
            "Expected at least one .py file containing 'FastAPI()' or "
            "'FastAPI(...)' at the top level."
        )

    # --- Detect and parse dependency file ---
    dep_file, dependencies = _parse_dependencies(path, errors)

    is_valid = entry_point is not None
    isolation_ready = is_valid and dep_file is not None

    return ValidationResult(
        is_valid=is_valid,
        entry_point=entry_point,
        dependency_file=dep_file,
        dependencies=dependencies,
        isolation_ready=isolation_ready,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Internal helpers — all file reads are bounded and wrapped in try/except
# ---------------------------------------------------------------------------

_MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB per file — avoid reading huge generated files
_MAX_PY_FILES = 200                # scan at most this many .py files


def _find_fastapi_entry(root: Path, errors: list[str]) -> str | None:
    """
    Walk the directory tree and find the first .py file that instantiates FastAPI().
    Uses ast.parse for static analysis — target code is never executed.
    """
    py_files = sorted(root.rglob("*.py"))
    scanned = 0

    for py_file in py_files:
        if scanned >= _MAX_PY_FILES:
            errors.append(
                f"Scanned {_MAX_PY_FILES} Python files without finding a FastAPI "
                "instance. If your app is larger, please check the entry point manually."
            )
            break

        try:
            size = py_file.stat().st_size
            if size > _MAX_FILE_SIZE:
                continue  # skip oversized files silently

            source = py_file.read_text(encoding="utf-8", errors="replace")
            scanned += 1

            if _ast_has_fastapi_instance(source):
                return str(py_file.relative_to(root))

        except OSError as exc:
            logger.debug("Could not read %s: %s", py_file, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unexpected error reading %s: %s", py_file, exc)

    return None


def _ast_has_fastapi_instance(source: str) -> bool:
    """
    Return True if the source contains a call that looks like FastAPI(...).

    Accepts both:
      app = FastAPI()
      app = FastAPI(title="...")
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Direct call: FastAPI()
            if isinstance(func, ast.Name) and func.id == "FastAPI":
                return True
            # Attribute call: fastapi.FastAPI()
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "FastAPI"
            ):
                return True
    return False


def _parse_dependencies(
    root: Path, errors: list[str]
) -> tuple[str | None, list[str]]:
    """
    Look for requirements.txt or pyproject.toml and parse dependency names.
    Returns (relative_path, [dep_name, ...]).
    """
    # requirements.txt takes precedence if both exist
    req_txt = root / "requirements.txt"
    if req_txt.exists():
        deps = _parse_requirements_txt(req_txt, errors)
        return "requirements.txt", deps

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        deps = _parse_pyproject_toml(pyproject, errors)
        return "pyproject.toml", deps

    # Check one level deeper (e.g. src layout)
    for candidate in sorted(root.iterdir()):
        if candidate.is_dir() and not candidate.name.startswith("."):
            nested_req = candidate / "requirements.txt"
            if nested_req.exists():
                rel = str(nested_req.relative_to(root))
                deps = _parse_requirements_txt(nested_req, errors)
                return rel, deps

    errors.append(
        "No dependency file found (requirements.txt or pyproject.toml). "
        "A dependency file is needed to assess isolation readiness."
    )
    return None, []


def _parse_requirements_txt(path: Path, errors: list[str]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"Could not read requirements.txt: {exc}")
        return []

    deps: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip version specifiers: name>=x.y → name
        for sep in (">=", "<=", "!=", "~=", "==", ">", "<", "[", ";"):
            line = line.split(sep)[0].strip()
        if line:
            deps.append(line)
    return deps


def _parse_pyproject_toml(path: Path, errors: list[str]) -> list[str]:
    try:
        text = path.read_bytes()
    except OSError as exc:
        errors.append(f"Could not read pyproject.toml: {exc}")
        return []

    try:
        if sys.version_info >= (3, 11):
            import tomllib  # stdlib in 3.11+
            data = tomllib.loads(text.decode("utf-8", errors="replace"))
        else:
            import tomli  # type: ignore[import]
            data = tomli.loads(text.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Could not parse pyproject.toml: {exc}")
        return []

    # Support PEP 621 [project] dependencies and Poetry [tool.poetry] dependencies
    raw: list[str] = []
    raw.extend(data.get("project", {}).get("dependencies", []))
    raw.extend(
        data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys()
    )

    deps: list[str] = []
    for entry in raw:
        # Strip version specifiers similarly to requirements.txt
        name = str(entry)
        for sep in (">=", "<=", "!=", "~=", "==", ">", "<", "[", ";", " "):
            name = name.split(sep)[0].strip()
        if name and name.lower() != "python":
            deps.append(name)
    return deps
