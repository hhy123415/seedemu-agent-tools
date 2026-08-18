"""Fake-backend tests for DNS delegation tracing."""

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


def invoke_trace(
    backend: FakeRuntimeBackend,
    arguments: dict[str, object],
) -> Any:
    """Register and invoke dns.trace through the same path used by clients."""

    registry = ToolRegistry()
    register_dns_tools(registry, backend)
    return anyio.run(registry.invoke, "dns.trace", arguments)


def test_trace_parses_delegation_steps_and_selects_final_answer() -> None:
    output = (
        ". 518400 IN NS a.root-servers.net.\n"
        "a.root-servers.net. 518400 IN A 198.41.0.4\n"
        ";; Received 239 bytes from 10.153.0.53#53(10.153.0.53) in 1 ms\n\n"
        "net. 172800 IN NS a.gtld-servers.net.\n"
        "a.gtld-servers.net. 172800 IN A 192.0.2.10\n"
        ";; Received 117 bytes from 198.41.0.4#53(a.root-servers.net) in 8 ms\n\n"
        "example.net. 86400 IN NS ns.example.net.\n"
        "ns.example.net. 86400 IN A 192.0.2.53\n"
        ";; Received 121 bytes from 192.0.2.10#53(a.gtld-servers.net) in 12 ms\n\n"
        "www.example.net. 300 IN A 1.2.3.4\n"
        ";; Received 60 bytes from 192.0.2.53#53(ns.example.net) in 3 ms\n"
    )
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(exit_code=0, stdout=output, stderr="")
    )

    result = invoke_trace(
        backend,
        {"source": "client", "name": "www.example.net"},
    )

    assert backend.container == "client"
    assert backend.command == [
        "dig",
        "+trace",
        "+time=3",
        "+tries=1",
        "www.example.net",
        "A",
    ]
    assert result.source == "client"
    assert result.name == "www.example.net"
    assert result.record_type == "A"
    assert result.server is None
    assert result.successful is True
    assert result.exit_code == 0
    assert result.stderr == ""
    assert len(result.steps) == 4
    assert result.steps[0].responding_server == "10.153.0.53#53(10.153.0.53)"
    assert result.steps[0].response_time_ms == 1
    assert [record.record_type for record in result.steps[1].records] == ["NS", "A"]
    assert [record.value for record in result.final_answers] == ["1.2.3.4"]
    assert result.raw_output == output


def test_trace_uses_requested_type_server_and_timeout() -> None:
    output = (
        "example.net. 86400 IN NS ns.example.net.\n"
        ";; Received 80 bytes from 192.0.2.1#53(start.example) in 4 ms\n\n"
        "www.example.net. 300 IN AAAA 2001:db8::10\n"
        ";; Received 72 bytes from 192.0.2.53#53(ns.example.net) in 2 ms\n"
    )
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(exit_code=0, stdout=output, stderr="")
    )

    result = invoke_trace(
        backend,
        {
            "source": "client",
            "name": "www.example.net",
            "record_type": "AAAA",
            "server": "192.0.2.1",
            "timeout_seconds": 5,
        },
    )

    assert backend.command == [
        "dig",
        "+trace",
        "+time=5",
        "+tries=1",
        "@192.0.2.1",
        "www.example.net",
        "AAAA",
    ]
    assert result.server == "192.0.2.1"
    assert result.record_type == "AAAA"
    assert [record.value for record in result.final_answers] == ["2001:db8::10"]


def test_trace_reports_command_failure_without_records() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=9,
            stdout=";; communications error: timed out\n",
            stderr="no servers could be reached",
        )
    )

    result = invoke_trace(
        backend,
        {"source": "client", "name": "www.example.net"},
    )

    assert result.successful is False
    assert result.exit_code == 9
    assert result.stderr == "no servers could be reached"
    assert result.steps == []
    assert result.final_answers == []


def test_trace_does_not_treat_delegation_glue_as_a_final_answer() -> None:
    output = (
        "example.net. 86400 IN NS ns.example.net.\n"
        "ns.example.net. 86400 IN A 192.0.2.53\n"
        ";; Received 100 bytes from 198.41.0.4#53(a.root-servers.net) in 7 ms\n\n"
        "www.example.net. 300 IN CNAME unavailable.example.net.\n"
        ";; Received 70 bytes from 192.0.2.53#53(ns.example.net) in 2 ms\n"
    )
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(exit_code=0, stdout=output, stderr="")
    )

    result = invoke_trace(
        backend,
        {"source": "client", "name": "www.example.net"},
    )

    assert len(result.steps) == 2
    assert any(record.value == "192.0.2.53" for record in result.steps[0].records)
    assert result.final_answers == []


def test_trace_preserves_records_without_a_final_received_line() -> None:
    output = (
        ";; communications error to 192.0.2.53#53: timed out\n"
        "www.example.net. 300 IN A 1.2.3.4\n"
    )
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(exit_code=9, stdout=output, stderr="trace failed")
    )

    result = invoke_trace(
        backend,
        {"source": "client", "name": "www.example.net"},
    )

    assert result.successful is False
    assert result.exit_code == 9
    assert result.stderr == "trace failed"
    assert len(result.steps) == 1
    assert result.steps[0].responding_server is None
    assert result.steps[0].response_time_ms is None
    assert [record.value for record in result.final_answers] == ["1.2.3.4"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("record_type", "INVALID"),
        ("timeout_seconds", 0),
        ("timeout_seconds", 31),
    ],
)
def test_trace_rejects_invalid_arguments_before_execution(
    field: str,
    value: object,
) -> None:
    backend = FakeRuntimeBackend(RuntimeCommandResult(exit_code=0, stdout="", stderr=""))
    arguments: dict[str, object] = {
        "source": "client",
        "name": "www.example.net",
        field: value,
    }

    with pytest.raises(ValidationError):
        invoke_trace(backend, arguments)

    assert backend.command is None
