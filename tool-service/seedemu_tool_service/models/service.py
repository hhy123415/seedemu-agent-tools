"""Models describing the service itself."""

from typing import Literal

from pydantic import BaseModel


class ServiceInfo(BaseModel):
    """Public service metadata."""

    name: str
    version: str
    docs_url: str | None


class HealthResponse(BaseModel):
    """Health-check response."""

    status: Literal["ok"]
    service: str
    version: str
