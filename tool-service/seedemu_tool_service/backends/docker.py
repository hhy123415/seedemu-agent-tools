"""Docker Engine runtime backend."""

from typing import Any

import docker
from docker.errors import DockerException

from seedemu_tool_service.models.runtime import RuntimeStatus


class DockerRuntimeBackend:
    """Access the Docker Engine configured through the process environment."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def status(self) -> RuntimeStatus:
        """Check access to the Docker daemon and report its version."""

        try:
            client = self._client or docker.from_env()
            if not client.ping():
                return RuntimeStatus(backend="docker", available=False)
            daemon_version = client.version().get("Version")
        except DockerException:
            return RuntimeStatus(backend="docker", available=False)

        return RuntimeStatus(
            backend="docker",
            available=True,
            daemon_version=daemon_version,
        )
