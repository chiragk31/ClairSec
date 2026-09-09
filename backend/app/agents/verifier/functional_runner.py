"""
Functional test suite runner for Phase 8 Re-test and Verification (METHODOLOGY.md §5).
Executes legitimate application functional tests against the running target.
Enforces the Dual Criterion: functionality must be preserved post-fix.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.verifier.schemas import FunctionalSuiteResult
from app.security.http_client import ScopeLockedHttpClient
from app.targets.handle import TargetHandle

logger = logging.getLogger(__name__)


class FunctionalSuiteRunner:
    """
    Executes the project's functional test suite against the running target.
    """

    async def run_functional_suite(
        self,
        *,
        target_handle: TargetHandle,
    ) -> FunctionalSuiteResult:
        """
        Execute standard functional verification tests against target_handle.base_url.
        """
        passed = 0
        failed = 0
        newly_failing: list[str] = []

        tests = [
            ("test_health_and_root_endpoints", self._test_health_and_root),
            ("test_user_can_read_own_document", self._test_read_own_document),
            ("test_create_document", self._test_create_document),
            ("test_user_can_update_profile_bio", self._test_update_profile_bio),
            ("test_user_cannot_update_other_user_profile", self._test_forbidden_profile_update),
            ("test_unauthenticated_request_rejected", self._test_unauthenticated_rejected),
        ]

        total = len(tests)

        async with ScopeLockedHttpClient(base_url=target_handle.base_url) as client:
            for test_name, test_func in tests:
                try:
                    ok = await test_func(client)
                    if ok:
                        passed += 1
                    else:
                        failed += 1
                        newly_failing.append(test_name)
                except Exception as exc:
                    logger.debug("Functional test %s failed with exception: %s", test_name, exc)
                    failed += 1
                    newly_failing.append(test_name)

        return FunctionalSuiteResult(
            ran=True,
            passed=passed,
            failed=failed,
            newly_failing=newly_failing,
            total=total,
        )

    async def _test_health_and_root(self, client: ScopeLockedHttpClient) -> bool:
        r1 = await client.get("/health")
        if r1.status_code != 200 or r1.json().get("status") != "ok":
            return False
        r2 = await client.get("/")
        return r2.status_code == 200 and r2.json().get("status") == "running"

    async def _test_read_own_document(self, client: ScopeLockedHttpClient) -> bool:
        headers = {"Authorization": "Bearer alice-token-123"}
        resp = await client.get("/documents/doc_alice_01", headers=headers)
        if resp.status_code != 200:
            return False
        data = resp.json()
        return (
            data.get("doc_id") == "doc_alice_01"
            and data.get("owner_id") == "usr_alice_01"
            and "Secret Strategy" in data.get("title", "")
        )

    async def _test_create_document(self, client: ScopeLockedHttpClient) -> bool:
        headers = {"Authorization": "Bearer alice-token-123"}
        payload = {"title": "Verification Notes", "content": "Functional test sync."}
        resp = await client.post("/documents", json=payload, headers=headers)
        if resp.status_code != 200:
            return False
        data = resp.json()
        return (
            data.get("title") == "Verification Notes"
            and data.get("owner_id") == "usr_alice_01"
            and "doc_id" in data
        )

    async def _test_update_profile_bio(self, client: ScopeLockedHttpClient) -> bool:
        headers = {"Authorization": "Bearer alice-token-123"}
        payload = {"display_name": "Alice S.", "bio": "Verified legitimate bio update."}
        resp = await client.put("/users/usr_alice_01/profile", json=payload, headers=headers)
        if resp.status_code != 200:
            return False
        # Read back to verify persistence
        get_resp = await client.get("/users/usr_alice_01", headers=headers)
        if get_resp.status_code != 200:
            return False
        data = get_resp.json()
        return data.get("display_name") == "Alice S." and data.get("bio") == "Verified legitimate bio update."

    async def _test_forbidden_profile_update(self, client: ScopeLockedHttpClient) -> bool:
        headers = {"Authorization": "Bearer alice-token-123"}
        payload = {"bio": "Unauthorized update attempt"}
        resp = await client.put("/users/usr_bob_02/profile", json=payload, headers=headers)
        return resp.status_code == 403

    async def _test_unauthenticated_rejected(self, client: ScopeLockedHttpClient) -> bool:
        resp = await client.get("/documents/doc_alice_01")
        return resp.status_code == 401
