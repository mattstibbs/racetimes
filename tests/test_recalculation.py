"""The recalculation acceptance criterion for slice 0.

"Changing any finish and re-scoring gives correct downstream handicaps."

The brief's central invariant is that handicaps are never edited directly: they
are derived from the base handicap plus the race history, so correcting a
finish half way through a season must recalculate every later race. These tests
take "any finish" literally and sweep every recorded finish in a series, one at
a time.

What they are really guarding against is a future optimisation. Replaying the
whole series is cheap now, but the day someone adds caching, or has a race
mutate the boats it was given, the failure mode is a handicap that is stale
rather than wrong - invisible in any single-race test, and wrong in a way that
only shows up weeks later in the standings.
"""

import pytest

from nhc import (
    Boat,
    Finish,
    HandicapProgression,
    RaceStatus,
    Series,
    SeriesRace,
    SeriesType,
    score_series,
)

FIN = RaceStatus.FINISHED

BOATS = (("A", 0.95), ("B", 1.00), ("C", 1.08), ("D", 0.88))

#: A four-race club series with a retirement and an absentee in it. Values are
#: elapsed seconds, or a RaceStatus for a boat that did not finish; a boat left
#: out of a race has no recorded finish at all and is scored DNC.
RACES = (
    ("R1", {"A": 3600, "B": 3500, "C": 3800, "D": 4000}),
    ("R2", {"A": 3650, "B": 3600, "C": RaceStatus.DNF, "D": 3900}),
    ("R3", {"A": 3700, "B": 3550, "C": 3600}),
    ("R4", {"A": 3550, "B": 3650, "C": 3700, "D": 3850}),
)

#: Every recorded finish in the series, as (race index, boat id). "Recorded"
#: matters: D has no entry at all in R3, so there is no finish there to correct.
RECORDED = tuple(
    (index, boat_id)
    for index, (_, finishes) in enumerate(RACES)
    for boat_id in finishes
)
RECORDED_IDS = [f"{RACES[i][0]}-{b}" for i, b in RECORDED]

FINISHERS = tuple(
    (index, boat_id)
    for index, boat_id in RECORDED
    if not isinstance(RACES[index][1][boat_id], RaceStatus)
)
FINISHER_IDS = [f"{RACES[i][0]}-{b}" for i, b in FINISHERS]


def build(races=RACES, **kwargs):
    boats = [Boat(b, base_number=bn, current_tcf=bn) for b, bn in BOATS]
    series_races = [
        SeriesRace(
            race_id,
            [
                Finish(boat_id, value, None)
                if isinstance(value, RaceStatus)
                else Finish(boat_id, FIN, value)
                for boat_id, value in finishes.items()
            ],
        )
        for race_id, finishes in races
    ]
    return Series(boats=boats, races=series_races, **kwargs)


def change(index, boat_id, value, races=RACES):
    """The same series with one finish altered."""
    altered = []
    for position, (race_id, finishes) in enumerate(races):
        if position == index:
            finishes = {**finishes, boat_id: value}
        altered.append((race_id, finishes))
    return tuple(altered)


def slower(index, boat_id, by=120):
    """The same series with one boat's recorded time made slower.

    A plausible correction: a race officer misread a stopwatch by two minutes.
    """
    original = RACES[index][1][boat_id]
    return change(index, boat_id, original + by)


# --------------------------------------------------------------------------
# The sweep: correct any one finish, and check what moves
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_races_before_a_correction_are_untouched(index, boat_id):
    before = score_series(build())
    after = score_series(build(slower(index, boat_id)))
    assert after.races[:index] == before.races[:index]


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_the_corrected_race_changes(index, boat_id):
    before = score_series(build())
    after = score_series(build(slower(index, boat_id)))
    assert after.races[index] != before.races[index]


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_every_later_race_changes(index, boat_id):
    """Not just the corrected race: the handicaps it produces feed the next one,
    so a correction ripples to the end of the series."""
    before = score_series(build())
    after = score_series(build(slower(index, boat_id)))
    for later in range(index + 1, len(RACES)):
        assert after.races[later] != before.races[later], f"{RACES[later][0]} did not move"


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_the_handicap_chain_still_holds_after_a_correction(index, boat_id):
    """Each race must still be scored on exactly what the previous one
    produced."""
    outcome = score_series(build(slower(index, boat_id)))
    for earlier, later in zip(outcome.races, outcome.races[1:]):
        produced = {r.boat_id: r.effective_next_tcf for r in earlier.results}
        used = {r.boat_id: r.tcf_used for r in later.results}
        assert used == produced


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_putting_the_finish_back_restores_the_original_results(index, boat_id):
    """The round trip. If anything accumulated state across a scoring run, this
    is where it would show."""
    before = score_series(build())
    score_series(build(slower(index, boat_id)))
    assert score_series(build()) == before


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_a_correction_moves_the_other_boats_too(index, boat_id):
    """A handicap is computed from the whole fleet's times, so correcting one
    boat's finish is not local to that boat."""
    before = {r.boat_id: r for r in score_series(build()).races[index].results}
    after = {r.boat_id: r for r in score_series(build(slower(index, boat_id))).races[index].results}
    moved = [b for b in after if after[b].next_tcf != before[b].next_tcf and b != boat_id]
    assert moved, "only the corrected boat's handicap moved"


# --------------------------------------------------------------------------
# Corrections that change a scoring code
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("index", "boat_id"), FINISHERS, ids=FINISHER_IDS)
def test_a_finisher_later_recorded_as_retired_ripples_the_same_way(index, boat_id):
    """Not every correction is a time. A boat recorded as finishing may turn out
    to have retired, which removes it from the handicap sums entirely."""
    before = score_series(build())
    after = score_series(build(change(index, boat_id, RaceStatus.DNF)))
    assert after.races[:index] == before.races[:index]
    assert after.races[index] != before.races[index]
    for later in range(index + 1, len(RACES)):
        assert after.races[later] != before.races[later]


def test_a_retirement_corrected_to_a_finish_ripples_too():
    """C retired in R2. If the finish line reports it did complete the course,
    every later race must be rescored."""
    before = score_series(build())
    after = score_series(build(change(1, "C", 3750)))
    assert after.races[0] == before.races[0]
    assert after.races[1] != before.races[1]
    assert after.races[2] != before.races[2]
    assert after.races[3] != before.races[3]


def test_swapping_one_non_finishing_code_for_another_changes_only_the_code():
    """In a club series DNC and DNS are scored alike - excluded from the sums,
    handicap carried forward, and the same points under A5.2. So the recorded
    code changes and not one number does."""
    before = score_series(build(change(1, "C", RaceStatus.DNC)))
    after = score_series(build(change(1, "C", RaceStatus.DNS)))

    changed = {r.boat_id: r for r in before.races[1].results}["C"]
    recoded = {r.boat_id: r for r in after.races[1].results}["C"]
    assert changed.status is RaceStatus.DNC
    assert recoded.status is RaceStatus.DNS
    assert recoded.points == changed.points
    assert recoded.next_tcf == changed.next_tcf
    assert after.races[2:] == before.races[2:]


def test_the_same_swap_does_change_the_points_under_a5_3():
    """A5.3 is the rule that distinguishes them: one came to the starting area
    and one did not.

    This uses R3, where D is absent as well, because with only one boat missing
    the two codes coincide. A lone DNC scores entries + 1, while the same boat
    as a DNS scores (everyone came) + 1 - and those are the same number. A
    second absentee pulls the "came to the starting area" count down and the
    scores apart.
    """

    def points_for_c(outcome):
        return {r.boat_id: r.points for r in outcome.races[2].results}["C"]

    as_dnc = score_series(build(change(2, "C", RaceStatus.DNC), apply_a5_3=True))
    as_dns = score_series(build(change(2, "C", RaceStatus.DNS), apply_a5_3=True))

    assert points_for_c(as_dnc) == 5.0   # four boats entered, plus one
    assert points_for_c(as_dns) == 4.0   # three came to the starting area, plus one


# --------------------------------------------------------------------------
# Nothing leaks between runs
# --------------------------------------------------------------------------


def test_scoring_the_same_series_repeatedly_is_stable():
    series = build()
    first = score_series(series)
    for _ in range(5):
        assert score_series(series) == first


def test_scoring_does_not_move_the_boats_it_was_given():
    """The boats carry current_tcf, which is where the series starts. If
    scoring wrote back to them, a second run would start somewhere else."""
    series = build()
    before = [(b.boat_id, b.base_number, b.current_tcf) for b in series.boats]
    score_series(series)
    assert [(b.boat_id, b.base_number, b.current_tcf) for b in series.boats] == before


def test_scoring_another_series_in_between_changes_nothing():
    first = score_series(build())
    score_series(build(slower(0, "A")))
    score_series(build(races=RACES[:2]))
    assert score_series(build()) == first


def test_a_correction_in_the_last_race_leaves_every_earlier_race_alone():
    before = score_series(build())
    after = score_series(build(slower(3, "A")))
    assert after.races[:3] == before.races[:3]
    assert after.races[3] != before.races[3]


# --------------------------------------------------------------------------
# The standings follow
# --------------------------------------------------------------------------


def test_a_correction_that_changes_a_result_changes_the_standings():
    """A2.1 totals the race scores, so a corrected finish that moves a place has
    to reach the table."""
    before = score_series(build())
    # B wins R1 comfortably; make it finish well behind instead.
    after = score_series(build(change(0, "B", 4500)))
    assert after.standings != before.standings


def test_standings_stay_consistent_with_the_races_they_came_from():
    outcome = score_series(build(slower(1, "B")))
    for standing in outcome.standings:
        for score, race in zip(standing.scores, outcome.races):
            recorded = {r.boat_id: r.points for r in race.results}[standing.boat_id]
            assert score.race_id == race.race_id
            assert score.points == recorded


# --------------------------------------------------------------------------
# The same, for a regatta
# --------------------------------------------------------------------------


def regatta_races():
    return (
        ("R1", {"A": 3600, "B": 3500, "C": 3800, "D": 4000}),
        ("R2", {"A": 3650, "B": 3600, "C": RaceStatus.DNF, "D": 3900}),
        ("R3", {"A": 3700, "B": 3550, "C": 3600, "D": 3800}),
    )


def test_a_regatta_correction_ripples_the_same_way():
    kwargs = {"series_type": SeriesType.REGATTA}
    before = score_series(build(regatta_races(), **kwargs))
    after = score_series(build(change(1, "A", 3900, regatta_races()), **kwargs))
    assert after.races[0] == before.races[0]
    assert after.races[1] != before.races[1]
    assert after.races[2] != before.races[2]


def test_correcting_a_regatta_non_finisher_moves_the_fleet():
    """In a regatta the non-finishers are back-calculated into the sums, so
    changing C's retirement to a finish moves everyone - unlike a club series,
    where it would only restore C to the sums."""
    kwargs = {"series_type": SeriesType.REGATTA}
    before = score_series(build(regatta_races(), **kwargs))
    after = score_series(build(change(1, "C", 3700, regatta_races()), **kwargs))
    first = {r.boat_id: r.effective_next_tcf for r in before.races[1].results}
    second = {r.boat_id: r.effective_next_tcf for r in after.races[1].results}
    assert all(first[b] != second[b] for b in first)


def test_a_regatta_correction_keeps_the_clamped_chain_intact():
    series = build(change(1, "A", 3000, regatta_races()), series_type=SeriesType.REGATTA)
    outcome = score_series(series)
    for earlier, later in zip(outcome.races, outcome.races[1:]):
        produced = {r.boat_id: r.effective_next_tcf for r in earlier.results}
        used = {r.boat_id: r.tcf_used for r in later.results}
        assert used == produced


# --------------------------------------------------------------------------
# And for a series that starts from drifted handicaps
# --------------------------------------------------------------------------


def test_a_correction_ripples_when_the_series_carries_handicaps_over():
    """The chain has to hold wherever the series started, not just from base
    numbers."""
    boats = [Boat(b, base_number=bn, current_tcf=bn * 1.05) for b, bn in BOATS]
    kwargs = {"progression": HandicapProgression.CARRY_OVER}

    def scored(races):
        return score_series(Series(boats=boats, races=build(races).races, **kwargs))

    before = scored(RACES)
    after = scored(slower(1, "A"))
    assert after.races[0] == before.races[0]
    assert after.races[1] != before.races[1]
    assert after.races[3] != before.races[3]
