"""Slice 25, part B: RYA YTC, scored by sailscoring.fixed_number.

The worked examples YTC-1 and YTC-2 are in tests/fixtures/ytc.yaml, worked by
hand from section 6.2 of the RYA YTC 2026 Policy and Procedures and checked by
the project owner. The engine is never used to produce an expected value.

YTC is another fixed-number system, so the general behaviour (no handicap
moves, a changed finish changes only its race, the refusals) is tested for
every system in tests/test_fixed_number.py. This module checks what is specific
to YTC: the formula, the examples, and that the engine knows nothing about a
boat's two numbers.
"""

import dataclasses

import pytest

from sailscoring import (
    Finish,
    FixedNumberBoat,
    FixedNumberResult,
    FixedNumberSeries,
    FixedNumberSystem,
    InvalidInput,
    RaceStatus,
    SeriesRace,
    fixed_number_corrected_time,
    score_fixed_number_series,
)
from tests.scenario_loader import YTC_FIXTURE

YTC = FixedNumberSystem.YTC
EXAMPLES = YTC_FIXTURE
DISPLAY_TOLERANCE = 0.0005


def build(example, boats=None, system=YTC):
    boats = example["boats"] if boats is None else boats
    races = []
    for race in example["races"]:
        finishes = []
        for boat_id, value in race["finishes"].items():
            if isinstance(value, str):
                finishes.append(Finish(boat_id=boat_id, status=RaceStatus(value)))
            else:
                finishes.append(
                    Finish(
                        boat_id=boat_id,
                        status=RaceStatus.FINISHED,
                        elapsed_seconds=value,
                    )
                )
        races.append(SeriesRace(race_id=race["race_id"], finishes=finishes))
    return FixedNumberSeries(
        [FixedNumberBoat(boat_id=b, number=n) for b, n in boats.items()],
        races,
        system,
        discards=example["discards"],
    )


def check_races(outcome, expected_races):
    for race, expected in zip(outcome.races, expected_races, strict=True):
        results = {r.boat_id: r for r in race.results}
        for boat_id, want in expected.items():
            got = results[boat_id]
            assert got.points == want["points"], (race.race_id, boat_id)
            if "place" in want:
                assert got.position == want["place"], (race.race_id, boat_id)
                assert got.corrected_time == pytest.approx(
                    want["corrected"], abs=DISPLAY_TOLERANCE
                ), (race.race_id, boat_id)
            else:
                assert got.position is None and got.corrected_time is None


def check_standings(outcome, expected):
    assert [(s.boat_id, s.position, s.total) for s in outcome.standings] == [
        (row["boat"], row["position"], row["total"]) for row in expected
    ]


@pytest.mark.parametrize("example_id", list(EXAMPLES))
def test_the_worked_examples(example_id):
    example = EXAMPLES[example_id]
    outcome = score_fixed_number_series(build(example))
    check_races(outcome, [race["expected"] for race in example["races"]])
    check_standings(outcome, example["standings"])


def test_the_same_series_with_a_on_her_ytc_number_gives_the_other_table():
    """YTC-1: which number A is entered on decides who wins the series."""
    example = EXAMPLES["YTC-1"]
    other = example["with_a_on_her_ytc_number"]
    outcome = score_fixed_number_series(build(example, boats=other["boats"]))
    check_races(outcome, [race["expected"] for race in other["races"]])
    check_standings(outcome, other["standings"])


def test_a_boat_sails_every_race_on_the_number_she_was_given():
    example = EXAMPLES["YTC-1"]
    for result in (
        r
        for race in score_fixed_number_series(build(example)).races
        for r in race.results
    ):
        assert result.number == example["boats"][result.boat_id]


def test_equal_corrected_times_tie_and_a_near_miss_does_not():
    results = {
        r.boat_id: r
        for r in score_fixed_number_series(build(EXAMPLES["YTC-2"])).races[0].results
    }
    assert results["D"].position == results["E"].position == 1
    assert results["F"].position == 3 and results["G"].position == 4
    # The pages round both to the same second; places use the full value.
    assert round(results["F"].corrected_time) == round(results["G"].corrected_time)


@pytest.mark.parametrize(
    ("elapsed", "number"), [(3600, 899), (3600, 873), (4190, 1010), (3800, 950)]
)
def test_ytc_corrected_time_is_elapsed_times_1000_over_the_number(elapsed, number):
    assert fixed_number_corrected_time(elapsed, number, YTC) == elapsed * 1000 / number


def test_the_formula_refuses_an_unusable_number_or_time():
    for elapsed, number in [(0, 899), (-5, 899), (3600, 0), (3600, -1)]:
        with pytest.raises(InvalidInput):
            fixed_number_corrected_time(elapsed, number, YTC)


def test_ytc_and_portsmouth_use_the_same_formula_but_are_different_systems():
    assert YTC is not FixedNumberSystem.PY
    assert YTC.value == "YTC"
    assert fixed_number_corrected_time(3600, 900, YTC) == fixed_number_corrected_time(
        3600, 900, FixedNumberSystem.PY
    )
    outcome = score_fixed_number_series(build(EXAMPLES["YTC-2"]))
    assert outcome.system is YTC


def test_the_engine_has_no_idea_of_spinnakers():
    """A boat's two numbers are the site's business: the engine takes one number."""
    fields = {
        f.name
        for cls in (FixedNumberBoat, FixedNumberResult)
        for f in dataclasses.fields(cls)
    }
    assert not any("spinnaker" in name or "ytc" in name for name in fields)
