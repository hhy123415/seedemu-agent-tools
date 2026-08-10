"""Service health endpoint."""

from fastapi import APIRouter

from seedemu_tool_service import __version__
from seedemu_tool_service.config import get_settings
from seedemu_tool_service.models.service import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report whether the API process is available."""

    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, version=__version__)
