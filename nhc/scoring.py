"""Corrected times and finishing places (RYA spec section 2, RRS A3 and A7).

This is the scoring half of a race: elapsed time times handicap gives a
corrected time, and the fleet is ranked on that. It computes no handicap
adjustment - that is ``compute_club_adjustment`` - so the results it returns
leave the handicap fields as None.
"""

from __future__ import annotations

import math

from .domain import RaceInput, RaceResult

#: Corrected times this close are treated as equal.
#:
#: This absorbs binary floating-point representation error and nothing more. It
#: is not a "near enough to call it a tie" rule: a nanosecond is many orders of
#: magnitude below any real timing system's resolution, and two boats whose
#: corrected times differ by even a hundredth of a second are not tied. Without
#: it, a genuine dead heat could miss by one unit in the last place purely
#: because a handicap like 0.8 has no exact binary representation.
TIE_TOLERANCE_SECONDS = 1e-9


def corrected_time(elapsed_seconds: float, tcf: float) -> float:
    """C = E x TCF (spec section 2).

    Kept at full precision. Rounding to whole seconds is for display only; see
    the note in ``nhc/domain.py``.
    """
    return elapsed_seconds * tcf


def score_race(race: RaceInput) -> tuple[RaceResult, ...]:
    """Corrected times and finishing places for one race.

    Takes a ``RaceInput`` rather than the bare entry list of the spec's
    suggested signature, so the race's own invariants - no duplicate boats, a
    non-empty fleet - are already guaranteed.

    Results come back in the order the entries were given, not in finishing
    order. That keeps the output lined up with the input for a caller zipping
    the two together; sort on ``position`` for a results table.

    Boats without a corrected time (DNC, DNS, DNF) get ``position = None``.
    Their points are an RRS Appendix A matter, decided by a later layer that
    knows how many boats entered the series.
    """
    scored = sorted(
        (
            (corrected_time(entry.elapsed_seconds, entry.tcf_used), entry.boat_id)
            for entry in race.finishers
        ),
        key=lambda pair: pair[0],
    )

    positions = _assign_positions(scored)
    corrected = dict(
        (boat_id, value) for value, boat_id in scored
    )

    return tuple(
        RaceResult(
            boat_id=entry.boat_id,
            status=entry.status,
            tcf_used=entry.tcf_used,
            elapsed_seconds=entry.elapsed_seconds,
            corrected_time=corrected.get(entry.boat_id),
            position=positions.get(entry.boat_id),
        )
        for entry in race.entries
    )


def _assign_positions(scored: list[tuple[float, str]]) -> dict[str, int]:
    """Finishing places from corrected times already sorted ascending.

    Boats with equal corrected times share the better place, so a two-way tie
    for first is scored 1, 1, 3 - the place below is consumed, not reused. That
    is the ranking half of RRS A7; the other half, splitting the points for the
    tied places equally, needs a points system and belongs to the Appendix A
    layer.
    """
    positions: dict[str, int] = {}
    index = 0
    while index < len(scored):
        # Compare every candidate against the first of the group rather than
        # against its neighbour, so a long run of near-equal times cannot drift
        # a tolerance-width at a time into a tie that isn't one.
        first_time = scored[index][0]
        last = index
        while last + 1 < len(scored) and math.isclose(
            scored[last + 1][0], first_time, rel_tol=0.0, abs_tol=TIE_TOLERANCE_SECONDS
        ):
            last += 1

        place = index + 1
        for _, boat_id in scored[index : last + 1]:
            positions[boat_id] = place
        index = last + 1

    return positions
