"""Registration entry point for network-domain tools."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.network.models import InspectIPAddressArguments, PingArguments
from seedemu_tool_service.tools.network.tools import NetworkTools


def register_network_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Create the network tool set and register its handlers."""

    tools = NetworkTools(backend)
    registry.register(
        definition=ToolDefinition(
            name="network.inspect_ip_address",
            domain="network",
            description="Normalize an IPv4 or IPv6 address and inspect its properties.",
        ),
        handler=tools.inspect_ip_address,
        arguments_model=InspectIPAddressArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="network.ping",
            domain="network",
            description="Test whether a target host is reachable from an emulated node using ICMP.",
        ),
        handler=tools.ping,
        arguments_model=PingArguments,
    )
