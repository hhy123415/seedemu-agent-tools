"""Runtime backend contract."""

from typing import Protocol

from seedemu_tool_service.models.runtime import RuntimeStatus


class RuntimeBackend(Protocol):
    """Interface implemented by emulator runtime backends."""

    def status(self) -> RuntimeStatus:
        """Return backend connectivity and version information."""

        ...
