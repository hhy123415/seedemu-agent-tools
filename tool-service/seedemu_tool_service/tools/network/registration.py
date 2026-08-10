"""Registration entry point for network-domain tools."""

from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.network.models import InspectIPAddressArguments
from seedemu_tool_service.tools.network.tools import NetworkTools


def register_network_tools(registry: ToolRegistry) -> None:
    """Create the network tool set and register its handlers."""

    tools = NetworkTools()
    registry.register(
        definition=ToolDefinition(
            name="network.inspect_ip_address",
            domain="network",
            description="Normalize an IPv4 or IPv6 address and inspect its properties.",
            input_schema=InspectIPAddressArguments.model_json_schema(),
        ),
        handler=tools.inspect_ip_address,
    )
