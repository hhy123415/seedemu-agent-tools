# SEEDemu Agent Tool Service

FastAPI service exposing agent-facing operations for SEED-Emulator.

## Development Setup

From this directory, create and activate a virtual environment:

```bash
python -m venv .venv
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the service and development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the Service

```bash
python -m uvicorn seedemu_tool_service.main:app --reload
```

The service is then available at:

- API: <http://127.0.0.1:8000>
- OpenAPI documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/v1/health>
- Runtime backend: <http://127.0.0.1:8000/api/v1/runtime>
- Tool discovery: <http://127.0.0.1:8000/api/v1/tools>

## Run Tests

```bash
python -m pytest
```

## Run with Docker Compose

The container connects to the host Docker daemon through `/var/run/docker.sock`. This gives
the tool service control over host containers, images, networks, and volumes. Only run the
service from trusted code and do not expose its API to untrusted networks.

On Linux, set `DOCKER_GID` to the group owner of the Docker socket so the non-root application
user can access it:

```bash
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
docker compose up --build
```

With Docker Desktop, start the service directly:

```powershell
docker compose up --build
```

Use the runtime endpoint to verify daemon access:

```bash
curl http://127.0.0.1:8000/api/v1/runtime
```

A healthy response includes `"available": true` and the host Docker daemon version. Stop and
remove the service container with:

```bash
docker compose down
```

## Tool Domains

Tools are grouped into packages under `seedemu_tool_service/tools/`. Each domain exposes one
registration function that binds its functions or methods to the shared `ToolRegistry`.

The network-domain skeleton is organized as follows:

```text
tools/network/
|-- models.py        # Tool argument and result models
|-- tools.py         # Tool function or bound-method implementations
`-- registration.py  # Tool metadata and registry bindings
```

The initial network tools are:

- `network.inspect_ip_address`: normalize an IPv4 or IPv6 address and inspect its properties.
- `network.ping`: execute ICMP echo requests inside a selected emulated source container and
  report whether the target host is reachable.

Both demonstrate bound methods, Pydantic argument validation, domain registration, discovery, and
registry invocation. The ping command is passed to Docker as an argument vector rather than through
a shell. New network tools should follow the same pattern and be added to
`register_network_tools()`.
