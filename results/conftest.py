"""pytest fixtures for the results app's tests.

It re-exports races/conftest.py's fixtures, including the autouse ones, since
that conftest only reaches tests under races/.
"""

import pytest

from races.conftest import (  # noqa: F401
    admin_user,
    committee,
    committee_client,
    fast_password_hashing,
    plain_csrf_tokens,
    run_on_commit,
    season,
    single_club,
    staff_client,
    staff_user,
)
from races.testing import enter, finish_clock, make_boat, make_race, make_series, record
from tests.scenario_loader import SCEN_005


@pytest.fixture
def scen_005():
    """Race 1 as the fixture has it, and race 2 scheduled, so boats have a next race."""
    series = make_series("SCEN-005")
    race = make_race(series, start="18:30:00")
    make_race(series, 2)
    boats = {}
    for boat in SCEN_005["boats"]:
        entry = enter(
            series, make_boat(boat["boat_id"], base_number=boat["start_handicap"])
        )
        boats[boat["boat_id"]] = entry.boat
        if boat["status"] == "FINISHED":
            record(race, entry, finish_clock("18:30:00", boat["elapsed_seconds"]))
        else:
            record(race, entry, status=boat["status"])
    return series, boats
