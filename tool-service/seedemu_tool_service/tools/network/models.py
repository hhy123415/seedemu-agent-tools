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
