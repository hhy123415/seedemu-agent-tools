"""Models describing a runtime backend."""

from pydantic import BaseModel


class RuntimeStatus(BaseModel):
    """Connectivity information for the selected runtime backend."""

    backend: str
    available: bool
    daemon_version: str | None = None


class RuntimeCommandResult(BaseModel):
    """Result of executing a command in an emulated node."""

    exit_code: int
    stdout: str
    stderr: str
