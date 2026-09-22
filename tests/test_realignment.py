"""Tests for end-of-series realignment (spec section 5).

SCEN-006 is the RYA's published vector and is the test that matters most: a
failure there is a defect in the engine, never a fixture to adjust.
"""

import pytest

from nhc import (
    Boat,
    Finish,
    HandicapProgression,
    InvalidInput,
    RaceStatus,
    RealignmentEntry,
    Series,
    SeriesRace,
    realign_series,
    realigned_boats,
    realignment_entries,
    score_series,
)
from tests.scenario_loader import (
    REALIGNMENT_SCENARIOS,
    TOLERANCE,
    build_realignment_entries,
    expected_for,
)

#: The RYA's published 3 d.p. results for SCEN-006 (spec section 5). Hard-coded
#: rather than read from the fixture, so this checks the fixture too.
RYA_PUBLISHED_CN = {
    "BOAT_1": 0.906,
    "BOAT_2": 0.768,
    "BOAT_3": 0.881,
    "BOAT_4": 0.904,
    "BOAT_5": 0.922,
}

SCENARIO = REALIGNMENT_SCENARIOS[0]
FIXTURE_BOATS = [boat["boat_id"] for boat in SCENARIO["boats"]]


def entry(boat_id, base, ending):
    return RealignmentEntry(boat_id=boat_id, base_number=base, ending_handicap=ending)


def realigned_by_id(entries):
    return {r.boat_id: r.realigned_tcf for r in realign_series(entries)}


# --------------------------------------------------------------------------
# The RYA's published vector
# --------------------------------------------------------------------------


@pytest.mark.parametrize("boat_id", FIXTURE_BOATS)
def test_reproduces_the_rya_published_vector(boat_id):
    realigned = realigned_by_id(build_realignment_entries(SCENARIO))
    assert round(realigned[boat_id], 3) == RYA_PUBLISHED_CN[boat_id]


@pytest.mark.parametrize("boat_id", FIXTURE_BOATS)
def test_full_precision_matches_the_fixture(boat_id):
    realigned = realigned_by_id(build_realignment_entries(SCENARIO))
    assert realigned[boat_id] == pytest.approx(
        expected_for(SCENARIO)[boat_id]["realigned_tcf"], abs=TOLERANCE
    )


def test_the_canary_is_not_rounded():
    """BOAT_3 lands on 0.88050096, a millionth above the 3 d.p. boundary. If
    anything in the chain rounded, this is where it would show."""
    realigned = realigned_by_id(build_realignment_entries(SCENARIO))
    assert realigned["BOAT_3"] == pytest.approx(0.88050096, abs=TOLERANCE)
    assert realigned["BOAT_3"] != round(realigned["BOAT_3"], 3)


# --------------------------------------------------------------------------
# What realignment actually does
# --------------------------------------------------------------------------


def test_realigned_handicaps_total_the_base_numbers():
    """The point of the exercise. Whatever the fleet's handicaps drifted to
    over the season, the realigned numbers add back up to the published base
    numbers."""
    entries = build_realignment_entries(SCENARIO)
    realigned = realign_series(entries)
    assert sum(r.realigned_tcf for r in realigned) == pytest.approx(
        sum(e.base_number for e in entries), abs=TOLERANCE
    )


def test_the_fleets_internal_spread_is_untouched():
    """Every boat is scaled by the same factor, so a boat rated 10% faster than
    another before realignment is still rated 10% faster after."""
    entries = [entry("A", 0.90, 1.00), entry("B", 1.00, 1.20), entry("C", 0.80, 0.95)]
    realigned = realigned_by_id(entries)
    for first, second in (("A", "B"), ("B", "C")):
        before = next(e.ending_handicap for e in entries if e.boat_id == first) / next(
            e.ending_handicap for e in entries if e.boat_id == second
        )
        after = realigned[first] / realigned[second]
        assert after == pytest.approx(before, abs=TOLERANCE)


def test_a_fleet_still_on_its_base_numbers_is_left_alone():
    """Nothing has drifted, so there is nothing to pull back."""
    entries = [entry("A", 0.90, 0.90), entry("B", 1.05, 1.05)]
    assert realigned_by_id(entries) == {"A": 0.90, "B": 1.05}


def test_a_fleet_that_drifted_up_is_pulled_back_down():
    entries = [entry("A", 0.90, 1.00), entry("B", 1.00, 1.10)]
    realigned = realigned_by_id(entries)
    assert realigned["A"] < 1.00
    assert realigned["B"] < 1.10


def test_a_single_boat_returns_to_its_own_base_number():
    """With one boat the ratio is BN/EH, so the drift is undone exactly."""
    assert realigned_by_id([entry("A", 0.90, 1.07)])["A"] == pytest.approx(0.90, abs=TOLERANCE)


def test_results_come_back_in_the_order_given():
    entries = [entry("Z", 1.0, 1.0), entry("A", 0.9, 0.9)]
    assert [r.boat_id for r in realign_series(entries)] == ["Z", "A"]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_realigning_nobody_is_rejected():
    with pytest.raises(InvalidInput, match="at least one boat"):
        realign_series([])


def test_a_boat_cannot_appear_twice():
    with pytest.raises(InvalidInput, match="appears twice"):
        realign_series([entry("A", 0.9, 1.0), entry("A", 0.9, 1.0)])


# --------------------------------------------------------------------------
# Joining up with a scored series
# --------------------------------------------------------------------------


def sailed_series(progression=HandicapProgression.CARRY_OVER):
    boats = [
        Boat("ALBA", base_number=0.95, current_tcf=0.95),
        Boat("BREEZE", base_number=1.00, current_tcf=1.00),
        Boat("CIRRUS", base_number=1.08, current_tcf=1.08),
    ]
    races = [
        SeriesRace("R1", [Finish("ALBA", RaceStatus.FINISHED, 3600),
                          Finish("BREEZE", RaceStatus.FINISHED, 3700),
                          Finish("CIRRUS", RaceStatus.FINISHED, 3500)]),
        SeriesRace("R2", [Finish("ALBA", RaceStatus.FINISHED, 3650),
                          Finish("BREEZE", RaceStatus.FINISHED, 3600),
                          Finish("CIRRUS", RaceStatus.FINISHED, 3550)]),
    ]
    series = Series(boats=boats, races=races, progression=progression)
    return series, score_series(series)


def test_realignment_entries_pair_base_numbers_with_ending_handicaps():
    series, outcome = sailed_series()
    entries = realignment_entries(series, outcome)
    assert [e.boat_id for e in entries] == ["ALBA", "BREEZE", "CIRRUS"]
    for e in entries:
        assert e.ending_handicap == outcome.ending_handicaps[e.boat_id]
        assert e.base_number == next(b.base_number for b in series.boats if b.boat_id == e.boat_id)


def test_realigning_a_series_with_no_races_is_a_no_op():
    """Nothing has been sailed, so every boat is still where it started."""
    boats = [Boat("A", base_number=0.9, current_tcf=0.9)]
    series = Series(boats=boats, races=[])
    entries = realignment_entries(series, score_series(series))
    assert realigned_by_id(entries)["A"] == pytest.approx(0.9, abs=TOLERANCE)


def test_realigned_boats_keep_their_base_numbers_and_move_only_their_tcf():
    series, outcome = sailed_series()
    results = realign_series(realignment_entries(series, outcome))
    next_boats = realigned_boats(series, results)

    realigned = {r.boat_id: r.realigned_tcf for r in results}
    for boat, was in zip(next_boats, series.boats):
        assert boat.base_number == was.base_number
        assert boat.current_tcf == realigned[boat.boat_id]


def test_the_next_series_starts_on_the_realigned_numbers():
    """The whole loop: sail a series, realign, carry forward."""
    series, outcome = sailed_series()
    results = realign_series(realignment_entries(series, outcome))
    next_boats = realigned_boats(series, results)

    next_series = Series(
        boats=next_boats,
        races=[SeriesRace("R1", [Finish("ALBA", RaceStatus.FINISHED, 3600)])],
        progression=HandicapProgression.CARRY_OVER,
    )
    used = {r.boat_id: r.tcf_used for r in score_series(next_series).races[0].results}
    assert used == {r.boat_id: r.realigned_tcf for r in results}


def test_resetting_the_next_series_ignores_the_realignment():
    """RESET starts from the published base number, so realigning first makes
    no difference."""
    series, outcome = sailed_series()
    results = realign_series(realignment_entries(series, outcome))
    next_series = Series(
        boats=realigned_boats(series, results),
        races=[SeriesRace("R1", [Finish("ALBA", RaceStatus.FINISHED, 3600)])],
        progression=HandicapProgression.RESET,
    )
    used = {r.boat_id: r.tcf_used for r in score_series(next_series).races[0].results}
    assert used == {b.boat_id: b.base_number for b in series.boats}


def test_realigned_boats_needs_a_result_for_every_boat():
    series, outcome = sailed_series()
    partial = realign_series(realignment_entries(series, outcome))[:1]
    with pytest.raises(InvalidInput, match="no realigned handicap"):
        realigned_boats(series, partial)
