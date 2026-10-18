"""System preflight and experience mode APIs (FEATURES.md F0, F1, F4)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import anyio
from fastapi import APIRouter
import httpx

from app.core.config import settings
from app.database.client import get_database
from app.isolation.docker_manager import DockerManager

router = APIRouter()


def _check_git_sync() -> dict:
    git_bin = shutil.which("git")
    if not git_bin:
        return {"available": False, "version": None}
    try:
        res = subprocess.run([git_bin, "--version"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            return {"available": True, "version": res.stdout.strip()}
    except Exception:  # noqa: BLE001
        pass
    return {"available": False, "version": None}


def _check_disk_sync(workspace_root_str: str) -> dict:
    try:
        path = Path(os.path.expanduser(workspace_root_str or "~/.clairsec/workspaces")).resolve()
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        return {
            "workspace_root": str(path),
            "free_bytes": usage.free,
            "free_gb": round(usage.free / (1024 ** 3), 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "workspace_root": str(workspace_root_str),
            "free_bytes": 0,
            "free_gb": 0.0,
            "error": str(exc),
        }


async def _check_ollama(url: str, required_model: str | None = None) -> dict:
    req_model = required_model or getattr(settings, "ollama_model", "llama3.2")
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{url.rstrip('/')}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", []) if isinstance(m, dict)]
                model_ready = False
                if req_model:
                    model_ready = any(
                        m == req_model
                        or str(m).startswith(f"{req_model}:")
                        or str(req_model).startswith(f"{m}:")
                        for m in models
                        if m
                    )
                else:
                    model_ready = True
                return {
                    "reachable": True,
                    "model_ready": model_ready,
                    "required_model": req_model,
                    "models": models,
                    "url": url,
                    "error": None if model_ready else f"Required model '{req_model}' not found in Ollama tags.",
                }
            return {
                "reachable": False,
                "model_ready": False,
                "required_model": req_model,
                "url": url,
                "error": f"Ollama returned HTTP {resp.status_code}",
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "reachable": False,
            "model_ready": False,
            "required_model": req_model,
            "url": url,
            "error": str(exc),
        }


def _resolve_experience_mode(
    docker_ready: bool,
    key_configured: bool,
    ollama_ready: bool | None = None,
    provider: str = "mock",
    *,
    ollama_reachable: bool | None = None,
) -> dict:
    """Compute active experience mode per FEATURES.md F4."""
    has_ollama = ollama_ready if ollama_ready is not None else (ollama_reachable or False)
    if docker_ready and (key_configured and provider != "mock"):
        return {
            "id": "live",
            "label": "LIVE",
            "reason": "Docker isolation is ready and cloud LLM provider is configured.",
        }
    if docker_ready and has_ollama:
        return {
            "id": "live_local_ai",
            "label": "LIVE · LOCAL AI",
            "reason": "Docker isolation is ready and local Ollama model is available.",
        }
    if docker_ready:
        return {
            "id": "live_offline_ai",
            "label": "LIVE · OFFLINE AI",
            "reason": "Docker isolation is ready with local offline mock/replay intelligence.",
        }
    return {
        "id": "demo",
        "label": "DEMO APP",
        "reason": "Docker is unavailable. Scans run against bundled demo apps via trusted fixture isolation.",
    }


async def get_system_mode() -> dict:
    """One shared mode-resolution function for /system/mode and /system/preflight (Audit defect A7)."""
    try:
        manager = await anyio.to_thread.run_sync(DockerManager)
        docker_report = await anyio.to_thread.run_sync(manager.preflight)
        docker_ready = bool(docker_report.get("ready"))
    except Exception:  # noqa: BLE001
        docker_ready = False

    key_configured = bool(
        settings.llm_api_key
        and settings.llm_api_key.strip()
        and settings.llm_api_key != "test-mock-key"
    )
    ollama_report = await _check_ollama(settings.ollama_url)

    return _resolve_experience_mode(
        docker_ready=docker_ready,
        key_configured=key_configured,
        ollama_ready=bool(ollama_report.get("model_ready")),
        provider=settings.llm_provider,
    )


@router.get("/system/preflight")
async def preflight() -> dict:
    """Report full system readiness and environment diagnostics. Never fails; problems are returned as data."""
    from app.database.client import storage_fallback_reason, storage_mode

    if storage_mode() == "memory":
        # Running on the in-memory fallback: usable, but nothing survives a restart.
        mongo = {
            "ok": False,
            "fallback": "memory",
            "error": storage_fallback_reason() or "MongoDB is not reachable.",
        }
    else:
        try:
            await get_database().command("ping")
            mongo = {"ok": True, "fallback": None, "error": None}
        except Exception as exc:  # noqa: BLE001
            mongo = {"ok": False, "fallback": None, "error": f"MongoDB is not reachable: {exc}"}

    try:
        manager = await anyio.to_thread.run_sync(DockerManager)
        docker_report = await anyio.to_thread.run_sync(manager.preflight)
    except Exception as exc:  # noqa: BLE001 — preflight never fails; problems are data
        docker_report = {"daemon_reachable": False, "ready": False, "hint": str(exc)}

    # LLM configuration (boolean flag only — NEVER the key itself)
    key_configured = bool(
        settings.llm_api_key
        and settings.llm_api_key.strip()
        and settings.llm_api_key != "test-mock-key"
    )
    llm_report = {
        "provider": settings.llm_provider,
        "key_configured": key_configured,
    }

    # Ollama reachability & model tag
    ollama_report = await _check_ollama(settings.ollama_url)

    # Git availability and version
    git_report = await anyio.to_thread.run_sync(_check_git_sync)

    # Free disk in WORKSPACE_ROOT
    disk_report = await anyio.to_thread.run_sync(_check_disk_sync, settings.workspace_root)

    # Experience mode computation using shared logic
    docker_ready = bool(docker_report.get("ready"))
    mode_report = _resolve_experience_mode(
        docker_ready=docker_ready,
        key_configured=key_configured,
        ollama_ready=bool(ollama_report.get("model_ready")),
        provider=settings.llm_provider,
    )

    return {
        "ready": bool(mongo["ok"] and docker_ready),
        "storage": "memory" if mongo.get("fallback") == "memory" else "mongodb",
        "mongodb": mongo,
        "docker": docker_report,
        "llm": llm_report,
        "ollama": ollama_report,
        "git": git_report,
        "disk": disk_report,
        "mode": mode_report,
    }


@router.get("/system/mode")
async def get_mode() -> dict:
    """Return the computed experience mode (F4) via the shared resolution function."""
    return await get_system_mode()

