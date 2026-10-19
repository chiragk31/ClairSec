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
import re
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
    dep_file, dependencies = _parse_dependencies(path, errors, entry_point)

    is_valid = entry_point is not None
    # Without a manifest the sandbox build infers dependencies from imports.
    isolation_ready = is_valid

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

_MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB per file - avoid reading huge generated files
_MAX_PY_FILES = 3000               # scan at most this many .py files (junk dirs are pruned first)

# Folders that never contain the project's own app: virtualenvs, installed packages,
# frontends, build output, caches. Walking into them used to exhaust the scan budget
# (a committed venv alone has thousands of .py files, several of which call FastAPI()).
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox",
    "venv", ".venv", "env", ".env", "virtualenv", "site-packages", "dist-packages", "lib64",
    "node_modules", "bower_components", "dist", "build", ".eggs", "htmlcov", "coverage",
    ".idea", ".vscode", "migrations", "alembic",
}
_ENTRY_NAMES = {"main.py": 40, "app.py": 35, "asgi.py": 35, "server.py": 30, "api.py": 25,
                "application.py": 25, "run.py": 15}
_TESTISH = ("test", "tests", "testing", "example", "examples", "docs", "doc", "sample", "samples", "scripts")


def _is_virtualenv(dirpath: Path) -> bool:
    return (dirpath / "pyvenv.cfg").is_file()


def _iter_project_files(root: Path, suffixes: tuple[str, ...] = (".py",)):
    """Walk the project, pruning virtualenvs / vendored / build folders."""
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if d.lower() not in _SKIP_DIRS and not d.endswith(".egg-info") and not _is_virtualenv(dp / d)
        )
        for f in sorted(filenames):
            if f.endswith(suffixes):
                yield dp / f


def _score_entry(rel: str, source: str) -> int:
    parts = rel.lower().split("/")
    name = parts[-1]
    score = _ENTRY_NAMES.get(name, 0)
    score -= 6 * (len(parts) - 1)                       # shallower is more likely the app
    if any(p in _TESTISH for p in parts[:-1]) or name.startswith("test_") or name == "conftest.py":
        score -= 60                                     # tests/examples build throwaway apps
    if re.search(r"^\s*app\s*=\s*(fastapi\.)?FastAPI\(", source, re.M):
        score += 25                                     # conventional module-level `app = FastAPI(...)`
    if "uvicorn.run(" in source or "__main__" in source:
        score += 10
    if "include_router(" in source:
        score += 10                                     # the real app wires routers together
    return score


def _find_fastapi_entry(root: Path, errors: list[str]) -> str | None:
    """
    Find the project's FastAPI application file, statically (code is never executed).

    Every file that instantiates FastAPI() is a candidate; candidates are ranked so the
    real app wins over tests, examples and helper apps, and junk folders (virtualenvs,
    site-packages, node_modules, build output) are never scanned.
    """
    scanned = 0
    candidates: list[tuple[int, str]] = []
    for py_file in _iter_project_files(root):
        if scanned >= _MAX_PY_FILES:
            errors.append(
                f"Scanned {_MAX_PY_FILES} Python files; the entry point was chosen from those. "
                "If it is wrong, import the app's sub-folder instead."
            )
            break
        try:
            if py_file.stat().st_size > _MAX_FILE_SIZE:
                continue
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.debug("Could not read %s: %s", py_file, exc)
            continue
        scanned += 1
        if "FastAPI" not in source:
            continue
        if _ast_has_fastapi_instance(source):
            rel = py_file.relative_to(root).as_posix()
            candidates.append((_score_entry(rel, source), rel))

    if candidates:
        candidates.sort(key=lambda c: (-c[0], len(c[1]), c[1]))
        best = candidates[0][1]
        logger.info(
            "Selected entry point '%s' in %s from %d candidate(s): %s",
            best, root, len(candidates), [c[1] for c in candidates[:5]],
            extra={"event": "entrypoint.selected"},
        )
        return best

    logger.warning(
        "No FastAPI entry point found in %s after scanning %d Python file(s).",
        root, scanned, extra={"event": "entrypoint.not_found"},
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


_REQ_NAME = re.compile(r"^requirements([-_.][\w.-]+)?\.txt$", re.I)
_REQ_PREFERENCE = ("requirements.txt", "requirements-prod.txt", "requirements_prod.txt",
                   "requirements-base.txt", "requirements/base.txt", "requirements/prod.txt",
                   "requirements/production.txt", "requirements/main.txt")


def _req_rank(rel: str) -> tuple[int, int, int, str]:
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    pref = next((i for i, p in enumerate(_REQ_PREFERENCE) if low.endswith(p)), len(_REQ_PREFERENCE))
    dev_penalty = 1 if any(k in name for k in ("dev", "test", "lint", "doc", "ci")) else 0
    return (dev_penalty, pref, low.count("/"), low)


def _pyproject_is_installable(path: Path) -> bool:
    """A pyproject.toml that only configures tools (ruff, black...) cannot be pip-installed."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "[project]" in text or "[tool.poetry]" in text or "[build-system]" in text


def _parse_dependencies(
    root: Path, errors: list[str], entry_point: str | None = None
) -> tuple[str | None, list[str]]:
    """
    Find the dependency manifest that belongs to the app and parse dependency names.

    Search order:
      1. the entry point's folder, then each parent folder up to the project root
         (requirements.txt, installable pyproject.toml, setup.py);
      2. requirements variants anywhere in the project (requirements-prod.txt,
         requirements/base.txt, ...), preferring non-dev files and shallow paths;
      3. any installable pyproject.toml / setup.py.
    Virtualenvs and vendored folders are never searched. Returns (relative_path, deps).
    """
    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    def found(path: Path) -> tuple[str, list[str]]:
        r = rel(path)
        if path.name == "pyproject.toml":
            deps = _parse_pyproject_toml(path, errors)
        elif path.name == "setup.py":
            deps = []
        else:
            deps = _parse_requirements_txt(path, errors)
        logger.info("Found dependency file '%s' with %d package(s)", r, len(deps),
                    extra={"event": "dependency.file.found"})
        return r, deps

    # 1. Walk up from the entry point's folder to the project root.
    folder = (root / entry_point).parent if entry_point else root
    while True:
        for name in ("requirements.txt", "pyproject.toml", "setup.py"):
            cand = folder / name
            if cand.is_file() and (name != "pyproject.toml" or _pyproject_is_installable(cand)):
                return found(cand)
        if folder == root or root not in folder.parents:
            break
        folder = folder.parent

    # 2./3. Anywhere in the project (pruned walk, max depth 5).
    reqs: list[Path] = []
    others: list[Path] = []
    for f in _iter_project_files(root, suffixes=(".txt", ".toml", ".py")):
        r = rel(f)
        if r.count("/") > 4:
            continue
        if _REQ_NAME.match(f.name) or (f.parent.name.lower() == "requirements" and f.suffix == ".txt"):
            reqs.append(f)
        elif f.name == "setup.py" or (f.name == "pyproject.toml" and _pyproject_is_installable(f)):
            others.append(f)
    if reqs:
        return found(sorted(reqs, key=lambda p: _req_rank(rel(p)))[0])
    if others:
        return found(sorted(others, key=lambda p: (rel(p).count("/"), rel(p)))[0])

    logger.info(
        "No dependency manifest in %s; dependencies will be inferred from imports when the sandbox is built",
        root, extra={"event": "dependency.file.inferred"},
    )
    errors.append(
        "No requirements.txt / pyproject.toml / setup.py found. ClairSec will infer the dependencies "
        "from the project's imports when it builds the sandbox (some optional packages may be missed)."
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
