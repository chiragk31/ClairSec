"""
Test-principal provisioning for authenticated adversarial testing (LLM.md, DATA_MODEL.md §4).
Ensures at least two distinct authenticated identities with different ownership domains.
"""
from __future__ import annotations

from app.agents.builder.schemas import TestPrincipal

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
    Provision at least two distinct test principals.
    Returns default synthetic identities if none provided.
    """
    if custom_principals and len(custom_principals) >= 2:
        return custom_principals
    return list(DEFAULT_TEST_PRINCIPALS)
