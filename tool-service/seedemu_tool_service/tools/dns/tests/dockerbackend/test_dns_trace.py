"""Docker integration tests for the DNS delegation trace tool."""

from collections.abc import Callable
from typing import Any

import anyio
import pytest

from seedemu_tool_service.backends import DockerRuntimeBackend
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools

# Name or ID of an already-running container that provides the dig command.
SOURCE_CONTAINER = "as150h-host_1-10.150.0.72"
STARTING_SERVER = "10.153.0.53"
KNOWN_DOMAIN = "www.example.net"
KNOWN_ADDRESS = "1.2.3.4"


@pytest.fixture(scope="module")
def docker_backend() -> DockerRuntimeBackend:
    """Create the real Docker backend shared by this test module."""

    return DockerRuntimeBackend()


@pytest.fixture(scope="module")
def tool_registry(docker_backend: DockerRuntimeBackend) -> ToolRegistry:
    """Register the DNS tools with the real Docker runtime backend."""

    registry = ToolRegistry()
    register_dns_tools(registry, docker_backend)
    return registry


def test_trace_returns_delegation_steps_and_final_answer(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    result = anyio.run(
        tool_registry.invoke,
        "dns.trace",
        {"source": SOURCE_CONTAINER, "name": KNOWN_DOMAIN},
    )

    show_dns_result(result)

    assert result.successful is True, result.stderr
    assert result.exit_code == 0
    assert len(result.steps) >= 4
    assert all(step.responding_server for step in result.steps)
    assert all(
        step.response_time_ms is not None and step.response_time_ms >= 0
        for step in result.steps
    )
    assert any(
        record.record_type == "NS"
        for step in result.steps[:-1]
        for record in step.records
    )
    assert any(
        record.record_type == "A" and record.value == KNOWN_ADDRESS
        for record in result.final_answers
    )
    assert KNOWN_DOMAIN in result.raw_output
    assert ";; Received" in result.raw_output


def test_trace_can_start_from_a_specific_server(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    result = anyio.run(
        tool_registry.invoke,
        "dns.trace",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "server": STARTING_SERVER,
            "timeout_seconds": 5,
        },
    )

    show_dns_result(result)

    assert result.successful is True, result.stderr
    assert result.exit_code == 0
    assert result.server == STARTING_SERVER
    assert result.steps
    assert any(record.value == KNOWN_ADDRESS for record in result.final_answers)


def test_trace_reports_unreachable_starting_server(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    result = anyio.run(
        tool_registry.invoke,
        "dns.trace",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "server": "192.0.2.1",
            "timeout_seconds": 1,
        },
    )

    show_dns_result(result)

    assert result.successful is False
    assert result.exit_code != 0
    assert result.steps == []
    assert result.final_answers == []
    assert result.raw_output or result.stderr.strip()
