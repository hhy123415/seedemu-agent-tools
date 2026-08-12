"""Registration entry point for DNS-domain tools."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns.models import DNSLookupArguments
from seedemu_tool_service.tools.dns.tools import DNSTools


def register_dns_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Create the DNS tool set and register its handlers."""

    tools = DNSTools(backend)
    registry.register(
        definition=ToolDefinition(
            name="dns.lookup",
            domain="dns",
            description="Resolve DNS records from an emulated node.",
        ),
        handler=tools.lookup,
        arguments_model=DNSLookupArguments,
    )
