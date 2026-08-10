"""Models describing a runtime backend."""

from pydantic import BaseModel


class RuntimeStatus(BaseModel):
    """Connectivity information for the selected runtime backend."""

    backend: str
    available: bool
    daemon_version: str | None = None
