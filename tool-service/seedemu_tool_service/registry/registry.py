"""In-memory tool registry."""

from seedemu_tool_service.models.tool import ToolDefinition


class ToolRegistry:
    """Store and discover agent-visible tool definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition, rejecting duplicate names."""

        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list_tools(self) -> list[ToolDefinition]:
        """Return registered tools sorted by name."""

        return [self._tools[name] for name in sorted(self._tools)]
