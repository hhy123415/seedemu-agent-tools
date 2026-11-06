"""DNS-domain tool tests."""

from collections.abc import Sequence

import anyio
import pytest
from pydantic import ValidationError

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools


class FakeRuntimeBackend:
    def __init__(self, result: RuntimeCommandResult | None = None) -> None:
        self.result = result or RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\n"
                ";; flags: qr rd ra; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 0\n"
                ";; ANSWER SECTION:\n"
                "www.example.test. 300 IN A 192.0.2.10\n"
                "www.example.test. 300 IN A 192.0.2.11\n"
            ),
            stderr="",
        )
        self.container: str | None = None
        self.command: list[str] | None = None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(backend="fake", available=True)

    def execute(self, container: str, command: Sequence[str]) -> RuntimeCommandResult:
        self.container = container
        self.command = list(command)
        return self.result


def test_dns_domain_registers_lookup_tool() -> None:
    registry = ToolRegistry()

    register_dns_tools(registry, FakeRuntimeBackend())

    definitions = {tool.name: tool for tool in registry.list_tools()}
    assert "dns.lookup" in definitions
    definition = definitions["dns.lookup"]
    assert definition.domain == "dns"
    properties = definition.input_schema["properties"]
    assert properties["record_type"]["default"] == "A"
    assert properties["timeout_seconds"]["maximum"] == 30


def test_lookup_uses_source_resolver_by_default() -> None:
    backend = FakeRuntimeBackend()
    registry = ToolRegistry()
    register_dns_tools(registry, backend)

    result = anyio.run(
        registry.invoke,
        "dns.lookup",
        {"source": "as150-host-0", "name": "www.example.test"},
    )

    assert backend.container == "as150-host-0"
    assert backend.command == [
        "dig",
        "+time=3",
        "+tries=1",
        "www.example.test",
        "A",
    ]
    assert result.command_successful is True
    assert result.response_status == "NOERROR"
    assert result.details is None
    assert result.answers == ["192.0.2.10", "192.0.2.11"]


def test_lookup_can_query_a_specific_server() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 2\n"
                ";; flags: qr aa rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 0\n"
                ";; ANSWER SECTION:\n"
                "example.test. 300 IN AAAA 2001:db8::10\n"
                "\n;; SERVER: 10.0.0.53#53(10.0.0.53) (UDP)\n"
            ),
            stderr="",
        )
    )
    registry = ToolRegistry()
    register_dns_tools(registry, backend)

    result = anyio.run(
        registry.invoke,
        "dns.lookup",
        {
            "source": "client",
            "name": "example.test",
            "record_type": "AAAA",
            "include_details": True,
            "server": "10.0.0.53",
            "timeout_seconds": 5,
        },
    )

    assert backend.command == [
        "dig",
        "+time=5",
        "+tries=1",
        "@10.0.0.53",
        "example.test",
        "AAAA",
    ]
    assert result.command_successful is True
    assert result.response_status == "NOERROR"
    assert result.answers == ["2001:db8::10"]
    assert result.details is not None
    assert result.details.answer_records[0].record_type == "AAAA"
    assert result.details.responding_server == "10.0.0.53#53(10.0.0.53)"


def test_lookup_reports_command_failure() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(exit_code=9, stdout="", stderr="query timed out")
    )
    registry = ToolRegistry()
    register_dns_tools(registry, backend)

    result = anyio.run(
        registry.invoke,
        "dns.lookup",
        {"source": "client", "name": "unavailable.test"},
    )

    assert result.command_successful is False
    assert result.exit_code == 9
    assert result.response_status == "timeout"
    assert result.answers == []
    assert result.stderr == "query timed out"


def test_lookup_arguments_are_validated_before_execution() -> None:
    backend = FakeRuntimeBackend()
    registry = ToolRegistry()
    register_dns_tools(registry, backend)

    with pytest.raises(ValidationError):
        anyio.run(
            registry.invoke,
            "dns.lookup",
            {"source": "client", "name": "example.test", "record_type": "INVALID"},
        )

    assert backend.container is None
    assert backend.command is None
