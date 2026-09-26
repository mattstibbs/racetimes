"""Optional extra steps in the club-series handicap adjustment (slice 14).

The RYA's club-series calculation (``nhc/handicap.py``, spec section 3) is the
default, and stays exactly as written there. Some clubs publish results with a
fuller method, which HalSail documents and Medway Cruising Club uses, adding
two steps. Each is off unless a series asks for it, and each lives here on its
own, so the core calculation reads like the RYA spec and these read like
additions to it:

**Step A: capping extreme results.** Before a finisher's achieved handicap is
worked out, a corrected time more than one standard deviation from the fleet's
mean is pulled back to the edge of that band, so one freak result can't swing a
handicap too far::

    CT      = E x TCF                     for each finisher (corrected time)
    lower   = mean(CT) - stdev(CT)        the SAMPLE standard deviation
    upper   = mean(CT) + stdev(CT)
    E used  = lower / TCF   if CT < lower
              upper / TCF   if CT > upper
              E             otherwise

The capped time is used for that boat's achieved handicap only. The fleet
ratio, sum(TCF) / sum(AS), still comes from the real elapsed times, and the
corrected times, places and points don't change.

**Step B: realignment to base numbers.** After every finisher's next handicap
is worked out, they are all scaled by one common factor so that their total
equals the total of the same boats' base numbers::

    factor  = sum(base number) / sum(TCFn)    over this race's finishers only
    TCFn    = TCFn x factor                   for each finisher

Non-finishers are left out of both steps: they carry their handicap forward
unchanged, as in the core calculation, and count towards no sum.

Neither step rounds. Handicaps stay at full precision between races (see the
precision note in ``nhc/domain.py``); 3 d.p. is for display only.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import replace

from .domain import RaceEntry, RaceResult

#: Step A needs a spread to measure: with fewer finishers than this, the
#: standard deviation says little (and with one it can't be computed), so no
#: time is capped.
MINIMUM_FINISHERS_TO_CAP = 3


def capped_elapsed_times(finishers: Sequence[RaceEntry]) -> dict[str, float]:
    """Step A: the elapsed time each finisher's achieved handicap is worked from.

    Returns every finisher's boat id mapped to its elapsed time, with the
    extreme results replaced by the band-edge time. A boat within the band, and
    every boat when there are too few finishers, keeps its real time.
    """
    used = {entry.boat_id: entry.elapsed_seconds for entry in finishers}
    if len(finishers) < MINIMUM_FINISHERS_TO_CAP:
        return used

    corrected = [entry.elapsed_seconds * entry.tcf_used for entry in finishers]
    mean = statistics.mean(corrected)
    # The sample standard deviation, as the method specifies. The population
    # one (pstdev) gives a narrower band and different handicaps.
    spread = statistics.stdev(corrected)
    lower, upper = mean - spread, mean + spread

    for entry, corrected_time in zip(finishers, corrected):
        if corrected_time < lower:
            used[entry.boat_id] = lower / entry.tcf_used
        elif corrected_time > upper:
            used[entry.boat_id] = upper / entry.tcf_used
    return used


def realignment_factor(
    finishers: Sequence[RaceEntry], next_tcfs: Mapping[str, float]
) -> float | None:
    """Step B's common factor: the finishers' base numbers over their new handicaps.

    None if any finisher has no base number, because a total made partly of
    base numbers and partly of stand-ins would realign to a meaningless figure;
    the caller then leaves the handicaps as they are.
    """
    if not finishers or any(entry.base_number is None for entry in finishers):
        return None
    total_base = sum(entry.base_number for entry in finishers)
    total_next = sum(next_tcfs[entry.boat_id] for entry in finishers)
    return total_base / total_next


def realign_to_base_numbers(
    results: Sequence[RaceResult], finishers: Sequence[RaceEntry]
) -> tuple[RaceResult, ...]:
    """Step B applied to a race's results: every finisher's TCFn times the common factor.

    Each realigned result records the factor it was scaled by, so the
    unrealigned TCFn is still recoverable for anyone checking the arithmetic.
    If the factor can't be worked out (a finisher with no base number), the
    results come back unchanged, with ``realignment_factor`` None.
    """
    factor = realignment_factor(
        finishers, {result.boat_id: result.next_tcf for result in results if result.status.is_finisher}
    )
    if factor is None:
        return tuple(results)
    return tuple(
        replace(result, next_tcf=result.next_tcf * factor, realignment_factor=factor)
        if result.status.is_finisher
        else result
        for result in results
    )
