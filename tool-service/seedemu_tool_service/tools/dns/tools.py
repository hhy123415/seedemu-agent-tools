"""DNS-domain tool implementations."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.tools.dns.models import DNSLookupResult, DNSRecordType


class DNSTools:
    """Bound-method tools for DNS inspection and operations."""

    def __init__(self, backend: RuntimeBackend) -> None:
        self._backend = backend

    def lookup(
        self,
        source: str,
        name: str,
        record_type: DNSRecordType = "A",
        server: str | None = None,
        timeout_seconds: int = 3,
    ) -> DNSLookupResult:
        """Resolve DNS records from an emulated source node using dig."""

        command = ["dig", f"+time={timeout_seconds}", "+tries=1", "+short"]
        if server is not None:
            command.append(f"@{server}")
        command.extend([name, record_type])

        result = self._backend.execute(source, command)
        answers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return DNSLookupResult(
            source=source,
            name=name,
            record_type=record_type,
            server=server,
            successful=result.exit_code == 0,
            answers=answers,
            exit_code=result.exit_code,
            stderr=result.stderr,
        )
