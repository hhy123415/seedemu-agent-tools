"""Registration entry point for BGP-domain tools."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.bgp.models import BGPSummaryArguments
from seedemu_tool_service.tools.bgp.tools import BGPTools


def register_bgp_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Create the BGP tool set and register its handlers."""

    tools = BGPTools(backend)
    registry.register(
        definition=ToolDefinition(
            name="bgp.summary",
            domain="bgp",
            description="Retrieve the IPv4-unicast BGP summary from an emulated router.",
        ),
        handler=tools.summary,
        arguments_model=BGPSummaryArguments,
    )
