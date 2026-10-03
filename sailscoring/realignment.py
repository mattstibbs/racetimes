"""End-of-series realignment (RYA spec section 5).

Over a season, progressive handicaps drift away from the published Base
Numbers: a fleet of improving sailors all get rated down, a fleet of rusty ones
all get rated up, and after a few series the numbers no longer mean what the
RYA intended. Realignment runs once after the final race and pulls the whole
fleet back:

    CN = (sum(BN) / sum(EH)) x EH

CN is the realigned club number, the TCF a boat starts the next series on. BN
is its published Base Number, EH its ending handicap - the TCFn left by the
final race. Both sums run over the fleet being realigned.

The shape of it: every boat is scaled by the same factor, so the fleet keeps
its internal spread exactly - a boat rated 10% faster than another before
realignment is still rated 10% faster after. What changes is the overall level,
which is pulled back so the realigned numbers total the base numbers again.
``test_realigned_handicaps_total_the_base_numbers`` pins that.

This is not the regatta clamp in section 4, which is a per-race limit on how
far one boat may move from its own base number. Realignment is fleet-wide and
happens between series.
"""

from __future__ import annotations

from collections.abc import Sequence

from .domain import Boat, RaceStatus, RealignmentEntry, RealignmentResult
from .errors import InvalidInput


def realign_series(
    entries: Sequence[RealignmentEntry],
) -> tuple[RealignmentResult, ...]:
    """Realign a fleet's handicaps after the final race of a club series.

    Returns results in the order given.
    """
    entry_list = list(entries)
    if not entry_list:
        raise InvalidInput("realignment needs at least one boat")

    boat_ids = [entry.boat_id for entry in entry_list]
    duplicates = {i for i in boat_ids if boat_ids.count(i) > 1}
    if duplicates:
        raise InvalidInput(
            f"boat appears twice in the realignment: {', '.join(sorted(duplicates))}"
        )

    # Both entries validate their numbers as finite and positive on
    # construction, so neither sum can be zero and the division is safe.
    total_base = sum(entry.base_number for entry in entry_list)
    total_ending = sum(entry.ending_handicap for entry in entry_list)
    ratio = total_base / total_ending

    return tuple(
        RealignmentResult(
            boat_id=entry.boat_id,
            realigned_tcf=ratio * entry.ending_handicap,
        )
        for entry in entry_list
    )


def realignment_entries(series, outcome) -> tuple[RealignmentEntry, ...]:
    """Build realignment input from a series and its scored outcome.

    Pairs each boat's published Base Number with the handicap the series left
    it on. A series with no races yet leaves every boat where it started, so
    realigning one is a no-op rather than an error.

    Only boats that took part are included: those that started at least one
    race (finished, or started and did not finish). Section 5 says "every boat
    that took part in that series", so a boat that entered but never sailed
    would only shift the ratio for everyone else (decided 2026-10-03). Such a
    boat is left out of the sums and ``realigned_boats`` leaves her handicap
    alone. If nobody has started a race, every boat is included, so realigning
    an unsailed series is still a no-op.
    """
    ending = outcome.ending_handicaps
    started = {
        result.boat_id
        for race in outcome.races
        for result in race.results
        if result.status in (RaceStatus.FINISHED, RaceStatus.DNF)
    }
    return tuple(
        RealignmentEntry(
            boat_id=boat.boat_id,
            base_number=boat.base_number,
            ending_handicap=ending[boat.boat_id],
        )
        for boat in series.boats
        if boat.boat_id in started or not started
    )


def realigned_boats(series, results: Sequence[RealignmentResult]) -> tuple[Boat, ...]:
    """The same boats, ready to start the next series on their realigned numbers.

    Base numbers are unchanged - they are published ratings, not something a
    season of racing alters. Only ``current_tcf`` moves. Feeding these into the
    next series with ``HandicapProgression.CARRY_OVER`` is how a club carries
    realigned handicaps forward. A boat with no result (one that never started,
    see ``realignment_entries``) keeps her current handicap.
    """
    realigned = {result.boat_id: result.realigned_tcf for result in results}
    return tuple(
        Boat(
            boat_id=boat.boat_id,
            base_number=boat.base_number,
            current_tcf=realigned.get(boat.boat_id, boat.current_tcf),
            name=boat.name,
        )
        for boat in series.boats
    )
