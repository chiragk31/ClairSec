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
    logger.info(
        "Validating project at '%s' (is_absolute=%s)",
        project_path,
        path.is_absolute(),
        extra={"event": "project.validation.started"},
    )

    # --- Basic directory checks ---
    if not path.exists():
        parent_entries: list[str] = []
        if path.parent.exists() and path.parent.is_dir():
            try:
                parent_entries = [p.name for p in sorted(path.parent.iterdir())[:20]]
            except Exception:
                pass
        logger.error(
            "Project path does not exist: '%s'. Parent '%s' entries (%d shown): %s",
            project_path,
            path.parent,
            len(parent_entries),
            parent_entries,
            extra={"event": "project.validation.failed"},
        )
        return ValidationResult(
            is_valid=False,
            errors=[f"Path does not exist: {project_path}"],
        )

    if not path.is_dir():
        logger.error(
            "Project path is not a directory: '%s'",
            project_path,
            extra={"event": "project.validation.failed"},
        )
        return ValidationResult(
            is_valid=False,
            errors=[f"Path is not a directory: {project_path}"],
        )

    try:
        entries = sorted(path.iterdir())
        sample_entries = [p.name for p in entries[:20]]
        logger.debug(
            "Directory '%s' exists with %d entries (first %d: %s)",
            path,
            len(entries),
            len(sample_entries),
            sample_entries,
            extra={"event": "project.directory.inspected"},
        )
    except Exception as exc:
        logger.debug("Could not list entries in %s: %s", path, exc)

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

    if is_valid:
        logger.info(
            "Project validation succeeded for '%s' (entry_point=%s, dep_file=%s, dependencies=%d, isolation_ready=%s)",
            project_path,
            entry_point,
            dep_file,
            len(dependencies),
            isolation_ready,
            extra={"event": "project.validation.succeeded"},
        )
    else:
        logger.warning(
            "Project validation failed for '%s': %s",
            project_path,
            errors,
            extra={"event": "project.validation.failed"},
        )

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
    logger.debug(
        "Checking %d candidate Python file(s) for FastAPI instance in %s",
        len(py_files),
        root,
        extra={"event": "entrypoint.candidates.checked"},
    )
    scanned = 0
    scanned_candidates: list[str] = []

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
            rel_candidate = py_file.relative_to(root).as_posix()
            scanned_candidates.append(rel_candidate)

            if _ast_has_fastapi_instance(source):
                logger.info(
                    "Selected entry point '%s' in %s (FastAPI instance detected)",
                    rel_candidate,
                    root,
                    extra={"event": "entrypoint.selected"},
                )
                return rel_candidate

        except OSError as exc:
            logger.debug("Could not read %s: %s", py_file, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unexpected error reading %s: %s", py_file, exc)

    logger.warning(
        "No FastAPI entry point found in %s after scanning %d candidate file(s): %s. "
        "Reason: no top-level or module-level FastAPI() call found.",
        root,
        len(scanned_candidates),
        scanned_candidates[:10],
        extra={"event": "entrypoint.not_found"},
    )
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
        logger.info(
            "Found dependency file 'requirements.txt' with %d package(s)",
            len(deps),
            extra={"event": "dependency.file.found"},
        )
        return "requirements.txt", deps

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        deps = _parse_pyproject_toml(pyproject, errors)
        logger.info(
            "Found dependency file 'pyproject.toml' with %d package(s)",
            len(deps),
            extra={"event": "dependency.file.found"},
        )
        return "pyproject.toml", deps

    # Check one level deeper (e.g. src layout)
    for candidate in sorted(root.iterdir()):
        if candidate.is_dir() and not candidate.name.startswith("."):
            nested_req = candidate / "requirements.txt"
            if nested_req.exists():
                rel = nested_req.relative_to(root).as_posix()
                deps = _parse_requirements_txt(nested_req, errors)
                logger.info(
                    "Found nested dependency file '%s' with %d package(s)",
                    rel,
                    len(deps),
                    extra={"event": "dependency.file.found"},
                )
                return rel, deps

    logger.warning(
        "No dependency file found (checked requirements.txt, pyproject.toml, and immediate subdirectories in %s)",
        root,
        extra={"event": "dependency.file.missing"},
    )
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
