"""Fake-backend tests for IPv4 and IPv6 reverse DNS lookups."""

from collections.abc import Sequence
from typing import Any

import anyio
import pytest
from pydantic import ValidationError

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools


class FakeRuntimeBackend:
    """Return a fixed dig result and capture the requested command."""

    def __init__(self, result: RuntimeCommandResult) -> None:
        self.result = result
        self.container: str | None = None
        self.command: list[str] | None = None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(backend="fake", available=True)

    def execute(self, container: str, command: Sequence[str]) -> RuntimeCommandResult:
        self.container = container
        self.command = list(command)
        return self.result


def invoke_reverse_lookup(
    backend: FakeRuntimeBackend,
    arguments: dict[str, object],
) -> Any:
    registry = ToolRegistry()
    register_dns_tools(registry, backend)
    return anyio.run(registry.invoke, "dns.reverse_lookup", arguments)


def test_reverse_lookup_ipv4_returns_ptr_names_and_records() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 10\n"
                ";; flags: qr rd ra; QUERY: 1, ANSWER: 2, AUTHORITY: 0, "
                "ADDITIONAL: 0\n\n"
                ";; ANSWER SECTION:\n"
                "4.3.2.1.in-addr.arpa. 300 IN PTR router.example.\n"
                "4.3.2.1.in-addr.arpa. 300 IN PTR backup.example.\n\n"
            ),
            stderr="",
        )
    )

    result = invoke_reverse_lookup(
        backend,
        {
            "source": "client",
            "address": "1.2.3.4",
            "server": "192.0.2.53",
            "timeout_seconds": 5,
        },
    )

    assert backend.container == "client"
    assert backend.command == [
        "dig",
        "+time=5",
        "+tries=1",
        "@192.0.2.53",
        "-x",
        "1.2.3.4",
    ]
    assert result.ptr_names == ["router.example.", "backup.example."]
    assert result.reverse_name == "4.3.2.1.in-addr.arpa"
    assert result.response_status == "NOERROR"
    assert [record.record_type for record in result.records] == ["PTR", "PTR"]
    assert result.successful is True


def test_reverse_lookup_normalizes_ipv6_and_builds_ip6_arpa_name() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 11\n"
                ";; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, "
                "ADDITIONAL: 0\n"
            ),
            stderr="",
        )
    )

    result = invoke_reverse_lookup(
        backend,
        {"source": "client", "address": "2001:0db8::1"},
    )

    assert backend.command == [
        "dig",
        "+time=3",
        "+tries=1",
        "-x",
        "2001:db8::1",
    ]
    assert result.reverse_name.endswith(".ip6.arpa")
    assert result.reverse_name.startswith("1.0.0.0.0.0.0.0")
    assert result.ptr_names == []
    assert result.response_status == "NXDOMAIN"
    assert result.successful is False


def test_reverse_lookup_reports_timeout() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=9,
            stdout=";; communications error to 192.0.2.53#53: timed out\n",
            stderr="no servers could be reached",
        )
    )

    result = invoke_reverse_lookup(
        backend,
        {"source": "client", "address": "192.0.2.1"},
    )

    assert result.response_status == "timeout"
    assert result.records == []
    assert result.successful is False


@pytest.mark.parametrize("address", ["example.com", "1.2.3.999", "2001:db8::zz"])
def test_reverse_lookup_rejects_non_ip_addresses(address: str) -> None:
    backend = FakeRuntimeBackend(RuntimeCommandResult(exit_code=0, stdout="", stderr=""))

    with pytest.raises(ValidationError):
        invoke_reverse_lookup(
            backend,
            {"source": "client", "address": address},
        )

    assert backend.command is None
