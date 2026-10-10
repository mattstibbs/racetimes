"""The scoring codes DSQ, RET, OCS and NSC, and RRS A6.1.

The worked examples CODE-1 to CODE-6 are in tests/fixtures/codes_and_a6_1.yaml,
worked by hand and checked by the project owner. The engine is never used to
produce an expected value. The rest of this module checks the rules the spec
states in words: a coded boat's time, the refusals, A6.1 as a sweep, and that a
coded boat is handicapped, regatta-adjusted, realigned and capped as a DNF is.
"""

import math

import pytest

from sailscoring import (
    Boat,
    Finish,
    FixedNumberBoat,
    FixedNumberSeries,
    FixedNumberSystem,
    InvalidInput,
    RaceEntry,
    RaceInput,
    RaceStatus,
    Series,
    SeriesRace,
    SeriesType,
    compute_club_adjustment,
    compute_regatta_adjustment,
    realignment_entries,
    score_fixed_number_series,
    score_series,
)
from tests.scenario_loader import CODES_FIXTURE

PY = FixedNumberSystem.PY
FIN = RaceStatus.FINISHED
DNC = RaceStatus.DNC
DNS = RaceStatus.DNS
DNF = RaceStatus.DNF
DSQ = RaceStatus.DSQ
RET = RaceStatus.RET
OCS = RaceStatus.OCS
NSC = RaceStatus.NSC

CODES = (DSQ, RET, OCS, NSC)
NON_FINISHERS_WITHOUT_TIMES = (DNC, DNS, DNF)

#: Corrected times and points in the fixtures are exact for these examples.
TOLERANCE = 1e-9

EXAMPLES = CODES_FIXTURE


def _finish(boat_id, value):
    """A Finish from a fixture value: a time, a code, or a mapping for a coded boat."""
    if isinstance(value, dict):
        return Finish(
            boat_id=boat_id,
            status=RaceStatus(value["status"]),
            elapsed_seconds=value.get("elapsed"),
            scoring_penalty=value.get("penalty", False),
        )
    if isinstance(value, str):
        return Finish(boat_id=boat_id, status=RaceStatus(value))
    return Finish(boat_id=boat_id, status=FIN, elapsed_seconds=value)


def build(example):
    """A fixed-number series (Portsmouth Yardstick, every boat on 1000) from an example."""
    boats = [
        FixedNumberBoat(boat_id=boat_id, number=number)
        for boat_id, number in example["boats"].items()
    ]
    assert len(boats) == example["entries"]
    races = [
        SeriesRace(
            race_id=race["race_id"],
            finishes=[
                _finish(boat_id, value) for boat_id, value in race["finishes"].items()
            ],
        )
        for race in example["races"]
    ]
    return FixedNumberSeries(
        boats,
        races,
        PY,
        apply_a5_3=example["apply_a5_3"],
        discards=example["discards"],
    )


def _without_coded_times(example):
    """The same example with every DSQ, RET, OCS or NSC boat's time taken away."""
    races = []
    for race in example["races"]:
        finishes = {}
        for boat_id, value in race["finishes"].items():
            if isinstance(value, dict) and value["status"] in {s.value for s in CODES}:
                finishes[boat_id] = {"status": value["status"]}
            else:
                finishes[boat_id] = value
        races.append({**race, "finishes": finishes})
    return {**example, "races": races}


# --- The worked examples ---------------------------------------------------------------


RACE_CASES = [
    (example_id, index)
    for example_id, example in EXAMPLES.items()
    for index in range(len(example["races"]))
]


@pytest.mark.parametrize(("example_id", "index"), RACE_CASES)
def test_each_race_matches_the_worked_example(example_id, index):
    example = EXAMPLES[example_id]
    race = score_fixed_number_series(build(example)).races[index]
    by_id = {result.boat_id: result for result in race.results}

    for boat_id, expected in example["races"][index]["expected"].items():
        result = by_id[boat_id]
        if "place" in expected:
            assert result.position == expected["place"], boat_id
            assert result.corrected_time is not None, boat_id
        else:
            assert result.position is None, boat_id
            assert result.corrected_time is None, boat_id
        assert result.points == pytest.approx(expected["points"], abs=TOLERANCE), (
            boat_id
        )
        if "kept" in expected:
            assert result.elapsed_seconds == expected["kept"], boat_id


def test_code_6_series_totals_with_and_without_a_discard():
    example = EXAMPLES["CODE-6"]
    expected = example["standings"][0]
    for discards, key in ((0, "total_no_discards"), (1, "total_one_discard")):
        series = build({**example, "discards": discards})
        standings = {
            standing.boat_id: standing
            for standing in score_fixed_number_series(series).standings
        }
        assert standings[expected["boat"]].total == expected[key], discards


# --- A coded boat's time changes nothing about her score --------------------------------


@pytest.mark.parametrize("example_id", list(EXAMPLES))
def test_a_coded_boat_scores_the_same_with_or_without_her_time(example_id):
    example = EXAMPLES[example_id]
    with_times = score_fixed_number_series(build(example))
    without_times = score_fixed_number_series(build(_without_coded_times(example)))

    for race, bare in zip(with_times.races, without_times.races, strict=True):
        for result, bare_result in zip(race.results, bare.results, strict=True):
            assert result.position == bare_result.position
            assert result.points == bare_result.points
            assert result.corrected_time == bare_result.corrected_time


def test_a_coded_boat_keeps_her_recorded_time_but_has_no_corrected_time():
    race = score_fixed_number_series(build(EXAMPLES["CODE-5"])).races[0]
    by_id = {result.boat_id: result for result in race.results}
    assert by_id["B"].elapsed_seconds == 3060
    assert by_id["B"].corrected_time is None
    assert by_id["B"].position is None


# --- What the form, the model and the engine refuse -------------------------------------


@pytest.mark.parametrize("status", NON_FINISHERS_WITHOUT_TIMES)
def test_dnc_dns_and_dnf_with_a_time_are_still_refused_on_a_finish(status):
    with pytest.raises(InvalidInput, match="elapsed time"):
        Finish(boat_id="A", status=status, elapsed_seconds=3000)


@pytest.mark.parametrize("status", NON_FINISHERS_WITHOUT_TIMES)
def test_dnc_dns_and_dnf_with_a_time_are_still_refused_on_an_entry(status):
    with pytest.raises(InvalidInput, match="elapsed time"):
        RaceEntry(boat_id="A", status=status, tcf_used=1.0, elapsed_seconds=3000)


@pytest.mark.parametrize("status", CODES)
@pytest.mark.parametrize("bad", [-5, -0.5, math.nan, math.inf, -math.inf])
def test_a_coded_boat_with_an_unusable_time_is_refused(status, bad):
    with pytest.raises(InvalidInput):
        Finish(boat_id="A", status=status, elapsed_seconds=bad)
    with pytest.raises(InvalidInput):
        RaceEntry(boat_id="A", status=status, tcf_used=1.0, elapsed_seconds=bad)


@pytest.mark.parametrize("status", CODES)
def test_zero_means_no_time_for_a_coded_boat(status):
    assert Finish(boat_id="A", status=status, elapsed_seconds=0).elapsed_seconds is None
    entry = RaceEntry(boat_id="A", status=status, tcf_used=1.0, elapsed_seconds=0)
    assert entry.elapsed_seconds is None


@pytest.mark.parametrize("status", CODES)
def test_a_scoring_penalty_is_refused_on_a_coded_boat(status):
    with pytest.raises(InvalidInput, match="scoring penalty"):
        Finish(boat_id="A", status=status, elapsed_seconds=3000, scoring_penalty=True)
    with pytest.raises(InvalidInput, match="scoring penalty"):
        RaceEntry(
            boat_id="A",
            status=status,
            tcf_used=1.0,
            elapsed_seconds=3000,
            scoring_penalty=True,
        )


# --- A6.1 as a sweep: any finisher changed to any code ---------------------------------

#: Five finishers with distinct times, and one boat at home. No ties, so A6.1's
#: effect is exactly "one place up" for each boat behind.
SWEEP_TIMES = {"A": 3000, "B": 3060, "C": 3120, "D": 3180, "E": 3240}


def _sweep_series(changed, status, keep_time):
    finishes = []
    for boat_id, seconds in SWEEP_TIMES.items():
        if boat_id == changed:
            if keep_time:
                finishes.append(Finish(boat_id, status, elapsed_seconds=seconds))
            else:
                finishes.append(Finish(boat_id, status))
        else:
            finishes.append(Finish(boat_id, FIN, elapsed_seconds=seconds))
    boats = [FixedNumberBoat(boat_id, 1000) for boat_id in [*SWEEP_TIMES, "F"]]
    return FixedNumberSeries(boats, [SeriesRace("R1", finishes)], PY, discards=0)


def _places(series):
    result = score_fixed_number_series(series).races[0].results
    return {r.boat_id: (r.position, r.points) for r in result}


@pytest.mark.parametrize("status", CODES)
@pytest.mark.parametrize("keep_time", [True, False])
@pytest.mark.parametrize("changed", list(SWEEP_TIMES))
def test_a_code_moves_each_boat_behind_up_one_and_no_boat_ahead(
    changed, status, keep_time
):
    before = _places(_sweep_series(changed, FIN, True))
    after = _places(_sweep_series(changed, status, keep_time))
    old_place_of_changed = before[changed][0]

    # Six boats are entered, so a boat that scores as a DNF scores 7.
    assert after[changed] == (None, 7)
    for boat_id, (old_place, _) in before.items():
        if boat_id == changed:
            continue
        new_place, new_points = after[boat_id]
        if old_place is None:
            # F stays at home (DNC) and scores the same throughout.
            assert (new_place, new_points) == (None, 7), boat_id
            continue
        if old_place > old_place_of_changed:
            assert new_place == old_place - 1, boat_id
        else:
            assert new_place == old_place, boat_id
        # Untied, so a boat's points are its place (A4).
        assert new_points == new_place, boat_id


def test_a_coded_boat_scores_as_a_dnf_does_in_a_six_boat_series():
    # The changed boat takes 7 points under A5.2 whatever the code.
    after = _places(_sweep_series("C", RET, True))
    assert after["C"] == (None, 7)


# --- Handicaps: a coded boat is treated exactly as a DNF is -----------------------------

CLUB_BOATS = (
    Boat("A", 0.95, 0.95),
    Boat("B", 1.00, 1.00),
    Boat("C", 1.08, 1.08),
    Boat("D", 0.88, 0.88),
)

#: A four-race club series: a value is elapsed seconds, or the status of a boat
#: that sailed and did not finish. Boats left out have no finish (DNC).
CLUB_RACES = (
    ("R1", {"A": 3600, "B": 3500, "C": 3800, "D": 4000}),
    ("R2", {"A": 3650, "B": 3600, "C": 3700, "D": 3900}),
    ("R3", {"A": 3700, "B": 3550, "C": 3600}),
    ("R4", {"A": 3550, "B": 3650, "C": 3700, "D": 3850}),
)


def _club_series(races):
    return Series(
        CLUB_BOATS,
        [SeriesRace(race_id, _club_finishes(finishes)) for race_id, finishes in races],
    )


def _club_finishes(finishes):
    result = []
    for boat_id, value in finishes.items():
        if isinstance(value, tuple):
            status, seconds = value
            result.append(Finish(boat_id, status, elapsed_seconds=seconds))
        elif isinstance(value, RaceStatus):
            result.append(Finish(boat_id, value))
        else:
            result.append(Finish(boat_id, FIN, elapsed_seconds=value))
    return result


def _handicap_view(outcome):
    """Everything a boat's next race depends on, race by race, for every boat."""
    return [
        sorted(
            (
                r.boat_id,
                r.position,
                r.corrected_time,
                r.points,
                r.adjustment_scale,
                r.achieved_handicap,
                r.performance,
                r.next_tcf,
            )
            for r in race.results
        )
        for race in outcome.races
    ]


#: Every finisher in the series, as (race index, boat), and the variants to try.
CLUB_FINISHER_CASES = [
    (index, boat_id)
    for index, (_, finishes) in enumerate(CLUB_RACES)
    for boat_id, value in finishes.items()
    if not isinstance(value, RaceStatus)
]


@pytest.mark.parametrize(("index", "boat_id"), CLUB_FINISHER_CASES)
@pytest.mark.parametrize("status", CODES)
@pytest.mark.parametrize("keep_time", [True, False])
def test_a_club_series_is_handicapped_as_if_the_code_were_a_dnf(
    index, boat_id, status, keep_time
):
    def replaced(new_value):
        races = [(race_id, dict(finishes)) for race_id, finishes in CLUB_RACES]
        races[index][1][boat_id] = new_value
        return _club_series(races)

    as_dnf = score_series(replaced(DNF))
    seconds = CLUB_RACES[index][1][boat_id] if keep_time else None
    coded = replaced((status, seconds) if keep_time else status)
    as_code = score_series(coded)

    assert _handicap_view(as_code) == _handicap_view(as_dnf)
    assert as_code.starting_handicaps == as_dnf.starting_handicaps


@pytest.mark.parametrize("status", CODES)
@pytest.mark.parametrize("keep_time", [True, False])
def test_a_regatta_back_calculates_a_code_as_a_dnf(status, keep_time):
    def race(boat_status, seconds):
        entries = [
            RaceEntry("A", FIN, tcf_used=1.00, elapsed_seconds=3000, base_number=1.00),
            RaceEntry("B", FIN, tcf_used=0.98, elapsed_seconds=3100, base_number=0.98),
            RaceEntry("C", FIN, tcf_used=1.02, elapsed_seconds=3150, base_number=1.02),
            RaceEntry(
                "D",
                boat_status,
                tcf_used=0.95,
                elapsed_seconds=seconds,
                base_number=0.95,
            ),
            RaceEntry("E", DNC, tcf_used=1.05, base_number=1.05),
        ]
        return compute_regatta_adjustment(
            RaceInput(SeriesType.REGATTA, entries, is_first_race_of_regatta=False)
        )

    as_dnf = race(DNF, None)
    seconds = 3300 if keep_time else None
    as_code = race(status, seconds)

    for dnf_result, code_result in zip(as_dnf, as_code, strict=True):
        assert code_result.boat_id == dnf_result.boat_id
        assert code_result.elapsed_seconds_used == pytest.approx(
            dnf_result.elapsed_seconds_used, abs=TOLERANCE
        )
        assert code_result.achieved_handicap == pytest.approx(
            dnf_result.achieved_handicap, abs=TOLERANCE
        )
        assert code_result.effective_next_tcf == pytest.approx(
            dnf_result.effective_next_tcf, abs=TOLERANCE
        )
        assert code_result.position == dnf_result.position


@pytest.mark.parametrize("status", CODES)
def test_a_coded_boat_takes_part_in_realignment(status):
    series = Series(
        CLUB_BOATS[:3],
        [
            SeriesRace(
                "R1",
                [
                    Finish("A", FIN, elapsed_seconds=3600),
                    Finish("B", FIN, elapsed_seconds=3500),
                    Finish("C", status, elapsed_seconds=3800),
                ],
            ),
            SeriesRace("R2", [Finish("A", FIN, elapsed_seconds=3650)]),
        ],
    )
    outcome = score_series(series)
    boats_in = {entry.boat_id for entry in realignment_entries(series, outcome)}
    assert boats_in == {"A", "B", "C"}


def test_a_boat_that_only_ever_did_not_come_is_left_out_of_realignment():
    series = Series(
        CLUB_BOATS[:3],
        [SeriesRace("R1", [Finish("A", FIN, elapsed_seconds=3600)])],
    )
    outcome = score_series(series)
    boats_in = {entry.boat_id for entry in realignment_entries(series, outcome)}
    assert boats_in == {"A"}


# --- capped: finishers only --------------------------------------------------------------


def test_a_coded_boat_with_a_time_is_never_capped_in_a_club_series():
    entries = [
        RaceEntry("A", FIN, tcf_used=1.0, elapsed_seconds=3000),
        RaceEntry("B", FIN, tcf_used=1.0, elapsed_seconds=3100),
        RaceEntry("C", DSQ, tcf_used=1.0, elapsed_seconds=3200),
    ]
    results = compute_club_adjustment(
        RaceInput(SeriesType.CLUB, entries), cap_extremes=True
    )
    by_id = {r.boat_id: r for r in results}
    assert by_id["C"].capped is False


def test_a_coded_boat_with_a_time_is_not_capped_in_a_regatta():
    entries = [
        RaceEntry("A", FIN, tcf_used=1.0, elapsed_seconds=3000, base_number=1.0),
        RaceEntry("B", FIN, tcf_used=1.0, elapsed_seconds=3100, base_number=1.0),
        RaceEntry("C", RET, tcf_used=1.0, elapsed_seconds=3200, base_number=1.0),
    ]
    results = compute_regatta_adjustment(RaceInput(SeriesType.REGATTA, entries))
    by_id = {r.boat_id: r for r in results}
    # Back-calculated, so it differs from the time she recorded, and still not capped.
    assert by_id["C"].elapsed_seconds_used != by_id["C"].elapsed_seconds
    assert by_id["C"].capped is False


def test_a_finisher_is_still_capped_when_her_time_is_capped():
    # Guards the is_finisher condition on RaceResult.capped: a finisher whose
    # time the cap changes must still say so. Five finishers, one far out.
    entries = [
        RaceEntry("A", FIN, tcf_used=1.0, elapsed_seconds=3000),
        RaceEntry("B", FIN, tcf_used=1.0, elapsed_seconds=3010),
        RaceEntry("C", FIN, tcf_used=1.0, elapsed_seconds=3020),
        RaceEntry("D", FIN, tcf_used=1.0, elapsed_seconds=3030),
        RaceEntry("E", FIN, tcf_used=1.0, elapsed_seconds=9000),
    ]
    results = compute_club_adjustment(
        RaceInput(SeriesType.CLUB, entries), cap_extremes=True
    )
    by_id = {r.boat_id: r for r in results}
    assert by_id["E"].capped is True
