"""Registry bindings for domain registration DNS tools."""

from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.tool import ToolDefinition
from seedemu_tool_service.registry import ToolRegistry
from seedemu_tool_service.tools.dns.domain_registration.models import (
    DNSConfigureArguments,
    RegistrarFindArguments,
    RegistrarRequestArguments,
)
from seedemu_tool_service.tools.dns.domain_registration.tools import DomainRegistrationTools


def register_domain_registration_tools(registry: ToolRegistry, backend: RuntimeBackend) -> None:
    """Register domain registration DNS tools."""

    tools = DomainRegistrationTools(backend)
    registry.register(
        definition=ToolDefinition(
            name="domain.registrar_find",
            domain="domain",
            description=(
                "Locate Registrar frontends explicitly exposed to the Agent. "
                "Call this before registrar_request; no interface inventory, node "
                "metadata, or secret is returned. The reserved filter argument "
                "must currently be empty."
            ),
        ),
        handler=tools.registrar_find,
        arguments_model=RegistrarFindArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="domain.registrar_request",
            domain="domain",
            description=(
                "Read a discovered Registrar frontend or submit one restricted "
                "same-origin request from an emulated source. Start with GET / and "
                "inspect returned HTML and scripts to understand the interface. "
                "Source is the identity boundary and must be authorized by the caller. "
                "The default authentication=auto reads this source's provisioned token "
                "and establishes a Loom session before the request. Use required to demand "
                "source authentication or none for anonymous requests. No token is returned. "
                "Reuse the returned session_id for cookies across requests, including "
                "login and CSRF forms. Redirects are reported but never followed automatically."
            ),
        ),
        handler=tools.registrar_request,
        arguments_model=RegistrarRequestArguments,
    )
    registry.register(
        definition=ToolDefinition(
            name="dns.configure",
            domain="dns",
            description=(
                "Provision an authorized source-owned Primary/Secondary zone and replace "
                "or delete its RRsets. The selected source authenticates with a private "
                "credential that never leaves that container; both authorities are verified."
            ),
        ),
        handler=tools.configure,
        arguments_model=DNSConfigureArguments,
    )
