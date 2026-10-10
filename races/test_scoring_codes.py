"""The codes DSQ, RET, OCS and NSC, and RRS A6.1, through the database and the pages.

The worked examples CODE-1 to CODE-6 (tests/fixtures/codes_and_a6_1.yaml, checked
by the project owner) are entered as clock times, as a race officer writes them,
and read back from the scoring, the pages, the CSV, the email and the WhatsApp
message. The engine's own checks are in tests/test_codes.py. Nothing here is
produced from the engine.
"""

import csv
import io
from datetime import time

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from races import final, sharing
from races.models import Finish, Race, ScoringChange
from races.publishing import amended_since_sent
from races.scoring import score_series
from races.templatetags.racing import hms
from races.testing import (
    declare,
    enter,
    finish_clock,
    make_boat,
    make_py_series,
    make_race,
    make_series,
    publish,
    record,
    start,
)
from tests.scenario_loader import CODES_FIXTURE

pytestmark = pytest.mark.django_db

EXAMPLES = CODES_FIXTURE
RACE_CASES = [
    (example_id, index)
    for example_id, example in EXAMPLES.items()
    for index in range(len(example["races"]))
]
START = "18:30:00"

DSQ_NOTE = "DSQ: Disqualified. Boats behind her moved up a place (RRS A6.1)."
RET_NOTE = (
    "RET: Retired. A boat that retires after finishing moves the boats behind "
    "her up a place (RRS A6.1)."
)
OCS_NOTE = (
    "OCS: Over the line at the start and failed to start. She has no place, "
    "and scores as a boat that did not finish."
)
NSC_NOTE = "NSC: Did not sail the course. Boats behind her moved up a place (RRS A6.1)."


def series_page(client, series, **query):
    return client.get(
        reverse("results:series", args=[series.pk]), query
    ).content.decode()


def race_table(page, number):
    start_at = page.index(f'id="race-{number}"')
    return page[start_at : page.index("</table>", start_at)]


def row_for(table, boat):
    start_at = table.index(f'{reverse("results:boat", args=[boat.pk])}">{boat}</a>')
    return table[start_at : table.index("</tr>", start_at)]


def pos_cell(table, boat):
    """The Pos cell of ``boat``'s row: what the page shows in the first column."""
    before = table[: table.index(row_for(table, boat))].rsplit("<tr", 1)[1]
    return before.rsplit('<td class="num">', 1)[1].split("</td>", 1)[0]


# --- The worked examples, through the database ----------------------------------------


@pytest.mark.parametrize(("example_id", "index"), RACE_CASES)
def test_each_race_matches_the_worked_example(example_id, index):
    example = EXAMPLES[example_id]
    series, entries, races = make_py_series(example)
    results = score_series(series)
    assert not results.error
    race_results = results.for_race(races[index])

    for letter, want in example["races"][index]["expected"].items():
        row = race_results.for_entry(entries[letter])
        if "place" in want:
            assert row.result.position == want["place"], letter
            assert row.result.corrected_time is not None, letter
        else:
            assert row.result.position is None, letter
            assert row.result.corrected_time is None, letter
        assert row.result.points == pytest.approx(want["points"], abs=1e-9), letter
        if "kept" in want:
            assert row.result.elapsed_seconds == want["kept"], letter


@pytest.mark.parametrize("discards", [0, 1])
def test_code_6_totals_with_and_without_a_discard(discards):
    example = {**EXAMPLES["CODE-6"], "discards": discards}
    series, entries, _ = make_py_series(example)
    standings = {row.entry.pk: row for row in score_series(series).standings}
    want = EXAMPLES["CODE-6"]["standings"][0]
    key = "total_no_discards" if discards == 0 else "total_one_discard"
    assert standings[entries["A"].pk].total == want[key]


# --- Read back from the pages --------------------------------------------------------


def test_the_race_table_shows_each_code_with_its_explanation(client):
    series, entries, _ = make_py_series(EXAMPLES["CODE-5"])
    page = series_page(client, series, race=1)
    table = race_table(page, 1)
    assert pos_cell(table, entries["A"].boat) == "1"
    for letter, code in [("B", "OCS"), ("C", "NSC"), ("D", "RET")]:
        assert pos_cell(table, entries[letter].boat) == code
    assert "OCS: Over the line at the start" in page
    assert NSC_NOTE in page and RET_NOTE in page
    assert "DSQ:" not in page  # only the codes in the table are explained


def test_a_disqualified_boat_keeps_her_time_in_more_detail(client):
    series, entries, _ = make_py_series(EXAMPLES["CODE-1"])
    page = series_page(client, series, race=2, detail=1)
    table = race_table(page, 2)
    assert pos_cell(table, entries["B"].boat) == "DSQ"
    row = row_for(table, entries["B"].boat)
    # The finish time, then the elapsed time: 51:00 after an 18:30 start.
    assert f">{finish_clock(START, 3060)}<" in row
    assert f">{hms(3060)}<" in row
    # Corrected time is blank: a coded boat has no place to rank.
    assert '<td class="num"></td>' in row
    assert DSQ_NOTE in page


def test_the_series_page_explains_codes_it_shows_for_any_race(client):
    series, _, _ = make_py_series(EXAMPLES["CODE-5"])
    page = series_page(client, series)
    assert OCS_NOTE in page and NSC_NOTE in page


def test_the_boat_page_shows_the_code_and_its_explanation(client):
    _, entries, _ = make_py_series(EXAMPLES["CODE-1"])
    page = client.get(reverse("results:boat", args=[entries["B"].boat.pk])).content
    page = page.decode()
    assert "DSQ" in page
    assert DSQ_NOTE in page


def coded_boats():
    """(example, letter, code) for each boat that takes a code in an example."""
    for example_id, example in EXAMPLES.items():
        for race in example["races"]:
            for letter, value in race["finishes"].items():
                if isinstance(value, dict):
                    code = value["status"]
                elif isinstance(value, str):
                    code = value
                else:
                    continue
                if code not in ("FINISHED", "DNC", "DNS", "DNF"):
                    yield example_id, letter, code


@pytest.mark.parametrize(("example_id", "letter", "code"), list(coded_boats()))
def test_every_boat_page_shows_its_codes(client, example_id, letter, code):
    _, entries, _ = make_py_series(EXAMPLES[example_id])
    page = client.get(reverse("results:boat", args=[entries[letter].boat.pk]))
    assert f'<td class="num">{code}</td>' in page.content.decode(), (
        example_id,
        letter,
    )


def test_the_csv_carries_the_code_the_kept_time_and_no_corrected_time(client):
    series, entries, _ = make_py_series(EXAMPLES["CODE-1"])
    response = client.get(reverse("results:series_csv", args=[series.pk]))
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    race_two_at = next(i for i, row in enumerate(rows) if row[:1] == ["Race 2"])
    sail = entries["B"].boat.sail_number
    race_two_row = next(row for row in rows[race_two_at:] if row[1:2] == [sail])
    # Columns: Pos, Sail, Name, Finish, Elapsed, PN, Corrected, Points, Code.
    assert race_two_row[0] == ""
    assert race_two_row[3] == finish_clock(START, 3060)
    assert race_two_row[4] == hms(3060)
    assert race_two_row[6] == ""
    assert race_two_row[8] == "DSQ"
    assert DSQ_NOTE in [row[0] for row in rows if row]


def test_the_email_carries_the_code_and_its_explanation():
    series, _, races = make_py_series(EXAMPLES["CODE-1"])
    results = score_series(series)
    user = get_user_model().objects.create_user(
        username="pat", email="pat@example.com", first_name="Pat"
    )
    text = render_to_string(
        "emails/race_results.txt",
        {
            "race": races[1],
            "race_results": results.for_race(races[1]),
            "note": "",
            "standings": results.standings,
            "updated": False,
            "results_url": "http://testserver/series/1/",
            "user": user,
        },
    )
    assert "DSQ" in text
    assert DSQ_NOTE in text


def test_the_whatsapp_race_message_carries_the_code():
    series, _, races = make_py_series(EXAMPLES["CODE-1"])
    results = score_series(series)
    request = RequestFactory().get("/")
    message = sharing.race_message(races[1], results, request)
    assert "DSQ" in message
    assert "Disqualified" not in message  # WhatsApp has no room for the explanation


# --- The Finishing view ------------------------------------------------------------------


def test_a_coded_boat_with_a_time_is_listed_after_the_finishers(committee_client):
    series = make_series("Autumn 2026")
    race = make_race(series, start="18:00:00")
    finished = enter(series, make_boat("GBR42", name="Kittiwake", base_number="0.9"))
    coded = enter(series, make_boat("GBR7", name="Tern", base_number="0.9"))
    early = enter(series, make_boat("GBR9", name="Gannet", base_number="0.9"))
    for entry in (finished, coded, early):
        start(race, entry)
    record(race, coded, "19:02:11", status=Finish.Status.DSQ)
    record(race, finished, "19:05:31")
    record(race, early, "19:01:00")
    html = committee_client.get(
        reverse("races:race_day", args=[race.pk]) + "?view=finish"
    ).content.decode()
    finished_part = html[html.index('id="finished"') :]
    assert finished_part.index("<strong>GBR9</strong>") < finished_part.index(
        "<strong>GBR42</strong>"
    )
    assert finished_part.index("<strong>GBR42</strong>") < finished_part.index(
        "<strong>GBR7</strong>"
    )
    assert (
        '<div class="order">1.</div>' in finished_part
        and '<div class="order">2.</div>' in finished_part
        and finished_part.count('<div class="order">') == 3
    )
    assert "<strong>DSQ</strong>, crossed the line at 19:02:11" in finished_part
    assert "elapsed 1:02:11" in finished_part  # elapsed from the 18:00 start


# --- Saving and correcting ---------------------------------------------------------------


@pytest.fixture
def racing(committee_client):
    series = make_series("Autumn 2026")
    race = make_race(series, start="18:00:00")
    entry = enter(series, make_boat("GBR42", name="Kittiwake", base_number="0.9"))
    other = enter(series, make_boat("GBR77", name="Puffin", base_number="0.9"))
    start(race, entry)
    start(race, other)
    record(race, other, "19:05:31")
    return {"series": series, "race": race, "entry": entry, "other": other}


def save(client, race, entry, data):
    prefix = f"entry-{entry.pk}"
    return client.post(
        reverse("races:save_finish", args=[race.pk, entry.pk]),
        {f"{prefix}-{key}": value for key, value in data.items()},
        HTTP_HX_REQUEST="true",
    )


def test_a_code_can_be_recorded_with_a_time(committee_client, racing):
    save(
        committee_client,
        racing["race"],
        racing["entry"],
        {"finish_time": "19:10:00", "status": "DSQ"},
    )
    finish = Finish.objects.get(entry=racing["entry"])
    assert (finish.status, finish.finish_time) == ("DSQ", time(19, 10))


def test_a_code_can_be_recorded_without_a_time(committee_client, racing):
    save(committee_client, racing["race"], racing["entry"], {"status": "RET"})
    finish = Finish.objects.get(entry=racing["entry"])
    assert (finish.status, finish.finish_time) == ("RET", None)


def test_a_code_saves_without_javascript(committee_client, racing):
    """The typed form is a plain form too: a code with a time, with no HTMX."""
    prefix = f"entry-{racing['entry'].pk}"
    response = committee_client.post(
        reverse("races:save_finish", args=[racing["race"].pk, racing["entry"].pk]),
        {f"{prefix}-finish_time": "19:10:00", f"{prefix}-status": "DSQ"},
    )
    assert response.status_code == 302
    finish = Finish.objects.get(entry=racing["entry"])
    assert (finish.status, finish.finish_time) == ("DSQ", time(19, 10))


@pytest.mark.parametrize("status", ["DNC", "DNS", "DNF"])
def test_a_non_finisher_with_a_time_is_refused(committee_client, racing, status):
    response = save(
        committee_client,
        racing["race"],
        racing["entry"],
        {"finish_time": "19:10:00", "status": status},
    )
    assert "A boat that did not finish has no finish time" in response.content.decode()
    assert not Finish.objects.filter(entry=racing["entry"]).exists()


def test_a_correction_to_a_code_keeps_the_time_and_needs_a_reason(
    committee_client, racing
):
    entry, race = racing["other"], racing["race"]
    response = save(
        committee_client,
        race,
        entry,
        {"finish_time": "19:05:31", "status": "DSQ"},
    )
    assert "give a reason" in response.content.decode()
    assert Finish.objects.get(entry=entry).status == "FINISHED"

    save(
        committee_client,
        race,
        entry,
        {"finish_time": "19:05:31", "status": "DSQ", "reason": "Protest upheld"},
    )
    finish = Finish.objects.get(entry=entry)
    assert (finish.status, finish.finish_time) == ("DSQ", time(19, 5, 31))
    change = ScoringChange.objects.filter(series=racing["series"]).latest("pk")
    assert change.changes == {"Status": ["Finished", "DSQ - disqualified"]}
    assert change.is_correction and change.reason == "Protest upheld"


def test_reinstating_a_boat_needs_no_retyping(committee_client, racing):
    entry, race = racing["other"], racing["race"]
    save(
        committee_client,
        race,
        entry,
        {"finish_time": "19:05:31", "status": "DSQ", "reason": "Protest"},
    )
    save(
        committee_client,
        race,
        entry,
        {"finish_time": "19:05:31", "status": "FINISHED", "reason": "Overturned"},
    )
    finish = Finish.objects.get(entry=entry)
    assert (finish.status, finish.finish_time) == ("FINISHED", time(19, 5, 31))


def test_correcting_a_code_in_a_published_race_marks_it_amended(
    committee_client, racing
):
    race, entry = racing["race"], racing["other"]
    publish(race)
    # The committee has emailed the results, then corrects one.
    Race.objects.filter(pk=race.pk).update(results_sent_at=timezone.now())
    race.refresh_from_db()
    assert not amended_since_sent(race)
    save(
        committee_client,
        race,
        entry,
        {"finish_time": "19:05:31", "status": "DSQ", "reason": "Protest"},
    )
    change = ScoringChange.objects.filter(series=racing["series"]).latest("pk")
    assert change.race_id == race.pk
    assert change.is_correction
    assert amended_since_sent(race)


# --- Model rules -------------------------------------------------------------------------


def test_the_database_refuses_a_time_on_a_non_finisher(racing):
    with pytest.raises(IntegrityError), transaction.atomic():
        Finish.objects.create(
            race=racing["race"],
            entry=racing["entry"],
            status="DNF",
            finish_time=time(19, 10),
        )


def test_the_database_refuses_a_finisher_without_a_time(racing):
    with pytest.raises(IntegrityError), transaction.atomic():
        Finish.objects.create(
            race=racing["race"], entry=racing["entry"], status="FINISHED"
        )


@pytest.mark.parametrize("status", ["DSQ", "RET", "OCS", "NSC"])
def test_a_code_may_keep_a_time_or_have_none(racing, status):
    with transaction.atomic():
        kept = Finish.objects.create(
            race=racing["race"],
            entry=racing["entry"],
            status=status,
            finish_time=time(19, 10),
        )
    kept.full_clean()
    kept.finish_time = None
    kept.save()
    kept.full_clean()


def test_full_clean_explains_a_time_on_a_non_finisher(racing):
    finish = Finish(
        race=racing["race"],
        entry=racing["entry"],
        status="DNS",
        finish_time=time(19, 10),
    )
    with pytest.raises(ValidationError) as refused:
        finish.full_clean()
    assert "finish_time" in refused.value.message_dict


# --- A final series -------------------------------------------------------------------------


def test_a_final_series_refuses_a_code(committee_client, racing):
    series, race, entry = racing["series"], racing["race"], racing["entry"]
    record(race, entry, "19:01:00")  # a declared series needs every boat's result
    publish(race)  # and every race published
    assert declare(committee_client, series).status_code == 200
    series.refresh_from_db()
    assert series.is_final

    response = save(
        committee_client,
        race,
        entry,
        {"finish_time": "19:10:00", "status": "DSQ"},
    )
    assert final.LOCKED in response.content.decode()
    finish = Finish.objects.get(entry=entry)
    assert (finish.status, finish.finish_time) == ("FINISHED", time(19, 1))


# --- Handicaps: a coded boat is handicapped as a DNF is, through the database ----------


def _nhc_series(code_or_dnf, keep_time, prefix):
    series = make_series(f"Club series {prefix}")
    boats = [
        enter(series, make_boat(f"{prefix}{number}", base_number=base))
        for number, base in [(1, "0.950"), (2, "1.000"), (3, "1.080"), (4, "0.880")]
    ]
    times = {0: 3600, 1: 3500, 2: 3800, 3: 4000}
    for index in range(3):
        race = make_race(series, index + 1, start=START)
        for position, entry in enumerate(boats):
            seconds = times[position] + index * 40
            if position == 2 and index == 1:
                if keep_time:
                    record(race, entry, finish_clock(START, seconds), code_or_dnf)
                else:
                    record(race, entry, status=code_or_dnf)
            else:
                record(race, entry, finish_clock(START, seconds))
    return series, boats, None


@pytest.mark.parametrize("code", ["DSQ", "RET", "OCS", "NSC"])
@pytest.mark.parametrize("keep_time", [True, False])
def test_an_nhc_series_hands_out_the_same_handicaps_as_for_a_dnf(code, keep_time):
    dnf_series, _, _ = _nhc_series("DNF", keep_time=False, prefix="D")
    coded_series, _, _ = _nhc_series(code, keep_time, prefix="C")

    def next_handicaps(series):
        return [
            # The boat's number within its series (the sail number less its prefix).
            (
                row.entry.boat.sail_number[1:],
                row.next_handicap,
                row.result.position,
                row.result.points,
            )
            for race in score_series(series).races
            for row in race.rows
        ]

    assert next_handicaps(coded_series) == next_handicaps(dnf_series)
