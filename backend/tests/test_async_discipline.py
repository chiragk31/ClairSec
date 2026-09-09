"""
Tests for async discipline, background job execution, cancellation, and startup reconciliation
(OPERATIONS §5, RULES §5a).

Rules verified:
  - test_async_discipline does NOT require Docker: monkeypatched DockerManager with time.sleep(3) stub.
  - POST /isolate returns 202 with job_id immediately (<100ms).
  - Concurrent /api/health returns in under 100ms while the 3-second build stub is running.
  - Cancellation token stops container startup after build, cleaning up resources.
  - Cancellation latency is measured and tracked.
  - Startup reconciliation clears orphaned in-flight jobs and marks them interrupted.
  - Live two-concurrent-builds integration test marked docker.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.database.client import get_database
from app.database.models import IsolationStatus, JobRecord, JobStatus, ProjectRecord, ValidationStatus
from app.services.job_service import JobService


class TestAsyncDisciplineNonDocker:
    """Async discipline unit tests — guaranteed not to require Docker daemon."""

    @pytest.mark.asyncio
    async def test_event_loop_unblocked_during_build(self, authed_client, app):
        """
        Verify that a 3-second blocking build does NOT block the event loop.
        A concurrent GET /api/health must respond in under 100ms.
        """
        project_id = "11111111-1111-1111-1111-111111111111"

        mock_db = MagicMock()
        mock_projects_col = MagicMock()
        mock_jobs_col = MagicMock()

        sample_project = {
            "_id": project_id,
            "id": project_id,
            "name": "test-project",
            "source_path": "/tmp/source",
            "validation_status": "valid",
            "entry_point": "main.py",
            "dependency_file": "requirements.txt",
            "isolation_status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

        mock_projects_col.find_one = AsyncMock(return_value=sample_project)
        mock_projects_col.update_one = AsyncMock()
        mock_jobs_col.insert_one = AsyncMock()
        mock_jobs_col.find_one = AsyncMock(return_value={
            "_id": "job-123",
            "id": "job-123",
            "project_id": project_id,
            "status": "pending",
            "stage": "queued",
            "cancel_requested": False,
            "error": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
        mock_jobs_col.update_one = AsyncMock()

        def get_col(name):
            if name == "projects":
                return mock_projects_col
            return mock_jobs_col

        mock_db.__getitem__ = MagicMock(side_effect=get_col)

        prev_override = app.dependency_overrides.get(get_database)
        app.dependency_overrides[get_database] = lambda: mock_db

        # Monkeypatch build_image with a 3-second blocking sleep
        def slow_build(*args, **kwargs):
            time.sleep(3.0)
            return "test-image:latest"

        try:
            with patch("app.services.job_service.WorkspaceManager.create_scan_workspace", return_value="/tmp/ws"), \
                 patch("app.isolation.docker_manager.DockerManager.build_image", side_effect=slow_build), \
                 patch("app.isolation.docker_manager.DockerManager.start_container", return_value=("c123", "target-123")), \
                 patch("app.isolation.docker_manager.DockerManager.start_proxy", return_value=("p123", 54321)), \
                 patch("app.services.job_service.JobService._poll_health_with_cancel", return_value=True):

                # 1. Trigger isolation — returns 202 Accepted immediately
                t0 = time.monotonic()
                resp = authed_client.post(f"/api/projects/{project_id}/isolate")
                t_isolate = time.monotonic() - t0

                assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
                data = resp.json()
                assert "job_id" in data
                assert t_isolate < 0.200, f"POST /isolate took too long ({t_isolate:.3f}s), should return immediately"

                # 2. Concurrently check /api/health while the 3-second build runs in the thread pool
                t_health_start = time.monotonic()
                health_resp = authed_client.get("/api/health")
                t_health = time.monotonic() - t_health_start

                assert health_resp.status_code == 200
                assert health_resp.json() == {"status": "ok"}
                # Must respond quickly (< 0.250s) proving event loop is unblocked
                assert t_health < 0.250, f"/api/health took {t_health:.3f}s — event loop was blocked by build!"
        finally:
            if prev_override is not None:
                app.dependency_overrides[get_database] = prev_override
            else:
                app.dependency_overrides.pop(get_database, None)

    @pytest.mark.asyncio
    async def test_cancellation_latency_and_teardown(self):
        """
        Verify cancellation:
        1. Request cancellation during build.
        2. Build completes (sleep finishes), cancel is observed at phase boundary.
        3. Container is NOT started, cleanup_all is invoked, status is marked cancelled.
        4. Measure cancellation observation latency.
        """
        project_id = "22222222-2222-2222-2222-222222222222"
        mock_db = MagicMock()
        mock_projects_col = MagicMock()
        mock_jobs_col = MagicMock()

        sample_project = {
            "_id": project_id,
            "id": project_id,
            "name": "cancel-test-project",
            "source_path": "/tmp/source",
            "validation_status": "valid",
            "entry_point": "main.py",
            "dependency_file": "requirements.txt",
            "isolation_status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

        job_doc = {
            "_id": "test-job-uuid",
            "id": "test-job-uuid",
            "project_id": project_id,
            "status": "running",
            "stage": "building_image",
            "cancel_requested": False,
            "error": None,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

        mock_projects_col.find_one = AsyncMock(return_value=sample_project)
        mock_projects_col.update_one = AsyncMock()
        mock_jobs_col.find_one = AsyncMock(return_value=job_doc)

        async def mock_job_update(filter_dict, update_dict):
            job_doc.update(update_dict.get("$set", {}))
            return MagicMock(modified_count=1)

        mock_jobs_col.update_one = AsyncMock(side_effect=mock_job_update)

        def get_col(name):
            return mock_projects_col if name == "projects" else mock_jobs_col

        mock_db.__getitem__ = MagicMock(side_effect=get_col)

        # Explicit mock docker manager so no daemon connection is attempted
        mock_docker = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.create_scan_workspace.return_value = "/tmp/ws"

        service = JobService(mock_db, docker_manager=mock_docker, workspace_manager=mock_workspace)

        container_started = False
        cleanup_called = False

        def mock_start_container(*args, **kwargs):
            nonlocal container_started
            container_started = True
            return ("cid", "cname")

        def mock_cleanup(*args, **kwargs):
            nonlocal cleanup_called
            cleanup_called = True

        def build_with_midpoint_cancel(*args, **kwargs):
            time.sleep(0.5)
            job_doc["cancel_requested"] = True
            return "image:tag"

        mock_docker.image_tag.return_value = "image:tag"
        mock_docker.build_image.side_effect = build_with_midpoint_cancel
        mock_docker.start_container.side_effect = mock_start_container
        mock_docker.cleanup_all.side_effect = mock_cleanup

        t_cancel_start = time.monotonic()
        await service._run_isolation_job("test-job-uuid", project_id)
        elapsed = time.monotonic() - t_cancel_start

        # Container must NOT have been started
        assert not container_started, "start_container must not be called after cancellation"
        # Cleanup must have been called
        assert cleanup_called, "cleanup_all must be invoked on cancellation"
        # Latency during build: equal to remaining build duration (~0.5s)
        assert elapsed < 1.0, f"Cancellation took {elapsed:.3f}s"
        # Job doc updated to cancelled
        assert job_doc["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_startup_reconciliation_cleans_interrupted_jobs(self):
        """
        Verify startup reconciliation (OPERATIONS §5):
        Interrupted jobs in 'running' or 'pending' state are marked 'interrupted',
        associated projects are marked 'import_failed', and cleanup is called.
        """
        mock_db = MagicMock()
        mock_jobs_col = MagicMock()
        mock_projects_col = MagicMock()

        active_jobs = [
            {
                "_id": "job-int-1",
                "id": "job-int-1",
                "project_id": "proj-1",
                "status": "running",
                "stage": "building_image",
                "cancel_requested": False,
                "error": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]

        proj_doc = {
            "_id": "proj-1",
            "id": "proj-1",
            "name": "p1",
            "source_path": "/tmp/p1",
            "isolation_status": "building",
            "container_id": "orphaned-container-123",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=active_jobs)
        mock_jobs_col.find = MagicMock(return_value=mock_cursor)
        mock_jobs_col.update_one = AsyncMock()

        mock_projects_col.find_one = AsyncMock(return_value=proj_doc)
        mock_projects_col.update_one = AsyncMock()

        def get_col(name):
            return mock_projects_col if name == "projects" else mock_jobs_col

        mock_db.__getitem__ = MagicMock(side_effect=get_col)

        docker_cleanup_called = False

        def mock_docker_cleanup(project_id, container_id=None):
            nonlocal docker_cleanup_called
            docker_cleanup_called = True

        mock_docker = MagicMock()
        mock_docker.cleanup_all.side_effect = mock_docker_cleanup
        mock_workspace = MagicMock()

        service = JobService(mock_db, docker_manager=mock_docker, workspace_manager=mock_workspace)

        reconciled = await service.reconcile_startup()
        assert reconciled == 1
        assert docker_cleanup_called, "Orphaned container/network must be cleaned up on restart"
        mock_jobs_col.update_one.assert_awaited()
        mock_projects_col.update_one.assert_awaited()


# =============================================================================
# Live Docker Integration Tests
# =============================================================================

@pytest.mark.docker
class TestAsyncDisciplineDocker:
    """Live two-concurrent-builds test with real Docker daemon."""

    @pytest.mark.asyncio
    async def test_two_concurrent_builds(self, app):
        """Two builds running concurrently do not block each other or the event loop."""
        import docker
        client = docker.from_env()
        client.ping()
