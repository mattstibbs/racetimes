"""The RYA's worked example (SCEN-005), read back from every results page.

The engine reproduces it on its own (tests/) and through the database
(races/test_scoring.py). What is checked here is that the pages show those
numbers, rounded for display and against the right boat.
"""

from datetime import datetime, timedelta

import pytest
from django.urls import reverse

from races.templatetags.racing import hms, tcf
from races.testing import enter, make_boat, make_race, make_series, record
from tests.scenario_loader import SCENARIOS

pytestmark = pytest.mark.django_db

SCEN_005 = next(s for s in SCENARIOS if s["scenario_id"].startswith("SCEN-005"))


def clock(start, elapsed_seconds):
    moment = datetime.fromisoformat(f"2026-01-01T{start}") + timedelta(seconds=elapsed_seconds)
    return moment.strftime("%H:%M:%S")


@pytest.fixture
def scen_005():
    """Race 1 as the fixture has it, and race 2 scheduled, so boats have a next race."""
    series = make_series("SCEN-005")
    race = make_race(series, start="18:30:00")
    make_race(series, 2)
    boats = {}
    for boat in SCEN_005["boats"]:
        entry = enter(series, make_boat(boat["boat_id"], base_number=boat["start_handicap"]))
        boats[boat["boat_id"]] = entry.boat
        if boat["status"] == "FINISHED":
            record(race, entry, clock("18:30:00", boat["elapsed_seconds"]))
        else:
            record(race, entry, status=boat["status"])
    return series, boats


def row_for(page, boat):
    """The table row that names this boat, from its link to the end of the row."""
    start = page.index(f'{reverse("results:boat", args=[boat.pk])}">{boat}</a>')
    return page[start:page.index("</tr>", start)]


def shown(boat):
    """What the pages should show for one of the fixture's boats."""
    expected = boat["expected"]
    return {
        "place": str(expected["rank"]) if expected["rank"] else boat["status"],
        "handicap": tcf(boat["start_handicap"]),
        "corrected": hms(expected["corrected_seconds"]),
        "next": tcf(expected["handicap_adjusted_next_race"]),
    }


@pytest.mark.parametrize("boat", SCEN_005["boats"], ids=lambda b: b["boat_id"])
def test_the_series_page_shows_the_worked_example(client, scen_005, boat):
    series, boats = scen_005
    page = client.get(reverse("results:series", args=[series.pk]), {"race": 1}).content.decode()
    page = page[page.index('id="race-1"'):]  # the race's table, not the standings
    row = row_for(page, boats[boat["boat_id"]])
    before = page[:page.index(row)].rsplit("<tr", 1)[1]
    figures = shown(boat)
    assert f'<td class="num">{figures["place"]}</td>' in before
    for key in ("handicap", "corrected", "next"):
        assert f">{figures[key]}</td>" in row


@pytest.mark.parametrize("boat", SCEN_005["boats"], ids=lambda b: b["boat_id"])
def test_the_boat_page_shows_the_worked_example(client, scen_005, boat):
    _, boats = scen_005
    page = client.get(reverse("results:boat", args=[boats[boat["boat_id"]].pk])).content.decode()
    figures = shown(boat)
    race_row = page[page.index("?race=1&amp;"):]
    race_row = race_row[:race_row.index("</tr>")]
    assert f'<td class="num">{figures["place"]}</td>' in race_row
    for key in ("handicap", "corrected", "next"):
        assert f">{figures[key]}</td>" in race_row
    assert f'sails race 2 on <strong>{figures["next"]}</strong>.' in page
