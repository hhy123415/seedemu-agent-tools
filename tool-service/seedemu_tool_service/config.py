"""Application configuration."""

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    """Static settings for the initial service skeleton."""

    app_name: str = "SEEDemu Agent Tool Service"
    api_v1_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide application settings."""

    return Settings()
