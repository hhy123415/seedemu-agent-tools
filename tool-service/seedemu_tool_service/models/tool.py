"""Models used for tool discovery."""

from pydantic import BaseModel, ConfigDict


class ToolDefinition(BaseModel):
    """Agent-visible metadata for a registered tool."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str


class ToolListResponse(BaseModel):
    """Response returned by the tool-discovery endpoint."""

    tools: list[ToolDefinition]
    count: int
