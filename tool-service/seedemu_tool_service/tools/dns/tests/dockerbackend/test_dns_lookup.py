"""Docker integration tests for structured DNS lookup output."""

from collections.abc import Callable
from typing import Any

import anyio
import pytest

from seedemu_tool_service.backends import DockerRuntimeBackend
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools

# Name or ID of an already-running container that provides the dig command.
SOURCE_CONTAINER = "as150h-host_1-10.150.0.72"
KNOWN_DOMAIN = "www.example.net"
KNOWN_ADDRESS = "1.2.3.4"
NONEXISTENT_DOMAIN = "does-not-exist.example.net"


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


def test_docker_backend_is_available(docker_backend: DockerRuntimeBackend) -> None:
    """Verify that the backend can connect to the Docker daemon."""

    status = docker_backend.status()

    assert status.available is True, "Docker daemon is unavailable"
    assert status.backend == "docker"
    assert status.daemon_version


def test_lookup_resolves_known_domain(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify the default structured result resolves the known A record."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {"source": SOURCE_CONTAINER, "name": KNOWN_DOMAIN},
    )

    show_dns_result(result)

    assert result.command_successful is True, result.stderr
    assert result.response_status == "NOERROR"
    assert result.authoritative is False
    assert result.truncated is False
    assert result.canonical_name is None
    assert result.exit_code == 0
    assert result.answers == [KNOWN_ADDRESS]
    assert result.details is None
    assert result.raw_output is None


def test_lookup_returns_no_answers_for_nxdomain(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify that a nonexistent DNS name has NXDOMAIN semantics."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {"source": SOURCE_CONTAINER, "name": NONEXISTENT_DOMAIN},
    )

    show_dns_result(result)

    assert result.command_successful is True, result.stderr
    assert result.response_status == "NXDOMAIN"
    assert result.exit_code == 0
    assert result.answers == []
    assert result.details is None
    assert result.raw_output is None


def test_lookup_distinguishes_nodata_from_nxdomain(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify an existing name without the requested RR type returns NODATA semantics."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "record_type": "TXT",
        },
    )

    show_dns_result(result)

    assert result.command_successful is True, result.stderr
    assert result.response_status == "NOERROR"
    assert result.exit_code == 0
    assert result.answers == []
    assert result.details is None
    assert result.raw_output is None


def test_lookup_reports_query_timeout(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify that a query timeout is reported as a command failure."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "server": "192.0.2.1",
            "timeout_seconds": 1,
        },
    )

    show_dns_result(result)

    assert result.command_successful is False
    assert result.response_status == "timeout"
    assert result.exit_code != 0
    assert result.answers == []
    assert result.details is None
    assert result.raw_output is None


def test_lookup_can_include_raw_output(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify raw dig output can be included without changing structured fields."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "include_details": True,
            "include_raw_output": True,
        },
    )

    show_dns_result(result)

    assert result.command_successful is True, result.stderr
    assert result.exit_code == 0
    assert result.response_status == "NOERROR"
    assert result.authoritative is False
    assert result.truncated is False
    assert result.canonical_name is None
    assert result.details is not None
    assert "qr" in result.details.flags
    assert result.details.recursion_available is True
    assert result.details.answer_records
    assert any(
        record.record_type == "A" and record.value == KNOWN_ADDRESS
        for record in result.details.answer_records
    )
    assert result.details.query_time_ms is not None
    assert result.details.query_time_ms >= 0
    assert result.details.responding_server
    assert result.raw_output is not None
    assert ";; ANSWER SECTION:" in result.raw_output
    assert KNOWN_ADDRESS in result.raw_output


def test_lookup_can_include_nxdomain_raw_output(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify diagnostic output retains the raw NXDOMAIN response."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": SOURCE_CONTAINER,
            "name": NONEXISTENT_DOMAIN,
            "include_raw_output": True,
        },
    )

    show_dns_result(result)

    assert result.command_successful is True, result.stderr
    assert result.exit_code == 0
    assert result.response_status == "NXDOMAIN"
    assert result.answers == []
    assert result.details is None
    assert result.raw_output is not None
    assert "status: NXDOMAIN" in result.raw_output


def test_lookup_can_include_timeout_raw_output(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Verify diagnostic output retains information from a timed-out query."""

    result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": SOURCE_CONTAINER,
            "name": KNOWN_DOMAIN,
            "include_raw_output": True,
            "server": "192.0.2.1",
            "timeout_seconds": 1,
        },
    )

    show_dns_result(result)

    assert result.command_successful is False
    assert result.response_status == "timeout"
    assert result.answers == []
    assert result.exit_code != 0
    assert result.details is None
    assert result.raw_output or result.stderr.strip()
