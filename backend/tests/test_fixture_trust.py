"""
Tests for Fixture Trust by Containment (Audit defect A1, A6).

Exit gate requirements:
- A path like <tmp>/workspaces/<id>/source/tests/fixtures/app is NOT trusted.
- A symlink inside the fixtures root pointing outside it is NOT trusted.
- A legitimate fixture path inside settings.trusted_fixtures_root IS trusted.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from app.core.config import settings
from app.targets.handle import (
    TargetAccessForbiddenError,
    TrustedFixtureTargetHandle,
    is_trusted_fixture_path,
)


def test_untrusted_substring_fixture_path_rejected(tmp_path: Path):
    """
    Audit A1 test: A path containing 'tests' and 'fixtures' in its segments
    outside settings.trusted_fixtures_root (e.g. workspace repo source)
    must NOT be trusted.
    """
    fake_fixture = tmp_path / "workspaces" / "project1" / "source" / "tests" / "fixtures" / "app"
    fake_fixture.mkdir(parents=True)

    assert not is_trusted_fixture_path(fake_fixture), (
        f"Path {fake_fixture} was trusted merely due to substring match!"
    )


def test_symlink_escaping_fixtures_root_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Audit A1 test: A symlink inside the fixtures root pointing to a directory
    outside it must NOT be trusted.
    """
    fake_fixtures_root = tmp_path / "fixtures_root"
    fake_fixtures_root.mkdir(parents=True)
    monkeypatch.setattr(settings, "trusted_fixtures_root", fake_fixtures_root.resolve())

    # Create target outside fixtures root
    outside_target = tmp_path / "outside_secret_project"
    outside_target.mkdir(parents=True)

    # Create symlink inside fixtures root pointing outside
    symlink_path = fake_fixtures_root / "evil_symlink"
    try:
        symlink_path.symlink_to(outside_target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks not supported in this environment: {exc}")

    assert not is_trusted_fixture_path(symlink_path), (
        "Symlink inside fixtures root pointing outside was trusted!"
    )


def test_legitimate_fixture_path_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Audit A1/A6 test: A legitimate path contained within trusted_fixtures_root is trusted.
    """
    fake_fixtures_root = tmp_path / "fixtures_root"
    app_dir = fake_fixtures_root / "vulnerable_app"
    app_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "trusted_fixtures_root", fake_fixtures_root.resolve())

    assert is_trusted_fixture_path(app_dir)
