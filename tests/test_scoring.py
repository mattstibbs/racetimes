"""Tests for corrected times and finishing places (spec section 2, RRS A3/A7).

The per-boat assertions are driven straight off the fixtures, so the RYA's own
published worked example (SCEN-005) is checked by the same code path as
everything else.
"""

import pytest

from nhc import InvalidInput, RaceEntry, RaceInput, RaceStatus, SeriesType, score_race
from nhc.scoring import TIE_TOLERANCE_SECONDS, corrected_time
from tests.scenario_loader import TOLERANCE, build_race_input, expected_for, race_boat_params

CORRECTED_PARAMS, CORRECTED_IDS = race_boat_params("corrected_seconds")
RANK_PARAMS, RANK_IDS = race_boat_params("rank")


def finisher(boat_id, tcf, elapsed):
    return RaceEntry(
        boat_id=boat_id, status=RaceStatus.FINISHED, tcf_used=tcf, elapsed_seconds=elapsed
    )


def club_race(*entries):
    return RaceInput(series_type=SeriesType.CLUB, entries=entries)


def results_by_id(race):
    return {result.boat_id: result for result in score_race(race)}


# --------------------------------------------------------------------------
# Against the fixtures
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("scenario", "boat_id"), CORRECTED_PARAMS, ids=CORRECTED_IDS)
def test_corrected_time_matches_the_fixture(scenario, boat_id):
    result = results_by_id(build_race_input(scenario))[boat_id]
    expected = expected_for(scenario)[boat_id]["corrected_seconds"]

    if expected is None:
        assert result.corrected_time is None
    else:
        assert result.corrected_time == pytest.approx(expected, abs=TOLERANCE)


@pytest.mark.parametrize(("scenario", "boat_id"), RANK_PARAMS, ids=RANK_IDS)
def test_finishing_place_matches_the_fixture(scenario, boat_id):
    result = results_by_id(build_race_input(scenario))[boat_id]
    assert result.position == expected_for(scenario)[boat_id]["rank"]


# --------------------------------------------------------------------------
# The formula
# --------------------------------------------------------------------------


def test_corrected_time_is_elapsed_times_handicap():
    assert corrected_time(3448, 0.964) == pytest.approx(3323.872, abs=TOLERANCE)


def test_corrected_time_is_not_rounded():
    """Spec section 7: rounding to whole seconds is for display only."""
    assert corrected_time(3527, 0.966) == 3527 * 0.966
    assert corrected_time(3527, 0.966) != round(3527 * 0.966)


def test_lowest_corrected_time_wins():
    """Spec section 2: boats are ranked by ascending corrected time. The boat
    with the longest elapsed time here wins on handicap."""
    race = club_race(
        finisher("FAST_BOAT", tcf=1.20, elapsed=3500),   # 4200
        finisher("SLOW_BOAT", tcf=0.80, elapsed=5000),   # 4000
    )
    results = results_by_id(race)
    assert results["SLOW_BOAT"].position == 1
    assert results["FAST_BOAT"].position == 2


# --------------------------------------------------------------------------
# Non-finishers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [RaceStatus.DNC, RaceStatus.DNS, RaceStatus.DNF], ids=str)
def test_non_finishers_have_no_corrected_time_or_place(status):
    race = club_race(
        finisher("A", tcf=0.95, elapsed=3600),
        RaceEntry(boat_id="B", status=status, tcf_used=1.05),
    )
    result = results_by_id(race)["B"]
    assert result.corrected_time is None
    assert result.position is None


def test_non_finishers_do_not_consume_a_place():
    race = club_race(
        finisher("A", tcf=1.0, elapsed=3600),
        RaceEntry(boat_id="DNF_BOAT", status=RaceStatus.DNF, tcf_used=1.0),
        finisher("B", tcf=1.0, elapsed=3700),
    )
    results = results_by_id(race)
    assert results["A"].position == 1
    assert results["B"].position == 2


def test_a_race_where_nobody_finishes_scores_nobody():
    race = club_race(
        RaceEntry(boat_id="A", status=RaceStatus.DNC, tcf_used=1.0),
        RaceEntry(boat_id="B", status=RaceStatus.DNS, tcf_used=0.9),
    )
    assert all(result.position is None for result in score_race(race))


# --------------------------------------------------------------------------
# Ties (RRS A7, ranking half)
# --------------------------------------------------------------------------


def test_tied_boats_share_the_better_place_and_consume_the_one_below():
    """RRS A7: a two-way tie for first is 1, 1, 3 - third place is not reused."""
    race = club_race(
        finisher("X", tcf=1.0, elapsed=4000),   # 4000
        finisher("Y", tcf=0.8, elapsed=5000),   # 4000
        finisher("Z", tcf=1.2, elapsed=3500),   # 4200
    )
    results = results_by_id(race)
    assert results["X"].position == 1
    assert results["Y"].position == 1
    assert results["Z"].position == 3


def test_a_three_way_tie_consumes_three_places():
    race = club_race(
        finisher("A", tcf=1.0, elapsed=4000),
        finisher("B", tcf=0.5, elapsed=8000),
        finisher("C", tcf=2.0, elapsed=2000),
        finisher("D", tcf=1.0, elapsed=4100),
    )
    results = results_by_id(race)
    assert [results[b].position for b in "ABC"] == [1, 1, 1]
    assert results["D"].position == 4


def test_a_tie_that_is_only_a_floating_point_artefact_still_ties():
    """0.8 has no exact binary representation, so a genuine dead heat can miss
    by a unit in the last place. The tolerance exists for exactly this."""
    race = club_race(
        finisher("X", tcf=1.0, elapsed=4000),
        finisher("Y", tcf=1.0, elapsed=4000 + TIE_TOLERANCE_SECONDS / 2),
    )
    assert {r.position for r in score_race(race)} == {1}


def test_times_a_real_timer_could_distinguish_are_not_a_tie():
    """The tolerance is not a 'near enough' rule - a hundredth of a second
    apart is two different times."""
    race = club_race(
        finisher("X", tcf=1.0, elapsed=4000),
        finisher("Y", tcf=1.0, elapsed=4000.01),
    )
    results = results_by_id(race)
    assert results["X"].position == 1
    assert results["Y"].position == 2


def test_a_run_of_close_times_does_not_drift_into_one_big_tie():
    """Each candidate is compared against the first of its group, not its
    neighbour, so successive near-equal gaps cannot accumulate."""
    step = TIE_TOLERANCE_SECONDS * 0.75
    race = club_race(*(finisher(f"B{i}", tcf=1.0, elapsed=4000 + i * step) for i in range(4)))
    results = results_by_id(race)
    # B0 and B1 are within tolerance of each other; B2 and B3 are not within
    # tolerance of B0, so they must not be swept into the same tie.
    assert results["B0"].position == 1
    assert results["B1"].position == 1
    assert results["B2"].position == 3


# --------------------------------------------------------------------------
# Output shape
# --------------------------------------------------------------------------


def test_results_come_back_in_entry_order():
    race = club_race(
        finisher("LAST", tcf=1.0, elapsed=5000),
        finisher("FIRST", tcf=1.0, elapsed=3000),
    )
    assert [r.boat_id for r in score_race(race)] == ["LAST", "FIRST"]


def test_every_entry_gets_exactly_one_result():
    scenario_race = club_race(
        finisher("A", tcf=1.0, elapsed=3600),
        RaceEntry(boat_id="B", status=RaceStatus.DNC, tcf_used=1.0),
    )
    results = score_race(scenario_race)
    assert len(results) == len(scenario_race.entries)


def test_scoring_leaves_the_handicap_fields_uncomputed():
    """score_race does no handicap adjustment, and says so by leaving those
    fields None rather than guessing at a value."""
    result = score_race(club_race(finisher("A", tcf=0.95, elapsed=3600)))[0]
    assert result.adjustment_scale is None
    assert result.achieved_handicap is None
    assert result.performance is None
    assert result.next_tcf is None


def test_a_single_boat_race_scores_that_boat_first():
    result = score_race(club_race(finisher("A", tcf=0.95, elapsed=3600)))[0]
    assert result.position == 1


def test_scoring_does_not_mutate_the_input():
    entry = finisher("A", tcf=0.95, elapsed=3600)
    race = club_race(entry)
    score_race(race)
    assert entry == finisher("A", tcf=0.95, elapsed=3600)
    assert race.entries == (entry,)


def test_an_empty_race_cannot_be_built_so_cannot_be_scored():
    with pytest.raises(InvalidInput):
        club_race()
