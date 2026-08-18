"""Docker integration tests for comparing DNS resolver responses."""

from collections.abc import Callable
from typing import Any

import anyio
import pytest

from seedemu_tool_service.backends import DockerRuntimeBackend
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools

# The source container's /etc/resolv.conf points at this recursive resolver.
SOURCE_CONTAINER = "as150h-host_1-10.150.0.72"
DEFAULT_RESOLVER = "10.153.0.53"
UNREACHABLE_SERVER = "192.0.2.1"
KNOWN_DOMAIN = "www.example.net"
KNOWN_ADDRESS = "1.2.3.4"


@pytest.fixture(scope="module")
def tool_registry() -> ToolRegistry:
    """Register DNS tools against the running Docker-based emulator."""

    registry = ToolRegistry()
    register_dns_tools(registry, DockerRuntimeBackend())
    return registry


def test_compare_default_and_explicit_resolver_are_consistent(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Compare the default resolver path with the same resolver explicitly."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.compare",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "servers": [None, DEFAULT_RESOLVER],
        },
    )

    show_dns_result(result)

    assert result.answers_consistent is True
    assert result.common_answers == [KNOWN_ADDRESS]
    assert result.differences == []
    assert result.timed_out_servers == []
    assert result.min_ttl is not None and result.min_ttl >= 0
    assert result.max_ttl is not None and result.max_ttl >= result.min_ttl
    assert [server_result.server for server_result in result.results] == [
        None,
        DEFAULT_RESOLVER,
    ]
    assert all(server_result.command_successful for server_result in result.results)
    assert all(
        server_result.response_status == "NOERROR" for server_result in result.results
    )
    assert all(server_result.answers == [KNOWN_ADDRESS] for server_result in result.results)
    assert all(server_result.ttls for server_result in result.results)
    assert all(
        server_result.latency_ms is not None and server_result.latency_ms >= 0
        for server_result in result.results
    )


def test_compare_reports_unreachable_server_and_missing_answer(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Compare a working resolver with a timeout and report the resulting difference."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.compare",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "servers": [DEFAULT_RESOLVER, UNREACHABLE_SERVER],
            "timeout_seconds": 1,
        },
    )

    show_dns_result(result)

    assert result.answers_consistent is False
    assert result.common_answers == []
    assert result.timed_out_servers == [UNREACHABLE_SERVER]
    assert len(result.differences) == 1
    assert result.differences[0].answer == KNOWN_ADDRESS
    assert result.differences[0].present_on == [DEFAULT_RESOLVER]
    assert result.differences[0].missing_from == [UNREACHABLE_SERVER]

    working_result, timeout_result = result.results
    assert working_result.command_successful is True
    assert working_result.response_status == "NOERROR"
    assert working_result.answers == [KNOWN_ADDRESS]
    assert working_result.timed_out is False
    assert timeout_result.command_successful is False
    assert timeout_result.response_status == "timeout"
    assert timeout_result.answers == []
    assert timeout_result.ttls == []
    assert timeout_result.latency_ms is None
    assert timeout_result.timed_out is True
