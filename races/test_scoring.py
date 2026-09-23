"""The database-to-engine adapter.

The engine's own arithmetic is tested in tests/. What is tested here is the
translation: clock times becoming elapsed seconds, settings reaching the
engine, and results finding their way back to the right boat and race.
"""

from datetime import datetime, timedelta

import pytest

from races.models import Finish, Series
from races.scoring import score_series
from races.testing import enter, make_boat, make_race, make_series, record
from tests.scenario_loader import SCENARIOS, TOLERANCE

pytestmark = pytest.mark.django_db

SCEN_005 = next(s for s in SCENARIOS if s["scenario_id"].startswith("SCEN-005"))


def clock(start, elapsed_seconds):
    """The clock time a boat finishes, elapsed_seconds after a start like "18:00:00"."""
    moment = datetime.fromisoformat(f"2026-01-01T{start}") + timedelta(seconds=elapsed_seconds)
    return moment.strftime("%H:%M:%S")


def test_rya_worked_example_reproduces_through_the_database():
    """SCEN-005, entered the way a race officer would: as clock times.

    The base numbers are the fixture's starting handicaps, because a series
    starts on base numbers. A failure here means the translation is wrong,
    since the engine reproduces this example on its own.
    """
    series = make_series()
    race = make_race(series, start="18:30:00")
    entries = {}
    for boat in SCEN_005["boats"]:
        entry = enter(series, make_boat(boat["boat_id"], base_number=boat["start_handicap"]))
        entries[boat["boat_id"]] = entry
        if boat["status"] == "FINISHED":
            record(race, entry, clock("18:30:00", boat["elapsed_seconds"]))
        else:
            record(race, entry, status=boat["status"])

    results = score_series(series).for_race(race)

    for boat in SCEN_005["boats"]:
        row = results.for_entry(entries[boat["boat_id"]])
        expected = boat["expected"]
        assert row.result.tcf_used == boat["start_handicap"]
        assert row.result.position == expected["rank"]
        if expected["corrected_seconds"] is None:
            assert row.result.corrected_time is None
        else:
            assert row.result.corrected_time == pytest.approx(expected["corrected_seconds"], abs=TOLERANCE)
        assert row.result.next_tcf == pytest.approx(
            expected["handicap_adjusted_next_race"], abs=TOLERANCE
        )

    assert [row.entry.boat.sail_number for row in results.rows] == [
        "BOAT_4", "BOAT_3", "BOAT_1", "BOAT_2", "BOAT_5",
    ]


@pytest.fixture
def three_boats():
    series = make_series()
    entries = [
        enter(series, make_boat("GBR1", base_number="0.950")),
        enter(series, make_boat("GBR2", base_number="0.900")),
        enter(series, make_boat("GBR3", base_number="1.000")),
    ]
    return series, entries


def test_elapsed_time_is_finish_minus_start(three_boats):
    series, (a, b, c) = three_boats
    race = make_race(series, start="18:00:00")
    record(race, a, "19:00:00")
    row = score_series(series).for_race(race).for_entry(a)
    assert row.result.elapsed_seconds == 3600
    assert row.result.corrected_time == pytest.approx(3600 * 0.95)


def test_a_boat_with_nothing_recorded_is_scored_dnc(three_boats):
    series, (a, b, c) = three_boats
    race = make_race(series)
    record(race, a, "19:00:00")
    record(race, b, "19:05:00")

    row = score_series(series).for_race(race).for_entry(c)
    assert row.finish is None
    assert row.result.status == "DNC"
    # RRS A5.2: entries in the series plus one.
    assert row.result.points == 4


def test_correcting_a_finish_changes_later_races():
    series = make_series()
    a = enter(series, make_boat("GBR1"))
    b = enter(series, make_boat("GBR2"))
    race_1, race_2 = make_race(series, 1), make_race(series, 2)
    finish = record(race_1, a, "19:00:00")
    record(race_1, b, "19:10:00")
    record(race_2, a, "19:05:00")

    before = score_series(series).for_race(race_2).for_entry(a).result.tcf_used
    finish.finish_time = datetime(2026, 1, 1, 19, 20).time()
    finish.save()
    after = score_series(series).for_race(race_2).for_entry(a).result.tcf_used

    assert after != before


def test_races_are_scored_in_number_order_not_the_order_created():
    series = make_series()
    a = enter(series, make_boat("GBR1"))
    b = enter(series, make_boat("GBR2"))
    race_2 = make_race(series, 2)
    race_1 = make_race(series, 1)
    record(race_1, a, "19:00:00")
    record(race_1, b, "19:10:00")
    record(race_2, a, "19:05:00")

    results = score_series(series)
    assert [r.race.number for r in results.races] == [1, 2]
    # Race 2 sails on the handicaps race 1 produced, not on base numbers.
    assert results.for_race(race_2).for_entry(a).result.tcf_used != 0.964


def test_series_settings_reach_the_engine(three_boats):
    series, (a, b, c) = three_boats
    series.discards = 0
    series.apply_a5_3 = True
    series.save()
    race = make_race(series)
    record(race, a, "19:00:00")
    record(race, b, status=Finish.Status.DNS)

    results = score_series(series)
    points = {row.entry.pk: row.result.points for row in results.for_race(race).rows}
    # A5.3: DNS scores the boats that came to the start + 1 (a and b, so 3);
    # DNC still scores the series entries + 1 (4). Under A5.2 both would be 4.
    assert points[b.pk] == 3
    assert points[c.pk] == 4
    assert not any(cell.discarded for row in results.standings for cell in row.scores)


def test_a_regatta_is_scored_under_regatta_rules(three_boats):
    series, (a, b, c) = three_boats
    series.series_type = Series.SeriesType.REGATTA
    series.save()
    race = make_race(series)
    record(race, a, "19:00:00")
    record(race, b, "19:05:00")
    record(race, c, "19:02:00")

    row = score_series(series).for_race(race).for_entry(a)
    assert row.result.next_tcf_clamped is not None


def test_standings_follow_the_engine(three_boats):
    series, (a, b, c) = three_boats
    race = make_race(series)
    record(race, a, "19:00:00")
    record(race, b, "19:30:00")
    record(race, c, status=Finish.Status.DNF)
    series.discards = 0
    series.save()

    standings = score_series(series).standings
    assert [(row.entry.pk, row.position, row.total) for row in standings] == [
        (a.pk, 1, 1), (b.pk, 2, 2), (c.pk, 3, 4),
    ]
    assert standings[0].scores[0].race == race


def test_a_series_with_no_entries_has_no_results():
    series = make_series()
    make_race(series)
    results = score_series(series)
    assert results.races == ()
    assert results.standings == ()


def test_a_series_with_no_races_has_no_standings(three_boats):
    series, _ = three_boats
    assert score_series(series).standings == ()


# --- Races that are not scored ---------------------------------------------


def test_a_race_with_nothing_recorded_is_not_scored(three_boats):
    series, (a, b, c) = three_boats
    race_1, race_2 = make_race(series, 1), make_race(series, 2)
    record(race_1, a, "19:00:00")
    record(race_1, b, "19:10:00")

    results = score_series(series)
    assert results.for_race(race_2) is None
    assert results.note_for(race_2) == "No results recorded yet."
    assert [cell.race for cell in results.standings[0].scores] == [race_1]


def test_an_unsailed_race_does_not_use_up_the_discard(three_boats):
    """Before this rule, a scheduled race scored everyone DNC and became their discard."""
    series, (a, b, c) = three_boats
    race_1, race_2 = make_race(series, 1), make_race(series, 2)
    make_race(series, 3)  # scheduled, not sailed
    record(race_1, a, "19:00:00")
    record(race_1, b, "19:10:00")
    record(race_2, a, "19:30:00")
    record(race_2, b, "19:05:00")

    standing = {row.entry.pk: row for row in score_series(series).standings}
    # One discard over two sailed races: each boat drops its worse result.
    assert standing[a.pk].total == 1
    assert standing[b.pk].total == 1


def test_a_code_alone_makes_a_race_sailed(three_boats):
    series, (a, b, c) = three_boats
    race = make_race(series)
    record(race, a, status=Finish.Status.DNF)
    assert score_series(series).for_race(race) is not None


@pytest.fixture
def regatta(three_boats):
    series, entries = three_boats
    series.series_type = Series.SeriesType.REGATTA
    series.save()
    race_1 = make_race(series, 1)
    record(race_1, entries[0], "19:00:00")
    record(race_1, entries[1], "19:05:00")
    return series, entries, race_1


def test_a_scheduled_regatta_race_does_not_stop_scoring(regatta):
    series, entries, race_1 = regatta
    race_2 = make_race(series, 2)
    results = score_series(series)
    assert results.for_race(race_1) is not None
    assert results.for_race(race_2) is None
    assert results.note_for(race_2) == "No results recorded yet."


def test_a_regatta_race_with_only_codes_waits_for_a_finish_time(regatta):
    series, entries, race_1 = regatta
    race_2, race_3 = make_race(series, 2), make_race(series, 3)
    record(race_2, entries[0], status=Finish.Status.DNF)
    record(race_3, entries[0], "19:00:00")

    results = score_series(series)
    assert [r.race for r in results.races] == [race_1]
    assert "at least one boat has a finish time" in results.note_for(race_2)
    # Race 3 sails on race 2's handicaps, so it cannot be scored either.
    assert "race 2 is not scored yet" in results.note_for(race_3)
    assert len(results.standings) == 3


def test_a_regatta_race_is_scored_once_a_time_is_saved(regatta):
    series, entries, _ = regatta
    race_2 = make_race(series, 2)
    record(race_2, entries[0], status=Finish.Status.DNF)
    record(race_2, entries[1], "19:10:00")
    assert score_series(series).for_race(race_2) is not None


def test_input_the_engine_refuses_is_reported_not_raised(three_boats, caplog):
    """A backstop: validation should stop this, but if it does not, no crash."""
    series, (a, b, c) = three_boats
    race = make_race(series, start="18:00:00")
    record(race, a, "19:00:00")
    # Bypass validation, as a bug or a direct database edit might.
    Finish.objects.filter(race=race).update(finish_time=datetime(2026, 1, 1, 17, 0).time())

    results = score_series(series)
    assert results.races == () and results.standings == ()
    assert "cannot be calculated" in results.error
    assert results.note_for(race) == results.error
    assert "could not be scored" in caplog.text
