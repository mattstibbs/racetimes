"""Slice 24, part B: a Portsmouth Yardstick series, read back from the pages.

The worked examples PY-1 and PY-2 (tests/fixtures/portsmouth_yardstick.yaml,
checked by the project owner) are entered as clock times, as SCEN-005 is, and the
pages must show them: the number each boat raced on under a heading that says
PN, the corrected time rounded for display, places decided on the full value,
and no next handicap, because none can move.
"""

import csv
import io
import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from races.models import Boat, Series
from races.templatetags.racing import hms
from races.testing import (
    enter,
    finish_clock,
    make_boat,
    make_committee,
    make_member,
    make_py_series,
    make_race,
    make_series,
    publish,
    record,
)
from tests.scenario_loader import PORTSMOUTH_YARDSTICK_FIXTURE

pytestmark = pytest.mark.django_db

PY_1 = PORTSMOUTH_YARDSTICK_FIXTURE["PY-1"]
PY_2 = PORTSMOUTH_YARDSTICK_FIXTURE["PY-2"]


def series_page(client, series, **query):
    return client.get(
        reverse("results:series", args=[series.pk]), query
    ).content.decode()


def race_table(page, number):
    """Just race ``number``'s table, not the standings or another race."""
    start = page.index(f'id="race-{number}"')
    return page[start : page.index("</table>", start)]


def row_for(table, boat):
    start = table.index(f'{reverse("results:boat", args=[boat.pk])}">{boat}</a>')
    return table[start : table.index("</tr>", start)]


def cells(row):
    return re.findall(r"<td[^>]*>(.*?)</td>", row)


# --- The series page --------------------------------------------------------------------------


@pytest.mark.parametrize("example_id", ["PY-1", "PY-2"])
def test_the_series_page_shows_the_worked_example(client, example_id):
    example = PORTSMOUTH_YARDSTICK_FIXTURE[example_id]
    series, entries, races = make_py_series(example)
    for race, race_example in zip(races, example["races"], strict=True):
        table = race_table(series_page(client, series, race=race.number), race.number)
        for letter, want in race_example["expected"].items():
            row = row_for(table, entries[letter].boat)
            before = table[: table.index(row)].rsplit("<tr", 1)[1]
            place = str(want["place"]) if "place" in want else "DNF"
            assert f'<td class="num">{place}</td>' in before, (letter, place)
            assert f'<td class="num detail">{example["boats"][letter]}</td>' in row
            if "corrected" in want:
                assert f'<td class="num">{hms(want["corrected"])}</td>' in row
            points = f"{want['points']:g}"
            assert f'<td class="num">{points}</td>' in row, (letter, points)


def test_the_race_table_is_headed_pn_and_has_no_next_handicap_column(client):
    series, _, _ = make_py_series(PY_1)
    table = race_table(series_page(client, series, race=1), 1)
    assert '<th class="num detail">PN</th>' in table
    assert "Next handicap" not in table and ">Handicap<" not in table
    assert "&dagger;" not in table


def test_the_series_page_says_which_system_it_is_scored_under(client):
    series, _, _ = make_py_series(PY_1)
    page = series_page(client, series)
    assert "Scored under Portsmouth Yardstick" in page
    assert "each boat races on one fixed number, so no handicap changes" in page
    assert "Handicaps adjusted" not in page


def test_two_boats_a_hair_apart_show_the_same_time_but_not_the_same_place(client):
    """PY-2: F and G are 0.386 s apart, shown alike; places use the full value."""
    series, entries, _ = make_py_series(PY_2)
    table = race_table(series_page(client, series, race=1), 1)
    f_row, g_row = row_for(table, entries["F"].boat), row_for(table, entries["G"].boat)
    assert '<td class="num">1:08:10</td>' in f_row
    assert '<td class="num">1:08:10</td>' in g_row
    f_before = table[: table.index(f_row)].rsplit("<tr", 1)[1]
    g_before = table[: table.index(g_row)].rsplit("<tr", 1)[1]
    assert '<td class="num">3</td>' in f_before
    assert '<td class="num">4</td>' in g_before


def test_a_tie_shares_its_place_and_points(client):
    series, entries, _ = make_py_series(PY_2)
    table = race_table(series_page(client, series, race=1), 1)
    for letter in ("D", "E"):
        row = row_for(table, entries[letter].boat)
        before = table[: table.index(row)].rsplit("<tr", 1)[1]
        assert '<td class="num">1</td>' in before
        assert '<td class="num">1.5</td>' in row


def test_the_standings_match_the_worked_example(client):
    series, entries, _ = make_py_series(PY_1)
    page = series_page(client, series)
    standings = page[page.index("<table") : page.index("</table>")]
    rows = re.findall(r"<tr>(.*?)</tr>", standings, re.S)[1:]
    for row, want in zip(rows, PY_1["standings"], strict=True):
        assert entries[want["boat"]].boat.name in row
        assert (
            f'<td class="num">{want["position"]}</td>'
            in row.split("</td>")[0] + "</td>"
        )
        assert f"{want['total']:g}" in row


# --- The boat page ------------------------------------------------------------------------------


@pytest.mark.parametrize("letter", ["A", "B", "C"])
def test_the_boat_page_shows_the_worked_example(client, letter):
    _, entries, _ = make_py_series(PY_1)
    boat = entries[letter].boat
    page = client.get(reverse("results:boat", args=[boat.pk])).content.decode()
    number = PY_1["boats"][letter]
    assert f"Portsmouth Number {number}." in page
    assert f"sails on PN <strong>{number}</strong> for the whole series" in page
    for race_number, race in enumerate(PY_1["races"], start=1):
        want = race["expected"][letter]
        row = page[page.index(f"?race={race_number}&amp;") :]
        row = row[: row.index("</tr>")]
        assert f'<td class="num">{number}</td>' in row
        assert f'<td class="num">{want["points"]:g}</td>' in row
        if "corrected" in want:
            assert f'<td class="num detail">{hms(want["corrected"])}</td>' in row


def test_the_boat_page_has_no_next_column_and_no_next_handicap_box(client):
    _, entries, _ = make_py_series(PY_1)
    boat = entries["A"].boat
    page = client.get(reverse("results:boat", args=[boat.pk])).content.decode()
    assert '<th class="num">PN</th>' in page
    assert '<th class="num">Next</th>' not in page
    assert "its base number" not in page and "handicap after race" not in page


def test_a_boat_in_both_kinds_of_series_shows_each_correctly(client):
    nhc = make_series("Autumn")
    py_series = make_series("Gaffers", handicap_system="PY")
    boat = make_boat("GBR1", base_number="0.964", py_number=1010, name="Both")
    other = make_boat("GBR2", base_number="0.900", py_number=1100, name="Other")
    for series in (nhc, py_series):
        race = make_race(series, start="18:30:00")
        record(race, enter(series, boat), finish_clock("18:30:00", 3600))
        record(race, enter(series, other), finish_clock("18:30:00", 3700))
    page = client.get(reverse("results:boat", args=[boat.pk])).content.decode()
    assert "Base number 0.964." in page and "Portsmouth Number 1010." in page
    autumn = page[page.index("Autumn</a>") : page.index("Gaffers</a>")]
    gaffers = page[page.index("Gaffers</a>") :]
    assert '<th class="num">Handicap</th><th class="num">Next</th>' in autumn
    assert '<th class="num">PN</th>' in gaffers and "Next</th>" not in gaffers
    assert "sails on PN <strong>1010</strong>" in page


# --- Nothing changes for NHC --------------------------------------------------------------------


def test_nhc_pages_keep_their_headings_and_columns(client):
    series = make_series("Autumn")
    race = make_race(series, start="18:30:00")
    for sail, base, elapsed in [("GBR1", "0.964", 3500), ("GBR2", "0.900", 3600)]:
        record(
            race,
            enter(series, make_boat(sail, base_number=base)),
            finish_clock("18:30:00", elapsed),
        )
    page = series_page(client, series, race=1)
    table = race_table(page, 1)
    assert '<th class="num detail">Handicap</th>' in table
    assert '<th class="num detail">Next handicap</th>' in table
    assert "Scored under RYA NHC." in page


# --- The CSV --------------------------------------------------------------------------------------


def read_csv(client, series):
    response = client.get(reverse("results:series_csv", args=[series.pk]))
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_the_csv_is_headed_pn_with_whole_numbers(client):
    series, _, _ = make_py_series(PY_1)
    rows = read_csv(client, series)
    header = next(row for row in rows if "Corrected" in row)
    assert header == [
        "Place", "Sail number", "Boat", "Finish time", "Elapsed", "PN",
        "Corrected", "Points", "Code",
    ]  # fmt: skip
    first = rows[rows.index(header) + 1]
    assert first[2] == "Boat B" and first[5] == "1072"
    assert "Handicap" not in {cell for row in rows for cell in row}


# --- Pages that must not break ------------------------------------------------------------------


def test_the_home_page_lists_a_portsmouth_series_and_its_latest_race(client):
    series, _, races = make_py_series(PY_1)
    publish(*races)
    response = client.get(reverse("results:home"))
    assert response.status_code == 200
    assert series.name in response.content.decode()


def test_a_portsmouth_series_that_cant_be_scored_says_so_on_every_page(client):
    series, entries, _ = make_py_series(PY_1)
    Boat.objects.filter(pk=entries["B"].boat.pk).update(py_number=None)
    boat = entries["A"].boat
    for url in (
        reverse("results:series", args=[series.pk]),
        reverse("results:boat", args=[boat.pk]),
        reverse("results:home"),
        reverse("results:series_csv", args=[series.pk]),
    ):
        response = client.get(url)
        assert response.status_code == 200, url
    page = series_page(client, series)
    assert "Boat B (PYB) has no Portsmouth Number (PN)" in page


def test_settings_that_got_past_the_forms_are_never_quietly_ignored(client):
    series, _, _ = make_py_series(PY_1)
    Series.objects.filter(pk=series.pk).update(nhc_cap_extremes=True)
    page = series_page(client, series)
    assert "can&#x27;t use extreme-result capping" in page


@pytest.fixture
def committee():
    office = Client()
    office.force_login(make_committee())
    return office


def test_the_race_day_page_works_for_a_portsmouth_series(committee):
    _, _, races = make_py_series(PY_1)
    page = committee.get(
        reverse("races:race_day", args=[races[0].pk]), {"view": "finish"}
    ).content.decode()
    assert "Publish results" in page
    assert "TCF" not in page


def test_the_final_results_page_works_for_a_portsmouth_series(committee):
    series, _, races = make_py_series(PY_1)
    publish(*races)
    page = committee.get(reverse("races:final", args=[series.pk])).content.decode()
    assert "Ready to declare final" in page
    assert "Boat B" in page


def test_the_results_email_doesnt_mention_handicaps_for_a_portsmouth_series(
    committee, run_on_commit
):
    _, entries, races = make_py_series(PY_1)
    owner = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    Boat.objects.filter(pk=entries["A"].boat.pk).update(owner=owner)
    committee.post(reverse("races:publish_results", args=[races[0].pk]))
    [message] = mail.outbox
    assert "Full results, including elapsed times:" in message.body
    assert "andicap" not in message.body


def test_the_results_email_for_an_nhc_series_still_mentions_handicaps(
    committee, run_on_commit
):
    series = make_series("Autumn")
    race = make_race(series, start="18:30:00")
    owner = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    for sail, base, elapsed, mine in [
        ("GBR1", "0.964", 3500, True),
        ("GBR2", "0.900", 3600, False),
    ]:
        boat = make_boat(sail, base_number=base, owner=owner if mine else None)
        record(race, enter(series, boat), finish_clock("18:30:00", elapsed))
    committee.post(reverse("races:publish_results", args=[race.pk]))
    [message] = mail.outbox
    assert "elapsed times and handicaps:" in message.body


def test_the_whatsapp_share_works_for_a_portsmouth_series(committee):
    _, _, races = make_py_series(PY_1)
    publish(*races)
    page = committee.get(
        reverse("races:race_day", args=[races[0].pk]), {"view": "finish"}
    ).content.decode()
    assert "Share to WhatsApp" in page


def test_the_office_pages_show_the_system_and_both_numbers(committee):
    series, _, _ = make_py_series(PY_1)
    page = committee.get(
        reverse("races:office_series", args=[series.pk])
    ).content.decode()
    assert "Scored under Portsmouth Yardstick" in page
    boats = committee.get(reverse("races:office_boats")).content.decode()
    assert '<th class="num">PN</th>' in boats
