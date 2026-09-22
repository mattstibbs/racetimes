"""Loads the scenario fixtures so tests can parametrise over them.

Kept as a plain module rather than living in ``conftest.py`` because
``@pytest.mark.parametrize`` needs the scenario list at import time, and
conftest fixtures are only available once a test is already running. The
conftest wraps these same objects as fixtures for tests that would rather
receive them as arguments.

Reading the file happens here, on the test side of the boundary: ``nhc`` itself
does no I/O and never learns that YAML exists.
"""

from pathlib import Path

import yaml

from nhc import RaceEntry, RaceInput, RaceStatus, RealignmentEntry, SeriesType

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "nhc_test_scenarios.yaml"

#: Scoring codes the spec's RaceStatus admits (section 6).
VALID_STATUSES = frozenset({"FINISHED", "DNC", "DNS", "DNF"})


def load_scenarios(path=FIXTURE_PATH):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


SCENARIOS = load_scenarios()
SCENARIO_IDS = [scenario["scenario_id"] for scenario in SCENARIOS]

#: Scenarios that score a single race. Excludes SCEN-006, which is an
#: end-of-series realignment and has a different shape (base_number +
#: ending_handicap in, realigned_tcf out).
RACE_SCENARIOS = [s for s in SCENARIOS if s.get("calculation") != "REALIGNMENT"]
RACE_SCENARIO_IDS = [s["scenario_id"] for s in RACE_SCENARIOS]

REALIGNMENT_SCENARIOS = [s for s in SCENARIOS if s.get("calculation") == "REALIGNMENT"]
REALIGNMENT_SCENARIO_IDS = [s["scenario_id"] for s in REALIGNMENT_SCENARIOS]

#: Absolute tolerance for comparing the fixtures' 8 d.p. expectations. The spec
#: (section 7) requires full precision be carried through the calculation, so
#: this is deliberately tight; 3 d.p. is a display convention only.
TOLERANCE = 1e-6


def build_race_entries(scenario):
    """Turn a race scenario's boats into RaceEntry objects.

    Lives on the test side because it knows the fixture file's shape, which is
    exactly the kind of knowledge nhc is meant not to have.
    """
    return [
        RaceEntry(
            boat_id=boat["boat_id"],
            status=RaceStatus(boat["status"]),
            tcf_used=boat["start_handicap"],
            elapsed_seconds=boat["elapsed_seconds"],
        )
        for boat in scenario["boats"]
    ]


def build_race_input(scenario, series_type=SeriesType.CLUB):
    """Turn a race scenario into a RaceInput ready to score."""
    return RaceInput(series_type=series_type, entries=build_race_entries(scenario))


def build_realignment_entries(scenario):
    """Turn the realignment scenario's boats into RealignmentEntry objects."""
    return [
        RealignmentEntry(
            boat_id=boat["boat_id"],
            base_number=boat["base_number"],
            ending_handicap=boat["ending_handicap"],
        )
        for boat in scenario["boats"]
    ]


def expected_for(scenario):
    """The scenario's expectations, keyed by boat_id."""
    return {boat["boat_id"]: boat["expected"] for boat in scenario["boats"]}


def race_boat_params(field):
    """(scenario, boat_id) pairs for every boat asserting `field`, plus test ids.

    Lets a test parametrise per boat rather than per scenario, so a failure
    names the one boat that is wrong instead of the whole race.
    """
    params, ids = [], []
    for scenario in RACE_SCENARIOS:
        for boat in scenario["boats"]:
            if field in boat["expected"]:
                params.append((scenario, boat["boat_id"]))
                ids.append(f"{scenario['scenario_id']}-{boat['boat_id']}")
    return params, ids
