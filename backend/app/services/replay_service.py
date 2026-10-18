"""
Exploit replay (FEATURES.md F8): re-send the exact stored attack and show what happens.

`original` targets the project as imported; `patched` targets a build of the
modified workspace. The same platform oracle decides the verdict both times.
Every replay is a NEW append-only test_cases record (kind="replay") — the
original evidence is never overwritten.

Host-execution rules are the verifier's: the original demo fixture may run on the
trusted fixture handle; patched code runs in a container, or on the host only for
demo fixtures with an offline provider (FEATURES.md F4).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.attacker.repository import TestCaseRepository
from app.agents.attacker.schemas import TestCaseRecord
from app.agents.evaluator.schemas import EvaluatedFinding
from app.agents.fixer.repository import PatchRepository
from app.agents.verifier.retester import OriginalExploitRetester
from app.agents.verifier.verifier import VerifierAgent
from app.database.repositories import ProjectRepository
from app.isolation.workspace import WorkspaceManager
from app.llm.factory import provider_name_for_scan
from app.services.event_bus import event_bus
from app.services.task_registry import task_registry
from app.targets.handle import ContainerTargetHandle, TrustedFixtureTargetHandle, is_trusted_fixture_path

logger = logging.getLogger(__name__)

REPLAYS = "replays"
VALID_TARGETS = ("original", "patched")


class ReplayError(Exception):
    """A replay cannot run; the message is shown to the user."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplayService:
    def __init__(self, db: AsyncIOMotorDatabase, workspace_manager: WorkspaceManager | None = None) -> None:
        self._db = db
        self._workspace = workspace_manager or WorkspaceManager()
        self._projects = ProjectRepository(db)
        self._test_cases = TestCaseRepository(db)
        self._patches = PatchRepository(db)

    async def _load_finding(self, finding_id: str) -> EvaluatedFinding:
        doc = await self._db["findings"].find_one({"id": finding_id})
        if not doc:
            raise ReplayError(f"Finding '{finding_id}' not found.")
        doc.pop("_id", None)
        return EvaluatedFinding.model_validate(doc)

    async def start(self, finding_id: str, target: str) -> dict[str, Any]:
        if target not in VALID_TARGETS:
            raise ReplayError(f"target must be one of {VALID_TARGETS}")
        finding = await self._load_finding(finding_id)
        replay = {
            "id": str(uuid.uuid4()),
            "finding_id": finding_id,
            "scan_id": finding.scan_id,
            "target": target,
            "state": "running",
            "created_at": _now(),
            "schema_version": 1,
        }
        await self._db[REPLAYS].insert_one(dict(replay))
        task = asyncio.create_task(self._run(replay["id"], finding, target))
        task_registry.register(f"replay-{replay['id']}", task)
        return replay

    async def get(self, replay_id: str) -> dict[str, Any] | None:
        doc = await self._db[REPLAYS].find_one({"id": replay_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def list_for_finding(self, finding_id: str) -> list[dict[str, Any]]:
        out = []
        async for doc in self._db[REPLAYS].find({"finding_id": finding_id}).sort("created_at", -1):
            doc.pop("_id", None)
            out.append(doc)
        return out

    async def _acquire(self, finding: EvaluatedFinding, target: str):
        """Returns (handle, release_coroutine_factory)."""
        project = await self._projects.get_by_id(finding.project_id)
        if project is None:
            raise ReplayError("The project for this finding no longer exists.")

        if target == "original":
            if project.container_id and project.proxy_port:
                handle = ContainerTargetHandle(proxy_port=project.proxy_port, container_id=project.container_id)
                if not await handle.is_healthy():
                    raise ReplayError("The isolated container is not running. Isolate the project again, then replay.")
                return handle, None
            if is_trusted_fixture_path(project.source_path):
                handle = TrustedFixtureTargetHandle(workspace_dir=project.source_path, entry_point=project.entry_point)
                await handle.start()
                return handle, handle.stop
            raise ReplayError("Start isolation for this project first — replays only run inside the sandbox.")

        patches = await self._patches.list_by_finding(finding.id)
        if not patches:
            raise ReplayError("There is no fix for this finding yet, so there is nothing patched to replay against.")
        patch = patches[-1]
        verifier = VerifierAgent(
            workspace_manager=self._workspace,
            provider_name=provider_name_for_scan(getattr(project, "origin", "user_project")),
        )
        handle, own_local, own_docker = await verifier._acquire_patched_handle(
            project_id=project.id,
            patch_id=patch.id,
            modified_workspace=self._workspace.get_modified_workspace_path(project.id),
            entry_point=project.entry_point,
            project=project,
        )

        async def release() -> None:
            await verifier._release_patched_handle(
                handle=handle, project_id=project.id, patch_id=patch.id,
                is_local_handle=own_local, is_docker_patched=own_docker,
            )

        return handle, release

    async def _run(self, replay_id: str, finding: EvaluatedFinding, target: str) -> None:
        release = None
        try:
            handle, release = await self._acquire(finding, target)
            result = await OriginalExploitRetester(test_case_repo=self._test_cases).retest(
                finding=finding, target_handle=handle,
            )
            exchange = result.exchange or {}
            record = TestCaseRecord(
                scan_id=finding.scan_id,
                category=finding.category,
                route_template=finding.route_template,
                method=finding.method,
                request=exchange.get("request") or {},
                response=exchange.get("response") or {},
                oracle_result={"fired": result.exploited, "rule_id": finding.oracle_rule_id,
                               "rationale": result.rationale},
                status="executed" if result.ran else "failed_error",
                error_detail=None if result.ran else result.rationale,
                generated_by={"agent": "user_replay", "prompt_id": None, "prompt_version": None,
                              "llm_call_id": None},
                kind="replay",
                replay_of=(finding.evidence_ids or [None])[0],
                replay_target=target,
            )
            await self._test_cases.save(record)
            await self._db[REPLAYS].update_one({"id": replay_id}, {"$set": {
                "state": "completed" if result.ran else "failed",
                "ran": result.ran,
                "oracle_fired": result.exploited,
                "verdict": ("Attack worked" if result.exploited else "Attack blocked") if result.ran
                else "Could not run",
                "rationale": result.rationale,
                "exchange": exchange,
                "test_case_id": record.id,
                "finished_at": _now(),
            }})
            await event_bus.emit(
                finding.scan_id, "oracle", "oracle_fired" if result.exploited else "oracle_clear",
                f"Replay on {target} app: {'attack worked' if result.exploited else 'attack blocked'}",
                refs={"finding_id": finding.id, "test_case_id": record.id},
            )
        except ReplayError as exc:
            await self._db[REPLAYS].update_one({"id": replay_id}, {"$set": {
                "state": "failed", "error": str(exc), "finished_at": _now()}})
        except Exception as exc:  # noqa: BLE001 — the user sees a plain failure, logs get the trace
            logger.exception("Replay %s failed: %s", replay_id, exc)
            await self._db[REPLAYS].update_one({"id": replay_id}, {"$set": {
                "state": "failed", "error": f"Replay failed: {exc}", "finished_at": _now()}})
        finally:
            if release is not None:
                try:
                    await release()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Replay target release failed: %s", exc)
