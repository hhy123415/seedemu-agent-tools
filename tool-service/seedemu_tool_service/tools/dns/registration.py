"""Registration entry point for DNS-domain tools."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns.models import (
    DNSCompareArguments,
    DNSLookupArguments,
    DNSReverseLookupArguments,
    DNSTraceArguments,
    DNSUpdateArguments,
)
from seedemu_tool_service.tools.dns.tools import DNSTools


def register_dns_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Create the DNS tool set and register its handlers."""

    tools = DNSTools(backend)
    registry.register(
        definition=ToolDefinition(
            name="dns.reverse_lookup",
            domain="dns",
            description=(
                "Resolve PTR records for a validated IPv4 or IPv6 address using "
                "the standard reverse DNS name."
            ),
        ),
        handler=tools.reverse_lookup,
        arguments_model=DNSReverseLookupArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="dns.lookup",
            domain="dns",
            description=(
                "Resolve DNS records from an emulated node and distinguish dig "
                "execution success from DNS response status and answer presence."
            ),
        ),
        handler=tools.lookup,
        arguments_model=DNSLookupArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="dns.compare",
            domain="dns",
            description=(
                "Query the same record from multiple DNS servers using one source "
                "node and compare statuses, answers, TTLs, latency, and timeouts."
            ),
        ),
        handler=tools.compare,
        arguments_model=DNSCompareArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="dns.trace",
            domain="dns",
            description=(
                "Trace DNS resolution through the delegation chain. Use this to "
                "diagnose authority paths; use dns.lookup for ordinary resolution."
            ),
        ),
        handler=tools.trace,
        arguments_model=DNSTraceArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="dns.update",
            domain="dns",
            description=(
                "Replace or delete a DNS RRset through RFC 2136 dynamic update. "
                "The primary server is discovered automatically from the zone SOA."
            ),
        ),
        handler=tools.update,
        arguments_model=DNSUpdateArguments,
    )
