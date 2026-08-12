"""PKI-domain tool tests."""

from collections.abc import Sequence

import anyio

from seedemu_tool_service.models.runtime import RuntimeCommandResult, RuntimeStatus
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.pki import register_pki_tools


class FakeRuntimeBackend:
    def __init__(self, result: RuntimeCommandResult | None = None) -> None:
        self.result = result or RuntimeCommandResult(
            exit_code=0,
            stdout="subject=CN=example.test\nissuer=CN=Example CA\n",
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


def test_pki_domain_registers_certificate_tool() -> None:
    registry = ToolRegistry()

    register_pki_tools(registry, FakeRuntimeBackend())

    definitions = registry.list_tools()
    assert [tool.name for tool in definitions] == ["pki.inspect_certificate_file"]
    assert definitions[0].domain == "pki"
    assert set(definitions[0].input_schema["properties"]) == {"source", "path"}


def test_inspect_certificate_executes_openssl_in_source() -> None:
    backend = FakeRuntimeBackend()
    registry = ToolRegistry()
    register_pki_tools(registry, backend)

    result = anyio.run(
        registry.invoke,
        "pki.inspect_certificate_file",
        {"source": "web-server", "path": "/etc/ssl/certs/server.pem"},
    )

    assert backend.container == "web-server"
    assert backend.command == [
        "openssl",
        "x509",
        "-in",
        "/etc/ssl/certs/server.pem",
        "-noout",
        "-subject",
        "-issuer",
        "-serial",
        "-dates",
        "-fingerprint",
        "-sha256",
    ]
    assert result.successful is True
    assert "subject=CN=example.test" in result.details


def test_inspect_certificate_reports_command_failure() -> None:
    backend = FakeRuntimeBackend(
        RuntimeCommandResult(exit_code=1, stdout="", stderr="unable to load certificate")
    )
    registry = ToolRegistry()
    register_pki_tools(registry, backend)

    result = anyio.run(
        registry.invoke,
        "pki.inspect_certificate_file",
        {"source": "web-server", "path": "/missing.pem"},
    )

    assert result.successful is False
    assert result.stderr == "unable to load certificate"
