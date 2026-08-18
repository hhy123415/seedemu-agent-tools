"""Docker integration test for updating and resolving a DNS A record."""

from collections.abc import Callable
from typing import Any

import anyio
import pytest

from seedemu_tool_service.backends import DockerRuntimeBackend
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns import register_dns_tools

# The google.com primary server also provides nsupdate; nsupdate discovers it via SOA.
UPDATE_SOURCE_CONTAINER = "as162h-google.com-10.162.0.71"
# A separate emulated host from which the updated record is queried with dig.
LOOKUP_SOURCE_CONTAINER = "as150h-host_1-10.150.0.72"
AUTHORITATIVE_SERVER = "10.162.0.71"
ZONE = "google.com"
RECORD_NAME = "www.google.com"
UPDATED_ADDRESS = "2.3.4.5"


@pytest.fixture(scope="module")
def tool_registry() -> ToolRegistry:
    """Register DNS tools against the running Docker-based emulator."""

    registry = ToolRegistry()
    register_dns_tools(registry, DockerRuntimeBackend())
    return registry


def test_update_google_address_and_resolve_from_another_source(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Update www.google.com and verify it directly against its authority."""

    update_result = anyio.run(
        tool_registry.invoke,
        "dns.update",
        {
            "source": UPDATE_SOURCE_CONTAINER,
            "zone": ZONE,
            "name": RECORD_NAME,
            "record_type": "A",
            "operation": "replace",
            "ttl": 1,
            "value": UPDATED_ADDRESS,
        },
    )

    show_dns_result(update_result)

    assert update_result.successful is True, (
        f"DNS update failed: stderr={update_result.stderr!r}"
    )
    assert update_result.exit_code == 0

    lookup_result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": LOOKUP_SOURCE_CONTAINER,
            "server": AUTHORITATIVE_SERVER,
            "name": RECORD_NAME,
            "record_type": "A",
        },
    )

    show_dns_result(lookup_result)

    assert lookup_result.command_successful is True, lookup_result.stderr
    assert lookup_result.response_status == "NOERROR"
    assert lookup_result.exit_code == 0
    assert lookup_result.answers == [UPDATED_ADDRESS]


def test_delete_google_address_from_another_source_and_verify(
    tool_registry: ToolRegistry,
    show_dns_result: Callable[[Any], None],
) -> None:
    """Delete www.google.com's A RRset from another source and verify removal."""

    delete_result = anyio.run(
        tool_registry.invoke,
        "dns.update",
        {
            "source": LOOKUP_SOURCE_CONTAINER,
            "zone": ZONE,
            "name": RECORD_NAME,
            "record_type": "A",
            "operation": "delete",
        },
    )

    show_dns_result(delete_result)

    assert delete_result.successful is True, (
        f"DNS delete failed: stderr={delete_result.stderr!r}"
    )
    assert delete_result.exit_code == 0

    lookup_result = anyio.run(
        tool_registry.invoke,
        "dns.lookup",
        {
            "source": UPDATE_SOURCE_CONTAINER,
            "server": AUTHORITATIVE_SERVER,
            "name": RECORD_NAME,
            "record_type": "A",
        },
    )

    show_dns_result(lookup_result)

    assert lookup_result.command_successful is True, lookup_result.stderr
    assert lookup_result.response_status in {"NOERROR", "NXDOMAIN"}
    assert lookup_result.exit_code == 0
    assert lookup_result.answers == []
