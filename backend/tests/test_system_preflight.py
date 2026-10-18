from unittest.mock import MagicMock

import docker.errors

from app.isolation.docker_manager import DockerManager
from app.isolation.errors import IsolationError


def test_preflight_reports_daemon_down_without_raising():
    client = MagicMock()
    client.ping.side_effect = RuntimeError("pipe missing")
    report = DockerManager(client=client).preflight()
    assert report["ready"] is False
    assert "pipe missing" in report["hint"]


def test_preflight_ready_when_daemon_up_and_image_cached():
    client = MagicMock()
    client.version.return_value = {"Version": "29.0"}
    report = DockerManager(client=client).preflight()
    assert report["ready"] and report["base_image_present"]
    assert report["server_version"] == "29.0"


def test_ensure_base_image_pulls_when_missing():
    client = MagicMock()
    client.images.get.side_effect = docker.errors.ImageNotFound("x")
    DockerManager(client=client).ensure_base_image()
    client.images.pull.assert_called_once()


def test_ensure_base_image_pull_failure_is_actionable():
    client = MagicMock()
    client.images.get.side_effect = docker.errors.ImageNotFound("x")
    client.images.pull.side_effect = RuntimeError("offline")
    try:
        DockerManager(client=client).ensure_base_image()
    except IsolationError as exc:
        assert "offline" in str(exc) and "DOCKER_BASE_IMAGE" in str(exc)
    else:
        raise AssertionError("expected IsolationError")
