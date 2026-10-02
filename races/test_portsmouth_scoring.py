"""Slice 24, part B: Portsmouth Yardstick through the database and the adapter.

The engine reproduces PY-1 and PY-2 on its own (tests/test_fixed_number.py).
What is checked here is the translation: clock times becoming elapsed seconds,
the series' system reaching the engine, results finding their way back to the
right boat, a series that can't be scored saying so instead of crashing, and a
final series keeping its results.

The worked examples are tests/fixtures/portsmouth_yardstick.yaml, as checked by
the project owner. Nothing here is produced from the engine.
"""

import pytest
from django.db.models import F

from races import final, scoring
from races.models import Boat, Finish, Series
from races.scoring import score_series
from races.testing import (
    declare,
    enter,
    finish_clock,
    make_boat,
    make_committee,
    make_py_series,
    make_race,
    make_series,
    publish,
    record,
)
from tests.scenario_loader import PORTSMOUTH_YARDSTICK_FIXTURE

pytestmark = pytest.mark.django_db

EXAMPLES = PORTSMOUTH_YARDSTICK_FIXTURE
DISPLAY_TOLERANCE = 0.0005


# --- The worked examples, through the database -----------------------------------------


@pytest.mark.parametrize("example_id", list(EXAMPLES))
def test_the_worked_examples_reproduce_through_the_database(example_id):
    example = EXAMPLES[example_id]
    series, entries, races = make_py_series(example)
    results = score_series(series)

    assert not results.error
    for race, race_example in zip(races, example["races"], strict=True):
        race_results = results.for_race(race)
        for letter, want in race_example["expected"].items():
            row = race_results.for_entry(entries[letter])
            assert row.result.points == want["points"], (
                example_id,
                race.number,
                letter,
            )
            if "place" in want:
                assert row.result.position == want["place"]
                assert row.result.corrected_time == pytest.approx(
                    want["corrected"], abs=DISPLAY_TOLERANCE
                )
            else:
                assert row.result.position is None
                assert row.result.corrected_time is None
            # The number the boat raced on is her Portsmouth Number, whole.
            assert row.raced_on == example["boats"][letter]


@pytest.mark.parametrize("example_id", list(EXAMPLES))
def test_the_worked_example_standings(example_id):
    example = EXAMPLES[example_id]
    series, entries, _ = make_py_series(example)
    standings = score_series(series).standings
    assert [(row.entry.pk, row.position, row.total) for row in standings] == [
        (entries[want["boat"]].pk, want["position"], want["total"])
        for want in example["standings"]
    ]


def test_no_handicap_moves_under_portsmouth_yardstick():
    series, _, _ = make_py_series(EXAMPLES["PY-1"])
    results = score_series(series)
    for race_results in results.races:
        for row in race_results.rows:
            assert row.is_fixed_number
            assert row.next_handicap is None
            assert not row.capped
            assert row.raced_on == row.entry.boat.py_number


def test_an_nhc_series_still_reports_its_handicaps():
    series = make_series()
    race = make_race(series, start="18:30:00")
    entry = enter(series, make_boat("GBR1", base_number="0.964"))
    other = enter(series, make_boat("GBR2", base_number="0.900"))
    record(race, entry, finish_clock("18:30:00", 3600))
    record(race, other, finish_clock("18:30:00", 3700))
    row = score_series(series).for_race(race).for_entry(entry)
    assert not row.is_fixed_number
    assert row.raced_on == pytest.approx(0.964)
    assert row.next_handicap is not None and row.next_handicap != row.raced_on


# --- Changing a finish changes only that race -----------------------------------------


def test_changing_any_finish_changes_only_that_race_and_the_standings():
    """The slice's recalculation test, through the database.

    Under NHC a corrected finish ripples into later races through the
    handicaps. Under a fixed number it can't: every other race scores as before.
    """
    example = {
        "discards": 1,
        "boats": {"A": 1010, "B": 1072, "C": 935, "D": 1150},
        "races": [
            {"finishes": {"A": 3600, "B": 3500, "C": 3800, "D": 4000}},
            {"finishes": {"A": 3650, "B": 3600, "C": "DNF", "D": 3900}},
            {"finishes": {"A": 3700, "B": 3550, "C": 3600, "D": 3700}},
            {"finishes": {"A": 3550, "B": 3650, "C": 3700, "D": 3850}},
        ],
    }
    series, entries, races = make_py_series(example)

    def snapshot():
        return [
            [
                (row.entry.pk, row.result.position, row.result.points, row.raced_on)
                for row in race_results.rows
            ]
            for race_results in score_series(series).races
        ]

    before = snapshot()
    finishers = [
        (race, entries[letter])
        for race, race_example in zip(races, example["races"], strict=True)
        for letter, value in race_example["finishes"].items()
        if not isinstance(value, str)
    ]
    assert finishers
    for index, (race, entry) in enumerate(finishers):
        finish = Finish.objects.get(race=race, entry=entry)
        original = finish.finish_time
        # Far slower: a day's racing has plenty of room before midnight.
        finish.finish_time = finish_clock("18:30:00", 7000)
        finish.save()
        after = snapshot()
        changed = [
            i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b
        ]
        assert changed in ([], [race.number - 1]), (index, changed)
        finish.finish_time = original
        finish.save()
    assert snapshot() == before


# --- A series that can't be scored says so --------------------------------------------


def test_a_boat_with_no_portsmouth_number_makes_the_series_unscorable():
    series, entries, races = make_py_series(EXAMPLES["PY-1"])
    # Past the forms, which refuse this.
    Boat.objects.filter(pk=entries["B"].boat.pk).update(py_number=None)
    results = score_series(series)
    assert results.races == () and results.standings == ()
    assert results.error.startswith(scoring.UNSCORABLE.split("(")[0])
    assert "Boat B (PYB) has no Portsmouth Number (PN)" in results.error
    # Every page that asks for a race's note says why, instead of crashing.
    assert results.note_for(races[0]) == results.error


def test_several_boats_missing_a_number_are_all_named():
    series, entries, _ = make_py_series(EXAMPLES["PY-1"])
    Boat.objects.filter(pk__in=[entries["A"].boat.pk, entries["C"].boat.pk]).update(
        py_number=None
    )
    error = score_series(series).error
    assert "Boat A (PYA)" in error and "Boat C (PYC)" in error
    assert "have no Portsmouth Number (PN)" in error


def test_an_nhc_boat_with_no_base_number_makes_the_series_unscorable():
    series = make_series()
    race = make_race(series)
    entry = enter(series, make_boat("GBR1"))
    record(race, entry, finish_clock("18:00:00", 3600))
    Boat.objects.filter(pk=entry.boat.pk).update(base_number=None)
    error = score_series(series).error
    assert "Boat" not in error or "GBR1" in error
    assert "has no NHC base number" in error


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"series_type": "REGATTA"}, "a regatta"),
        ({"minimum_finishers": 2}, "a minimum finishers threshold"),
        ({"nhc_cap_extremes": True}, "extreme-result capping"),
        ({"nhc_realign_to_base": True}, "realignment to base handicaps"),
    ],
)
def test_nhc_only_settings_on_a_portsmouth_series_are_never_quietly_ignored(
    change, named
):
    series, _, _ = make_py_series(EXAMPLES["PY-1"])
    Series.objects.filter(pk=series.pk).update(**change)
    results = score_series(Series.objects.get(pk=series.pk))
    assert results.races == () and results.standings == ()
    assert f"a Portsmouth Yardstick series can't use {named}" in results.error


def test_an_empty_portsmouth_series_scores_nothing_and_doesnt_crash():
    series = make_series("Empty", handicap_system="PY")
    results = score_series(series)
    assert results.races == () and results.standings == () and not results.error


# --- A final series keeps its results ------------------------------------------------------


@pytest.fixture
def committee_client(client):
    client.force_login(make_committee())
    return client


def test_a_final_portsmouth_series_stores_its_system_and_the_numbers_raced_on(
    committee_client,
):
    series, _, races = make_py_series(EXAMPLES["PY-1"])
    live = score_series(series)
    publish(*races)
    declare(committee_client, series)
    series = Series.objects.get(pk=series.pk)

    assert series.is_final
    stored = series.final_results
    assert stored["system"] == "PY"
    assert {
        result["number"] for race in stored["races"] for result in race["results"]
    } == set(EXAMPLES["PY-1"]["boats"].values())

    # Scored from the copy, it gives the very same results as the live replay.
    def shape(results):
        return [
            [
                (
                    r.entry.pk,
                    r.result.position,
                    r.result.corrected_time,
                    r.result.points,
                )
                for r in race.rows
            ]
            for race in results.races
        ], [(s.entry.pk, s.position, s.total) for s in results.standings]

    assert shape(score_series(series)) == shape(live)


def test_a_final_portsmouth_series_keeps_its_results_when_a_boats_number_changes(
    committee_client,
):
    series, entries, races = make_py_series(EXAMPLES["PY-1"])
    publish(*races)
    declare(committee_client, series)
    before = [
        (s.entry.pk, s.position, s.total)
        for s in score_series(Series.objects.get(pk=series.pk)).standings
    ]
    # The boat is changed (a final series' boats still can be) and, in the
    # worst case, her number is lost altogether.
    Boat.objects.filter(pk=entries["B"].boat.pk).update(py_number=F("py_number") + 100)
    Boat.objects.filter(pk=entries["A"].boat.pk).update(py_number=None)
    results = score_series(Series.objects.get(pk=series.pk))
    assert not results.error
    assert [(s.entry.pk, s.position, s.total) for s in results.standings] == before
    first = results.races[0].for_entry(entries["B"])
    assert first.raced_on == EXAMPLES["PY-1"]["boats"]["B"]  # as she raced


def test_a_stored_nhc_copy_from_before_this_slice_still_loads_as_nhc(
    committee_client,
):
    """Copies stored before slice 24 name no system. They are NHC results."""
    series = make_series("Old")
    race = make_race(series, start="18:30:00")
    for sail, base, elapsed in [("GBR1", "0.964", 3500), ("GBR2", "0.900", 3600)]:
        record(
            race,
            enter(series, make_boat(sail, base_number=base)),
            finish_clock("18:30:00", elapsed),
        )
    publish(race)
    declare(committee_client, series)
    series = Series.objects.get(pk=series.pk)
    assert series.final_results["system"] == "NHC"
    live = score_series(series)

    old_style = {k: v for k, v in series.final_results.items() if k != "system"}
    Series.objects.filter(pk=series.pk).update(final_results=old_style)
    reloaded = score_series(Series.objects.get(pk=series.pk))

    assert not reloaded.error
    assert not reloaded.races[0].rows[0].is_fixed_number
    assert [
        (r.entry.pk, r.result.tcf_used, r.result.next_tcf)
        for r in reloaded.races[0].rows
    ] == [
        (r.entry.pk, r.result.tcf_used, r.result.next_tcf) for r in live.races[0].rows
    ]


def test_load_reads_either_kind_of_stored_copy():
    nhc_copy = {
        "races": [],
        "starting_handicaps": [],
        "standings": [],
    }
    assert type(final.load(nhc_copy)).__name__ == "SeriesOutcome"
    assert type(final.load({**nhc_copy, "system": "NHC"})).__name__ == "SeriesOutcome"
    fixed = final.load({"system": "PY", "races": [], "standings": []})
    assert type(fixed).__name__ == "FixedNumberOutcome"
    assert fixed.system.value == "PY"
