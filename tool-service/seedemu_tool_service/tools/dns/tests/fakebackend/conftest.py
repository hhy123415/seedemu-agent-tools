"""Pytest configuration shared by fake-backend DNS tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Show one PASSED/FAILED line per fake-backend test by default."""

    if config.option.verbose == 0:
        config.option.verbose = 1
