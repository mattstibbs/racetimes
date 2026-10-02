"""Slice 23 part B: the scoring penalty (RRS 44.3(c), SCP) through the database.

The engine's arithmetic is tested in tests/test_scoring_penalty.py against the
hand-worked examples in tests/fixtures/scoring_penalty.yaml. Here the same
examples are entered the way a race officer would (clock times and codes) and
read back from the pages, the email, the CSV and the WhatsApp message.
"""

import html
import re
from urllib.parse import unquote

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from races import final
from races.models import Finish, ScoringChange
from races.scoring import score_series
from races.testing import (
    declare,
    enter,
    finish_clock,
    make_boat,
    make_race,
    make_series,
    publish,
    record,
    start,
)
from tests.scenario_loader import SCORING_PENALTY_FIXTURE
from tests.test_scoring_penalty import RACE_EXAMPLES

pytestmark = pytest.mark.django_db

SP6 = SCORING_PENALTY_FIXTURE["tie_example"]["SP-6"]


def sail(race, entries, example, *, penalties=True):
    """Record one race of a fixture example: finishers by place, codes otherwise.

    Elapsed times grow 20% a place, a gap that no handicap adjustment closes, so
    the places in the fixture are the places scored.
    """
    for name, boat in example["boats"].items():
        scp = penalties and boat.get("scp", False)
        if boat["outcome"] == "FINISHED":
            elapsed = 3600 * (1 + 0.2 * boat["place"])
            record(
                race,
                entries[name],
                finish_clock("18:00:00", elapsed),
                scoring_penalty=scp,
            )
        else:
            record(race, entries[name], status=boat["outcome"])


def series_for(example, prefix="SP"):
    series = make_series(prefix, apply_a5_3=example["a5_3"], discards=0)
    entries = {
        name: enter(
            series,
            make_boat(f"{prefix}{name}", name=f"Boat {name}", base_number="1.000"),
        )
        for name in example["boats"]
    }
    return series, entries


@pytest.mark.parametrize("name", ["SP-1", "SP-2", "SP-3", "SP-4"])
def test_the_fixture_examples_through_the_database(name):
    example = RACE_EXAMPLES[name]
    series, entries = series_for(example)
    race = make_race(series)
    sail(race, entries, example)
    results = score_series(series).for_race(race)
    for boat_name, want in example["boats"].items():
        row = results.for_entry(entries[boat_name])
        assert row.result.points == want["points"], (name, boat_name)
        assert row.result.position == want.get("place")


def test_a_penalty_changes_no_place_and_no_handicap():
    example = RACE_EXAMPLES["SP-1"]
    plain_series, plain_entries = series_for(example, "PL")
    penal_series, penal_entries = series_for(example, "PN")
    plain_race, penal_race = make_race(plain_series), make_race(penal_series)
    sail(plain_race, plain_entries, example, penalties=False)
    sail(penal_race, penal_entries, example)
    plain = score_series(plain_series).for_race(plain_race)
    penal = score_series(penal_series).for_race(penal_race)
    for name in example["boats"]:
        a, b = (
            plain.for_entry(plain_entries[name]),
            penal.for_entry(penal_entries[name]),
        )
        assert (a.result.position, a.result.corrected_time, a.result.next_tcf) == (
            b.result.position,
            b.result.corrected_time,
            b.result.next_tcf,
        )


def sail_sp6(series=None):
    series = series or make_series(discards=0)
    entries = {
        name: enter(
            series, make_boat(f"SP{name}", name=f"Boat {name}", base_number="1.000")
        )
        for name in SP6["scores"]
    }
    for number, race_data in enumerate(SP6["races"], start=1):
        race = make_race(series, number=number)
        for name, (place, scp) in race_data.items():
            elapsed = 3600 * (1 + 0.2 * place)
            record(
                race,
                entries[name],
                finish_clock("18:00:00", elapsed),
                scoring_penalty=scp,
            )
    return series, entries


def test_sp6_through_the_database_and_the_series_and_boat_pages(client):
    series, entries = sail_sp6()
    results = score_series(series)
    assert [row.entry.boat.name[-1] for row in results.standings] == SP6["order"]
    assert {row.entry.boat.name[-1]: row.total for row in results.standings} == SP6[
        "totals"
    ]
    page = client.get(reverse("results:series", args=[series.pk])).content.decode()
    assert "SCP</abbr>" in page
    assert "SCP: Scoring penalty (RRS 44.3(c))" in page
    assert "4.4" in page and "6.8" in page
    boat_page = client.get(
        reverse("results:boat", args=[entries["A"].boat.pk])
    ).content.decode()
    assert "SCP</abbr>" in boat_page and "2.4" in boat_page
    assert "SCP: Scoring penalty" in boat_page


def test_a_race_without_a_penalty_mentions_no_scp(client):
    example = RACE_EXAMPLES["SP-1"]
    series, entries = series_for(example)
    race = make_race(series)
    sail(race, entries, example, penalties=False)
    page = client.get(reverse("results:series", args=[series.pk])).content.decode()
    assert "SCP" not in page


def test_the_race_table_shows_scp_beside_the_points(client):
    example = RACE_EXAMPLES["SP-1"]
    series, entries = series_for(example)
    race = make_race(series)
    sail(race, entries, example)
    page = client.get(
        reverse("results:series", args=[series.pk]), {"race": race.number}
    ).content.decode()
    assert re.search(r'4\.4 <abbr title="Scoring penalty">SCP</abbr>', page)


def test_a_penalised_score_can_be_discarded(client):
    series = make_series(discards=1)
    boat = enter(series, make_boat("SPX", base_number="1.000"))
    other = enter(series, make_boat("SPY", base_number="1.000"))
    for number, penalty in [(1, False), (2, True), (3, False)]:
        race = make_race(series, number=number)
        record(race, boat, "19:00:00", scoring_penalty=penalty)
        record(race, other, "19:30:00")
    standing = next(row for row in score_series(series).standings if row.entry == boat)
    assert [(c.points, c.discarded) for c in standing.scores] == [
        (1, False),
        (1.6, True),
        (1, False),
    ]
    assert standing.total == 2
    page = client.get(reverse("results:series", args=[series.pk])).content.decode()
    assert "(1.6 <abbr" in page


# --- the model refuses a penalty on a code --------------------------------------


def test_the_model_and_the_database_refuse_a_penalty_on_a_code():
    series = make_series()
    entry = enter(series, make_boat("SPA"))
    race = make_race(series)
    start(race, entry)
    with pytest.raises(ValidationError) as refused:
        Finish(race=race, entry=entry, status="DNF", scoring_penalty=True).full_clean()
    assert "scoring_penalty" in refused.value.message_dict
    with pytest.raises(IntegrityError), transaction.atomic():
        record(race, entry, status="DNS", scoring_penalty=True)


# --- the race day page ----------------------------------------------------------


def post_finish(client, race, entry, **data):
    prefix = f"entry-{entry.pk}"
    body = {f"{prefix}-{key}": value for key, value in data.items()}
    return client.post(
        reverse("races:save_finish", args=[race.pk, entry.pk]),
        body,
        HTTP_HX_REQUEST="true",
    )


@pytest.fixture
def day(committee):
    series = make_series("Spring", discards=0)
    race = make_race(series)
    entry = enter(series, make_boat("SPA", name="Alpha", base_number="1.000"))
    other = enter(series, make_boat("SPB", name="Bravo", base_number="1.000"))
    record(race, other, "19:30:00")
    start(race, entry)
    return series, race, entry, other


def test_the_tick_is_on_the_finishing_view(client, day):
    _, race, entry, _ = day
    record(race, entry, "19:00:00")
    page = client.get(
        reverse("races:race_day", args=[race.pk]), {"view": "finish"}
    ).content.decode()
    assert "Scoring penalty (SCP)" in page
    assert f'name="entry-{entry.pk}-scoring_penalty"' in page


def test_ticking_it_on_a_new_finish_is_recorded_without_a_reason(client, day):
    _, race, entry, _ = day
    post_finish(
        client,
        race,
        entry,
        finish_time="19:00:00",
        status="FINISHED",
        scoring_penalty="on",
    )
    assert Finish.objects.get(race=race, entry=entry).scoring_penalty
    change = ScoringChange.objects.get()
    assert change.changes["Scoring penalty"] == ["", "Yes"]
    assert not change.is_correction


def test_ticking_it_later_is_a_correction_that_needs_a_reason(client, day):
    _, race, entry, _ = day
    record(race, entry, "19:00:00")
    refused = post_finish(
        client,
        race,
        entry,
        finish_time="19:00:00",
        status="FINISHED",
        scoring_penalty="on",
    )
    assert "give a reason" in refused.content.decode()
    assert not Finish.objects.get(race=race, entry=entry).scoring_penalty
    assert not ScoringChange.objects.exists()

    response = post_finish(
        client,
        race,
        entry,
        finish_time="19:00:00",
        status="FINISHED",
        scoring_penalty="on",
        reason="Touched the mark",
    )
    assert "Corrected." in response.content.decode()
    change = ScoringChange.objects.get()
    assert change.changes == {"Scoring penalty": ["No", "Yes"]}
    assert change.is_correction and change.reason == "Touched the mark"


def test_saving_with_the_tick_unchanged_records_nothing(client, day):
    _, race, entry, _ = day
    record(race, entry, "19:00:00", scoring_penalty=True)
    post_finish(
        client,
        race,
        entry,
        finish_time="19:00:00",
        status="FINISHED",
        scoring_penalty="on",
    )
    assert not ScoringChange.objects.exists()


def test_the_tick_is_refused_with_a_code(client, day):
    _, race, entry, _ = day
    response = post_finish(client, race, entry, status="DNF", scoring_penalty="on")
    assert "A scoring penalty needs a finish" in response.content.decode()
    assert not Finish.objects.filter(race=race, entry=entry).exists()


def test_a_penalty_marks_published_results_amended(client, day):
    _, race, entry, _ = day
    record(race, entry, "19:00:00")
    publish(race)
    post_finish(
        client,
        race,
        entry,
        finish_time="19:00:00",
        status="FINISHED",
        scoring_penalty="on",
        reason="Touched the mark",
    )
    from races import publishing

    assert publishing.amended_since_sent(race)


def test_a_final_series_refuses_the_tick(client, day):
    series, race, entry, _ = day
    record(race, entry, "19:00:00")
    publish(race)
    declare(client, series)
    response = post_finish(
        client,
        race,
        entry,
        finish_time="19:00:00",
        status="FINISHED",
        scoring_penalty="on",
        reason="Late",
    )
    assert final.LOCKED in response.content.decode()
    assert not Finish.objects.get(race=race, entry=entry).scoring_penalty


# --- the final series' stored results -----------------------------------------


def test_stored_final_results_keep_the_penalty_and_old_ones_load_without_it(client):
    series, _ = sail_sp6()
    results = final.dump(
        __import__("races.scoring", fromlist=["x"]).engine_outcome(series)
    )
    stored = final.load(results)
    assert any(r.scoring_penalty for race in stored.races for r in race.results)
    # A copy stored before this slice has neither field.
    for race in results["races"]:
        for result in race["results"]:
            del result["scoring_penalty"], result["penalty_points"]
    old = final.load(results)
    assert not any(r.scoring_penalty for race in old.races for r in race.results)
    assert [s.total for s in old.standings] == [s.total for s in stored.standings]


# --- email, CSV and WhatsApp ----------------------------------------------------


def test_the_csv_marks_scp(client):
    series, _ = sail_sp6()
    text = client.get(reverse("results:series_csv", args=[series.pk])).content.decode()
    assert "2.4 SCP" in text and "4.4 SCP" in text
    assert "SCP: scoring penalty (RRS 44.3(c))" in text
    assert "6.8" in text


def test_the_results_email_marks_scp(client, committee, run_on_commit):
    from races.testing import make_member

    owner = make_member("pat@example.com", first_name="Pat")
    series, entries = sail_sp6()
    boat = entries["A"].boat
    boat.owner = owner
    boat.save()
    race = series.races.get(number=1)
    with run_on_commit():
        client.post(reverse("races:publish_results", args=[race.pk]), {}, follow=True)
    body = mail.outbox[0].body
    assert "Boat A (SPA) - corrected 1:12:00 - 2.4 pts (SCP)" in body
    assert "SCP: scoring penalty (RRS 44.3(c))" in body


def shared_message(page):
    href = re.search(r'class="button secondary share-whatsapp" href="([^"]+)"', page)
    return unquote(html.unescape(href.group(1)).removeprefix("https://wa.me/?text="))


def test_the_whatsapp_race_message_marks_a_penalised_boat(client, committee):
    example = RACE_EXAMPLES["SP-1"]
    series, entries = series_for(example)
    race = make_race(series)
    sail(race, entries, example)
    publish(race)
    page = client.get(
        reverse("races:race_day", args=[race.pk]), {"view": "finish"}
    ).content.decode()
    message = shared_message(page)
    assert "3. Boat C (SPC) (SCP)" in message
    assert "(SCP)" not in message.replace("3. Boat C (SPC) (SCP)", "")


def test_the_whatsapp_race_message_is_unchanged_without_a_penalty(client, committee):
    example = RACE_EXAMPLES["SP-1"]
    series, entries = series_for(example)
    race = make_race(series)
    sail(race, entries, example, penalties=False)
    publish(race)
    page = client.get(
        reverse("races:race_day", args=[race.pk]), {"view": "finish"}
    ).content.decode()
    assert "SCP" not in shared_message(page)
