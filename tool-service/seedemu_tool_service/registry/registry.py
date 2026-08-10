"""In-memory tool registry."""

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

import anyio

from seedemu_tool_service.models.tool import ToolDefinition

ToolHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """A tool's agent-visible definition and executable handler."""

    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistry:
    """Store, discover, and invoke agent-facing tools."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """Register tool metadata and its function or bound method."""

        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        if not callable(handler):
            raise TypeError("Tool handler must be callable")
        self._tools[definition.name] = RegisteredTool(definition, handler)

    def list_tools(self) -> list[ToolDefinition]:
        """Return registered tools sorted by name."""

        return [self._tools[name].definition for name in sorted(self._tools)]

    async def invoke(self, name: str, arguments: Mapping[str, Any]) -> Any:
        """Invoke a registered handler with keyword arguments."""

        try:
            registered_tool = self._tools[name]
        except KeyError as error:
            raise KeyError(f"Tool not found: {name}") from error

        if inspect.iscoroutinefunction(registered_tool.handler):
            return await registered_tool.handler(**arguments)

        call = partial(registered_tool.handler, **arguments)
        return await anyio.to_thread.run_sync(call)
