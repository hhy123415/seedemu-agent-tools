"""Dependencies shared by API routes."""

from functools import lru_cache

from seedemu_tool_service.backends import DockerRuntimeBackend, RuntimeBackend
from seedemu_tool_service.registry.registry import ToolRegistry

_tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Return the process-wide tool registry."""

    return _tool_registry


@lru_cache
def get_runtime_backend() -> RuntimeBackend:
    """Return the configured runtime backend."""

    return DockerRuntimeBackend()
