import json
import logging
from pathlib import Path
from typing import Any
import httpx

from app.agents.builder.schemas import TestPrincipal

logger = logging.getLogger(__name__)

DEFAULT_TEST_PRINCIPALS = [
    TestPrincipal(
        user_id="usr_alice_01",
        username="alice",
        token="Bearer alice-token-123",
        display_name="Alice Smith",
        role="member",
        is_admin=False,
    ),
    TestPrincipal(
        user_id="usr_bob_02",
        username="bob",
        token="Bearer bob-token-456",
        display_name="Bob Jones",
        role="member",
        is_admin=False,
    ),
]


def provision_test_principals(custom_principals: list[TestPrincipal] | None = None) -> list[TestPrincipal]:
    """
    Synchronous fallback: provision at least two distinct test principals.
    Returns default synthetic identities if none provided.
    """
    if custom_principals and len(custom_principals) >= 2:
        return custom_principals
    return list(DEFAULT_TEST_PRINCIPALS)


async def discover_and_provision_principals(
    custom_principals: list[TestPrincipal] | None = None,
    target_handle: Any = None,
    project_dir: Path | str | None = None,
) -> list[TestPrincipal]:
    """
    Discover documented test credentials or authenticate against running target.
    Ensures at least two distinct authenticated principals with real tokens when available.
    """
    if custom_principals and len(custom_principals) >= 2:
        return custom_principals

    candidate_creds: list[dict[str, str]] = []

    # 1. Check for benchmark.json in project_dir
    if project_dir is not None:
        pdir = Path(project_dir).resolve()
        bench_file = pdir / "benchmark.json"
        if not bench_file.exists():
            for parent in pdir.parents:
                bf = parent / "benchmark.json"
                if bf.exists():
                    bench_file = bf
                    break

        if bench_file.exists():
            try:
                data = json.loads(bench_file.read_text(encoding="utf-8"))
                for c in data.get("demo_credentials", []):
                    candidate_creds.append(c)
            except Exception as exc:
                logger.debug("Failed to read credentials from %s: %s", bench_file, exc)

    # Common default test credentials
    if not candidate_creds:
        candidate_creds = [
            {"username": "alice", "password": "user123", "role": "member", "user_id": "2"},
            {"username": "bob", "password": "user123", "role": "member", "user_id": "3"},
            {"username": "admin", "password": "admin123", "role": "admin", "user_id": "1"},
        ]

    # 2. If target_handle is active, attempt login against common endpoints
    if target_handle is not None and getattr(target_handle, "base_url", None):
        base_url = target_handle.base_url.rstrip("/")
        login_endpoints = ["/auth/login", "/login", "/api/login", "/token", "/api/auth/login"]
        active_login_url: str | None = None

        async with httpx.AsyncClient(timeout=3.0) as client:
            for ep in login_endpoints:
                try:
                    resp = await client.post(f"{base_url}{ep}", json={"username": "probe", "password": "probe"})
                    if resp.status_code in (200, 400, 401, 422):
                        active_login_url = ep
                        break
                except Exception:
                    continue

            if active_login_url:
                provisioned: list[TestPrincipal] = []
                for cred in candidate_creds:
                    u = cred.get("username", "")
                    p = cred.get("password", "")
                    if not u or not p:
                        continue
                    try:
                        resp = await client.post(
                            f"{base_url}{active_login_url}",
                            json={"username": u, "password": p},
                        )
                        if resp.status_code == 200:
                            res_json = resp.json()
                            token_str = (
                                res_json.get("access_token")
                                or res_json.get("token")
                                or res_json.get("jwt")
                                or ""
                            )
                            if token_str:
                                uid = str(cred.get("user_id") or res_json.get("user_id") or res_json.get("id") or u)
                                role = str(cred.get("role") or res_json.get("role") or "member")
                                is_admin = role.lower() == "admin" or cred.get("is_admin", False)
                                provisioned.append(
                                    TestPrincipal(
                                        user_id=uid,
                                        username=u,
                                        token=f"Bearer {token_str}" if not token_str.startswith("Bearer ") else token_str,
                                        display_name=u.capitalize(),
                                        role=role,
                                        is_admin=is_admin,
                                    )
                                )
                    except Exception as exc:
                        logger.debug("Failed login for %s: %s", u, exc)

                if len(provisioned) >= 2:
                    logger.info("Successfully provisioned %d authenticated principals via %s", len(provisioned), active_login_url)
                    return provisioned

    return list(DEFAULT_TEST_PRINCIPALS)
