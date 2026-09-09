"""
Functional test suite for Notes & Identity API.
These tests verify legitimate application functionality.
Per TESTING.md §5a (Dual Criterion), these functional tests MUST PASS on both
the vulnerable build and any valid patched/secured build.
"""
import pytest
from fastapi.testclient import TestClient

from .main import app, reset_state


@pytest.fixture(autouse=True)
def run_around_tests():
    reset_state()
    yield
    reset_state()


@pytest.fixture
def client():
    return TestClient(app)


def test_health_and_root_endpoints(client):
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json() == {"status": "ok"}

    r_root = client.get("/")
    assert r_root.status_code == 200
    assert r_root.json().get("status") == "running"


def test_user_can_read_own_document(client):
    headers = {"Authorization": "Bearer alice-token-123"}
    resp = client.get("/documents/doc_alice_01", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == "doc_alice_01"
    assert data["owner_id"] == "usr_alice_01"
    assert "Secret Strategy" in data["title"]


def test_create_document(client):
    headers = {"Authorization": "Bearer alice-token-123"}
    payload = {"title": "New Meeting Notes", "content": "Action items from sync."}
    resp = client.post("/documents", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Meeting Notes"
    assert data["owner_id"] == "usr_alice_01"
    assert "doc_id" in data


def test_user_can_update_profile_bio(client):
    headers = {"Authorization": "Bearer alice-token-123"}
    update_payload = {"display_name": "Alice S.", "bio": "Updated bio text."}
    resp = client.put("/users/usr_alice_01/profile", json=update_payload, headers=headers)
    assert resp.status_code == 200

    # Verify update persisted
    get_resp = client.get("/users/usr_alice_01", headers=headers)
    assert get_resp.status_code == 200
    user_data = get_resp.json()
    assert user_data["display_name"] == "Alice S."
    assert user_data["bio"] == "Updated bio text."


def test_user_cannot_update_other_user_profile(client):
    headers = {"Authorization": "Bearer alice-token-123"}
    update_payload = {"bio": "Malicious takeover"}
    resp = client.put("/users/usr_bob_02/profile", json=update_payload, headers=headers)
    assert resp.status_code == 403


def test_unauthenticated_request_rejected(client):
    resp = client.get("/documents/doc_alice_01")
    assert resp.status_code == 401
