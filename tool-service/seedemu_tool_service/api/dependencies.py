"""Dependencies shared by API routes."""

from functools import lru_cache

from seedemu_tool_service.backends import DockerRuntimeBackend, RuntimeBackend
from seedemu_tool_service.registry.registry import ToolRegistry
from seedemu_tool_service.tools.network import register_network_tools


@lru_cache
def get_runtime_backend() -> RuntimeBackend:
    """Return the configured runtime backend."""

    return DockerRuntimeBackend()


def create_tool_registry() -> ToolRegistry:
    """Build the registry and load each tool domain."""

    registry = ToolRegistry()
    register_network_tools(registry, get_runtime_backend())
    return registry


_tool_registry = create_tool_registry()


def get_tool_registry() -> ToolRegistry:
    """Return the process-wide tool registry."""

    return _tool_registry
