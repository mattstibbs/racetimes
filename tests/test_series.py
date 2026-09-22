"""Tests for replaying a whole series.

The behaviour that matters most here is the chain: each race is scored on the
handicaps the previous race produced. Everything else in the module exists to
serve that.
"""

import pytest

from nhc import (
    Boat,
    Finish,
    HandicapProgression,
    InvalidInput,
    RaceStatus,
    Series,
    SeriesRace,
    SeriesType,
    score_series,
)

FIN = RaceStatus.FINISHED


def boat(boat_id, base=1.0, current=None):
    return Boat(boat_id=boat_id, base_number=base, current_tcf=base if current is None else current)


def three_boats():
    return [boat("A"), boat("B"), boat("C")]


def race(race_id, **times):
    """race("R1", A=3600, B=4000) - keyword per boat, or a RaceStatus for a code."""
    finishes = []
    for boat_id, value in times.items():
        if isinstance(value, RaceStatus):
            finishes.append(Finish(boat_id=boat_id, status=value))
        else:
            finishes.append(Finish(boat_id=boat_id, status=FIN, elapsed_seconds=value))
    return SeriesRace(race_id, finishes)


def results_by_id(outcome, race_id):
    return {r.boat_id: r for r in outcome.race(race_id).results}


# --------------------------------------------------------------------------
# The chain
# --------------------------------------------------------------------------


def test_each_race_is_scored_on_the_previous_races_handicaps():
    series = Series(
        boats=three_boats(),
        races=[
            race("R1", A=3600, B=4000, C=4600),
            race("R2", A=3700, B=3900, C=4400),
            race("R3", A=3500, B=4100, C=4500),
        ],
    )
    outcome = score_series(series)

    for earlier, later in zip(outcome.races, outcome.races[1:]):
        produced = {r.boat_id: r.next_tcf for r in earlier.results}
        used = {r.boat_id: r.tcf_used for r in later.results}
        assert used == produced, f"{later.race_id} did not inherit {earlier.race_id}"


def test_handicaps_actually_move_across_a_series():
    """Guards the chain test above against passing vacuously if nothing ever
    changed."""
    series = Series(boats=three_boats(), races=[race("R1", A=3600, B=4000, C=4600)])
    outcome = score_series(series)
    assert results_by_id(outcome, "R1")["A"].next_tcf != 1.0


def test_ending_handicaps_come_from_the_final_race():
    series = Series(
        boats=three_boats(),
        races=[race("R1", A=3600, B=4000, C=4600), race("R2", A=3700, B=3900, C=4400)],
    )
    outcome = score_series(series)
    assert outcome.ending_handicaps == {
        r.boat_id: r.next_tcf for r in outcome.races[-1].results
    }


def test_re_scoring_the_same_series_gives_the_same_answer():
    series = Series(boats=three_boats(), races=[race("R1", A=3600, B=4000, C=4600)])
    assert score_series(series) == score_series(series)


def test_correcting_a_finish_changes_that_race_and_every_later_one():
    """The brief's central invariant: handicaps are never edited directly, so a
    corrected finish must ripple forward. Races before it must not move."""
    races = [
        race("R1", A=3600, B=4000, C=4600),
        race("R2", A=3700, B=3900, C=4400),
        race("R3", A=3500, B=4100, C=4500),
    ]
    before = score_series(Series(boats=three_boats(), races=races))

    corrected = list(races)
    corrected[1] = race("R2", A=3750, B=3900, C=4400)  # A's time was mis-recorded
    after = score_series(Series(boats=three_boats(), races=corrected))

    assert after.race("R1") == before.race("R1")
    assert after.race("R2") != before.race("R2")
    assert after.race("R3") != before.race("R3")


# --------------------------------------------------------------------------
# Where the series starts (the progression policy)
# --------------------------------------------------------------------------


def test_carry_over_starts_from_the_boats_current_handicap():
    series = Series(
        boats=[boat("A", base=0.900, current=0.950), boat("B", base=1.000, current=1.020)],
        races=[race("R1", A=3600, B=4000)],
        progression=HandicapProgression.CARRY_OVER,
    )
    used = {r.boat_id: r.tcf_used for r in score_series(series).races[0].results}
    assert used == {"A": 0.950, "B": 1.020}


def test_reset_starts_from_the_published_base_number():
    series = Series(
        boats=[boat("A", base=0.900, current=0.950), boat("B", base=1.000, current=1.020)],
        races=[race("R1", A=3600, B=4000)],
        progression=HandicapProgression.RESET,
    )
    used = {r.boat_id: r.tcf_used for r in score_series(series).races[0].results}
    assert used == {"A": 0.900, "B": 1.000}


def test_carry_over_is_the_default():
    series = Series(boats=[boat("A", base=0.9, current=0.95)], races=[race("R1", A=3600)])
    assert score_series(series).races[0].results[0].tcf_used == 0.95


def test_the_two_progressions_agree_when_nothing_has_drifted():
    """Progression only picks the starting point. A boat still on its base
    number starts there either way, so the whole series must come out the same."""
    boats = [boat("A", base=1.0, current=1.0), boat("B", base=1.0, current=1.0)]
    races = [race("R1", A=3600, B=4000), race("R2", A=3700, B=3900)]
    carried = score_series(Series(boats=boats, races=races, progression=HandicapProgression.CARRY_OVER))
    reset = score_series(Series(boats=boats, races=races, progression=HandicapProgression.RESET))
    assert carried == reset


def test_a_drifted_handicap_makes_the_two_progressions_diverge_for_good():
    """Once they start apart they stay apart, because each race feeds the next."""
    boats = [boat("A", base=0.90, current=0.95), boat("B", base=1.00, current=1.02)]
    races = [race("R1", A=3600, B=4000), race("R2", A=3700, B=3900)]
    carried = score_series(Series(boats=boats, races=races, progression=HandicapProgression.CARRY_OVER))
    reset = score_series(Series(boats=boats, races=races, progression=HandicapProgression.RESET))
    assert carried.races[0] != reset.races[0]
    assert carried.races[1] != reset.races[1]


def test_starting_handicaps_are_recorded_on_the_outcome():
    series = Series(boats=[boat("A", base=0.9, current=0.95)], races=[])
    assert dict(score_series(series).starting_handicaps) == {"A": 0.95}


# --------------------------------------------------------------------------
# Boats with no recorded finish (RRS A2.2)
# --------------------------------------------------------------------------


def test_a_boat_with_no_recorded_finish_is_scored_dnc():
    series = Series(boats=three_boats(), races=[race("R1", A=3600, B=4000)])
    result = results_by_id(score_series(series), "R1")["C"]
    assert result.status is RaceStatus.DNC
    assert result.position is None


def test_an_absent_boat_keeps_its_handicap():
    series = Series(
        boats=[boat("A"), boat("B"), boat("ABSENT", base=1.07)],
        races=[race("R1", A=3600, B=4000)],
    )
    result = results_by_id(score_series(series), "R1")["ABSENT"]
    assert result.next_tcf == 1.07


def test_an_absent_boat_scores_the_series_entry_count_plus_one():
    series = Series(boats=three_boats(), races=[race("R1", A=3600, B=4000)])
    assert results_by_id(score_series(series), "R1")["C"].points == 4.0


def test_every_boat_gets_a_result_in_every_race():
    series = Series(
        boats=three_boats(),
        races=[race("R1", A=3600), race("R2", B=4000), race("R3", C=4600)],
    )
    outcome = score_series(series)
    for race_outcome in outcome.races:
        assert [r.boat_id for r in race_outcome.results] == ["A", "B", "C"]


def test_an_explicit_code_is_kept_rather_than_overwritten():
    series = Series(boats=three_boats(), races=[race("R1", A=3600, B=4000, C=RaceStatus.DNF)])
    assert results_by_id(score_series(series), "R1")["C"].status is RaceStatus.DNF


# --------------------------------------------------------------------------
# Series-level settings reaching the layers below
# --------------------------------------------------------------------------


def test_minimum_finishers_reaches_the_adjustment():
    races = [race("R1", A=3600, B=4000, C=RaceStatus.DNF)]
    without = score_series(Series(boats=three_boats(), races=races))
    with_threshold = score_series(Series(boats=three_boats(), races=races, minimum_finishers=3))
    assert results_by_id(without, "R1")["A"].next_tcf != 1.0
    assert results_by_id(with_threshold, "R1")["A"].next_tcf == 1.0


def test_apply_a5_3_reaches_the_points():
    races = [race("R1", A=3600, B=RaceStatus.DNS)]
    series = Series(boats=three_boats(), races=races, apply_a5_3=True)
    results = results_by_id(score_series(series), "R1")
    # B came to the starting area (2 boats did), C never did.
    assert results["B"].points == 3.0
    assert results["C"].points == 4.0


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_a_series_needs_at_least_one_boat():
    with pytest.raises(InvalidInput, match="at least one boat"):
        Series(boats=[], races=[])


def test_a_series_with_no_races_yet_is_allowed():
    """User journey 1 creates a series before any race is sailed."""
    outcome = score_series(Series(boats=three_boats(), races=[]))
    assert outcome.races == ()
    assert outcome.ending_handicaps == {"A": 1.0, "B": 1.0, "C": 1.0}


def test_a_boat_cannot_be_entered_twice():
    with pytest.raises(InvalidInput, match="entered twice"):
        Series(boats=[boat("A"), boat("A")], races=[])


def test_race_ids_must_be_unique():
    with pytest.raises(InvalidInput, match="duplicate race_id"):
        Series(boats=three_boats(), races=[race("R1", A=3600), race("R1", A=3700)])


def test_a_race_cannot_record_a_boat_that_is_not_in_the_series():
    with pytest.raises(InvalidInput, match="not entered in the series: STOWAWAY"):
        Series(boats=[boat("A")], races=[race("R1", A=3600, STOWAWAY=4000)])


def test_a_boat_cannot_have_two_finishes_in_one_race():
    with pytest.raises(InvalidInput, match="two recorded finishes"):
        SeriesRace("R1", [Finish("A", FIN, 3600), Finish("A", FIN, 3700)])


def test_a_race_needs_an_id():
    with pytest.raises(InvalidInput, match="race_id is required"):
        SeriesRace("", [])


def test_a_negative_threshold_is_rejected_when_the_series_is_built():
    with pytest.raises(InvalidInput, match="minimum_finishers"):
        Series(boats=three_boats(), races=[], minimum_finishers=-1)


def test_an_unknown_progression_is_rejected():
    with pytest.raises(InvalidInput, match="progression must be one of"):
        Series(boats=three_boats(), races=[], progression="SOMETIMES")


def test_regatta_series_are_refused_for_now():
    series = Series(boats=three_boats(), races=[], series_type=SeriesType.REGATTA)
    with pytest.raises(InvalidInput, match="not implemented yet"):
        score_series(series)


def test_looking_up_an_unknown_race_raises():
    outcome = score_series(Series(boats=three_boats(), races=[race("R1", A=3600)]))
    with pytest.raises(KeyError):
        outcome.race("NOPE")
