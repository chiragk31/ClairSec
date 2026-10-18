"""
Tests for shared experience mode resolution and Ollama model tag validation (Audit defect A7).

Exit gate:
- One shared mode-resolution function for both endpoints.
- Ollama counts as ready only if /api/tags lists settings.ollama_model.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from app.api.system import _check_ollama, _resolve_experience_mode, get_system_mode
from app.core.config import settings


@pytest.mark.asyncio
async def test_ollama_not_ready_if_model_missing():
    """
    Audit A7 test: If Ollama is reachable but /api/tags does not contain
    settings.ollama_model, it must NOT count as ready.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "mistral:latest"}, {"name": "qwen2.5:latest"}]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        report = await _check_ollama(settings.ollama_url, required_model="llama3.2")

        # Must report model_ready=False because llama3.2 is not in the models list
        assert report["reachable"] is True
        assert report.get("model_ready") is False
        assert "not found" in report.get("error", "")


@pytest.mark.asyncio
async def test_ollama_ready_if_model_present():
    """
    Audit A7 test: If Ollama is reachable and /api/tags contains settings.ollama_model,
    it counts as ready.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "llama3.2:latest"}, {"name": "llama3.2"}]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        report = await _check_ollama(settings.ollama_url, required_model="llama3.2")

        assert report["reachable"] is True
        assert report.get("model_ready") is True
        assert report.get("error") is None


@pytest.mark.asyncio
async def test_mode_resolution_uses_model_ready_not_just_reachable():
    """
    Audit A7 test: When Docker is up and Ollama is reachable but missing the model,
    experience mode must be live_offline_ai, NOT live_local_ai.
    When model is present, it resolves to live_local_ai.
    """
    mode_missing = _resolve_experience_mode(
        docker_ready=True,
        key_configured=False,
        ollama_ready=False,
        provider="mock",
    )
    assert mode_missing["id"] == "live_offline_ai"

    mode_present = _resolve_experience_mode(
        docker_ready=True,
        key_configured=False,
        ollama_ready=True,
        provider="mock",
    )
    assert mode_present["id"] == "live_local_ai"


@pytest.mark.asyncio
async def test_preflight_and_mode_endpoints_use_shared_resolution(authed_client):
    """
    Audit A7 test: Both GET /api/system/preflight and GET /api/system/mode
    return identical mode objects produced by the same shared function.
    """
    with patch("app.api.system._check_ollama") as mock_ollama, \
         patch("app.api.system.DockerManager") as mock_dm_cls:
        mock_ollama.return_value = {"reachable": False, "model_ready": False, "url": "http://127.0.0.1:11434"}
        mock_dm = MagicMock()
        mock_dm.preflight.return_value = {"ready": False}
        mock_dm_cls.return_value = mock_dm

        mode_resp = authed_client.get("/api/system/mode")
        assert mode_resp.status_code == 200
        mode_data = mode_resp.json()

        preflight_resp = authed_client.get("/api/system/preflight")
        assert preflight_resp.status_code == 200
        preflight_data = preflight_resp.json()

        assert preflight_data["mode"] == mode_data
