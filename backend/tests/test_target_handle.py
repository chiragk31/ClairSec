"""
Tests for TargetHandle abstraction and security boundaries (Rule R5).
"""
import pytest
from pathlib import Path
from app.targets.handle import (
    LocalFixtureTargetHandle,
    TargetAccessForbiddenError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.anyio
async def test_local_fixture_target_handle_lifecycle():
    """Verify local fixture runner starts on ephemeral port and stops cleanly."""
    vuln_dir = FIXTURES_DIR / "vulnerable_fastapi_app"
    handle = LocalFixtureTargetHandle(vuln_dir)

    base_url = await handle.start()
    assert base_url.startswith("http://127.0.0.1:")
    assert await handle.is_healthy() is True

    await handle.stop()
    assert await handle.is_healthy() is False


def test_local_fixture_runner_hard_gated_against_external_paths(tmp_path):
    """Verify that any path outside tests/fixtures/ is unconditionally refused."""
    external_dir = tmp_path / "imported_app"
    external_dir.mkdir()

    with pytest.raises(TargetAccessForbiddenError) as exc_info:
        LocalFixtureTargetHandle(external_dir)

    assert "refused path outside fixtures root" in str(exc_info.value)
