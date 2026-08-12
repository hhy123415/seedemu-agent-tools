"""Argument and result models for DNS-domain tools."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DNSRecordType = Literal["A", "AAAA", "CNAME", "MX", "NS", "PTR", "SOA", "TXT"]


class ToolArguments(BaseModel):
    """Base model for strict DNS tool argument validation."""

    model_config = ConfigDict(extra="forbid")


class DNSLookupArguments(ToolArguments):
    """Arguments accepted by the DNS lookup tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    name: str = Field(min_length=1, description="Domain name or address to query")
    record_type: DNSRecordType = Field(default="A", description="DNS record type")
    server: str | None = Field(
        default=None,
        description="Optional DNS server address; uses the source node resolver when omitted",
    )
    timeout_seconds: int = Field(
        default=3,
        ge=1,
        le=30,
        description="DNS query timeout in seconds",
    )


class DNSLookupResult(BaseModel):
    """Result of a DNS lookup performed from an emulated node."""

    source: str
    name: str
    record_type: DNSRecordType
    server: str | None
    successful: bool
    answers: list[str]
    exit_code: int
    stderr: str
