"""
Central Task Registry & Cancellation Management (C1, C2, PHASES Phase 9).

Holds app-scoped strong references to background asyncio Tasks (pipelines, scans, imports)
keyed by task/scan ID, each paired with a cancellation token (asyncio.Event) and any
associated Docker containers.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class TaskRegistry:
    """
    App-scoped registry holding strong references to running background tasks.
    Prevents garbage collection mid-run and coordinates cross-instance cancellation.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._tokens: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    def register(
        self,
        task_id: str,
        task: asyncio.Task,
        token: asyncio.Event | None = None,
    ) -> asyncio.Event:
        """Register a background task with a cancellation token."""
        tok = token if token is not None else asyncio.Event()
        self._tasks[task_id] = task
        self._tokens[task_id] = tok

        def _cleanup(done: asyncio.Task) -> None:
            # Drop the strong reference once finished — unless a newer task reused the id.
            if self._tasks.get(task_id) is done:
                self._tasks.pop(task_id, None)
                self._tokens.pop(task_id, None)
            logger.debug("Background task %s completed", task_id)

        task.add_done_callback(_cleanup)
        return tok

    def get_task(self, task_id: str) -> asyncio.Task | None:
        return self._tasks.get(task_id)

    def get_token(self, task_id: str) -> asyncio.Event | None:
        return self._tokens.get(task_id)

    def get_cancellation_token(self, task_id: str, create_if_missing: bool = True) -> asyncio.Event:
        """Get or lazily create a cancellation token for a task/scan ID."""
        if task_id not in self._tokens and create_if_missing:
            self._tokens[task_id] = asyncio.Event()
        return self._tokens.get(task_id)

    def is_cancelled(self, task_id: str) -> bool:
        tok = self._tokens.get(task_id)
        return tok.is_set() if tok is not None else False

    def request_cancellation(self, task_id: str) -> bool:
        """Signal cancellation on the token and cancel the asyncio Task."""
        found = False
        tok = self._tokens.get(task_id)
        if tok is not None:
            tok.set()
            found = True

        task = self._tasks.get(task_id)
        if task is not None and not task.done():
            task.cancel()
            found = True

        logger.info("Cancellation requested for task %s (found=%s)", task_id, found)
        return found

    def unregister(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._tokens.pop(task_id, None)


# Module-level singleton instance
task_registry = TaskRegistry()


async def reconcile_stale_tasks(db: AsyncIOMotorDatabase | None) -> dict[str, int]:
    """
    On server startup, reconcile tasks/scans/pipelines left in running states to 'interrupted'.
    """
    if db is None:
        return {"scans_interrupted": 0, "pipelines_interrupted": 0}

    now = datetime.now(timezone.utc)
    scans_count = 0
    pipelines_count = 0

    try:
        # Reconcile running scans
        scans_res = await db["scans"].update_many(
            {"state": "running"},
            {
                "$set": {
                    "state": "interrupted",
                    "terminal_reason": "server_restart",
                    "error": "Server restarted while scan was running",
                    "ended_at": now,
                }
            },
        )
        scans_count = scans_res.modified_count if hasattr(scans_res, "modified_count") else 0
        if scans_count > 0:
            logger.warning("Reconciled %d orphaned running scan(s) to 'interrupted'", scans_count)
    except Exception as exc:
        logger.error("Failed to reconcile stale scans: %s", exc)

    try:
        # Reconcile running pipelines
        pipelines_res = await db["pipelines"].update_many(
            {"status": {"$in": ["running", "pending"]}},
            {
                "$set": {
                    "status": "interrupted",
                    "error": "Server restarted while pipeline was running",
                    "ended_at": now,
                }
            },
        )
        pipelines_count = pipelines_res.modified_count if hasattr(pipelines_res, "modified_count") else 0
        if pipelines_count > 0:
            logger.warning("Reconciled %d orphaned pipeline(s) to 'interrupted'", pipelines_count)
    except Exception as exc:
        logger.error("Failed to reconcile stale pipelines: %s", exc)

    return {
        "scans_interrupted": scans_count,
        "pipelines_interrupted": pipelines_count,
    }
