"""Input and output models for network-domain tools."""

from typing import Literal

from pydantic import BaseModel, Field


class InspectIPAddressArguments(BaseModel):
    """Arguments accepted by the IP-address inspection tool."""

    address: str = Field(description="IPv4 or IPv6 address to inspect")


class IPAddressInfo(BaseModel):
    """Normalized properties of an IP address."""

    address: str
    version: Literal[4, 6]
    is_private: bool
    is_loopback: bool
    is_multicast: bool
    is_global: bool


class PingArguments(BaseModel):
    """Arguments accepted by the host-reachability tool."""

    source: str = Field(description="Name or ID of the emulated source container")
    target: str = Field(description="Destination IPv4 address, IPv6 address, or hostname")
    count: int = Field(default=3, ge=1, le=10, description="Number of ICMP echo requests")
    timeout_seconds: int = Field(
        default=2,
        ge=1,
        le=30,
        description="Per-request timeout in seconds",
    )


class ReachabilityResult(BaseModel):
    """Result of an ICMP reachability test."""

    source: str
    target: str
    reachable: bool
    exit_code: int
    stdout: str
    stderr: str
