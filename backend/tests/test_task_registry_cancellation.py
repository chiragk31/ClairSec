"""
Tests for C1 + C2: Task registry, cross-service scan cancellation, and startup reconciliation.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.database.models import PipelineRecord, PipelineStage, PipelineStageInfo, PipelineStatus, ProjectRecord, ScanRecord
from app.services.task_registry import TaskRegistry, task_registry, reconcile_stale_tasks
from app.services.scan_service import ScanService
from app.services.pipeline_orchestrator import PipelineOrchestrator


@pytest.mark.asyncio
async def test_task_registry_strong_ref_and_cancellation():
    """Verify registry holds strong reference and propagates cancellation token."""
    reg = TaskRegistry()
    loop = asyncio.get_running_loop()

    started = asyncio.Event()

    async def dummy_coro(token: asyncio.Event):
        started.set()
        while not token.is_set():
            await asyncio.sleep(0.01)

    tok = asyncio.Event()
    task = asyncio.create_task(dummy_coro(tok))
    reg.register("task-1", task, tok)

    await started.wait()
    assert reg.get_task("task-1") is task
    assert not reg.is_cancelled("task-1")

    cancelled = reg.request_cancellation("task-1")
    assert cancelled is True
    assert reg.is_cancelled("task-1")
    assert tok.is_set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    assert task.done()


@pytest.mark.asyncio
async def test_cancel_from_different_service_instance_stops_task():
    """C1: Cancel scan from a *different* service instance stops the task."""
    scan_id = "test-scan-cancel-inst"
    project_id = "test-proj-cancel-inst"

    # Instance A starts the task
    service_a = ScanService(db=None)
    # Instance B will cancel the task
    service_b = ScanService(db=None)

    step_counter = 0
    token = asyncio.Event()

    async def fake_pipeline():
        nonlocal step_counter
        while not token.is_set():
            step_counter += 1
            await asyncio.sleep(0.02)

    bg_task = asyncio.create_task(fake_pipeline())
    task_registry.register(scan_id, bg_task, token)

    await asyncio.sleep(0.05)
    assert step_counter > 0
    initial_steps = step_counter

    # Mock scan repo in service_b
    mock_scan = ScanRecord(
        id=scan_id,
        project_id=project_id,
        state="running",
        stage="attacker",
    )
    service_b._scan_repo.get_by_id = AsyncMock(return_value=mock_scan)
    service_b._scan_repo.update = AsyncMock()

    # Cancel via service_b
    cancelled_scan = await service_b.cancel_scan(scan_id)
    assert cancelled_scan is not None
    assert cancelled_scan.state == "cancelled"

    await asyncio.sleep(0.05)
    # Task should have stopped incrementing
    after_cancel_steps = step_counter
    await asyncio.sleep(0.05)
    assert step_counter == after_cancel_steps


@pytest.mark.asyncio
async def test_cancelled_scan_stops_issuing_requests():
    """C2: A cancelled scan stops issuing requests (fake target counts requests)."""
    scan_id = "test-scan-req-count"
    token = asyncio.Event()
    request_count = 0

    class FakeTarget:
        async def send_request(self):
            nonlocal request_count
            request_count += 1
            await asyncio.sleep(0.02)

    target = FakeTarget()

    async def attacker_loop(tok: asyncio.Event):
        for _ in range(50):
            if tok.is_set():
                break
            await target.send_request()

    task = asyncio.create_task(attacker_loop(token))
    task_registry.register(scan_id, task, token)

    await asyncio.sleep(0.05)
    assert request_count > 0

    # Cancel
    task_registry.request_cancellation(scan_id)
    with pytest.raises(asyncio.CancelledError):
        await task

    final_count = request_count
    await asyncio.sleep(0.05)
    assert request_count == final_count
    assert final_count < 50


@pytest.mark.asyncio
async def test_startup_reconciliation():
    """C1: Reconcile pipelines and scans left 'running' on server restart to 'interrupted'."""
    mock_db = MagicMock()

    # Setup mock collections for scans and pipelines
    scans_col = AsyncMock()
    pipelines_col = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "scans": scans_col,
        "pipelines": pipelines_col,
    }[name]

    scans_col.update_many = AsyncMock(return_value=MagicMock(modified_count=2))
    pipelines_col.update_many = AsyncMock(return_value=MagicMock(modified_count=1))

    reconciled = await reconcile_stale_tasks(mock_db)
    assert reconciled["scans_interrupted"] == 2
    assert reconciled["pipelines_interrupted"] == 1

    # Verify update queries
    scans_col.update_many.assert_called_once()
    pipelines_col.update_many.assert_called_once()
    scan_query = scans_col.update_many.call_args[0][0]
    assert scan_query["state"] == "running"
    scan_update = scans_col.update_many.call_args[0][1]
    assert scan_update["$set"]["state"] == "interrupted"
    assert scan_update["$set"]["terminal_reason"] == "server_restart"
