"""Argument and result models for BGP-domain tools."""

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    """Base model for strict BGP tool argument validation."""

    model_config = ConfigDict(extra="forbid")


class BGPSummaryArguments(ToolArguments):
    """Arguments accepted by the BGP summary tool."""

    source: str = Field(description="Name or ID of the emulated router container")


class BGPSummaryResult(BaseModel):
    """Result of retrieving a router's BGP summary."""

    source: str
    successful: bool
    output: str
    exit_code: int
    stderr: str
