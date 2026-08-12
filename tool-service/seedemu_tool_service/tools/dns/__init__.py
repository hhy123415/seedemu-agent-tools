"""DNS-domain tools."""

from seedemu_tool_service.tools.dns.registration import register_dns_tools
from seedemu_tool_service.tools.dns.tools import DNSTools

__all__ = ["DNSTools", "register_dns_tools"]
