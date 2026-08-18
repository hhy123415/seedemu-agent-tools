"""Fake-backend tests for multi-resolver DNS comparison."""

from collections.abc import Sequence
from typing import Any

import anyio
import pytest
from pydantic import ValidationError

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools
from seedemu_tool_service.tools.dns.models import DNSCompareArguments


def dig_response(server: str, answers: list[tuple[int, str]], latency_ms: int) -> str:
    """Build the relevant parts of a successful dig response."""

    records = "".join(
        f"www.example. {ttl} IN A {answer}\n" for ttl, answer in answers
    )
    return (
        ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\n"
        f";; flags: qr ra; QUERY: 1, ANSWER: {len(answers)}, AUTHORITY: 0, ADDITIONAL: 0\n\n"
        ";; ANSWER SECTION:\n"
        f"{records}\n"
        f";; Query time: {latency_ms} msec\n"
        f";; SERVER: {server}#53({server}) (UDP)\n"
    )


class FakeRuntimeBackend:
    """Return one configured result per queried server."""

    def __init__(self, results: dict[str | None, RuntimeCommandResult]) -> None:
        self.results = results
        self.commands: list[list[str]] = []

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(backend="fake", available=True)

    def execute(self, container: str, command: Sequence[str]) -> RuntimeCommandResult:
        command = list(command)
        self.commands.append(command)
        server_argument = next((part[1:] for part in command if part.startswith("@")), None)
        return self.results[server_argument]


def invoke_compare(backend: FakeRuntimeBackend, arguments: dict[str, object]) -> Any:
    registry = ToolRegistry()
    register_dns_tools(registry, backend)
    return anyio.run(registry.invoke, "dns.compare", arguments)


def test_compare_reports_answer_ttl_latency_and_record_differences() -> None:
    backend = FakeRuntimeBackend(
        {
            None: RuntimeCommandResult(
                exit_code=0,
                stdout=dig_response("10.0.0.53", [(120, "192.0.2.10")], 7),
                stderr="",
            ),
            "10.0.0.54": RuntimeCommandResult(
                exit_code=0,
                stdout=dig_response(
                    "10.0.0.54", [(300, "192.0.2.10"), (300, "192.0.2.11")], 2
                ),
                stderr="",
            ),
        }
    )

    result = invoke_compare(
        backend,
        {
            "source": "client",
            "name": "www.example",
            "servers": [None, "10.0.0.54"],
        },
    )

    assert result.answers_consistent is False
    assert result.common_answers == ["192.0.2.10"]
    assert result.min_ttl == 120
    assert result.max_ttl == 300
    assert result.timed_out_servers == []
    assert result.results[0].latency_ms == 7
    assert result.results[0].ttls == [120]
    assert result.results[1].answers == ["192.0.2.10", "192.0.2.11"]
    assert result.differences[0].answer == "192.0.2.11"
    assert result.differences[0].present_on == ["10.0.0.54"]
    assert result.differences[0].missing_from == [None]
    assert "@10.0.0.54" in backend.commands[1]
    assert not any(part.startswith("@") for part in backend.commands[0])


def test_compare_reports_timeout_and_status_mismatch() -> None:
    backend = FakeRuntimeBackend(
        {
            "10.0.0.53": RuntimeCommandResult(
                exit_code=0,
                stdout=dig_response("10.0.0.53", [], 1),
                stderr="",
            ),
            "10.0.0.99": RuntimeCommandResult(
                exit_code=9,
                stdout=";; communications error to 10.0.0.99#53: timed out\n",
                stderr="no servers could be reached",
            ),
        }
    )

    result = invoke_compare(
        backend,
        {
            "source": "client",
            "name": "www.example",
            "servers": ["10.0.0.53", "10.0.0.99"],
            "timeout_seconds": 5,
        },
    )

    assert result.answers_consistent is False
    assert result.timed_out_servers == ["10.0.0.99"]
    assert result.results[1].response_status == "timeout"
    assert result.results[1].timed_out is True
    assert result.min_ttl is None
    assert result.max_ttl is None
    assert all("+time=5" in command for command in backend.commands)


def test_compare_treats_order_and_ttl_only_changes_as_consistent() -> None:
    backend = FakeRuntimeBackend(
        {
            "10.0.0.53": RuntimeCommandResult(
                exit_code=0,
                stdout=dig_response(
                    "10.0.0.53", [(20, "192.0.2.10"), (20, "192.0.2.11")], 1
                ),
                stderr="",
            ),
            "10.0.0.54": RuntimeCommandResult(
                exit_code=0,
                stdout=dig_response(
                    "10.0.0.54", [(200, "192.0.2.11"), (200, "192.0.2.10")], 1
                ),
                stderr="",
            ),
        }
    )

    result = invoke_compare(
        backend,
        {
            "source": "client",
            "name": "www.example",
            "servers": ["10.0.0.53", "10.0.0.54"],
        },
    )

    assert result.answers_consistent is True
    assert result.differences == []
    assert result.min_ttl == 20
    assert result.max_ttl == 200


@pytest.mark.parametrize(
    "servers",
    [["10.0.0.53"], ["10.0.0.53", "10.0.0.53"], ["10.0.0.53", "  "]],
)
def test_compare_rejects_invalid_server_lists(servers: list[str]) -> None:
    with pytest.raises(ValidationError):
        DNSCompareArguments(source="client", name="www.example", servers=servers)
