"""Docker runtime backend tests."""

import pytest
from docker.errors import DockerException

from seedemu_tool_service.backends.docker import DockerRuntimeBackend


class AvailableDockerClient:
    def ping(self) -> bool:
        return True

    def version(self) -> dict[str, str]:
        return {"Version": "test-version"}


class UnavailableDockerClient:
    def ping(self) -> bool:
        raise DockerException("daemon unavailable")


def test_docker_backend_reports_daemon_version() -> None:
    backend = DockerRuntimeBackend(client=AvailableDockerClient())

    assert backend.status().model_dump() == {
        "backend": "docker",
        "available": True,
        "daemon_version": "test-version",
    }


def test_docker_backend_reports_unavailable_daemon() -> None:
    backend = DockerRuntimeBackend(client=UnavailableDockerClient())

    assert backend.status().model_dump() == {
        "backend": "docker",
        "available": False,
        "daemon_version": None,
    }


def test_docker_backend_handles_client_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_client() -> None:
        raise DockerException("socket unavailable")

    monkeypatch.setattr("seedemu_tool_service.backends.docker.docker.from_env", unavailable_client)

    assert DockerRuntimeBackend().status().available is False
