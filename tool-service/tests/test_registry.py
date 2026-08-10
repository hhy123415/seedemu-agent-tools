"""Tool registry unit tests."""

import anyio
import pytest

from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry


def test_registry_sorts_tools_by_name() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(name="test.zebra", domain="test", description="Last tool"),
        lambda: "zebra",
    )
    registry.register(
        ToolDefinition(name="test.alpha", domain="test", description="First tool"),
        lambda: "alpha",
    )

    assert [tool.name for tool in registry.list_tools()] == ["test.alpha", "test.zebra"]


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(name="network.ping", domain="network", description="Test connectivity")
    registry.register(tool, lambda: None)

    with pytest.raises(ValueError, match="Tool already registered: network.ping"):
        registry.register(tool, lambda: None)


def test_registry_invokes_bound_method() -> None:
    class ExampleTools:
        def echo(self, value: str) -> str:
            return value

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(name="test.echo", domain="test", description="Echo a value"),
        ExampleTools().echo,
    )

    result = anyio.run(registry.invoke, "test.echo", {"value": "hello"})

    assert result == "hello"


def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(KeyError, match="Tool not found: test.missing"):
        anyio.run(registry.invoke, "test.missing", {})
