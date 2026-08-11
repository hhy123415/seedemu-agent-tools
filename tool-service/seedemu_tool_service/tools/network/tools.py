"""Network-domain tool implementations."""

from ipaddress import ip_address

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.tools.network.models import IPAddressInfo, ReachabilityResult


class NetworkTools:
    """Bound-method tools for network inspection and operations."""

    def __init__(self, backend: RuntimeBackend) -> None:
        self._backend = backend

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

    def ping(
        self,
        source: str,
        target: str,
        count: int = 3,
        timeout_seconds: int = 2,
    ) -> ReachabilityResult:
        """Test whether a target is reachable from an emulated source node."""

        command = [
            "ping",
            "-c",
            str(count),
            "-W",
            str(timeout_seconds),
            target,
        ]
        result = self._backend.execute(source, command)
        return ReachabilityResult(
            source=source,
            target=target,
            reachable=result.exit_code == 0,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )
