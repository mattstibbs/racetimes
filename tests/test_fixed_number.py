"""Slice 24: fixed-number series (Portsmouth Yardstick), scored by sailscoring.fixed_number.

Organised by acceptance criterion. The worked examples PY-1 and PY-2 are in
tests/fixtures/portsmouth_yardstick.yaml, worked by hand and checked by the
project owner. The engine is never used to produce an expected value.
"""

import ast
import dataclasses
import math
from pathlib import Path

import pytest

import sailscoring
from sailscoring import (
    Finish,
    FixedNumberBoat,
    FixedNumberSeries,
    FixedNumberSystem,
    InvalidInput,
    RaceStatus,
    SeriesRace,
    fixed_number_corrected_time,
    score_fixed_number_series,
)
from tests.scenario_loader import (
    FIXED_NUMBER_RULES_FIXTURE,
    PORTSMOUTH_YARDSTICK_FIXTURE,
)

PY = FixedNumberSystem.PY
FIN = RaceStatus.FINISHED
EXAMPLES = PORTSMOUTH_YARDSTICK_FIXTURE

#: Corrected times in the fixture are written to three decimal places.
DISPLAY_TOLERANCE = 0.0005


def build(example, system=PY):
    """A FixedNumberSeries from a fixture example. Clock times never get here:
    the engine takes elapsed seconds, as it does for NHC."""
    boats = [
        FixedNumberBoat(boat_id=boat_id, number=number)
        for boat_id, number in example["boats"].items()
    ]
    races = []
    for race in example["races"]:
        finishes = []
        for boat_id, value in race["finishes"].items():
            if isinstance(value, str):
                finishes.append(Finish(boat_id=boat_id, status=RaceStatus(value)))
            else:
                finishes.append(
                    Finish(boat_id=boat_id, status=FIN, elapsed_seconds=value)
                )
        races.append(SeriesRace(race_id=race["race_id"], finishes=finishes))
    return FixedNumberSeries(
        boats,
        races,
        system,
        discards=example["discards"],
    )


# --- The worked examples ---------------------------------------------------------------


RACE_CASES = [
    (example_id, index)
    for example_id, example in EXAMPLES.items()
    for index in range(len(example["races"]))
]


@pytest.mark.parametrize(("example_id", "index"), RACE_CASES)
def test_each_race_matches_the_worked_example(example_id, index):
    example = EXAMPLES[example_id]
    outcome = score_fixed_number_series(build(example))
    expected = example["races"][index]["expected"]
    results = {r.boat_id: r for r in outcome.races[index].results}
    assert set(results) == set(example["boats"])
    for boat_id, want in expected.items():
        got = results[boat_id]
        assert got.points == want["points"], (example_id, index, boat_id)
        if "place" in want:
            assert got.position == want["place"], (example_id, index, boat_id)
            assert got.corrected_time == pytest.approx(
                want["corrected"], abs=DISPLAY_TOLERANCE
            ), (example_id, index, boat_id)
        else:
            assert got.position is None and got.corrected_time is None


@pytest.mark.parametrize("example_id", list(EXAMPLES))
def test_the_standings_match_the_worked_example(example_id):
    example = EXAMPLES[example_id]
    standings = score_fixed_number_series(build(example)).standings
    assert [(s.boat_id, s.position, s.total) for s in standings] == [
        (row["boat"], row["position"], row["total"]) for row in example["standings"]
    ]


def test_a_boat_sails_every_race_on_the_same_number():
    example = EXAMPLES["PY-1"]
    outcome = score_fixed_number_series(build(example))
    for race in outcome.races:
        for result in race.results:
            assert result.number == example["boats"][result.boat_id]


def test_equal_corrected_times_tie_and_a_hair_apart_do_not():
    """PY-2: D and E tie on exactly 4000 s. F and G are 0.386 s apart, which the
    pages would show as the same time, but places are decided on the full value."""
    results = {
        r.boat_id: r
        for r in score_fixed_number_series(build(EXAMPLES["PY-2"])).races[0].results
    }
    assert results["D"].position == results["E"].position == 1
    assert results["F"].position == 3 and results["G"].position == 4
    assert round(results["F"].corrected_time) == round(results["G"].corrected_time)


# --- The formula, as written ----------------------------------------------------------


@pytest.mark.parametrize(
    ("elapsed", "number"), [(4150, 1072), (3930, 1010), (3700, 935), (4400, 1100)]
)
def test_corrected_time_is_elapsed_times_1000_over_the_number(elapsed, number):
    # Exactly the formula as written, not the number turned into a TCF first.
    assert fixed_number_corrected_time(elapsed, number, PY) == elapsed * 1000 / number


def test_the_formula_is_kept_at_full_precision():
    got = fixed_number_corrected_time(4385, 1072, PY)
    assert got != round(got)
    assert got == pytest.approx(4090.485, abs=DISPLAY_TOLERANCE)


def test_the_formula_refuses_an_unusable_number_or_time():
    for elapsed, number in [(0, 1000), (-5, 1000), (3600, 0), (3600, -1)]:
        with pytest.raises(InvalidInput):
            fixed_number_corrected_time(elapsed, number, PY)
    with pytest.raises(InvalidInput):
        fixed_number_corrected_time(3600, 1000, "NOT A SYSTEM")


# --- Nothing moves after a race ------------------------------------------------------------

BOATS = {"A": 1010, "B": 1072, "C": 935, "D": 1150}

#: A four-race series with a retirement and an absentee in it, as in
#: tests/test_recalculation.py. Elapsed seconds, or a status for a non-finisher;
#: a boat left out of a race has no recorded finish at all and scores DNC.
RACES = (
    ("R1", {"A": 3600, "B": 3500, "C": 3800, "D": 4000}),
    ("R2", {"A": 3650, "B": 3600, "C": "DNF", "D": 3900}),
    ("R3", {"A": 3700, "B": 3550, "C": 3600}),
    ("R4", {"A": 3550, "B": 3650, "C": 3700, "D": 3850}),
)
FINISHERS = [
    (index, boat_id)
    for index, (_, finishes) in enumerate(RACES)
    for boat_id, value in finishes.items()
    if not isinstance(value, str)
]


def sweep_series(races):
    return build(
        {
            "boats": BOATS,
            "discards": 1,
            "races": [{"race_id": rid, "finishes": f} for rid, f in races],
        }
    )


def race_results(outcome):
    return [race.results for race in outcome.races]


@pytest.mark.parametrize(
    ("changed_race", "boat_id"), FINISHERS, ids=[f"R{i + 1}-{b}" for i, b in FINISHERS]
)
def test_changing_any_finish_changes_only_that_race_and_the_standings(
    changed_race, boat_id
):
    """The fixed-number counterpart of slice 0's recalculation test.

    Under NHC a corrected finish ripples into every later race through the
    handicaps. Here no number moves, so every other race scores exactly as it
    did, whatever the finish.
    """
    before = score_fixed_number_series(sweep_series(RACES))

    changed = [
        (rid, {**f, boat_id: f[boat_id] * 2} if index == changed_race else f)
        for index, (rid, f) in enumerate(RACES)
    ]
    after = score_fixed_number_series(sweep_series(changed))

    for index, (old, new) in enumerate(
        zip(race_results(before), race_results(after), strict=True)
    ):
        if index != changed_race:
            assert old == new, f"race {index + 1} changed"
    # The boat is now far slower, so its race really did change.
    assert race_results(before)[changed_race] != race_results(after)[changed_race]


def test_no_number_moves_whatever_the_finishes():
    outcome = score_fixed_number_series(sweep_series(RACES))
    for race in outcome.races:
        for result in race.results:
            assert result.number == BOATS[result.boat_id]


def test_a_boat_with_no_recorded_finish_scores_dnc():
    outcome = score_fixed_number_series(sweep_series(RACES))
    d_in_r3 = next(r for r in outcome.races[2].results if r.boat_id == "D")
    assert d_in_r3.status is RaceStatus.DNC
    assert d_in_r3.position is None and d_in_r3.points == 5  # 4 entries + 1


def test_scoring_does_not_change_the_series_it_is_given():
    series = sweep_series(RACES)
    score_fixed_number_series(series)
    assert series == sweep_series(RACES)


# --- Appendix A is shared, so slice 23's rules work here too ------------------------------


RULES = FIXED_NUMBER_RULES_FIXTURE


def build_rules(example, races=None, discard_threshold=None):
    """A FixedNumberSeries from tests/fixtures/fixed_number_rules.yaml."""
    race_list = []
    for race in example["races"][:races]:
        penalised = set(race.get("scp", ()))
        race_list.append(
            SeriesRace(
                race["race_id"],
                [
                    Finish(boat, FIN, elapsed, scoring_penalty=boat in penalised)
                    for boat, elapsed in race["finishes"].items()
                ],
            )
        )
    return FixedNumberSeries(
        [FixedNumberBoat(boat, number) for boat, number in example["boats"].items()],
        race_list,
        PY,
        discards=example["discards"],
        discard_threshold=(
            example.get("discard_threshold", 0)
            if discard_threshold is None
            else discard_threshold
        ),
    )


def totals(outcome):
    return {row.boat_id: row.total for row in outcome.standings}


def discarded(outcome):
    return sum(score.discarded for row in outcome.standings for score in row.scores)


def test_the_discard_threshold_applies():
    """DT-FN-1: no discard until three races are scored."""
    example = RULES["DT-FN-1"]
    two = score_fixed_number_series(build_rules(example, races=2))
    assert totals(two) == example["totals_after_2"]
    assert discarded(two) == example["discarded_after_2"]

    three = score_fixed_number_series(build_rules(example))
    assert totals(three) == example["totals_after_3"]
    assert discarded(three) == example["discarded_after_3"]

    without = score_fixed_number_series(
        build_rules(example, races=2, discard_threshold=0)
    )
    assert totals(without) == example["totals_after_2_without_threshold"]


@pytest.mark.parametrize("example_id", ["SP-FN-1", "SP-FN-2"])
def test_a_scoring_penalty_worsens_points_and_nothing_else(example_id):
    """The penalty is 20% of the DNF score, capped at the DNF score, and it moves
    neither the place nor the corrected time."""
    example = RULES[example_id]
    outcome = score_fixed_number_series(build_rules(example))
    plain = score_fixed_number_series(
        build_rules(
            {
                **example,
                "races": [{**race, "scp": []} for race in example["races"]],
            }
        )
    )
    for race, race_example, plain_race in zip(
        outcome.races, example["races"], plain.races, strict=True
    ):
        got = {r.boat_id: r for r in race.results}
        without = {r.boat_id: r for r in plain_race.results}
        for boat, want in race_example["expected"].items():
            assert got[boat].points == pytest.approx(want), (race.race_id, boat)
            assert got[boat].scoring_penalty == (boat in race_example.get("scp", ()))
            assert got[boat].position == without[boat].position
            assert got[boat].corrected_time == without[boat].corrected_time


# --- Validation ----------------------------------------------------------------------------


@pytest.mark.parametrize("number", [0, -1, -1000, math.nan, math.inf, -math.inf])
def test_a_boats_number_must_be_positive_and_finite(number):
    with pytest.raises(InvalidInput):
        FixedNumberBoat(boat_id="A", number=number)


def test_a_boats_number_is_required():
    with pytest.raises(InvalidInput):
        FixedNumberBoat(boat_id="A", number=None)


def test_a_boat_needs_an_id():
    with pytest.raises(InvalidInput):
        FixedNumberBoat(boat_id="", number=1000)


def test_the_engine_doesnt_insist_a_number_is_whole():
    # The formula works for any positive number; the site's form insists on a
    # whole one.
    assert FixedNumberBoat("A", 1000.5).number == 1000.5


def test_the_system_must_be_a_known_one():
    with pytest.raises(InvalidInput):
        FixedNumberSeries([FixedNumberBoat("A", 1000)], [], "PY")


# --- The checks every series shares give the same messages --------------------------------

#: (Two finishes for one boat is refused by SeriesRace itself, before any series
#: exists, and is covered in tests/test_series.py.)
SHARED_CASES = {
    "no boats": {"boats": [], "races": []},
    "negative discards": {"boats": ["A"], "races": [], "discards": -1},
    "negative threshold": {"boats": ["A"], "races": [], "discard_threshold": -1},
    "threshold within discards": {
        "boats": ["A"],
        "races": [],
        "discards": 2,
        "discard_threshold": 2,
    },
    "duplicate boat": {"boats": ["A", "A"], "races": []},
    "duplicate race": {"boats": ["A"], "races": [("R1", []), ("R1", [])]},
    "finish for a boat not entered": {
        "boats": ["A"],
        "races": [("R1", [Finish("Z", FIN, 3600)])],
    },
}


def both_kinds(case):
    options = {k: v for k, v in case.items() if k not in ("boats", "races")}
    races = [SeriesRace(race_id, finishes) for race_id, finishes in case["races"]]

    def nhc_series():
        return sailscoring.Series(
            [sailscoring.Boat(b, 1.0, 1.0) for b in case["boats"]], races, **options
        )

    def fixed_series():
        return FixedNumberSeries(
            [FixedNumberBoat(b, 1000) for b in case["boats"]], races, PY, **options
        )

    return nhc_series, fixed_series


@pytest.mark.parametrize("name", list(SHARED_CASES))
def test_an_nhc_series_and_a_fixed_number_series_refuse_the_same_input_alike(name):
    nhc_series, fixed_series = both_kinds(SHARED_CASES[name])
    with pytest.raises(InvalidInput) as nhc_error:
        nhc_series()
    with pytest.raises(InvalidInput) as fixed_error:
        fixed_series()
    assert str(nhc_error.value) == str(fixed_error.value)


def test_an_nhc_series_still_reports_its_own_checks_in_the_same_order():
    """Moving the shared checks into domain.py must not change which error comes
    first when two things are wrong at once. Checked against the code as it was
    before slice 24, over every pair of faults, when this was refactored."""

    def first_error(**options):
        boats = options.pop("boats", [sailscoring.Boat("A", 1.0, 1.0)])
        with pytest.raises(InvalidInput) as error:
            sailscoring.Series(boats, options.pop("races", []), **options)
        return str(error.value)

    # No boats comes before the series' own option checks...
    assert first_error(boats=[], progression="SIDEWAYS") == (
        "a series needs at least one boat"
    )
    # ...which come before the discard checks...
    assert first_error(progression="SIDEWAYS", discards=-1).startswith(
        "progression must be one of"
    )
    assert first_error(series_type="ODD", discards=-1).startswith(
        "series_type must be one of"
    )
    # ...which come before minimum finishers and the regatta-only options...
    assert first_error(discards=-1, minimum_finishers=-1).startswith(
        "discards cannot be negative"
    )
    # ...which come before the checks for a boat or race entered twice.
    assert first_error(
        minimum_finishers=-1, boats=[sailscoring.Boat("A", 1.0, 1.0)] * 2
    ).startswith("minimum_finishers cannot be negative")
    assert first_error(
        series_type=sailscoring.SeriesType.REGATTA,
        cap_extremes=True,
        races=[SeriesRace("R1"), SeriesRace("R1")],
    ).startswith("cap_extremes and realign_to_base are club-series options")


# --- The two kinds of series stay apart ----------------------------------------------------

#: The NHC types as they were before slice 24. A fixed-number series is not an
#: NHC series with a field left empty, so these must not gain or lose a field.
NHC_FIELDS = {
    "Boat": ("boat_id", "base_number", "current_tcf", "name"),
    "Series": (
        "boats",
        "races",
        "series_type",
        "progression",
        "minimum_finishers",
        "apply_a5_3",
        "discards",
        "discard_threshold",
        "cap_extremes",
        "realign_to_base",
    ),
    "RaceEntry": (
        "boat_id",
        "status",
        "tcf_used",
        "elapsed_seconds",
        "base_number",
        "scoring_penalty",
    ),
    "RaceResult": (
        "boat_id",
        "status",
        "tcf_used",
        "elapsed_seconds",
        "corrected_time",
        "position",
        "adjustment_scale",
        "achieved_handicap",
        "performance",
        "next_tcf",
        "next_tcf_clamped",
        "points",
        "elapsed_seconds_used",
        "realignment_factor",
        "scoring_penalty",
        "penalty_points",
    ),
}


@pytest.mark.parametrize("name", list(NHC_FIELDS))
def test_the_nhc_types_have_the_same_fields_as_before(name):
    fields = tuple(f.name for f in dataclasses.fields(getattr(sailscoring, name)))
    assert fields == NHC_FIELDS[name]


def test_a_fixed_number_result_has_no_handicap_fields():
    fields = {f.name for f in dataclasses.fields(sailscoring.FixedNumberResult)}
    assert not fields & {
        "tcf_used",
        "next_tcf",
        "achieved_handicap",
        "adjustment_scale",
        "performance",
        "realignment_factor",
    }
    # What the shared Appendix A code reads and writes.
    assert fields >= {
        "boat_id",
        "status",
        "number",
        "elapsed_seconds",
        "corrected_time",
        "position",
        "points",
        "scoring_penalty",
        "penalty_points",
    }


PACKAGE = Path(sailscoring.__file__).resolve().parent
NHC_MODULES = ("handicap", "regatta", "options", "realignment", "series")


def relative_imports(module):
    """Names of the package's own modules that this one imports from."""
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                names.add(node.module.split(".")[0])
            else:  # "from . import x"
                names.update(alias.name for alias in node.names)
    return names


def test_the_fixed_number_module_imports_nothing_from_the_nhc_modules():
    assert not relative_imports("fixed_number") & set(NHC_MODULES)


@pytest.mark.parametrize("module", NHC_MODULES)
def test_the_nhc_modules_import_nothing_from_the_fixed_number_module(module):
    assert "fixed_number" not in relative_imports(module)


def test_the_shared_modules_import_neither_kind_of_series():
    shared = ("scoring", "points", "standings", "domain", "errors")
    for module in shared:
        assert not relative_imports(module) & (set(NHC_MODULES) | {"fixed_number"}), (
            module
        )
