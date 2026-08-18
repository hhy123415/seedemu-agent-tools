"""Fake-backend tests for DNS lookup command and response semantics."""

from collections.abc import Sequence
from typing import Any

import anyio

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools


class FakeRuntimeBackend:
    """Return a fixed dig result without requiring the emulator."""

    def __init__(self, result: RuntimeCommandResult) -> None:
        self.result = result
        self.command: list[str] | None = None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(backend="fake", available=True)

    def execute(
        self, container: str, command: Sequence[str]
    ) -> RuntimeCommandResult:
        self.command = list(command)
        return self.result


def invoke_lookup(
    backend: FakeRuntimeBackend,
    arguments: dict[str, object],
) -> Any:
    """Register and invoke dns.lookup through the same path used by clients."""

    registry = ToolRegistry()
    register_dns_tools(registry, backend)
    return anyio.run(registry.invoke, "dns.lookup", arguments)


def test_lookup_distinguishes_nxdomain_from_command_failure() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 1\n"
                ";; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, "
                "ADDITIONAL: 0\n"
            ),
            stderr="",
        )
    )

    result = invoke_lookup(
        backend,
        {"source": "client", "name": "missing.example"},
    )

    assert "+short" not in (backend.command or [])
    assert result.command_successful is True
    assert result.response_status == "NXDOMAIN"
    assert result.answers == []
    assert result.details is None
    assert result.raw_output is None


def test_lookup_exposes_records_flags_cname_and_requested_answer() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 2\n"
                ";; flags: qr aa tc rd ra ad; QUERY: 1, ANSWER: 2, AUTHORITY: 0, "
                "ADDITIONAL: 0\n\n"
                ";; ANSWER SECTION:\n"
                "www.example. 300 IN CNAME target.example.\n"
                "target.example. 300 IN A 192.0.2.10\n\n"
            ),
            stderr="",
        )
    )

    result = invoke_lookup(
        backend,
        {
            "source": "client",
            "name": "www.example",
            "record_type": "A",
            "include_details": True,
        },
    )

    assert result.command_successful is True
    assert result.response_status == "NOERROR"
    assert result.authoritative is True
    assert result.truncated is True
    assert result.canonical_name == "target.example"
    assert result.answers == ["192.0.2.10"]
    assert result.details is not None
    assert [record.record_type for record in result.details.answer_records] == [
        "CNAME",
        "A",
    ]
    assert result.details.flags == ["qr", "aa", "tc", "rd", "ra", "ad"]
    assert result.details.recursion_available is True
    assert result.details.authenticated_data is True
    assert result.raw_output is None


def test_lookup_reports_timeout_separately_from_dns_status() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=9,
            stdout=";; communications error to 192.0.2.1#53: timed out\n",
            stderr="no servers could be reached",
        )
    )

    result = invoke_lookup(
        backend,
        {"source": "client", "name": "www.example"},
    )

    assert result.command_successful is False
    assert result.response_status == "timeout"
    assert result.answers == []


def test_lookup_can_include_raw_output_for_diagnostics() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(
            exit_code=0,
            stdout=(
                ";; ->>HEADER<<- opcode: QUERY, status: REFUSED, id: 3\n"
                ";; flags: qr; QUERY: 1, ANSWER: 0, AUTHORITY: 0, ADDITIONAL: 0\n"
            ),
            stderr="",
        )
    )

    result = invoke_lookup(
        backend,
        {
            "source": "client",
            "name": "www.example",
            "include_details": True,
            "include_raw_output": True,
        },
    )

    assert result.command_successful is True
    assert result.response_status == "REFUSED"
    assert result.answers == []
    assert result.details is not None
    assert result.details.flags == ["qr"]
    assert result.details.answer_records == []
    assert result.raw_output is not None
    assert "status: REFUSED" in result.raw_output
