# Tool Service Class Structure

## Application Composition

This diagram shows how the FastAPI application, route modules, dependency providers, registry,
tool domains, and runtime backend are assembled.

```mermaid
flowchart LR
    CreateApp[create_app]
    FastAPIApp[FastAPI application]
    APIRouter[API router]
    HealthRoutes[Health routes]
    ToolRoutes[Tool discovery routes]
    RuntimeRoutes[Runtime routes]
    Dependencies[Dependency providers]
    Registry[ToolRegistry]
    NetworkRegistration[register_network_tools]
    NetworkTools[NetworkTools]
    Backend[DockerRuntimeBackend]

    CreateApp --> FastAPIApp
    FastAPIApp -->|includes| APIRouter
    APIRouter --> HealthRoutes
    APIRouter --> ToolRoutes
    APIRouter --> RuntimeRoutes
    ToolRoutes -->|Depends| Dependencies
    RuntimeRoutes -->|Depends| Dependencies
    Dependencies -->|creates| Registry
    Dependencies -->|creates| Backend
    Dependencies --> NetworkRegistration
    NetworkRegistration -->|registers with| Registry
    NetworkRegistration -->|constructs| NetworkTools
    NetworkTools -->|uses| Backend
```

The dependency-provider module is the composition root. It creates the runtime backend, builds the
registry, and asks each domain to register its tools.

## Registry Classes

The registry keeps agent-visible metadata separate from executable Python callables. A registered
tool combines both pieces and may also hold a Pydantic argument model for invocation-time
validation.

```mermaid
classDiagram
    class ToolRegistry {
        -tools
        +register(definition, handler, arguments_model)
        +list_tools()
        +invoke(name, arguments)
    }

    class RegisteredTool {
        +definition
        +handler
        +arguments_model
    }

    class ToolDefinition {
        +name: str
        +domain: str
        +description: str
        +input_schema: dict
    }

    class ToolHandler {
        <<callable>>
    }

    class PydanticArguments {
        <<BaseModel type>>
        +model_validate(arguments)
        +model_json_schema()
    }

    class ToolListResponse {
        +tools
        +count: int
    }

    ToolRegistry "1" *-- "0..*" RegisteredTool : stores
    RegisteredTool --> ToolDefinition : exposes
    RegisteredTool --> ToolHandler : invokes
    RegisteredTool --> PydanticArguments : validates with
    ToolListResponse o-- ToolDefinition : contains
```

`ToolDefinition` is returned by tool discovery. `ToolHandler` and the argument-model class remain
internal to the service and are used when `ToolRegistry.invoke()` executes a tool.

## Network Domain and Runtime Backend

The network domain owns its argument and result models. `NetworkTools` depends only on the
`RuntimeBackend` protocol, so another backend can replace Docker without changing the tools.

```mermaid
classDiagram
    class NetworkDomainRegistration {
        <<module>>
        +register_network_tools(registry, backend)
    }

    class NetworkTools {
        -backend: RuntimeBackend
        +inspect_ip_address(address) IPAddressInfo
        +ping(source, target, count, timeout_seconds) ReachabilityResult
    }

    class RuntimeBackend {
        <<Protocol>>
        +status() RuntimeStatus
        +execute(container, command) RuntimeCommandResult
    }

    class DockerRuntimeBackend {
        -client
        +status() RuntimeStatus
        +execute(container, command) RuntimeCommandResult
    }

    class InspectIPAddressArguments {
        +address: str
    }

    class IPAddressInfo {
        +address: str
        +version: int
        +is_private: bool
        +is_loopback: bool
        +is_multicast: bool
        +is_global: bool
    }

    class PingArguments {
        +source: str
        +target: str
        +count: int
        +timeout_seconds: int
    }

    class ReachabilityResult {
        +source: str
        +target: str
        +reachable: bool
        +exit_code: int
        +stdout: str
        +stderr: str
    }

    class RuntimeStatus {
        +backend: str
        +available: bool
        +daemon_version: str
    }

    class RuntimeCommandResult {
        +exit_code: int
        +stdout: str
        +stderr: str
    }

    class RuntimeBackendError
    class RuntimeTargetNotFoundError
    class ToolRegistry

    RuntimeBackend <|.. DockerRuntimeBackend : implements
    NetworkTools --> RuntimeBackend : uses
    NetworkDomainRegistration ..> NetworkTools : constructs
    NetworkDomainRegistration ..> ToolRegistry : registers with
    NetworkDomainRegistration ..> InspectIPAddressArguments : publishes schema
    NetworkDomainRegistration ..> PingArguments : publishes schema
    NetworkTools ..> IPAddressInfo : returns
    NetworkTools ..> ReachabilityResult : returns
    DockerRuntimeBackend ..> RuntimeStatus : returns
    DockerRuntimeBackend ..> RuntimeCommandResult : returns
    RuntimeBackendError <|-- RuntimeTargetNotFoundError
    DockerRuntimeBackend ..> RuntimeBackendError : raises
```

## Ping Invocation Sequence

The following sequence connects the class relationships to a concrete invocation of
`network.ping`.

```mermaid
sequenceDiagram
    participant Caller
    participant Registry as ToolRegistry
    participant Arguments as PingArguments
    participant Tools as NetworkTools
    participant Backend as DockerRuntimeBackend
    participant Docker as Docker Engine

    Caller->>Registry: invoke network.ping with arguments
    Registry->>Arguments: model_validate(arguments)
    Arguments-->>Registry: validated values
    Registry->>Tools: ping(source, target, count, timeout)
    Tools->>Backend: execute(source, ping argument vector)
    Backend->>Docker: containers.get(source)
    Docker-->>Backend: source container
    Backend->>Docker: exec_run(ping arguments)
    Docker-->>Backend: exit code, stdout, stderr
    Backend-->>Tools: RuntimeCommandResult
    Tools-->>Registry: ReachabilityResult
    Registry-->>Caller: tool result
```

The ping command is passed as an argument vector rather than a shell command. An exit code of zero
is mapped to `reachable = true`; other ping exit codes are mapped to `reachable = false`.
