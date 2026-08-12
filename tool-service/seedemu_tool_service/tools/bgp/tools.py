"""BGP-domain tool implementations."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.tools.bgp.models import BGPSummaryResult


class BGPTools:
    """Bound-method tools for BGP inspection and operations."""

    def __init__(self, backend: RuntimeBackend) -> None:
        self._backend = backend

    def summary(self, source: str) -> BGPSummaryResult:
        """Retrieve the IPv4-unicast BGP summary from an emulated router."""

        result = self._backend.execute(source, ["vtysh", "-c", "show bgp ipv4 unicast summary"])
        return BGPSummaryResult(
            source=source,
            successful=result.exit_code == 0,
            output=result.stdout,
            exit_code=result.exit_code,
            stderr=result.stderr,
        )
