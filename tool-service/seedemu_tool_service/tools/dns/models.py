"""Argument and result models for DNS-domain tools."""

from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DNSRecordType = Literal["A", "AAAA", "CNAME", "MX", "NS", "PTR", "SOA", "TXT"]
DNSUpdateOperation = Literal["replace", "delete"]


class ToolArguments(BaseModel):
    """Base model for strict DNS tool argument validation."""

    model_config = ConfigDict(extra="forbid")


class DNSLookupArguments(ToolArguments):
    """Arguments accepted by the DNS lookup tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    name: str = Field(min_length=1, description="Domain name or address to query")
    record_type: DNSRecordType = Field(default="A", description="DNS record type")
    include_details: bool = Field(
        default=False,
        description="Include parsed DNS records, flags, server, and timing metadata",
    )
    include_raw_output: bool = Field(
        default=False,
        description="Include the complete dig output for diagnostics",
    )
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


class DNSRecord(BaseModel):
    """A resource record parsed from a section of regular dig output."""

    name: str
    ttl: int
    record_class: str
    record_type: str
    value: str


class DNSReverseLookupArguments(ToolArguments):
    """Arguments accepted by the IP reverse-lookup tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    address: str = Field(description="Strictly validated IPv4 or IPv6 address")
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

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        """Reject non-IP input and normalize valid IPv4 and IPv6 addresses."""

        return str(ip_address(value))


class DNSReverseLookupResult(BaseModel):
    """Structured result of an IPv4 or IPv6 reverse DNS query."""

    ptr_names: list[str] = Field(default_factory=list)
    reverse_name: str
    response_status: str | None = None
    records: list[DNSRecord] = Field(default_factory=list)
    successful: bool


class DNSLookupDetails(BaseModel):
    """Optional structured diagnostics parsed from a DNS response."""

    flags: list[str] = Field(default_factory=list)
    answer_records: list[DNSRecord] = Field(default_factory=list)
    authority_records: list[DNSRecord] = Field(default_factory=list)
    additional_records: list[DNSRecord] = Field(default_factory=list)
    recursion_available: bool = False
    authenticated_data: bool = False
    query_time_ms: int | None = None
    responding_server: str | None = None


class DNSLookupResult(BaseModel):
    """Compact DNS lookup result with optional diagnostic evidence."""

    command_successful: bool = Field(
        description="Whether dig completed successfully, independent of the DNS response code"
    )
    response_status: str | None = Field(
        default=None,
        description="DNS response code, or timeout when the query timed out",
    )
    authoritative: bool = False
    truncated: bool = False
    canonical_name: str | None = None
    answers: list[str] = Field(
        default_factory=list,
        description="Values from answer records matching the requested record type",
    )
    exit_code: int
    stderr: str
    details: DNSLookupDetails | None = None
    raw_output: str | None = None


class DNSCompareArguments(ToolArguments):
    """Arguments accepted by the multi-resolver comparison tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    name: str = Field(min_length=1, description="Domain name or address to query")
    record_type: DNSRecordType = Field(default="A", description="DNS record type")
    servers: list[str | None] = Field(
        min_length=2,
        description=(
            "DNS servers to compare; use null for the source node's default resolver"
        ),
    )
    timeout_seconds: int = Field(
        default=3,
        ge=1,
        le=30,
        description="Timeout for each DNS server query in seconds",
    )

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, servers: list[str | None]) -> list[str | None]:
        """Reject empty and duplicate server selectors."""

        normalized = [server.strip() if server is not None else None for server in servers]
        if any(server == "" for server in normalized):
            raise ValueError("server addresses must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("servers must be unique")
        return normalized


class DNSCompareServerResult(BaseModel):
    """One server's response included in a DNS comparison."""

    server: str | None = Field(
        description="Queried DNS server, or null for the source node's default resolver"
    )
    command_successful: bool
    response_status: str | None = None
    answers: list[str] = Field(default_factory=list)
    answer_records: list[DNSRecord] = Field(default_factory=list)
    ttls: list[int] = Field(default_factory=list)
    latency_ms: int | None = None
    timed_out: bool = False


class DNSCompareDifference(BaseModel):
    """Presence of one answer value across the queried DNS servers."""

    answer: str
    present_on: list[str | None] = Field(default_factory=list)
    missing_from: list[str | None] = Field(default_factory=list)


class DNSCompareResult(BaseModel):
    """Structured comparison of the same query across DNS servers."""

    source: str
    name: str
    record_type: DNSRecordType
    results: list[DNSCompareServerResult]
    answers_consistent: bool
    common_answers: list[str] = Field(default_factory=list)
    differences: list[DNSCompareDifference] = Field(default_factory=list)
    min_ttl: int | None = None
    max_ttl: int | None = None
    timed_out_servers: list[str | None] = Field(default_factory=list)


class DNSTraceArguments(ToolArguments):
    """Arguments accepted by the DNS delegation trace tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    name: str = Field(min_length=1, description="Domain name to trace")
    record_type: DNSRecordType = Field(
        default="A",
        description="DNS record type requested at the end of the trace",
    )
    server: str | None = Field(
        default=None,
        description=(
            "Optional server used to start the trace; subsequent queries follow "
            "DNS delegations"
        ),
    )
    timeout_seconds: int = Field(
        default=3,
        ge=1,
        le=30,
        description="Timeout for each DNS query in seconds",
    )


class DNSTraceStep(BaseModel):
    """One response received while following the DNS delegation chain."""

    records: list[DNSRecord] = Field(default_factory=list)
    responding_server: str | None = None
    response_time_ms: int | None = None


class DNSTraceResult(BaseModel):
    """Structured result produced by a dig +trace invocation."""

    source: str
    name: str
    record_type: DNSRecordType
    server: str | None
    successful: bool
    exit_code: int
    stderr: str
    steps: list[DNSTraceStep] = Field(default_factory=list)
    final_answers: list[DNSRecord] = Field(default_factory=list)
    raw_output: str


class DNSUpdateArguments(ToolArguments):
    """Arguments accepted by the dynamic DNS update tool."""

    source: str = Field(description="Name or ID of a container that provides nsupdate")
    zone: str = Field(min_length=1, description="DNS zone to update, for example example.net")
    name: str = Field(min_length=1, description="Fully-qualified owner name to update")
    record_type: DNSRecordType = Field(default="A", description="DNS record type")
    operation: DNSUpdateOperation = Field(
        default="replace",
        description="Replace the complete RRset with one value, or delete the complete RRset",
    )
    ttl: int = Field(default=300, ge=0, le=2_147_483_647, description="Record TTL in seconds")
    value: str | None = Field(
        default=None,
        description="Record value; required for replace and omitted for delete",
    )

    @model_validator(mode="after")
    def validate_update(self) -> "DNSUpdateArguments":
        """Reject nsupdate control injection and inconsistent operations."""

        single_token_fields = {
            "source": self.source,
            "zone": self.zone,
            "name": self.name,
        }
        for field_name, field_value in single_token_fields.items():
            if any(character.isspace() for character in field_value):
                raise ValueError(f"{field_name} must not contain whitespace")

        if self.operation == "replace":
            if self.value is None or not self.value.strip():
                raise ValueError("value is required for replace operations")
            if "\n" in self.value or "\r" in self.value:
                raise ValueError("value must not contain line breaks")
        elif self.value is not None:
            raise ValueError("value must be omitted for delete operations")

        return self


class DNSUpdateResult(BaseModel):
    """Result of a dynamic DNS update request."""

    source: str
    zone: str
    name: str
    record_type: DNSRecordType
    operation: DNSUpdateOperation
    ttl: int | None = None
    value: str | None = None
    successful: bool
    exit_code: int
    stderr: str
