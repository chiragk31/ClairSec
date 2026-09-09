"""
Tests for Phase 2: FastAPI project validator and Projects API.

The API tests use mocked MongoDB so they run without a live MongoDB instance.
The validator tests run purely against the filesystem (test fixtures).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Fixtures path ──────────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_APP_PATH = str(FIXTURES_DIR / "valid_fastapi_app")
INVALID_APP_PATH = str(FIXTURES_DIR)           # a dir with no FastAPI code
NON_EXISTENT_PATH = "/this/path/does/not/exist/12345"


# =============================================================================
# Validator unit tests (pure filesystem, no MongoDB, no subprocess)
# =============================================================================

class TestFastAPIValidator:
    def test_valid_project_detected(self):
        from app.services.fastapi_validator import validate_fastapi_project
        result = validate_fastapi_project(VALID_APP_PATH)
        assert result.is_valid is True
        assert result.entry_point is not None
        assert "main.py" in result.entry_point
        assert result.dependency_file == "requirements.txt"
        assert "fastapi" in result.dependencies
        assert result.isolation_ready is True
        assert result.errors == []

    def test_non_fastapi_directory(self, tmp_path):
        from app.services.fastapi_validator import validate_fastapi_project
        # Create a Python file with no FastAPI import
        (tmp_path / "script.py").write_text("def hello(): return 'world'")
        result = validate_fastapi_project(str(tmp_path))
        assert result.is_valid is False
        assert result.entry_point is None
        assert len(result.errors) > 0

    def test_non_existent_path(self):
        from app.services.fastapi_validator import validate_fastapi_project
        result = validate_fastapi_project(NON_EXISTENT_PATH)
        assert result.is_valid is False
        assert "does not exist" in result.errors[0].lower() or "not exist" in result.errors[0]

    def test_path_is_file_not_dir(self, tmp_path):
        from app.services.fastapi_validator import validate_fastapi_project
        f = tmp_path / "file.py"
        f.write_text("app = FastAPI()")
        result = validate_fastapi_project(str(f))
        assert result.is_valid is False

    def test_no_dependency_file(self, tmp_path):
        from app.services.fastapi_validator import validate_fastapi_project
        (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        result = validate_fastapi_project(str(tmp_path))
        # Valid entry point found, but no dep file → isolation_ready=False
        assert result.is_valid is True
        assert result.isolation_ready is False
        assert result.dependency_file is None

    def test_pyproject_toml_parsed(self, tmp_path):
        from app.services.fastapi_validator import validate_fastapi_project
        (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi>=0.100", "uvicorn"]\n'
        )
        result = validate_fastapi_project(str(tmp_path))
        assert result.is_valid is True
        assert result.dependency_file == "pyproject.toml"
        assert "fastapi" in result.dependencies
        assert "uvicorn" in result.dependencies

    def test_syntax_error_in_target_is_safe(self, tmp_path):
        from app.services.fastapi_validator import validate_fastapi_project
        # A file with a syntax error must not crash the validator
        (tmp_path / "bad.py").write_text("def broken(:\n    pass")
        (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        result = validate_fastapi_project(str(tmp_path))
        # Should still find the valid main.py
        assert result.is_valid is True


# =============================================================================
# Projects API tests (mocked MongoDB)
# =============================================================================

def _make_client_with_mock_db():
    """Create a TestClient with the database dependency mocked out."""
    from app.main import create_app
    from app.database.client import get_database

    mock_db = MagicMock()
    # Mock the collection insert_one and find operations
    mock_col = MagicMock()
    mock_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test"))
    mock_col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_col.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    test_app = create_app()
    test_app.dependency_overrides[get_database] = lambda: mock_db
    return TestClient(test_app), mock_col


class TestProjectsAPI:
    def test_import_valid_project(self):
        client, mock_col = _make_client_with_mock_db()
        response = client.post("/api/projects", json={"path": VALID_APP_PATH})
        assert response.status_code == 201
        data = response.json()
        assert data["validation_status"] == "valid"
        assert data["entry_point"] is not None
        assert data["isolation_ready"] is True

    def test_import_invalid_project(self, tmp_path):
        client, mock_col = _make_client_with_mock_db()
        # Directory exists but has no FastAPI code
        (tmp_path / "notfastapi.py").write_text("x = 1")
        response = client.post("/api/projects", json={"path": str(tmp_path)})
        assert response.status_code == 201
        data = response.json()
        assert data["validation_status"] == "invalid"
        assert len(data["validation_errors"]) > 0

    def test_import_nonexistent_path(self):
        client, _ = _make_client_with_mock_db()
        response = client.post("/api/projects", json={"path": NON_EXISTENT_PATH})
        assert response.status_code == 201
        data = response.json()
        assert data["validation_status"] == "invalid"

    def test_list_projects_empty(self):
        client, _ = _make_client_with_mock_db()
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_project_not_found(self):
        client, _ = _make_client_with_mock_db()
        response = client.get("/api/projects/nonexistent-id")
        assert response.status_code == 404

    def test_project_name_defaults_to_dirname(self):
        client, _ = _make_client_with_mock_db()
        response = client.post("/api/projects", json={"path": VALID_APP_PATH})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "valid_fastapi_app"

    def test_project_custom_name(self):
        client, _ = _make_client_with_mock_db()
        response = client.post(
            "/api/projects",
            json={"path": VALID_APP_PATH, "name": "My Custom App"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "My Custom App"
