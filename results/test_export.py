"""Slice 10: a series' standings and race results as one CSV file, for anyone."""

import csv
import io

import pytest
from django.urls import reverse

from races.models import Finish
from races.scoring import score_series
from races.templatetags.racing import hms, points, tcf
from races.test_final import declare, publish, season  # noqa: F401 (fixtures)
from races.test_audit import post_boat
from races.testing import enter, make_boat, make_committee, make_member, make_race, make_series, record, start
from results.test_scen_005 import scen_005  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db


def download(client, series):
    response = client.get(reverse("results:series_csv", args=[series.pk]))
    assert response.status_code == 200
    return response


def rows_of(response):
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # the byte-order mark Excel needs for UTF-8
    return list(csv.reader(io.StringIO(text[1:])))


def block(rows, heading):
    """The rows after a heading row, up to the next blank line."""
    start = next(i for i, row in enumerate(rows) if row and row[0] == heading) + 1
    end = next((i for i in range(start, len(rows)) if not rows[i]), len(rows))
    return rows[start:end]


def test_anyone_can_download_it_as_a_named_attachment(client, season):
    response = download(client, season["series"])
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == 'attachment; filename="Autumn 2026 results.csv"'


def test_the_standings_match_the_series_page(client, season):
    rows = rows_of(download(client, season["series"]))
    standings = block(rows, "Series Standings")
    assert standings[0] == ["Place", "Sail number", "Boat", "R1", "R2", "Total"]
    results = score_series(season["series"])
    assert standings[1:] == [
        [str(row.position), row.entry.boat.sail_number, row.entry.boat.name,
         *[f"({points(c.points)})" if c.discarded else points(c.points) for c in row.scores], points(row.total)]
        for row in results.standings
    ]


def test_each_race_is_listed_with_its_rows(client, season):
    rows = rows_of(download(client, season["series"]))
    race_2 = next(i for i, row in enumerate(rows) if row and row[0] == "Race 2")
    assert rows[race_2][1:3] == ["30 September 2026", "Start 18:00:00"]
    assert rows[race_2][3].startswith("Published ")
    header, *lines = block(rows, "Race 2")
    assert header == ["Place", "Sail number", "Boat", "Finish time", "Elapsed", "Handicap", "Corrected", "Points", "Code"]
    tern = next(line for line in lines if line[1] == "GBR7")
    assert tern[0] == "" and tern[3] == "" and tern[-1] == "DNF"
    kittiwake = next(line for line in lines if line[1] == "GBR42")
    # Race 2 sails on the handicap race 1 produced, not the base number.
    scored = score_series(season["series"]).races[1].for_entry(season["entries"][0]).result
    assert kittiwake[3:6] == ["19:01:00", "1:01:00", tcf(scored.tcf_used)]
    assert tcf(scored.tcf_used) != "0.805"
    # Race 3 was never sailed: it says so.
    assert ["Race 3", "7 October 2026", "No results recorded yet."] in rows


def test_scen_005_reads_back_from_the_file(client, scen_005):  # noqa: F811
    series, boats = scen_005
    rows = rows_of(download(client, series))
    header, *lines = block(rows, "Race 1")
    results = score_series(series).races[0]
    assert len(lines) == len(results.rows)
    for line, row in zip(lines, results.rows):
        assert line[1] == row.entry.boat.sail_number
        assert line[5:8] == [tcf(row.result.tcf_used), hms(row.result.corrected_time), points(row.result.points)]


def test_it_says_provisional_or_final(client, season):
    assert rows_of(download(client, season["series"]))[1][0].startswith("Provisional standings as at ")
    client.force_login(make_committee())
    declare(client, season["series"])
    assert rows_of(download(client, season["series"]))[1][0].startswith("Final standings (declared ")


def test_a_final_series_file_keeps_its_places_after_a_base_number_change(client, admin_client, season):
    client.force_login(make_committee())
    declare(client, season["series"])
    before = block(rows_of(download(client, season["series"])), "Series Standings")
    post_boat(admin_client, season["entries"][2].boat, base_number="0.600", reason="New certificate")
    assert block(rows_of(download(client, season["series"])), "Series Standings") == before


def test_no_owner_names_or_persons_on_board(client):
    series = make_series()
    owner = make_member("pat@example.com", first_name="Patricia", last_name="Quennell")
    entry = enter(series, make_boat("GBR42", name="Kittiwake", owner=owner, owner_name="Typed Owner"))
    race = make_race(series)
    start(race, entry, persons_on_board=77)
    record(race, entry, "19:05:31")
    text = download(client, series).content.decode()
    for private in ("Patricia", "Quennell", "Typed Owner", "pat@example.com", "77"):
        assert private not in text


def test_a_boat_not_recorded_says_so(client):
    series = make_series()
    a, b = enter(series, make_boat("A1")), enter(series, make_boat("B2"))
    race = make_race(series)
    record(race, a, "19:00:00")
    start(race, b)
    lines = block(rows_of(download(client, series)), "Race 1")[1:]
    assert next(line for line in lines if line[1] == "B2")[-1] == "Not recorded"


@pytest.mark.parametrize("setup", ["no entries", "no races"])
def test_an_empty_series_gives_a_file_that_says_so(client, setup):
    series = make_series("Empty")
    if setup == "no races":
        enter(series, make_boat())
    else:
        make_race(series)
    rows = rows_of(download(client, series))
    assert block(rows, "Series Standings") == [["Nothing is scored in this series yet."]]


def test_an_unsafe_series_name_gives_a_safe_file_name(client):
    series = make_series('Spring "Open" / 2026')
    response = download(client, series)
    assert response["Content-Disposition"] == 'attachment; filename="Spring Open  2026 results.csv"'


def test_the_series_page_links_to_the_download(client, season):
    page = client.get(reverse("results:series", args=[season["series"].pk])).content.decode()
    assert f'href="{reverse("results:series_csv", args=[season["series"].pk])}" download>Download (CSV)' in page
