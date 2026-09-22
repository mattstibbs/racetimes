"""Tests for regatta handicap adjustment (spec section 4).

There is no published RYA vector for regattas the way there is for club series
(section 8), so the expectations here are hand-derived from the formulas. Where
a value is hard-coded it was computed independently of the engine; where the
relationship matters more than the number, the test asserts the relationship.
"""

import pytest

from nhc import (
    InvalidInput,
    Performance,
    RaceEntry,
    RaceInput,
    RaceStatus,
    SeriesType,
    clamp_to_base_number,
    compute_regatta_adjustment,
)
from nhc.regatta import (
    FIRST_RACE_WEIGHT,
    OVER_PERFORMANCE_WEIGHT,
    UNDER_PERFORMANCE_WEIGHT,
)
from tests.scenario_loader import TOLERANCE

TOL = TOLERANCE


def entry(boat_id, tcf, elapsed=None, status=RaceStatus.FINISHED, base=None):
    return RaceEntry(
        boat_id=boat_id,
        status=status,
        tcf_used=tcf,
        elapsed_seconds=elapsed,
        base_number=tcf if base is None else base,
    )


def regatta(*entries, first=False):
    return RaceInput(
        series_type=SeriesType.REGATTA,
        entries=entries,
        is_first_race_of_regatta=first,
    )


def by_id(race):
    return {r.boat_id: r for r in compute_regatta_adjustment(race)}


# --------------------------------------------------------------------------
# Step 3 - the blend
# --------------------------------------------------------------------------


def test_first_race_moves_every_boat_sixty_percent_of_the_way():
    """Hand-derived: two boats on 1.000 over 3600s and 4000s give TCFr of
    1.05263158 and 0.94736842, and the first race blends both at 0.6."""
    results = by_id(regatta(entry("A", 1.0, 3600), entry("B", 1.0, 4000), first=True))
    assert results["A"].achieved_handicap == pytest.approx(1.05263158, abs=TOL)
    assert results["B"].achieved_handicap == pytest.approx(0.94736842, abs=TOL)
    assert results["A"].next_tcf == pytest.approx(1.03157895, abs=TOL)
    assert results["B"].next_tcf == pytest.approx(0.96842105, abs=TOL)


def test_first_race_makes_no_over_under_distinction():
    """Spec section 4, step 3: "all boats, no over/under distinction". Reporting
    a classification would be misleading, since it is not what drove the
    weight."""
    results = by_id(regatta(entry("A", 1.0, 3600), entry("B", 1.0, 4000), first=True))
    assert results["A"].performance is None
    assert results["B"].performance is None


def test_later_races_rate_over_performance_down_harder_than_under_performance_up():
    """0.6 against 0.5 - the same asymmetry as a club series, but far less
    pronounced, because a regatta has only a few races to find the numbers."""
    results = by_id(regatta(entry("A", 1.0, 3600), entry("B", 1.0, 4000)))
    assert results["A"].performance is Performance.OVER
    assert results["B"].performance is Performance.UNDER
    assert results["A"].next_tcf == pytest.approx(1.03157895, abs=TOL)
    assert results["B"].next_tcf == pytest.approx(0.97368421, abs=TOL)


@pytest.mark.parametrize("first", [True, False], ids=["first-race", "later-race"])
def test_the_blend_is_always_tcf_plus_weight_times_the_gap(first):
    """TCFn = TCF + w x (TCFr - TCF), whichever w applies."""
    results = by_id(
        regatta(entry("A", 0.95, 3600), entry("B", 1.05, 4000), entry("C", 1.0, 3800), first=first)
    )
    for result in results.values():
        if first:
            weight = FIRST_RACE_WEIGHT
        else:
            weight = (
                OVER_PERFORMANCE_WEIGHT
                if result.performance is Performance.OVER
                else UNDER_PERFORMANCE_WEIGHT
            )
        gap = result.achieved_handicap - result.tcf_used
        assert result.next_tcf == pytest.approx(result.tcf_used + weight * gap, abs=TOL)


# --------------------------------------------------------------------------
# Step 1 - back-calculating elapsed times for non-finishers
# --------------------------------------------------------------------------


def three_finishers_plus(*extra):
    """Finishers with corrected times 3420, 3500, 3600 - median 3500, top-3
    average 3506.66666667."""
    return regatta(
        entry("F1", 0.95, 3600),   # 3420
        entry("F2", 1.00, 3500),   # 3500
        entry("F3", 1.00, 3600),   # 3600
        *extra,
    )


@pytest.mark.parametrize("status", [RaceStatus.DNC, RaceStatus.DNS], ids=str)
def test_a_boat_that_never_sailed_is_given_the_top_finishers_average(status):
    """Spec section 4 step 1: E = (average corrected time of the top 3
    finishers) / TCF."""
    results = by_id(three_finishers_plus(entry("ABSENT", 1.20, status=status)))
    assert results["ABSENT"].elapsed_seconds_used == pytest.approx(3506.66666667 / 1.20, abs=TOL)


def test_a_boat_that_retired_is_given_the_median_finishers_time():
    """Spec section 4 step 1: E = (corrected time of the median finisher) / TCF.
    Retiring is treated as a notional average result, not a good one."""
    results = by_id(three_finishers_plus(entry("RETIRED", 1.20, status=RaceStatus.DNF)))
    assert results["RETIRED"].elapsed_seconds_used == pytest.approx(3500.0 / 1.20, abs=TOL)


def test_the_median_of_an_even_fleet_averages_the_two_middle_boats():
    """Corrected times 3400, 3420, 3500, 3600 - median (3420 + 3500) / 2."""
    race = regatta(
        entry("F0", 1.00, 3400),
        entry("F1", 0.95, 3600),   # 3420
        entry("F2", 1.00, 3500),
        entry("F3", 1.00, 3600),
        entry("RETIRED", 1.00, status=RaceStatus.DNF),
    )
    assert by_id(race)["RETIRED"].elapsed_seconds_used == pytest.approx(3460.0, abs=TOL)


def test_the_top_three_average_uses_only_the_best_three():
    race = regatta(
        entry("F0", 1.00, 3400),
        entry("F1", 0.95, 3600),   # 3420
        entry("F2", 1.00, 3500),
        entry("F3", 1.00, 3600),   # excluded from the top three
        entry("ABSENT", 1.00, status=RaceStatus.DNC),
    )
    assert by_id(race)["ABSENT"].elapsed_seconds_used == pytest.approx(3440.0, abs=TOL)


@pytest.mark.parametrize("finishers", [1, 2], ids=["one-finisher", "two-finishers"])
def test_with_fewer_than_three_finishers_it_averages_whatever_finished(finishers):
    """Spec section 7 asks for this rather than an error."""
    sailed = [entry("F1", 0.95, 3600), entry("F2", 1.00, 3500)][:finishers]
    expected = [3420.0, 3460.0][finishers - 1]
    race = regatta(*sailed, entry("ABSENT", 1.00, status=RaceStatus.DNC))
    assert by_id(race)["ABSENT"].elapsed_seconds_used == pytest.approx(expected, abs=TOL)


def test_a_race_nobody_finished_is_an_explicit_error():
    """Spec section 7: "Return an explicit error rather than dividing by an
    empty set"."""
    race = regatta(
        entry("A", 1.0, status=RaceStatus.DNF),
        entry("B", 1.0, status=RaceStatus.DNC),
    )
    with pytest.raises(InvalidInput, match="at least one finisher"):
        compute_regatta_adjustment(race)


def test_finishers_keep_their_real_elapsed_time():
    results = by_id(three_finishers_plus(entry("ABSENT", 1.0, status=RaceStatus.DNC)))
    assert results["F1"].elapsed_seconds_used == 3600
    assert results["F1"].elapsed_seconds == 3600


def test_back_calculated_boats_still_get_no_corrected_time_or_place():
    """The back-calculated time is for the handicap sums only. A boat that did
    not finish did not finish, and takes no place."""
    result = by_id(three_finishers_plus(entry("ABSENT", 1.0, status=RaceStatus.DNC)))["ABSENT"]
    assert result.corrected_time is None
    assert result.position is None


# --------------------------------------------------------------------------
# Step 2 - the sums run over the whole fleet
# --------------------------------------------------------------------------


def test_a_non_finisher_does_move_everyone_elses_handicap():
    """The opposite of a club series, where an absent boat is excluded from the
    sums entirely. Here it is back-calculated in, so it counts."""
    sailed = (entry("A", 0.95, 3600), entry("B", 1.00, 3500))
    without = by_id(regatta(*sailed))
    with_absentee = by_id(regatta(*sailed, entry("GHOST", 1.30, status=RaceStatus.DNC)))
    assert with_absentee["A"].achieved_handicap != without["A"].achieved_handicap


def test_every_boat_gets_an_adjustment_scale():
    """No zeroes here: every boat has a usable elapsed time, so every boat has
    an AS."""
    results = by_id(three_finishers_plus(entry("ABSENT", 1.0, status=RaceStatus.DNC)))
    assert all(r.adjustment_scale > 0 for r in results.values())


# --------------------------------------------------------------------------
# Step 4 - the clamp
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tcf", "base", "expected"),
    [
        (1.00, 1.00, 1.00),    # inside the band
        (1.20, 1.00, 1.10),    # above
        (0.80, 1.00, 0.90),    # below
        (1.10, 1.00, 1.10),    # exactly on the upper bound
        (0.90, 1.00, 0.90),    # exactly on the lower bound
        (1.045, 0.95, 1.045),  # band scales with the boat's own base number
        (1.100, 0.95, 1.045),
    ],
)
def test_clamp_holds_a_handicap_within_ten_percent_of_its_base_number(tcf, base, expected):
    assert clamp_to_base_number(tcf, base) == pytest.approx(expected, abs=TOL)


def test_a_runaway_result_is_clamped():
    """A boat far quicker than its rating earns a big TCFr, but cannot be rated
    more than 10% above its own base number in one go."""
    race = regatta(
        entry("FLYER", 1.0, 1800, base=1.0),
        entry("B", 1.0, 4000, base=1.0),
        entry("C", 1.0, 4200, base=1.0),
    )
    result = by_id(race)["FLYER"]
    assert result.next_tcf > 1.1
    assert result.next_tcf_clamped == pytest.approx(1.1, abs=TOL)


def test_the_pre_clamp_value_stays_visible():
    """Spec section 6 keeps TCFn and the clamped TCFn apart so the arithmetic
    can be checked."""
    race = regatta(entry("FLYER", 1.0, 1800), entry("B", 1.0, 4000), entry("C", 1.0, 4200))
    result = by_id(race)["FLYER"]
    assert result.next_tcf != result.next_tcf_clamped


def test_effective_next_tcf_is_the_clamped_one():
    race = regatta(entry("FLYER", 1.0, 1800), entry("B", 1.0, 4000), entry("C", 1.0, 4200))
    result = by_id(race)["FLYER"]
    assert result.effective_next_tcf == result.next_tcf_clamped


def test_the_clamp_applies_on_the_first_race_too():
    """Spec section 4, step 4: "at every race of the regatta, not just the
    first"."""
    race = regatta(
        entry("FLYER", 1.0, 1800), entry("B", 1.0, 4000), entry("C", 1.0, 4200), first=True
    )
    assert by_id(race)["FLYER"].next_tcf_clamped == pytest.approx(1.1, abs=TOL)


def test_a_result_inside_the_band_is_left_alone():
    race = regatta(entry("A", 1.0, 3600), entry("B", 1.0, 3700))
    result = by_id(race)["A"]
    assert result.next_tcf_clamped == pytest.approx(result.next_tcf, abs=TOL)


def test_the_clamp_uses_each_boats_own_base_number():
    """Not the fleet's, and not the handicap it is racing under."""
    race = regatta(
        entry("SMALL", 1.0, 1800, base=0.80),
        entry("B", 1.0, 4000, base=1.00),
        entry("C", 1.0, 4200, base=1.00),
    )
    assert by_id(race)["SMALL"].next_tcf_clamped == pytest.approx(0.88, abs=TOL)


# --------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------


def test_a_club_race_is_refused():
    race = RaceInput(
        series_type=SeriesType.CLUB,
        entries=[RaceEntry("A", RaceStatus.FINISHED, 1.0, 3600)],
    )
    with pytest.raises(InvalidInput, match="compute_club_adjustment"):
        compute_regatta_adjustment(race)


def test_results_come_back_in_entry_order():
    race = regatta(
        entry("Z", 1.0, 4000), entry("Y", 1.0, status=RaceStatus.DNC), entry("X", 1.0, 3600)
    )
    assert [r.boat_id for r in compute_regatta_adjustment(race)] == ["Z", "Y", "X"]


def test_adjustment_does_not_mutate_the_input():
    first = entry("A", 0.95, 3600)
    race = regatta(first, entry("B", 1.0, 3500))
    compute_regatta_adjustment(race)
    assert race.entries[0] is first
    assert first.tcf_used == 0.95


def test_handicaps_are_not_rounded():
    result = by_id(regatta(entry("A", 1.0, 3600), entry("B", 1.0, 4000)))["A"]
    assert result.next_tcf != round(result.next_tcf, 3)
