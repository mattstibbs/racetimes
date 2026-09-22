"""Tests for series standings (RRS A2.1 and A8).

Most of these build RaceOutcomes directly from points rather than sailing a
series, because the interesting cases are exact patterns of scores that would
be fiddly to produce from elapsed times.
"""

import pytest

from nhc import (
    Boat,
    Finish,
    InvalidInput,
    RaceOutcome,
    RaceResult,
    RaceStatus,
    Series,
    SeriesRace,
    compute_standings,
    score_series,
)


def race(race_id, **points):
    """race("R1", A=1, B=2) - a scored race, given only the points."""
    results = tuple(
        RaceResult(
            boat_id=boat_id,
            status=RaceStatus.FINISHED,
            tcf_used=1.0,
            elapsed_seconds=3600.0,
            corrected_time=3600.0,
            position=None,
            points=None if value is None else float(value),
        )
        for boat_id, value in points.items()
    )
    return RaceOutcome(race_id=race_id, results=results)


def order(standings):
    return [s.boat_id for s in standings]


def by_id(standings):
    return {s.boat_id: s for s in standings}


# --------------------------------------------------------------------------
# A2.1 - totals and discards
# --------------------------------------------------------------------------


def test_lowest_total_wins():
    standings = compute_standings([race("R1", A=3, B=1, C=2)], discards=0)
    assert order(standings) == ["B", "C", "A"]
    assert [s.position for s in standings] == [1, 2, 3]


def test_the_worst_score_is_excluded_by_default():
    """A2.1's default is one discard."""
    standing = by_id(compute_standings([race("R1", A=1), race("R2", A=9)]))["A"]
    assert standing.total == 1.0
    assert standing.discarded_race_ids == ("R2",)


def test_no_discard_when_asked_for_none():
    standing = by_id(compute_standings([race("R1", A=1), race("R2", A=9)], discards=0))["A"]
    assert standing.total == 10.0
    assert standing.discarded_race_ids == ()


def test_two_discards_drop_the_two_worst():
    races = [race("R1", A=1), race("R2", A=9), race("R3", A=4), race("R4", A=7)]
    standing = by_id(compute_standings(races, discards=2))["A"]
    assert standing.total == 5.0
    assert sorted(standing.discarded_race_ids) == ["R2", "R4"]


def test_equal_worst_scores_discard_the_earliest_race():
    """A2.1: "the score(s) for the race(s) sailed earliest in the series shall
    be excluded". The total is the same either way, so only the race named in
    brackets reveals whether this is right."""
    races = [race("R1", A=5), race("R2", A=2), race("R3", A=5)]
    standing = by_id(compute_standings(races, discards=1))["A"]
    assert standing.discarded_race_ids == ("R1",)
    assert standing.counted_points == (2.0, 5.0)


def test_discarding_more_races_than_were_sailed_zeroes_everyone():
    """The literal reading of A2.1 under a misconfigured discard count: with
    one race and one or more discards, every boat totals zero. It surfaces the
    mistake rather than hiding it.

    The fleet is still ranked, because A8.2 breaks the resulting tie on the
    last race and explicitly uses excluded scores - which here is every score
    there is."""
    standings = compute_standings([race("R1", A=1, B=2)], discards=3)
    assert all(s.total == 0.0 for s in standings)
    assert order(standings) == ["A", "B"]


def test_scores_stay_in_series_order_for_display():
    races = [race("R1", A=9), race("R2", A=1), race("R3", A=5)]
    standing = by_id(compute_standings(races))["A"]
    assert [s.race_id for s in standing.scores] == ["R1", "R2", "R3"]
    assert [s.discarded for s in standing.scores] == [True, False, False]


# --------------------------------------------------------------------------
# A8.1 - countback on the counted scores
# --------------------------------------------------------------------------


def test_a8_1_breaks_a_tie_on_the_best_score():
    """Equal totals; A has a first, B has a second, so A wins."""
    races = [race("R1", A=1, B=2), race("R2", A=4, B=3)]
    assert order(compute_standings(races, discards=0)) == ["A", "B"]


def test_a8_1_compares_position_by_position_not_just_the_best():
    """Both boats have a first, so the tie falls to their second-best score.
    Sorted, A is [1, 3, 5] and B is [1, 4, 4]: equal at the front, and A is
    better at the next position down."""
    races = [race("R1", A=1, B=1), race("R2", A=5, B=4), race("R3", A=3, B=4)]
    assert order(compute_standings(races, discards=0)) == ["A", "B"]


# --------------------------------------------------------------------------
# A8.2 - countback on the later races, discarded scores included
# --------------------------------------------------------------------------


def test_a8_2_breaks_a_surviving_tie_on_the_last_race():
    """Identical sorted scores, so A8.1 cannot separate them. B wins the last
    race and so wins the series."""
    races = [race("R1", A=1, B=3), race("R2", A=3, B=1)]
    assert order(compute_standings(races, discards=0)) == ["B", "A"]


def test_a8_2_falls_back_to_the_next_to_last_race():
    races = [race("R1", A=1, B=4), race("R2", A=4, B=1), race("R3", A=3, B=3)]
    assert order(compute_standings(races, discards=0)) == ["B", "A"]


def test_a8_1_ignores_discarded_scores_but_a8_2_uses_them():
    """The one place the two rules deliberately disagree, and the only test
    here that can tell a correct implementation from a plausible wrong one.

    A discards R3 (5), B discards R1 (9). Both count {2, 3}, so A8.1 ties and
    the series falls to A8.2 on the last race: A scored 5, B scored 3, so B
    wins - and A's 5 is a discarded score being used, exactly as A8.2 requires.

    An implementation that let discarded scores into A8.1 would compare
    [2,3,5] against [2,3,9], break the tie there, and hand it to A.
    """
    races = [
        race("R1", A=2, B=9),
        race("R2", A=3, B=2),
        race("R3", A=5, B=3),
    ]
    standings = compute_standings(races, discards=1)
    rows = by_id(standings)

    assert rows["A"].total == rows["B"].total == 5.0
    assert rows["A"].discarded_race_ids == ("R3",)
    assert rows["B"].discarded_race_ids == ("R1",)
    assert sorted(rows["A"].counted_points) == sorted(rows["B"].counted_points)
    assert order(standings) == ["B", "A"]


def test_boats_that_stay_tied_share_a_place_and_consume_the_one_below():
    races = [race("R1", A=1, B=1, C=3), race("R2", A=1, B=1, C=3)]
    standings = by_id(compute_standings(races, discards=0))
    assert standings["A"].position == 1
    assert standings["B"].position == 1
    assert standings["C"].position == 3


# --------------------------------------------------------------------------
# Properties
# --------------------------------------------------------------------------


def test_counted_points_excludes_the_discards():
    races = [race("R1", A=1), race("R2", A=9), race("R3", A=4)]
    standing = by_id(compute_standings(races, discards=1))["A"]
    assert standing.counted_points == (1.0, 4.0)


def test_points_are_kept_as_floats_including_shared_tie_points():
    races = [race("R1", A=1.5, B=1.5), race("R2", A=1, B=2)]
    rows = by_id(compute_standings(races, discards=0))
    assert rows["A"].total == 2.5
    assert rows["B"].total == 3.5


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_negative_discards_are_rejected():
    with pytest.raises(InvalidInput, match="discards cannot be negative"):
        compute_standings([race("R1", A=1)], discards=-1)


def test_a_series_with_no_races_has_no_standings():
    assert compute_standings([]) == ()


def test_races_covering_different_boats_are_rejected():
    """A boat entered in a series is scored for the whole series (A2.2), so a
    gap means the outcomes were assembled by hand and got it wrong."""
    races = [race("R1", A=1, B=2), race("R2", A=1)]
    with pytest.raises(InvalidInput, match="does not cover the same boats"):
        compute_standings(races)


def test_unscored_races_are_rejected():
    with pytest.raises(InvalidInput, match="has no points"):
        compute_standings([race("R1", A=None)])


# --------------------------------------------------------------------------
# Through a real series
# --------------------------------------------------------------------------


def sailed_series(**kwargs):
    boats = [Boat(b, base_number=1.0, current_tcf=1.0) for b in ("ALBA", "BREEZE", "CIRRUS")]
    races = [
        SeriesRace("R1", [Finish("ALBA", RaceStatus.FINISHED, 3600),
                          Finish("BREEZE", RaceStatus.FINISHED, 3700),
                          Finish("CIRRUS", RaceStatus.FINISHED, 3800)]),
        SeriesRace("R2", [Finish("ALBA", RaceStatus.FINISHED, 3800),
                          Finish("BREEZE", RaceStatus.FINISHED, 3600),
                          Finish("CIRRUS", RaceStatus.DNF)]),
        SeriesRace("R3", [Finish("ALBA", RaceStatus.FINISHED, 3700),
                          Finish("BREEZE", RaceStatus.FINISHED, 3800),
                          Finish("CIRRUS", RaceStatus.FINISHED, 3600)]),
        SeriesRace("R4", [Finish("ALBA", RaceStatus.FINISHED, 3900),
                          Finish("BREEZE", RaceStatus.FINISHED, 3650),
                          Finish("CIRRUS", RaceStatus.FINISHED, 3700)]),
    ]
    return score_series(Series(boats=boats, races=races, **kwargs))


def test_score_series_produces_standings():
    standings = sailed_series().standings
    assert order(standings) == ["BREEZE", "ALBA", "CIRRUS"]
    assert [s.total for s in standings] == [4.0, 5.0, 6.0]


def test_a_boats_dnf_is_scored_and_can_be_discarded():
    standing = by_id(sailed_series().standings)["CIRRUS"]
    # Three boats entered, so a DNF scores 4 under A5.2 - and it is the worst.
    assert standing.discarded_race_ids == ("R2",)


def test_the_series_discard_setting_reaches_the_standings():
    assert [s.total for s in sailed_series(discards=0).standings] != [
        s.total for s in sailed_series(discards=1).standings
    ]


def test_a_negative_discard_count_is_rejected_when_the_series_is_built():
    with pytest.raises(InvalidInput, match="discards cannot be negative"):
        Series(boats=[Boat("A", base_number=1.0, current_tcf=1.0)], races=[], discards=-1)
