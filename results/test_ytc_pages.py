"""Slice 25, part B: an RYA YTC series, read back from the pages.

The worked examples YTC-1 and YTC-2 (tests/fixtures/ytc.yaml, checked by the
project owner) are entered as clock times, and the pages must show them: the
number each boat raced on under a heading that says YTC, a boat on her
non-spinnaker number marked NS, and no next handicap, because none can move.
"""

import csv
import io
import re

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from races.models import Boat
from races.templatetags.racing import hms
from races.testing import (
    make_committee,
    make_member,
    make_ytc_series,
    publish,
)
from tests.scenario_loader import YTC_FIXTURE

pytestmark = pytest.mark.django_db

YTC_1 = YTC_FIXTURE["YTC-1"]
YTC_2 = YTC_FIXTURE["YTC-2"]


def series_page(client, series, **query):
    return client.get(
        reverse("results:series", args=[series.pk]), query
    ).content.decode()


def race_table(page, number):
    start = page.index(f'id="race-{number}"')
    return page[start : page.index("</table>", start)]


def row_for(table, boat):
    start = table.index(f'{reverse("results:boat", args=[boat.pk])}">{boat}</a>')
    return table[start : table.index("</tr>", start)]


@pytest.fixture
def committee():
    office = Client()
    office.force_login(make_committee())
    return office


# --- The series page ------------------------------------------------------------------------


@pytest.mark.parametrize("example_id", list(YTC_FIXTURE))
def test_the_series_page_shows_the_worked_example(client, example_id):
    example = YTC_FIXTURE[example_id]
    series, entries, races = make_ytc_series(example)
    for race, race_example in zip(races, example["races"], strict=True):
        table = race_table(series_page(client, series, race=race.number), race.number)
        assert '<th class="num detail">YTC</th>' in table
        assert "Next TCF" not in table
        for letter, want in race_example["expected"].items():
            row = row_for(table, entries[letter].boat)
            number = example["boats"][letter]
            assert f'<td class="num detail">{number}' in row
            if "corrected" in want:
                assert f'<td class="num">{hms(want["corrected"])}</td>' in row
            assert f'<td class="num">{want["points"]:g}</td>' in row, letter


def test_a_boat_on_her_non_spinnaker_number_is_marked_ns_and_explained(client):
    series, entries, _ = make_ytc_series(YTC_1)
    page = series_page(client, series, race=1, detail=1)
    table = race_table(page, 1)
    assert '899 <abbr title="Non-spinnaker YTC number">NS</abbr>' in row_for(
        table, entries["A"].boat
    )
    assert "NS</abbr>" not in row_for(table, entries["B"].boat)
    assert "NS: Raced on the boat's non-spinnaker YTC number" in page


def test_no_ns_note_when_nobody_is_on_a_non_spinnaker_number(client):
    series, _, _ = make_ytc_series(YTC_2)
    page = series_page(client, series, race=1, detail=1)
    assert "NS</abbr>" not in page and "NS: Raced" not in page


def test_the_series_page_names_the_system(client):
    series, _, _ = make_ytc_series(YTC_1)
    assert "Scored under RYA YTC" in series_page(client, series)


# --- A boat's page -----------------------------------------------------------------------------


def test_the_boat_page_says_which_number_she_sails_on(client):
    _series, entries, _ = make_ytc_series(YTC_1)
    ns = client.get(
        reverse("results:boat", args=[entries["A"].boat.pk])
    ).content.decode()
    assert (
        "sails on her non-spinnaker YTC <strong>899</strong> for the whole series" in ns
    )
    assert "YTC number 873." in ns and "Non-spinnaker YTC number 899." in ns
    assert '<th class="num">YTC</th>' in ns and "Next</th>" not in ns
    assert "NS</abbr>" in ns
    plain = client.get(
        reverse("results:boat", args=[entries["B"].boat.pk])
    ).content.decode()
    assert "sails on YTC <strong>940</strong> for the whole series" in plain
    assert "NS</abbr>" not in plain and "non-spinnaker" not in plain


def test_a_final_series_keeps_the_number_in_the_sentence(client, committee):
    series, entries, races = make_ytc_series(YTC_1)
    publish(*races)
    committee.post(reverse("races:declare_final", args=[series.pk]))
    Boat.objects.filter(pk=entries["A"].boat.pk).update(ytc_number_non_spinnaker=950)
    page = client.get(
        reverse("results:boat", args=[entries["A"].boat.pk])
    ).content.decode()
    assert "<strong>899</strong> for the whole series" in page


# --- The CSV ----------------------------------------------------------------------------------------


def test_the_csv_is_headed_ytc_and_marks_ns(client):
    series, _, _ = make_ytc_series(YTC_1)
    response = client.get(reverse("results:series_csv", args=[series.pk]))
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    header = next(row for row in rows if "Corrected" in row)
    assert header[5:7] == ["YTC", "NS"]  # NS has a column of its own
    first = rows[rows.index(header) + 1]
    assert first[2] == "Boat A" and first[5:7] == ["899", "NS"]
    boat_b = next(r for r in rows[rows.index(header) + 1 :] if r[2] == "Boat B")
    assert boat_b[5:7] == ["940", ""]
    assert any(row and row[0].startswith("NS: raced on") for row in rows)


# --- The results email --------------------------------------------------------------------------------


def test_the_results_email_marks_ns(committee, run_on_commit):
    _, entries, races = make_ytc_series(YTC_1)
    owner = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    Boat.objects.filter(pk=entries["B"].boat.pk).update(owner=owner)
    committee.post(reverse("races:publish_results", args=[races[0].pk]))
    [message] = mail.outbox
    assert "Boat A (YTCA) (NS)" in message.body
    assert "NS: raced on the boat's non-spinnaker YTC number." in message.body
    assert "andicap" not in message.body


# --- The race day page ------------------------------------------------------------------------------------


def test_the_race_day_page_marks_ns_on_the_start_sheet_and_finishing_views(committee):
    _, _entries, races = make_ytc_series(YTC_1)
    start_sheet = committee.get(
        reverse("races:race_day", args=[races[0].pk]), {"view": "start"}
    ).content.decode()
    finishing = committee.get(
        reverse("races:race_day", args=[races[0].pk]), {"view": "finish"}
    ).content.decode()
    for page in (start_sheet, finishing):
        boat_a = page[page.index("YTCA") :][:300]
        assert "NS</abbr>" in boat_a
        boat_b = page[page.index("YTCB") :][:200]
        assert "NS</abbr>" not in boat_b


def test_ns_is_not_marked_anywhere_in_an_nhc_series(committee, client):
    from races.testing import (
        enter,
        finish_clock,
        make_boat,
        make_race,
        make_series,
        record,
    )

    series = make_series("Autumn")
    race = make_race(series, start="18:30:00")
    boat = enter(series, make_boat("GBR1", ytc_number_non_spinnaker=899))
    record(race, boat, finish_clock("18:30:00", 3600))
    page = series_page(client, series, race=1, detail=1)
    assert "NS</abbr>" not in page


# --- The office and the data exports ------------------------------------------------------------------------


def test_the_boats_list_has_both_ytc_columns(committee):
    make_ytc_series(YTC_1)
    page = committee.get(reverse("races:office_boats")).content.decode()
    assert '<th class="num">YTC</th><th class="num">YTC (NS)</th>' in page
    assert re.search(r">873</td>\s*<td class=\"num\">899</td>", page)


def test_the_clubs_data_export_and_a_persons_download_include_the_new_fields(committee):
    import zipfile

    from races.testing import make_administrator

    make_ytc_series(YTC_1)
    admin = Client()
    admin.force_login(make_administrator())
    response = admin.get(reverse("races:export_club_data"))
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    boats = archive.read("boats.csv").decode("utf-8-sig")
    assert "ytc_number" in boats.splitlines()[0]
    assert "ytc_number_non_spinnaker" in boats.splitlines()[0]
    entries = archive.read("series_entries.csv").decode("utf-8-sig")
    assert "ytc_number_used" in entries.splitlines()[0]
    assert "Non-spinnaker YTC number" in entries
