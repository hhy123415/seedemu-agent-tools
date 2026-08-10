"""Tool discovery endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from seedemu_tool_service.api.dependencies import get_tool_registry
from seedemu_tool_service.models.tool import ToolListResponse
from seedemu_tool_service.registry.registry import ToolRegistry

router = APIRouter(tags=["tools"])


@router.get("", response_model=ToolListResponse)
def list_tools(
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> ToolListResponse:
    """List tools currently registered with the service."""

    tools = registry.list_tools()
    return ToolListResponse(tools=tools, count=len(tools))
