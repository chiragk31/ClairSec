"""
Tests for project_id UUID validation — THREAT_MODEL C2.3.

Traceability:
    C2.3 — test_valid_uuid_accepted, test_non_uuid_rejected,
           test_path_traversal_rejected, test_empty_string_rejected,
           test_uppercase_uuid_rejected, test_api_rejects_invalid_uuid
"""
from __future__ import annotations

import uuid

import pytest

from app.core.validators import validate_project_id


class TestUUIDValidation:
    """C2.3: project_id must match the UUID pattern before any path/container use."""

    def test_valid_uuid_accepted(self):
        """A well-formed UUIDv4 hex string passes validation."""
        valid_id = str(uuid.uuid4())
        result = validate_project_id(valid_id)
        assert result == valid_id

    def test_non_uuid_rejected(self):
        """A non-UUID string is rejected."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("not-a-uuid")

    def test_path_traversal_rejected(self):
        """A path-traversal attack string is rejected."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("../../../etc/passwd")

    def test_path_traversal_with_uuid_prefix_rejected(self):
        """A path-traversal hidden after a UUID-like prefix is rejected."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("550e8400-e29b-41d4-a716-446655440000/../../../etc")

    def test_empty_string_rejected(self):
        """An empty string is rejected."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("")

    def test_uppercase_uuid_rejected(self):
        """UUID with uppercase hex chars is rejected (pattern requires lowercase)."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("550E8400-E29B-41D4-A716-446655440000")

    def test_null_bytes_rejected(self):
        """Null bytes in project_id are rejected."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("550e8400\x00-e29b-41d4-a716-446655440000")

    def test_shell_injection_rejected(self):
        """Shell metacharacters are rejected."""
        with pytest.raises(ValueError, match="Invalid project_id"):
            validate_project_id("$(whoami)")


class TestAPIRejectsInvalidUUID:
    """C2.3: API endpoints reject non-UUID project_id before any filesystem use."""

    def test_isolation_status_rejects_invalid_id(self, authed_client):
        """GET /api/projects/{id}/status rejects path-traversal id."""
        response = authed_client.get("/api/projects/..etc..passwd/status")
        assert response.status_code == 422

    def test_isolate_rejects_invalid_id(self, authed_client):
        """POST /api/projects/{id}/isolate rejects non-UUID id."""
        response = authed_client.post("/api/projects/not-a-valid-uuid/isolate")
        assert response.status_code == 422

    def test_stop_rejects_invalid_id(self, authed_client):
        """POST /api/projects/{id}/stop rejects non-UUID id."""
        response = authed_client.post("/api/projects/hack/stop")
        assert response.status_code == 422

    def test_valid_uuid_passes_validation_layer(self, authed_client):
        """A valid UUID passes the validation layer (may 404 since project doesn't exist)."""
        valid_id = str(uuid.uuid4())
        response = authed_client.get(f"/api/projects/{valid_id}/status")
        # 404 is expected (project doesn't exist in DB) — but NOT 422
        assert response.status_code != 422
