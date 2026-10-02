"""The scoring penalty (RRS 44.3(c), A10 SCP; slice 23 part B).

Expected values come from the hand-worked examples in
``tests/fixtures/scoring_penalty.yaml``.
"""

import pytest

from sailscoring import (
    Finish,
    InvalidInput,
    RaceEntry,
    RaceOutcome,
    RaceResult,
    RaceStatus,
    compute_standings,
    score_points,
)
from tests.scenario_loader import SCORING_PENALTY_FIXTURE

RACE_EXAMPLES = SCORING_PENALTY_FIXTURE["race_examples"]


def result(boat_id, status=RaceStatus.FINISHED, place=None, scp=False):
    return RaceResult(
        boat_id=boat_id,
        status=status,
        tcf_used=1.0,
        elapsed_seconds=3600.0 if place else None,
        corrected_time=3600.0 + (place or 0) if place else None,
        position=place,
        scoring_penalty=scp,
    )


def example_results(example):
    return [
        result(
            boat_id,
            status=RaceStatus(boat["outcome"]),
            place=boat.get("place"),
            scp=boat.get("scp", False),
        )
        for boat_id, boat in example["boats"].items()
    ]


@pytest.mark.parametrize("name", RACE_EXAMPLES)
def test_race_examples(name):
    example = RACE_EXAMPLES[name]
    scored = score_points(
        example_results(example),
        series_entry_count=example["entered"],
        apply_a5_3=example["a5_3"],
    )
    for row in scored:
        want = example["boats"][row.boat_id]
        assert row.points == want["points"], (name, row.boat_id)
        assert row.penalty_points == want.get("penalty"), (name, row.boat_id)
        assert row.scoring_penalty is want.get("scp", False)
        # No place changes: the penalty touches points only.
        assert row.position == want.get("place")


def test_a_penalty_changes_no_other_boats_points():
    plain = example_results(RACE_EXAMPLES["SP-1"])
    plain = [result(r.boat_id, r.status, r.position) for r in plain]
    with_penalty = score_points(
        example_results(RACE_EXAMPLES["SP-1"]), series_entry_count=6
    )
    without = score_points(plain, series_entry_count=6)
    for a, b in zip(with_penalty, without, strict=True):
        if a.boat_id != "C":
            assert a.points == b.points


@pytest.mark.parametrize("status", [RaceStatus.DNC, RaceStatus.DNS, RaceStatus.DNF])
def test_a_boat_that_did_not_finish_cannot_take_a_penalty(status):
    with pytest.raises(InvalidInput, match="scoring penalty"):
        Finish("A", status, scoring_penalty=True)
    with pytest.raises(InvalidInput, match="scoring penalty"):
        RaceEntry("A", status, 1.0, scoring_penalty=True)


def test_sp5_a_penalised_score_in_a_series_and_its_discard():
    scores = SCORING_PENALTY_FIXTURE["series_example"]["SP-5"]
    for discards, total in scores["totals"].items():
        races = [
            RaceOutcome(
                race_id=f"R{n}",
                results=(
                    RaceResult(
                        boat_id="A",
                        status=RaceStatus.FINISHED,
                        tcf_used=1.0,
                        elapsed_seconds=1.0,
                        corrected_time=1.0,
                        position=1,
                        points=float(points),
                    ),
                ),
            )
            for n, points in enumerate(scores["race_points"], start=1)
        ]
        (standing,) = compute_standings(races, discards=discards)
        assert standing.total == total


def sp6_standings():
    example = SCORING_PENALTY_FIXTURE["tie_example"]["SP-6"]
    outcomes = []
    for n, race in enumerate(example["races"], start=1):
        scored = score_points(
            [result(boat, place=p, scp=scp) for boat, (p, scp) in race.items()],
            series_entry_count=example["entered"],
        )
        outcomes.append(RaceOutcome(race_id=f"R{n}", results=scored))
    return example, compute_standings(outcomes, discards=0)


def test_sp6_totals_level_on_tenths_are_tied_and_go_to_a8():
    example, standings = sp6_standings()
    assert [s.boat_id for s in standings] == example["order"]
    for standing in standings:
        assert standing.total == example["totals"][standing.boat_id]
        assert [s.points for s in standing.scores] == example["scores"][
            standing.boat_id
        ]
    # A and B are level on 6.8 exactly, so they are separated by A8.1 (best
    # score: A's 2.4), not left as a tie and not decided by float noise. A8.2
    # (the last race) would have favoured B.
    by_id = {s.boat_id: s for s in standings}
    assert by_id["A"].total == by_id["B"].total == 6.8
    assert (by_id["A"].position, by_id["B"].position) == (2, 3)


def test_a_float_sum_of_the_tenths_would_not_have_tied():
    # Why standings count in whole tenths: 2.4 + 4.4 is not 6.8 as a float.
    assert 2.4 + 4.4 != 3.4 + 3.4
