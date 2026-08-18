"""Unit tests for RFC 2136 dynamic DNS updates."""

import base64
from collections.abc import Sequence

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.tools.dns.tools import DNSTools


class FakeRuntimeBackend:
    """Capture the nsupdate invocation without running a container."""

    def __init__(self) -> None:
        self.container: str | None = None
        self.command: list[str] | None = None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(backend="fake", available=True)

    def execute(
        self, container: str, command: Sequence[str]
    ) -> RuntimeCommandResult:
        self.container = container
        self.command = list(command)
        return RuntimeCommandResult(exit_code=0, stdout="", stderr="")


def test_update_lets_nsupdate_discover_primary_server() -> None:
    """Do not pin a server; nsupdate should discover it from the zone SOA."""

    backend = FakeRuntimeBackend()
    result = DNSTools(backend).update(
        source="dns-client",
        zone="example.net",
        name="www.example.net",
        record_type="A",
        operation="replace",
        ttl=60,
        value="192.0.2.10",
    )

    assert backend.container == "dns-client"
    assert backend.command is not None
    update_script = base64.b64decode(backend.command[-1]).decode()
    assert update_script == (
        "zone example.net.\n"
        "update delete www.example.net A\n"
        "update add www.example.net 60 A 192.0.2.10\n"
        "send\n"
    )
    assert not any(line.startswith("server ") for line in update_script.splitlines())
    assert result.successful is True
    assert result.zone == "example.net"


def test_delete_omits_server_and_add_command() -> None:
    """A delete update should contain only zone, delete, and send commands."""

    backend = FakeRuntimeBackend()
    result = DNSTools(backend).update(
        source="dns-client",
        zone="example.net.",
        name="old.example.net.",
        record_type="AAAA",
        operation="delete",
    )

    assert backend.command is not None
    update_script = base64.b64decode(backend.command[-1]).decode()
    assert update_script == (
        "zone example.net.\n"
        "update delete old.example.net. AAAA\n"
        "send\n"
    )
    assert "server " not in update_script
    assert "update add " not in update_script
    assert result.successful is True
    assert result.ttl is None
    assert result.value is None
