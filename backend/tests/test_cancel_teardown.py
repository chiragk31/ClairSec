"""
D4: cancellation must clean up what it started, and must not rewrite history.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.verifier.verifier import VerifierAgent
from app.database.models import ProjectRecord, ScanRecord
from app.services.scan_service import ScanNotCancellableError, ScanService
from app.services.task_registry import TaskRegistry


@pytest.mark.asyncio
async def test_cancel_during_patched_health_wait_tears_down_container(tmp_path: Path, monkeypatch):
    """Cancelling while the patched container boots must still remove it."""
    entered_health = threading.Event()
    release = threading.Event()

    docker = MagicMock()
    docker.patched_image_tag.return_value = "img:tag"
    docker.preflight.return_value = {"ready": True}
    docker.start_patched_target.return_value = ("tgt", "prx", 49999)

    def slow_health(*_a, **_k):
        entered_health.set()
        release.wait(5)
        return False

    docker.wait_for_healthy.side_effect = slow_health

    mod_ws = tmp_path / "workspaces" / "p" / "modified_workspace"
    mod_ws.mkdir(parents=True)
    (mod_ws / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    project = ProjectRecord(id=str(uuid.uuid4()), name="u", source_path=str(tmp_path / "src"),
                            entry_point="main.py", dependency_file=None)
    verifier = VerifierAgent(docker_manager=docker, provider_name="mock")

    task = asyncio.create_task(verifier._acquire_patched_handle(
        project_id=project.id, patch_id=str(uuid.uuid4()), modified_workspace=mod_ws,
        entry_point="main.py", project=project,
    ))
    while not entered_health.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    docker.cleanup_patched_target.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_completed_scan_is_refused():
    svc = ScanService(db=None)
    scan = ScanRecord(id=str(uuid.uuid4()), project_id=str(uuid.uuid4()), state="completed")
    await svc._scan_repo.create(scan)
    with pytest.raises(ScanNotCancellableError):
        await svc.cancel_scan(scan.id)
    assert (await svc._scan_repo.get_by_id(scan.id)).state == "completed"


def test_cancel_completed_scan_api_returns_409(authed_client):
    from app.api import scans as scans_api

    class _Svc:
        async def cancel_scan(self, scan_id):
            raise ScanNotCancellableError("Scan is already completed.")

    authed_client.app.dependency_overrides[scans_api.get_scan_service] = lambda: _Svc()
    try:
        r = authed_client.post(f"/api/scans/{uuid.uuid4()}/cancel")
        assert r.status_code == 409
    finally:
        authed_client.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_finished_tasks_leave_the_registry():
    reg = TaskRegistry()

    async def quick():
        return 1

    t = asyncio.create_task(quick())
    reg.register("t1", t)
    await t
    await asyncio.sleep(0)
    assert reg.get_task("t1") is None
