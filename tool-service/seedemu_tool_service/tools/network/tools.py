"""Network-domain tool implementations."""

from ipaddress import ip_address

from seedemu_tool_service.tools.network.models import IPAddressInfo


class NetworkTools:
    """Bound-method tools for network inspection and operations."""

    def inspect_ip_address(self, address: str) -> IPAddressInfo:
        """Normalize an IP address and report its standard properties."""

        parsed_address = ip_address(address)
        return IPAddressInfo(
            address=str(parsed_address),
            version=parsed_address.version,
            is_private=parsed_address.is_private,
            is_loopback=parsed_address.is_loopback,
            is_multicast=parsed_address.is_multicast,
            is_global=parsed_address.is_global,
        )
