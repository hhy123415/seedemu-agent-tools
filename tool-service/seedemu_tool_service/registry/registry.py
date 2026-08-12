"""In-memory tool registry."""

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

import anyio
from pydantic import BaseModel

from seedemu_tool_service.models.tool import ToolDefinition

ToolHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """A tool's agent-visible definition and executable handler."""

    definition: ToolDefinition
    handler: ToolHandler
    arguments_model: type[BaseModel]


class ToolRegistry:
    """Store, discover, and invoke agent-facing tools."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
        arguments_model: type[BaseModel],
    ) -> None:
        """Register a handler and its explicit Pydantic argument model."""

        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        if not callable(handler):
            raise TypeError("Tool handler must be callable")

        definition = definition.model_copy(
            update={"input_schema": arguments_model.model_json_schema()}
        )
        self._tools[definition.name] = RegisteredTool(definition, handler, arguments_model)

    def list_tools(self) -> list[ToolDefinition]:
        """Return registered tools sorted by name."""

        return [self._tools[name].definition for name in sorted(self._tools)]

    async def invoke(self, name: str, arguments: Mapping[str, Any]) -> Any:
        """Invoke a registered handler with keyword arguments."""

        try:
            registered_tool = self._tools[name]
        except KeyError as error:
            raise KeyError(f"Tool not found: {name}") from error

        validated_arguments = registered_tool.arguments_model.model_validate(arguments).model_dump()

        if inspect.iscoroutinefunction(registered_tool.handler):
            return await registered_tool.handler(**validated_arguments)

        call = partial(registered_tool.handler, **validated_arguments)
        return await anyio.to_thread.run_sync(call)
