"""Runtime backend status endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from seedemu_tool_service.api.dependencies import get_runtime_backend
from seedemu_tool_service.backends import RuntimeBackend
from seedemu_tool_service.models.runtime import RuntimeStatus

router = APIRouter(tags=["runtime"])


@router.get("", response_model=RuntimeStatus)
def runtime_status(
    response: Response,
    backend: Annotated[RuntimeBackend, Depends(get_runtime_backend)],
) -> RuntimeStatus:
    """Report whether the configured runtime backend is reachable."""

    backend_status = backend.status()
    if not backend_status.available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return backend_status
