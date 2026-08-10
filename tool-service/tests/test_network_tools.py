"""Network-domain tool tests."""

import anyio

from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.network import register_network_tools


def test_network_domain_registers_its_tools() -> None:
    registry = ToolRegistry()

    register_network_tools(registry)

    definitions = registry.list_tools()
    assert [tool.name for tool in definitions] == ["network.inspect_ip_address"]
    assert definitions[0].domain == "network"
    assert "address" in definitions[0].input_schema["properties"]


def test_inspect_ip_address_bound_method() -> None:
    registry = ToolRegistry()
    register_network_tools(registry)

    result = anyio.run(
        registry.invoke,
        "network.inspect_ip_address",
        {"address": "2001:0db8::1"},
    )

    assert result.address == "2001:db8::1"
    assert result.version == 6
