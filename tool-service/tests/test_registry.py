"""Tool registry unit tests."""

import pytest

from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry


def test_registry_sorts_tools_by_name() -> None:
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="zebra", description="Last tool"))
    registry.register(ToolDefinition(name="alpha", description="First tool"))

    assert [tool.name for tool in registry.list_tools()] == ["alpha", "zebra"]


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(name="ping", description="Test connectivity")
    registry.register(tool)

    with pytest.raises(ValueError, match="Tool already registered: ping"):
        registry.register(tool)
