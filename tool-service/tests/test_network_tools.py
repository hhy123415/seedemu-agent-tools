"""Network-domain tool tests."""

from collections.abc import Sequence

import anyio
import pytest
from pydantic import ValidationError

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.network import register_network_tools


class FakeRuntimeBackend:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.container: str | None = None
        self.command: list[str] | None = None

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(backend="fake", available=True)

    def execute(self, container: str, command: Sequence[str]) -> RuntimeCommandResult:
        self.container = container
        self.command = list(command)
        return RuntimeCommandResult(
            exit_code=self.exit_code,
            stdout="ping output",
            stderr="",
        )


def test_network_domain_registers_its_tools() -> None:
    registry = ToolRegistry()

    register_network_tools(registry, FakeRuntimeBackend())

    definitions = registry.list_tools()
    assert [tool.name for tool in definitions] == [
        "network.inspect_ip_address",
        "network.ping",
    ]
    assert definitions[0].domain == "network"
    assert "address" in definitions[0].input_schema["properties"]
    assert "source" in definitions[1].input_schema["properties"]
    assert "target" in definitions[1].input_schema["properties"]


def test_inspect_ip_address_bound_method() -> None:
    registry = ToolRegistry()
    register_network_tools(registry, FakeRuntimeBackend())

    result = anyio.run(
        registry.invoke,
        "network.inspect_ip_address",
        {"address": "2001:0db8::1"},
    )

    assert result.address == "2001:db8::1"
    assert result.version == 6


def test_ping_reports_reachable_host() -> None:
    backend = FakeRuntimeBackend(exit_code=0)
    registry = ToolRegistry()
    register_network_tools(registry, backend)

    result = anyio.run(
        registry.invoke,
        "network.ping",
        {
            "source": "as150-host-0",
            "target": "10.150.0.71",
            "count": 2,
            "timeout_seconds": 4,
        },
    )

    assert result.reachable is True
    assert backend.container == "as150-host-0"
    assert backend.command == ["ping", "-c", "2", "-W", "4", "10.150.0.71"]


def test_ping_reports_unreachable_host() -> None:
    registry = ToolRegistry()
    register_network_tools(registry, FakeRuntimeBackend(exit_code=1))

    result = anyio.run(
        registry.invoke,
        "network.ping",
        {"source": "source", "target": "192.0.2.1"},
    )

    assert result.reachable is False
    assert result.exit_code == 1


def test_ping_arguments_are_validated_before_execution() -> None:
    registry = ToolRegistry()
    register_network_tools(registry, FakeRuntimeBackend())

    with pytest.raises(ValidationError):
        anyio.run(
            registry.invoke,
            "network.ping",
            {"source": "source", "target": "target", "count": 0},
        )
