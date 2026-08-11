"""HTTP API smoke tests."""

from fastapi.testclient import TestClient

from seedemu_tool_service.api.dependencies import get_runtime_backend
from seedemu_tool_service.main import app
from seedemu_tool_service.models.runtime import RuntimeStatus

client = TestClient(app)


def test_service_info() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "SEEDemu Agent Tool Service",
        "version": "0.1.0",
        "docs_url": "/docs",
    }


def test_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_tool_registry_lists_network_tools() -> None:
    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["tools"][0]["name"] == "network.inspect_ip_address"
    assert body["tools"][0]["domain"] == "network"
    assert body["tools"][1]["name"] == "network.ping"


def test_runtime_status() -> None:
    class AvailableBackend:
        def status(self) -> RuntimeStatus:
            return RuntimeStatus(
                backend="docker",
                available=True,
                daemon_version="test-version",
            )

    app.dependency_overrides[get_runtime_backend] = AvailableBackend
    try:
        response = client.get("/api/v1/runtime")
    finally:
        app.dependency_overrides.pop(get_runtime_backend, None)

    assert response.status_code == 200
    assert response.json() == {
        "backend": "docker",
        "available": True,
        "daemon_version": "test-version",
    }


def test_openapi_includes_public_routes() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
    assert "/api/v1/runtime" in response.json()["paths"]
    assert "/api/v1/tools" in response.json()["paths"]
