"""Tests for race points under RRS Appendix A.

Source of truth is Appendix A of the 2025-2028 rules, in docs/reference/. The
rule numbers in the test names are the ones being pinned.
"""

import pytest

from nhc import (
    InvalidInput,
    RaceEntry,
    RaceInput,
    RaceStatus,
    SeriesType,
    points_for_place,
    score_points,
    score_race,
)
from tests.scenario_loader import build_race_input, expected_for, race_boat_params

POINTS_PARAMS, POINTS_IDS = race_boat_params("points")


def finisher(boat_id, tcf, elapsed):
    return RaceEntry(
        boat_id=boat_id, status=RaceStatus.FINISHED, tcf_used=tcf, elapsed_seconds=elapsed
    )


def club_race(*entries):
    return RaceInput(series_type=SeriesType.CLUB, entries=entries)


def points_by_id(race, *, series_entry_count=None, **kwargs):
    results = score_race(race)
    if series_entry_count is None:
        series_entry_count = len(results)
    scored = score_points(results, series_entry_count=series_entry_count, **kwargs)
    return {r.boat_id: r.points for r in scored}


# --------------------------------------------------------------------------
# A4 - Low Point System
# --------------------------------------------------------------------------


@pytest.mark.parametrize("place", range(1, 9))
def test_a4_points_equal_the_finishing_place(place):
    assert points_for_place(place) == float(place)


def test_a4_scores_a_fleet_in_order():
    race = club_race(*(finisher(f"B{i}", tcf=1.0, elapsed=3600 + i * 60) for i in range(5)))
    assert points_by_id(race) == {"B0": 1.0, "B1": 2.0, "B2": 3.0, "B3": 4.0, "B4": 5.0}


def test_points_are_floats_even_when_whole():
    """A7 ties produce halves, so the field is a float throughout rather than
    changing type depending on whether anyone tied."""
    assert isinstance(points_by_id(club_race(finisher("A", 1.0, 3600)))["A"], float)


# --------------------------------------------------------------------------
# A7 - race ties
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("scenario", "boat_id"), POINTS_PARAMS, ids=POINTS_IDS)
def test_points_match_the_fixture(scenario, boat_id):
    race = build_race_input(scenario)
    assert points_by_id(race)[boat_id] == pytest.approx(
        expected_for(scenario)[boat_id]["points"]
    )


def test_a7_two_boats_tied_for_first_share_first_and_second():
    """(1 + 2) / 2 = 1.5 each, and the next boat is third on 3 - the place
    below a tie is consumed, not reused."""
    race = club_race(
        finisher("X", tcf=1.0, elapsed=4000),   # 4000
        finisher("Y", tcf=0.8, elapsed=5000),   # 4000
        finisher("Z", tcf=1.2, elapsed=3500),   # 4200
    )
    assert points_by_id(race) == {"X": 1.5, "Y": 1.5, "Z": 3.0}


def test_a7_three_boats_tied_for_first_share_the_first_three_places():
    race = club_race(
        finisher("A", tcf=1.0, elapsed=4000),
        finisher("B", tcf=0.5, elapsed=8000),
        finisher("C", tcf=2.0, elapsed=2000),
        finisher("D", tcf=1.0, elapsed=4100),
    )
    assert points_by_id(race) == {"A": 2.0, "B": 2.0, "C": 2.0, "D": 4.0}


def test_a7_a_tie_further_down_the_fleet():
    race = club_race(
        finisher("WINNER", tcf=1.0, elapsed=3000),
        finisher("TIED_A", tcf=1.0, elapsed=4000),
        finisher("TIED_B", tcf=0.8, elapsed=5000),
        finisher("LAST", tcf=1.0, elapsed=5000),
    )
    assert points_by_id(race) == {
        "WINNER": 1.0,
        "TIED_A": 2.5,
        "TIED_B": 2.5,
        "LAST": 4.0,
    }


@pytest.mark.parametrize(
    ("place", "tied", "expected"),
    [(1, 1, 1.0), (1, 2, 1.5), (1, 3, 2.0), (2, 2, 2.5), (5, 4, 6.5)],
)
def test_points_for_place_averages_the_consumed_places(place, tied, expected):
    assert points_for_place(place, tied) == expected


# --------------------------------------------------------------------------
# A5.2 - boats that did not finish
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [RaceStatus.DNC, RaceStatus.DNS, RaceStatus.DNF], ids=str)
def test_a5_2_non_finishers_score_one_more_than_the_series_entry_count(status):
    """The 2025-2028 wording treats every non-finisher alike. Earlier editions
    split DNC from the rest."""
    race = club_race(
        finisher("A", tcf=1.0, elapsed=3600),
        RaceEntry(boat_id="B", status=status, tcf_used=1.0),
    )
    assert points_by_id(race, series_entry_count=12)["B"] == 13.0


def test_a5_2_uses_the_series_entry_count_not_the_boats_present():
    """A race with absentees must not under-score its non-finishers - which is
    why the count is a required argument rather than inferred."""
    race = club_race(
        finisher("A", tcf=1.0, elapsed=3600),
        RaceEntry(boat_id="B", status=RaceStatus.DNF, tcf_used=1.0),
    )
    assert points_by_id(race, series_entry_count=2)["B"] == 3.0
    assert points_by_id(race, series_entry_count=20)["B"] == 21.0


def test_a_race_nobody_finished_scores_everyone_as_a_non_finisher():
    race = club_race(
        RaceEntry(boat_id="A", status=RaceStatus.DNC, tcf_used=1.0),
        RaceEntry(boat_id="B", status=RaceStatus.DNS, tcf_used=1.0),
    )
    assert points_by_id(race, series_entry_count=6) == {"A": 7.0, "B": 7.0}


# --------------------------------------------------------------------------
# A5.3 - the option for boats that at least turned up
# --------------------------------------------------------------------------


def a5_3_race():
    return club_race(
        finisher("SAILED", tcf=1.0, elapsed=3600),
        RaceEntry(boat_id="CAME_BUT_DNS", status=RaceStatus.DNS, tcf_used=1.0),
        RaceEntry(boat_id="STARTED_BUT_DNF", status=RaceStatus.DNF, tcf_used=1.0),
        RaceEntry(boat_id="STAYED_HOME", status=RaceStatus.DNC, tcf_used=1.0),
    )


def test_a5_3_is_off_unless_asked_for():
    """A5.3 applies only if the notice of race or sailing instructions say so."""
    points = points_by_id(a5_3_race(), series_entry_count=10)
    assert points["CAME_BUT_DNS"] == 11.0
    assert points["STAYED_HOME"] == 11.0


def test_a5_3_scores_boats_that_came_to_the_starting_area_more_kindly():
    """Three of the four boats came to the starting area, so they score 4; the
    DNC never came and still scores the series entry count plus one."""
    points = points_by_id(a5_3_race(), series_entry_count=10, apply_a5_3=True)
    assert points["CAME_BUT_DNS"] == 4.0
    assert points["STARTED_BUT_DNF"] == 4.0
    assert points["STAYED_HOME"] == 11.0


def test_a5_3_does_not_change_finishers():
    assert points_by_id(a5_3_race(), series_entry_count=10, apply_a5_3=True)["SAILED"] == 1.0


# --------------------------------------------------------------------------
# Validation and shape
# --------------------------------------------------------------------------


def test_a_series_entry_count_below_the_fleet_size_is_rejected():
    race = club_race(finisher("A", 1.0, 3600), finisher("B", 1.0, 3700))
    with pytest.raises(InvalidInput, match="smaller than the number of boats"):
        score_points(score_race(race), series_entry_count=1)


def test_a_series_entry_count_of_zero_is_rejected():
    with pytest.raises(InvalidInput, match="at least 1"):
        score_points(score_race(club_race(finisher("A", 1.0, 3600))), series_entry_count=0)


@pytest.mark.parametrize(("place", "tied"), [(0, 1), (-1, 1), (1, 0)])
def test_points_for_place_rejects_nonsense(place, tied):
    with pytest.raises(InvalidInput):
        points_for_place(place, tied)


def test_scoring_points_preserves_the_other_fields():
    race = club_race(finisher("A", tcf=0.95, elapsed=3600))
    before = score_race(race)[0]
    after = score_points([before], series_entry_count=1)[0]
    assert after.corrected_time == before.corrected_time
    assert after.position == before.position
    assert after.tcf_used == before.tcf_used
    assert after.points == 1.0


def test_results_come_back_in_the_order_given():
    race = club_race(
        finisher("LAST", tcf=1.0, elapsed=5000),
        finisher("FIRST", tcf=1.0, elapsed=3000),
    )
    scored = score_points(score_race(race), series_entry_count=2)
    assert [r.boat_id for r in scored] == ["LAST", "FIRST"]


def test_points_are_none_until_scored():
    assert score_race(club_race(finisher("A", 1.0, 3600)))[0].points is None
