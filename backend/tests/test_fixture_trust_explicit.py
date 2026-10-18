"""
D5: host-execution trust must come from explicit, database-derived inputs only —
never from files on disk next to repository content.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.targets.handle import TargetAccessForbiddenError, TrustedFixtureTargetHandle

FIXTURES = Path(settings.trusted_fixtures_root)


def test_repo_shipped_marker_grants_no_trust(tmp_path: Path):
    """A repository that ships `.source_path` pointing at the fixtures root gains nothing."""
    clone = tmp_path / "workspaces" / "imports" / "p1" / "source"
    nested = clone / "app"
    nested.mkdir(parents=True)
    (nested / "main.py").write_text("raise SystemExit('must never import')\n")
    marker_target = str(FIXTURES / "vulnerable_fastapi_app")
    for d in (clone, nested, clone.parent):
        (d / ".source_path").write_text(marker_target)

    for path in (clone, nested, nested / "main.py"):
        with pytest.raises(TargetAccessForbiddenError):
            TrustedFixtureTargetHandle(workspace_dir=path)


def test_explicit_db_source_trusts_only_inside_own_workspace_root(tmp_path: Path):
    project_root = tmp_path / "workspaces" / "pid"
    mod_ws = project_root / "modified_workspace"
    mod_ws.mkdir(parents=True)
    fixture_src = FIXTURES / "vulnerable_fastapi_app"

    # Allowed: DB says fixture origin, workspace is this project's own.
    TrustedFixtureTargetHandle(
        workspace_dir=mod_ws, trusted_source_path=fixture_src, project_workspace_root=project_root
    )
    # Refused: a workspace outside the project's root, even with a fixture source.
    other = tmp_path / "elsewhere"
    other.mkdir()
    with pytest.raises(TargetAccessForbiddenError):
        TrustedFixtureTargetHandle(
            workspace_dir=other, trusted_source_path=fixture_src, project_workspace_root=project_root
        )
    # Refused: a non-fixture DB source.
    with pytest.raises(TargetAccessForbiddenError):
        TrustedFixtureTargetHandle(
            workspace_dir=mod_ws, trusted_source_path=tmp_path, project_workspace_root=project_root
        )
