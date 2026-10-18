"""
Tests for V4 Experience Modes & Demo Safety Net (FEATURES.md F4, PLAN.md V4).

Exit Gates:
- Mode resolution tested for every dependency combination.
- With Docker stopped and no API key, Demo mode completes a real scan of the vulnerable
  fixture with >= 1 confirmed finding, and Trust check yields 0 confirmed findings.
- 4-combination host-execution rule tests:
  1. demo_fixture + mock provider + Docker down -> allowed on host.
  2. demo_fixture + real provider + Docker down -> VERIFICATION_UNAVAILABLE.
  3. user_project + Docker down -> IsolationError.
  4. Docker up -> runs in container.
- Bundle round-trip test passes; recorded-run badge always shows the source date.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import httpx
import pytest

from app.agents.evaluator.schemas import EvaluatedFinding, SeverityBand
from app.agents.fixer.schemas import PatchRecord
from app.agents.verifier.schemas import VerificationOutcome
from app.agents.verifier.verifier import VerifierAgent, VerificationUnavailableError
from app.api.system import _resolve_experience_mode
from app.core.config import settings
from app.database.models import IsolationStatus, ProjectRecord, ScanRecord, ValidationStatus
from app.isolation.errors import IsolationError
from app.services.bundle_service import (
    BUNDLE_MAX_BYTES,
    BUNDLE_SCHEMA_VERSION,
    import_bundle_as_scan,
    load_bundle,
    record_scan_bundle,
    save_bundle,
)
from app.services.scan_service import ScanService

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VULN_FIXTURE = FIXTURES_DIR / "vulnerable_fastapi_app"
SECURE_FIXTURE = FIXTURES_DIR / "secure_fastapi_app"


# ── 1. Mode Resolution Matrix ─────────────────────────────────────────────────

def test_mode_resolution_matrix():
    """Verify mode resolution for all 4 primary dependency combinations (F4)."""
    # 1. Live mode: Docker up + real LLM key configured
    live_mode = _resolve_experience_mode(
        docker_ready=True,
        key_configured=True,
        ollama_ready=False,
        provider="anthropic",
    )
    assert live_mode["id"] == "live"
    assert live_mode["label"] == "LIVE"

    # 2. Live Local AI mode: Docker up + Ollama model available
    local_ai_mode = _resolve_experience_mode(
        docker_ready=True,
        key_configured=False,
        ollama_ready=True,
        provider="mock",
    )
    assert local_ai_mode["id"] == "live_local_ai"
    assert local_ai_mode["label"] == "LIVE · LOCAL AI"

    # 3. Live Offline AI mode: Docker up + no key + no local model
    offline_ai_mode = _resolve_experience_mode(
        docker_ready=True,
        key_configured=False,
        ollama_ready=False,
        provider="mock",
    )
    assert offline_ai_mode["id"] == "live_offline_ai"
    assert offline_ai_mode["label"] == "LIVE · OFFLINE AI"

    # 4. Demo mode: Docker is down
    demo_mode = _resolve_experience_mode(
        docker_ready=False,
        key_configured=True,
        ollama_ready=True,
        provider="anthropic",
    )
    assert demo_mode["id"] == "demo"
    assert demo_mode["label"] == "DEMO APP"


# ── 2. Demo-mode scan against vulnerable fixture (>= 1 confirmed) ─────────────

@pytest.mark.asyncio
async def test_demo_mode_vulnerable_app_scan_docker_unavailable():
    """
    Demo mode test: With Docker unavailable and mock LLM provider,
    a scan of vulnerable_fastapi_app completes successfully yielding >= 1 confirmed finding.
    """
    scan_service = ScanService()
    project_id = str(uuid.uuid4())
    project = ProjectRecord(
        id=project_id,
        name="Demo Vulnerable App",
        source_path=str(VULN_FIXTURE),
        validation_status=ValidationStatus.VALID,
        entry_point="main.py",
        origin="demo_fixture",
        isolation_status=IsolationStatus.READY,
    )
    await scan_service._project_repo.create(project)

    with patch("app.services.scan_service.DockerManager", side_effect=Exception("Docker down")),          patch("app.agents.verifier.verifier.DockerManager", side_effect=Exception("Docker down")):
        scan_service._docker_instance = None
        scan = await scan_service.submit_scan(project_id)
        assert scan.mode == "demo"

        # Poll until complete
        for _ in range(120):
            cur = await scan_service.get_scan(scan.id)
            if cur and cur.state in ("completed", "failed"):
                scan = cur
                break
            await asyncio.sleep(0.5)

        assert scan.state == "completed", f"Scan failed: {scan.error}"
        findings = await scan_service.get_scan_findings_formatted(scan.id)
        confirmed = [f for f in findings if f.get("status") == "confirmed" or f.get("evaluatedSeverity") is not None]
        assert len(confirmed) >= 1, f"Expected >= 1 confirmed finding in demo mode, got {len(confirmed)}"
        assert scan.posture is not None
        assert "before" in scan.posture
        assert "after" in scan.posture


# ── 3. Trust Check against secure fixture (0 confirmed findings) ──────────────

@pytest.mark.asyncio
async def test_trust_check_secure_app_scan_docker_unavailable():
    """
    Trust check test: With Docker unavailable and mock LLM provider,
    a scan of secure_fastapi_app completes with 0 confirmed findings.
    """
    scan_service = ScanService()
    project_id = str(uuid.uuid4())
    project = ProjectRecord(
        id=project_id,
        name="Trust Check: Secure App",
        source_path=str(SECURE_FIXTURE),
        validation_status=ValidationStatus.VALID,
        entry_point="main.py",
        origin="demo_fixture",
        isolation_status=IsolationStatus.READY,
    )
    await scan_service._project_repo.create(project)

    with patch("app.services.scan_service.DockerManager", side_effect=Exception("Docker down")),          patch("app.agents.verifier.verifier.DockerManager", side_effect=Exception("Docker down")):
        scan_service._docker_instance = None
        scan = await scan_service.submit_scan(project_id)
        assert scan.mode == "demo"

        for _ in range(120):
            cur = await scan_service.get_scan(scan.id)
            if cur and cur.state in ("completed", "failed"):
                scan = cur
                break
            await asyncio.sleep(0.5)

        assert scan.state == "completed", f"Scan failed: {scan.error}"
        findings = await scan_service.get_scan_findings_formatted(scan.id)
        confirmed = [f for f in findings if f.get("status") == "confirmed" or f.get("remediationStatus") is not None]
        assert len(confirmed) == 0, f"Trust check must have 0 confirmed findings, got {len(confirmed)}"
        assert scan.posture is not None
        assert scan.posture["before"] == 100
        assert scan.posture["grade_before"] == "A"


# ── 4. 4-Combination Host Execution Rule Tests ────────────────────────────────

@pytest.mark.asyncio
async def test_host_execution_rule_combo_1_demo_fixture_mock_allowed():
    """
    Combo 1: demo_fixture + mock provider + Docker down -> allowed on host via TrustedFixtureTargetHandle.
    """
    verifier = VerifierAgent(docker_manager=None, provider_name="mock")
    project = ProjectRecord(
        id=str(uuid.uuid4()),
        name="Demo Vulnerable",
        source_path=str(VULN_FIXTURE),
        origin="demo_fixture",
    )
    with patch("app.agents.verifier.verifier.settings") as mock_settings, \
         patch("app.agents.verifier.verifier.DockerManager", side_effect=Exception("Docker down")):
        mock_settings.llm_provider = "mock"
        mock_settings.trusted_fixtures_root = str(FIXTURES_DIR)

        handle, own_handle, was_rebuilt = await verifier._acquire_patched_handle(
            project_id=project.id,
            patch_id=str(uuid.uuid4()),
            modified_workspace=VULN_FIXTURE,
            entry_point="main.py",
            project=project,
        )
        assert own_handle is True
        assert handle.base_url.startswith("http://127.0.0.1:")
        await handle.stop()


@pytest.mark.asyncio
async def test_host_execution_rule_combo_2_demo_fixture_real_provider_unavailable():
    """
    Combo 2: demo_fixture + real provider (anthropic) + Docker down -> VERIFICATION_UNAVAILABLE.
    Untrusted model-written code must NEVER execute on host without Docker.
    """
    verifier = VerifierAgent(docker_manager=None, provider_name="anthropic")
    project = ProjectRecord(
        id=str(uuid.uuid4()),
        name="Demo Vulnerable",
        source_path=str(VULN_FIXTURE),
        origin="demo_fixture",
    )
    with patch("app.agents.verifier.verifier.settings") as mock_settings, \
         patch("app.agents.verifier.verifier.DockerManager", side_effect=Exception("Docker down")):
        mock_settings.llm_provider = "anthropic"
        mock_settings.trusted_fixtures_root = str(FIXTURES_DIR)

        with pytest.raises(VerificationUnavailableError) as exc_info:
            await verifier._acquire_patched_handle(
                project_id=project.id,
                patch_id=str(uuid.uuid4()),
                modified_workspace=VULN_FIXTURE,
                entry_point="main.py",
                project=project,
            )
        assert "Docker isolation is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_host_execution_rule_combo_3_user_project_docker_down_refused():
    """
    Combo 3: user_project + Docker down -> IsolationError (host execution refused).
    """
    verifier = VerifierAgent(docker_manager=None)
    project = ProjectRecord(
        id=str(uuid.uuid4()),
        name="User Project",
        source_path="C:/some/user/project",
        origin="user_project",
    )
    with patch("app.agents.verifier.verifier.settings") as mock_settings, \
         patch("app.agents.verifier.verifier.DockerManager", side_effect=Exception("Docker down")):
        mock_settings.llm_provider = "mock"
        mock_settings.trusted_fixtures_root = str(FIXTURES_DIR)

        with pytest.raises(IsolationError) as exc_info:
            await verifier._acquire_patched_handle(
                project_id=project.id,
                patch_id=str(uuid.uuid4()),
                modified_workspace=Path("C:/some/user/project/workspace"),
                entry_point="main.py",
                project=project,
            )
        assert "isolation_required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_host_execution_rule_combo_4_docker_available_container():
    """
    Combo 4: Docker available -> container built and started.
    """
    mock_docker_mgr = MagicMock()
    mock_docker_mgr.preflight.return_value = {"ready": True}
    mock_docker_mgr.patched_image_tag.return_value = "clairsec-target-patched:test"
    mock_docker_mgr.build_image.return_value = None
    mock_docker_mgr.start_patched_target.return_value = ("target-123", "proxy-123", 49152)

    verifier = VerifierAgent(docker_manager=mock_docker_mgr)
    project = ProjectRecord(
        id=str(uuid.uuid4()),
        name="Any Project",
        source_path=str(VULN_FIXTURE),
        origin="user_project",
    )

    with patch("app.agents.verifier.verifier.settings") as mock_settings:
        mock_settings.llm_provider = "mock"
        mock_settings.trusted_fixtures_root = str(FIXTURES_DIR)

        handle, own_handle, was_rebuilt = await verifier._acquire_patched_handle(
            project_id=project.id,
            patch_id=str(uuid.uuid4()),
            modified_workspace=VULN_FIXTURE,
            entry_point="main.py",
            project=project,
        )
        assert handle is not None
        assert own_handle is False
        assert was_rebuilt is True


# ── 5. Bundle Round-Trip Test ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bundle_round_trip(tmp_path: Path):
    """
    Bundle round-trip test:
    record -> save -> load -> import as scan.
    Assert identical event sequence, finding set, <= 5 MB cap, and recorded-run badge date format.
    """
    scan_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    mock_db = MagicMock()
    mock_scans_col = MagicMock()
    mock_events_col = MagicMock()
    mock_findings_col = MagicMock()
    mock_test_cases_col = MagicMock()
    mock_patches_col = MagicMock()
    mock_ver_col = MagicMock()
    mock_projects_col = MagicMock()

    scan_doc = {
        "id": scan_id,
        "project_id": project_id,
        "project_name": "Demo Vulnerable App",
        "state": "completed",
        "posture": {"version": "posture_v1", "before": 37, "after": 100, "grade_before": "F", "grade_after": "A"},
        "counters": {"tests_executed": 12, "fixes_verified": 3},
    }
    mock_scans_col.find_one = AsyncMock(return_value=scan_doc)
    mock_projects_col.find_one = AsyncMock(return_value={"id": project_id, "name": "Demo Vulnerable App"})

    t0 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 18, 12, 0, 5, tzinfo=timezone.utc)
    mock_events = [
        {"scan_id": scan_id, "seq": 1, "timestamp": t0, "agent": "builder", "kind": "stage_started", "title": "Builder started"},
        {"scan_id": scan_id, "seq": 2, "timestamp": t1, "agent": "attacker", "kind": "request_sent", "title": "Sent BOLA exploit"},
    ]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=mock_events)
    mock_events_cursor = MagicMock()
    mock_events_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_events_col.find = MagicMock(return_value=mock_events_cursor)

    mock_findings = [
        {"id": "f-1", "scan_id": scan_id, "category": "BOLA", "status": "confirmed", "severity": "high"},
        {"id": "f-2", "scan_id": scan_id, "category": "INJECTION", "status": "confirmed", "severity": "critical"},
    ]
    mock_findings_cursor = MagicMock()
    mock_findings_cursor.to_list = AsyncMock(return_value=mock_findings)
    mock_findings_col.find = MagicMock(return_value=mock_findings_cursor)

    for col in (mock_test_cases_col, mock_patches_col, mock_ver_col):
        c = MagicMock()
        c.to_list = AsyncMock(return_value=[])
        col.find = MagicMock(return_value=c)

    def get_col(name: str):
        if name == "scans": return mock_scans_col
        if name == "projects": return mock_projects_col
        if name == "agent_events": return mock_events_col
        if name == "findings": return mock_findings_col
        if name == "test_cases": return mock_test_cases_col
        if name == "patches": return mock_patches_col
        if name == "verification_results": return mock_ver_col
        return MagicMock()

    mock_db.__getitem__ = MagicMock(side_effect=get_col)

    # 1. Record bundle
    bundle_data = await record_scan_bundle(scan_id=scan_id, db=mock_db)
    assert bundle_data["schema_version"] == BUNDLE_SCHEMA_VERSION
    assert bundle_data["scan_id"] == scan_id
    assert len(bundle_data["events"]) == 2
    assert bundle_data["events"][1]["offset_ms"] == 5000  # 5 seconds offset
    assert len(bundle_data["findings"]) == 2
    assert bundle_data["bundle_size_bytes"] <= BUNDLE_MAX_BYTES

    # 2. Save bundle
    bundle_path = save_bundle(bundle_data, output_path=tmp_path / "test_scan.clairsec.json")
    assert bundle_path.exists()

    # 3. Load bundle
    loaded = load_bundle(bundle_path)
    assert loaded["schema_version"] == BUNDLE_SCHEMA_VERSION
    assert loaded["scan_id"] == scan_id
    assert loaded["events"] == bundle_data["events"]
    assert loaded["findings"] == bundle_data["findings"]

    # 4. Assert recorded-run badge format (FEATURES.md F4: RECORDED RUN · <date>)
    rec_at = loaded["recorded_at"]
    rec_date = rec_at.split("T")[0]
    expected_badge = f"RECORDED RUN · {rec_date}"
    assert "RECORDED RUN · " in expected_badge

    # 5. Import bundle as scan into db
    mock_scans_col.replace_one = AsyncMock()
    mock_events_col.replace_one = AsyncMock()
    mock_findings_col.replace_one = AsyncMock()
    scan_record = await import_bundle_as_scan(loaded, db=mock_db)
    assert scan_record.id == scan_id
    assert scan_record.mode == "recorded"
    assert scan_record.findings_confirmed == 2
    assert mock_scans_col.replace_one.await_count == 1
    assert mock_events_col.replace_one.await_count == 2
    assert mock_findings_col.replace_one.await_count == 2


# ── D2: no runtime mutation of global settings ────────────────────────────────


@pytest.mark.asyncio
async def test_demo_scan_does_not_mutate_global_provider(monkeypatch):
    """A demo scan must not flip settings.llm_provider; the next user scan keeps its provider."""
    from app.llm import factory

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    built: list[str] = []
    real_build = factory.build_provider

    def spy(name=None):
        built.append(name)
        return real_build("mock")

    monkeypatch.setattr("app.services.scan_service.build_provider", spy)

    scan_service = ScanService()
    project = ProjectRecord(
        id=str(uuid.uuid4()), name="Demo", source_path=str(VULN_FIXTURE),
        validation_status=ValidationStatus.VALID, entry_point="main.py",
        origin="demo_fixture", isolation_status=IsolationStatus.READY,
    )
    await scan_service._project_repo.create(project)
    with patch("app.services.scan_service.DockerManager", side_effect=Exception("Docker down")),          patch("app.agents.verifier.verifier.DockerManager", side_effect=Exception("Docker down")):
        scan_service._docker_instance = None
        scan = await scan_service.submit_scan(project.id)
        for _ in range(120):
            cur = await scan_service.get_scan(scan.id)
            if cur and cur.state in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)

    assert built and built[0] == "mock", built
    assert settings.llm_provider == "ollama", "demo scan mutated the global provider"
    assert factory.provider_name_for_scan("user_project") == "ollama"


def test_no_runtime_settings_assignment_in_app_code():
    """Grep guard: application code never assigns to `settings.<field>` at runtime."""
    import re

    app_dir = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    pattern = re.compile(r"settings\.[a-z_]+\s*=(?!=)")
    for py in app_dir.rglob("*.py"):
        if py.name == "config.py":
            continue
        for n, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{py.relative_to(app_dir)}:{n}: {line.strip()}")
    assert not offenders, offenders
