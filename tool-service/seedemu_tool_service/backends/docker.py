"""Docker Engine runtime backend."""

from collections.abc import Sequence
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus


class RuntimeBackendError(RuntimeError):
    """Base error raised when a runtime-backend operation fails."""


class RuntimeTargetNotFoundError(RuntimeBackendError):
    """Raised when an emulated node cannot be found."""


class DockerRuntimeBackend:
    """Access the Docker Engine configured through the process environment."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def status(self) -> RuntimeStatus:
        """Check access to the Docker daemon and report its version."""

        try:
            client = self._get_client()
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

    def execute(self, container: str, command: Sequence[str]) -> RuntimeCommandResult:
        """Execute a command in a container through the Docker Engine API."""

        try:
            target = self._get_client().containers.get(container)
            exit_code, output = target.exec_run(list(command), demux=True)
        except NotFound as error:
            raise RuntimeTargetNotFoundError(f"Emulated node not found: {container}") from error
        except DockerException as error:
            raise RuntimeBackendError("Docker command execution failed") from error

        stdout_bytes, stderr_bytes = output
        return RuntimeCommandResult(
            exit_code=exit_code,
            stdout=self._decode_output(stdout_bytes),
            stderr=self._decode_output(stderr_bytes),
        )

    @staticmethod
    def _decode_output(output: bytes | None) -> str:
        return output.decode("utf-8", errors="replace") if output else ""
