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
