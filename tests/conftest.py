"""Shared pytest fixtures for the scoring engine's tests."""

import pytest

from tests import scenario_loader


@pytest.fixture(scope="session")
def scenarios():
    """Every scenario in tests/fixtures/, in file order."""
    return scenario_loader.SCENARIOS


@pytest.fixture(scope="session")
def scenarios_by_id():
    """Scenarios keyed by scenario_id, for tests that want one by name."""
    return {s["scenario_id"]: s for s in scenario_loader.SCENARIOS}


@pytest.fixture(scope="session")
def tolerance():
    """Absolute tolerance for float comparisons against the fixtures."""
    return scenario_loader.TOLERANCE
