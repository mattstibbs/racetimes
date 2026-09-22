"""Tests for club-series handicap adjustment (spec section 3).

SCEN-005 is the RYA's own published worked example and is the test that matters
most here: if it fails, the engine is wrong, not the fixture.
"""

import pytest

from nhc import (
    InvalidInput,
    Performance,
    RaceEntry,
    RaceInput,
    RaceStatus,
    SeriesType,
    compute_club_adjustment,
)
from nhc.handicap import adjustment_scale, classify_performance
from tests.scenario_loader import TOLERANCE, build_race_input, expected_for, race_boat_params

SCALE_PARAMS, SCALE_IDS = race_boat_params("adjustment_scale")
ACHIEVED_PARAMS, ACHIEVED_IDS = race_boat_params("achieved_handicap")
PERF_PARAMS, PERF_IDS = race_boat_params("performance")
NEXT_PARAMS, NEXT_IDS = race_boat_params("handicap_adjusted_next_race")

#: The RYA's published 3 d.p. results for SCEN-005 (spec section 8). Hard-coded
#: rather than read from the fixture, so this is an independent check on the
#: fixture as well as on the engine.
RYA_PUBLISHED_TCFN = {
    "BOAT_4": 0.974,
    "BOAT_3": 0.948,
    "BOAT_1": 0.969,
    "BOAT_2": 0.808,
    "BOAT_5": 0.983,
}


def finisher(boat_id, tcf, elapsed):
    return RaceEntry(
        boat_id=boat_id, status=RaceStatus.FINISHED, tcf_used=tcf, elapsed_seconds=elapsed
    )


def club_race(*entries):
    return RaceInput(series_type=SeriesType.CLUB, entries=entries)


def adjusted_by_id(race, **kwargs):
    return {r.boat_id: r for r in compute_club_adjustment(race, **kwargs)}


# --------------------------------------------------------------------------
# The RYA's published worked example
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("boat_id", "published"), sorted(RYA_PUBLISHED_TCFN.items()))
def test_reproduces_the_rya_published_worked_example(scenarios_by_id, boat_id, published):
    """Spec section 8. A failure here is a defect in the engine, never a
    fixture to adjust."""
    scenario = scenarios_by_id["SCEN-005_RYA_PUBLISHED_WORKED_EXAMPLE"]
    result = adjusted_by_id(build_race_input(scenario))[boat_id]
    assert round(result.next_tcf, 3) == published


# --------------------------------------------------------------------------
# Against the fixtures, step by step
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("scenario", "boat_id"), SCALE_PARAMS, ids=SCALE_IDS)
def test_adjustment_scale_matches_the_fixture(scenario, boat_id):
    result = adjusted_by_id(build_race_input(scenario))[boat_id]
    assert result.adjustment_scale == pytest.approx(
        expected_for(scenario)[boat_id]["adjustment_scale"], abs=TOLERANCE
    )


@pytest.mark.parametrize(("scenario", "boat_id"), ACHIEVED_PARAMS, ids=ACHIEVED_IDS)
def test_achieved_handicap_matches_the_fixture(scenario, boat_id):
    result = adjusted_by_id(build_race_input(scenario))[boat_id]
    expected = expected_for(scenario)[boat_id]["achieved_handicap"]

    if expected is None:
        assert result.achieved_handicap is None
    else:
        assert result.achieved_handicap == pytest.approx(expected, abs=TOLERANCE)


@pytest.mark.parametrize(("scenario", "boat_id"), PERF_PARAMS, ids=PERF_IDS)
def test_performance_matches_the_fixture(scenario, boat_id):
    result = adjusted_by_id(build_race_input(scenario))[boat_id]
    assert result.performance == expected_for(scenario)[boat_id]["performance"]


@pytest.mark.parametrize(("scenario", "boat_id"), NEXT_PARAMS, ids=NEXT_IDS)
def test_next_handicap_matches_the_fixture(scenario, boat_id):
    result = adjusted_by_id(build_race_input(scenario))[boat_id]
    assert result.next_tcf == pytest.approx(
        expected_for(scenario)[boat_id]["handicap_adjusted_next_race"], abs=TOLERANCE
    )


# --------------------------------------------------------------------------
# The formulas on their own
# --------------------------------------------------------------------------


def test_adjustment_scale_is_100_over_elapsed():
    assert adjustment_scale(3448) == pytest.approx(0.02900232, abs=TOLERANCE)


def test_over_performance_is_rated_down_harder_than_under_is_rated_up():
    """0.30 against 0.15 - the asymmetry is what stops a fleet's handicaps
    drifting upwards over a season."""
    race = club_race(
        finisher("QUICK", tcf=1.0, elapsed=3600),
        finisher("MID", tcf=1.0, elapsed=4000),
        finisher("SLOW", tcf=1.0, elapsed=4600),
    )
    results = adjusted_by_id(race)
    moved_up = results["QUICK"].next_tcf - 1.0
    moved_down = 1.0 - results["SLOW"].next_tcf
    assert moved_up > moved_down


@pytest.mark.parametrize(
    ("achieved", "raced_under", "expected"),
    [
        (1.1, 1.0, Performance.OVER),
        (0.9, 1.0, Performance.UNDER),
        (1.0, 1.0, Performance.UNDER),
    ],
    ids=["faster-than-rated", "slower-than-rated", "exactly-as-rated"],
)
def test_equality_counts_as_under_performance(achieved, raced_under, expected):
    """The spec's second branch is "TCFr <= TCF", so a boat that sails exactly
    to its handicap is UNDER, not OVER."""
    assert classify_performance(achieved, raced_under) is expected


def test_classification_is_not_fooled_by_float_noise():
    """A value a unit in the last place above TCF is equality, not
    over-performance."""
    import math

    assert classify_performance(math.nextafter(0.95, 1.0), 0.95) is Performance.UNDER


# --------------------------------------------------------------------------
# Non-finishers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [RaceStatus.DNC, RaceStatus.DNS, RaceStatus.DNF], ids=str)
def test_non_finishers_carry_their_handicap_forward_unchanged(status):
    race = club_race(
        finisher("A", tcf=0.95, elapsed=3600),
        finisher("B", tcf=1.00, elapsed=3800),
        RaceEntry(boat_id="ABSENT", status=status, tcf_used=1.05),
    )
    result = adjusted_by_id(race)["ABSENT"]
    assert result.next_tcf == 1.05
    assert result.achieved_handicap is None
    assert result.performance is None
    assert result.adjustment_scale == 0.0


def test_a_non_finisher_cannot_move_anyone_elses_handicap():
    """Spec section 3: non-starters are excluded from the sums for every other
    boat's calculation. An absurd handicap on an absent boat must change
    nothing."""
    racers = (finisher("A", tcf=0.95, elapsed=3600), finisher("B", tcf=1.00, elapsed=3800))
    without = adjusted_by_id(club_race(*racers))
    with_absentee = adjusted_by_id(
        club_race(*racers, RaceEntry(boat_id="GHOST", status=RaceStatus.DNC, tcf_used=99.0))
    )
    for boat_id in ("A", "B"):
        assert with_absentee[boat_id].next_tcf == without[boat_id].next_tcf
        assert with_absentee[boat_id].achieved_handicap == without[boat_id].achieved_handicap


def test_a_race_nobody_finished_adjusts_nobody_and_does_not_divide_by_zero():
    race = club_race(
        RaceEntry(boat_id="A", status=RaceStatus.DNC, tcf_used=0.95),
        RaceEntry(boat_id="B", status=RaceStatus.DNS, tcf_used=1.05),
    )
    results = adjusted_by_id(race)
    assert results["A"].next_tcf == 0.95
    assert results["B"].next_tcf == 1.05


def test_a_sole_finisher_keeps_its_exact_handicap():
    """Spec section 7's degenerate case: with one boat in the sums the ratio
    collapses and TCFr comes out equal to TCF, so nothing moves."""
    race = club_race(
        finisher("A", tcf=0.95, elapsed=3600),
        RaceEntry(boat_id="B", status=RaceStatus.DNF, tcf_used=1.05),
    )
    result = adjusted_by_id(race)["A"]
    assert result.achieved_handicap == pytest.approx(0.95, abs=TOLERANCE)
    assert result.performance is Performance.UNDER
    assert result.next_tcf == pytest.approx(0.95, abs=TOLERANCE)


# --------------------------------------------------------------------------
# The minimum-finisher threshold (spec section 9)
# --------------------------------------------------------------------------


def two_finisher_race():
    return club_race(finisher("A", tcf=1.0, elapsed=3600), finisher("B", tcf=1.0, elapsed=4000))


def test_threshold_is_off_by_default():
    """The RYA's own text does not require a threshold, so handicaps move even
    in a two-boat race unless a caller asks otherwise."""
    results = adjusted_by_id(two_finisher_race())
    assert results["A"].next_tcf != 1.0


def test_threshold_of_zero_matches_the_default():
    assert compute_club_adjustment(two_finisher_race(), minimum_finishers=0) == (
        compute_club_adjustment(two_finisher_race())
    )


def test_below_the_threshold_no_handicap_moves():
    results = adjusted_by_id(two_finisher_race(), minimum_finishers=3)
    assert results["A"].next_tcf == 1.0
    assert results["B"].next_tcf == 1.0


def test_below_the_threshold_the_adjustment_fields_stay_uncomputed():
    """None distinguishes "the adjustment did not run" from a boat that ran
    through it and earned no change."""
    result = adjusted_by_id(two_finisher_race(), minimum_finishers=3)["A"]
    assert result.adjustment_scale is None
    assert result.achieved_handicap is None
    assert result.performance is None


def test_below_the_threshold_the_race_is_still_scored():
    """The threshold stops handicaps moving; it does not stop the race being a
    race. Corrected times and places are unaffected."""
    results = adjusted_by_id(two_finisher_race(), minimum_finishers=3)
    assert results["A"].position == 1
    assert results["B"].position == 2
    assert results["A"].corrected_time == pytest.approx(3600.0, abs=TOLERANCE)


def test_at_the_threshold_handicaps_move():
    race = club_race(
        finisher("A", tcf=1.0, elapsed=3600),
        finisher("B", tcf=1.0, elapsed=4000),
        finisher("C", tcf=1.0, elapsed=4600),
    )
    results = adjusted_by_id(race, minimum_finishers=3)
    assert results["A"].next_tcf != 1.0


def test_non_finishers_do_not_count_towards_the_threshold():
    race = club_race(
        finisher("A", tcf=1.0, elapsed=3600),
        finisher("B", tcf=1.0, elapsed=4000),
        RaceEntry(boat_id="C", status=RaceStatus.DNF, tcf_used=1.0),
    )
    assert adjusted_by_id(race, minimum_finishers=3)["A"].next_tcf == 1.0


def test_a_negative_threshold_is_rejected():
    with pytest.raises(InvalidInput, match="minimum_finishers"):
        compute_club_adjustment(two_finisher_race(), minimum_finishers=-1)


# --------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------


def test_a_regatta_race_is_refused():
    """Club rules applied to a regatta produce plausible-looking numbers from
    the wrong formulas, so refuse rather than guess."""
    race = RaceInput(
        series_type=SeriesType.REGATTA,
        entries=[
            RaceEntry(
                boat_id="A",
                status=RaceStatus.FINISHED,
                tcf_used=0.95,
                elapsed_seconds=3600,
                base_number=0.95,
            )
        ],
    )
    with pytest.raises(InvalidInput, match="compute_regatta_adjustment"):
        compute_club_adjustment(race)


def test_handicaps_are_not_rounded():
    """Spec section 7: full precision through the calculation. 3 d.p. is for
    display."""
    result = adjusted_by_id(two_finisher_race())["A"]
    assert result.next_tcf != round(result.next_tcf, 3)


def test_adjustment_does_not_mutate_the_input():
    entry = finisher("A", tcf=0.95, elapsed=3600)
    race = club_race(entry, finisher("B", tcf=1.0, elapsed=3800))
    compute_club_adjustment(race)
    assert entry.tcf_used == 0.95
    assert race.entries[0] is entry


def test_every_entry_gets_exactly_one_result_in_entry_order():
    race = club_race(
        finisher("Z", tcf=1.0, elapsed=4000),
        RaceEntry(boat_id="Y", status=RaceStatus.DNC, tcf_used=1.0),
        finisher("X", tcf=1.0, elapsed=3600),
    )
    assert [r.boat_id for r in compute_club_adjustment(race)] == ["Z", "Y", "X"]
