"""Argument and result models for PKI-domain tools."""

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    """Base model for strict PKI tool argument validation."""

    model_config = ConfigDict(extra="forbid")


class InspectCertificateFileArguments(ToolArguments):
    """Arguments accepted by the certificate-file inspection tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    path: str = Field(min_length=1, description="Certificate path inside the source container")


class CertificateInspectionResult(BaseModel):
    """Result of inspecting an X.509 certificate file."""

    source: str
    path: str
    successful: bool
    details: str
    exit_code: int
    stderr: str
