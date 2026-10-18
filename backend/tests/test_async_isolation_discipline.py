"""
Tests for Async Isolation Discipline (Audit defect A2, RULES §5a).

Exit gate:
- No blocking Docker call may run on the event loop.
- During a mocked 2-second build during auto-isolation / IsolationService,
  a concurrent GET /api/health returns in < 200 ms.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import uuid
import pytest

from app.database.client import get_database
from app.database.models import ProjectRecord, ValidationStatus, IsolationStatus
from app.isolation.docker_manager import DockerManager
from app.services.isolation_service import IsolationService


@pytest.mark.asyncio
async def test_isolation_service_does_not_block_event_loop(authed_client, app, tmp_path: Path):
    """
    Audit A2 test: IsolationService.start_isolation must run DockerManager calls
    (build_image, start_container, start_proxy, wait_for_healthy) in worker threads
    via anyio.to_thread.run_sync.
    During a 2-second blocking build, a concurrent GET /api/health must respond in < 200ms.
    """
    project_id = str(uuid.uuid4())

    untrusted_source = tmp_path / "untrusted_source"
    untrusted_source.mkdir(parents=True)
    (untrusted_source / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")

    sample_project = ProjectRecord(
        id=project_id,
        name="Untrusted App",
        source_path=str(untrusted_source),
        entry_point="main.py",
        validation_status=ValidationStatus.VALID,
        isolation_status=IsolationStatus.PENDING,
    )

    mock_db = MagicMock()
    mock_proj_col = MagicMock()
    proj_doc = sample_project.model_dump()
    proj_doc["_id"] = project_id
    mock_proj_col.find_one = AsyncMock(return_value=proj_doc)
    mock_proj_col.update_one = AsyncMock()

    mock_db.__getitem__ = MagicMock(return_value=mock_proj_col)
    mock_docker = MagicMock(spec=DockerManager)
    mock_docker.image_tag.return_value = "clairsec-target:test"

    import threading
    main_thread_id = threading.get_ident()
    build_thread_id = None

    def slow_build(*args, **kwargs):
        nonlocal build_thread_id
        build_thread_id = threading.get_ident()
        time.sleep(2.0)
        return "clairsec-target:test"

    mock_docker.build_image.side_effect = slow_build
    mock_docker.start_container.return_value = ("cid_123", "cname_123")
    mock_docker.start_proxy.return_value = ("proxy_123", 59999)
    mock_docker.wait_for_healthy.return_value = True

    isolation_svc = IsolationService(
        db=mock_db,
        docker_manager=mock_docker,
    )

    prev_override = app.dependency_overrides.get(get_database)
    app.dependency_overrides[get_database] = lambda: mock_db

    try:
        # Start isolation in a background coroutine on the event loop
        iso_task = asyncio.create_task(isolation_svc.start_isolation(project_id))

        # Wait until build_image has started running
        for _ in range(50):
            if mock_docker.build_image.called:
                break
            await asyncio.sleep(0.05)
        assert mock_docker.build_image.called, "build_image was not called!"

        # Concurrently request GET /api/health while build is running
        t0 = time.monotonic()
        health_resp = authed_client.get("/api/health")
        t_health = time.monotonic() - t0

        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}
        assert t_health < 0.200, f"/api/health took {t_health:.3f}s (> 200ms) — event loop was blocked during build!"

        await iso_task

        assert build_thread_id is not None, "build_image was never called"
        assert build_thread_id != main_thread_id, (
            f"Blocking build_image ran directly on event loop thread ({build_thread_id})! "
            "Must run in worker thread via anyio.to_thread.run_sync."
        )
    finally:
        if prev_override is not None:
            app.dependency_overrides[get_database] = prev_override
        else:
            app.dependency_overrides.pop(get_database, None)
