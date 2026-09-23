"""Well-formedness checks on the scenario fixtures themselves.

The fixtures are the specification the engine is built against, so a typo in
them is worse than a bug in the code: it silently moves the target. These
checks are cheap and catch the structural mistakes - a duplicated scenario id,
a status outside the spec's vocabulary, a boat with no expectations - before
they can be mistaken for engine failures.
"""

import pytest

from tests.scenario_loader import (
    RACE_SCENARIOS,
    RACE_SCENARIO_IDS,
    REALIGNMENT_SCENARIOS,
    REALIGNMENT_SCENARIO_IDS,
    SCENARIOS,
    SCENARIO_IDS,
    VALID_STATUSES,
)


def test_fixtures_load():
    assert SCENARIOS, "no scenarios loaded; check tests/fixtures/"


def test_scenario_ids_are_unique():
    duplicates = {i for i in SCENARIO_IDS if SCENARIO_IDS.count(i) > 1}
    assert not duplicates, f"duplicate scenario ids: {sorted(duplicates)}"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=SCENARIO_IDS)
def test_scenario_is_described(scenario):
    assert scenario.get("description", "").strip(), "every scenario needs a description"
    assert scenario.get("boats"), "every scenario needs boats"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=SCENARIO_IDS)
def test_boat_ids_are_unique_within_a_scenario(scenario):
    ids = [boat["boat_id"] for boat in scenario["boats"]]
    assert len(ids) == len(set(ids)), f"duplicate boat_id in {scenario['scenario_id']}"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=SCENARIO_IDS)
def test_every_boat_has_expectations(scenario):
    for boat in scenario["boats"]:
        assert boat.get("expected"), f"{boat['boat_id']} has no expected values"


@pytest.mark.parametrize("scenario", RACE_SCENARIOS, ids=RACE_SCENARIO_IDS)
def test_race_scenarios_use_spec_statuses(scenario):
    for boat in scenario["boats"]:
        status = boat.get("status")
        assert status in VALID_STATUSES, (
            f"{boat['boat_id']} has status {status!r}; the spec admits "
            f"{sorted(VALID_STATUSES)}"
        )


@pytest.mark.parametrize("scenario", RACE_SCENARIOS, ids=RACE_SCENARIO_IDS)
def test_finishers_have_a_positive_elapsed_time(scenario):
    """Spec section 7: FINISHED with elapsed <= 0 is invalid input."""
    for boat in scenario["boats"]:
        if boat["status"] == "FINISHED":
            assert boat["elapsed_seconds"] > 0, f"{boat['boat_id']} finished in <= 0s"
        else:
            assert not boat["elapsed_seconds"], (
                f"{boat['boat_id']} is {boat['status']} but has an elapsed time"
            )


@pytest.mark.parametrize("scenario", RACE_SCENARIOS, ids=RACE_SCENARIO_IDS)
def test_handicaps_are_positive(scenario):
    """Spec section 7: TCF <= 0 is invalid input - every formula divides by it."""
    for boat in scenario["boats"]:
        assert boat["start_handicap"] > 0, f"{boat['boat_id']} has a non-positive TCF"


@pytest.mark.parametrize("scenario", REALIGNMENT_SCENARIOS, ids=REALIGNMENT_SCENARIO_IDS)
def test_realignment_scenarios_have_base_numbers(scenario):
    for boat in scenario["boats"]:
        assert boat["base_number"] > 0, f"{boat['boat_id']} has a non-positive BN"
        assert boat["ending_handicap"] > 0, f"{boat['boat_id']} has a non-positive EH"
        assert "realigned_tcf" in boat["expected"]
