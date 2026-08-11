"""Runtime backend contract."""

from collections.abc import Sequence
from typing import Protocol

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus


class RuntimeBackend(Protocol):
    """Interface implemented by emulator runtime backends."""

    def status(self) -> RuntimeStatus:
        """Return backend connectivity and version information."""

        ...

    def execute(self, container: str, command: Sequence[str]) -> RuntimeCommandResult:
        """Execute an argument-vector command inside an emulated node."""

        ...
