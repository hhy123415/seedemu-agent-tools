"""Registration entry point for PKI-domain tools."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.pki.models import InspectCertificateFileArguments
from seedemu_tool_service.tools.pki.tools import PKITools


def register_pki_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Create the PKI tool set and register its handlers."""

    tools = PKITools(backend)
    registry.register(
        definition=ToolDefinition(
            name="pki.inspect_certificate_file",
            domain="pki",
            description="Inspect an X.509 certificate file inside an emulated node.",
        ),
        handler=tools.inspect_certificate_file,
        arguments_model=InspectCertificateFileArguments,
    )
