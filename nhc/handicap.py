"""Club-series handicap adjustment (RYA spec section 3).

After each race, every boat that finished gets a new handicap for its next
race, blended from the handicap it raced under and the handicap it would have
needed to tie for first. Boats that did not finish carry theirs forward
untouched and are excluded from the fleet-wide sums entirely.

The whole calculation is four steps:

    AS   = 100 / E                          for each finisher
    TCFr = (sum(TCF) / sum(AS)) x AS        sums over finishers only
    TCFn = 0.70 x TCF + 0.30 x TCFr         if TCFr >  TCF (over-performance)
           0.85 x TCF + 0.15 x TCFr         if TCFr <= TCF (under-performance)

Over-performance is rated down twice as hard as under-performance is rated up,
which is what stops a fleet's handicaps drifting upwards over a season.

Nothing here rounds. See the precision note in ``nhc/domain.py``.
"""

from __future__ import annotations

import math
from dataclasses import replace

from .domain import Performance, RaceInput, RaceResult, SeriesType
from .errors import InvalidInput
from .options import capped_elapsed_times, realign_to_base_numbers
from .scoring import score_race

#: Numerator of the adjustment scale, AS = 100 / E (spec section 3, step 1).
#: An arbitrary constant that cancels out of TCFr; it keeps AS a convenient
#: size rather than a very small fraction.
ADJUSTMENT_SCALE_NUMERATOR = 100.0

#: Blend weights for the new handicap (spec section 3, step 4).
OVER_PERFORMANCE_WEIGHT = 0.30
UNDER_PERFORMANCE_WEIGHT = 0.15

#: How close TCFr must be to TCF to count as equal rather than as
#: over-performance.
#:
#: This absorbs floating-point representation error only. It matters in the
#: degenerate single-finisher case, where the sums collapse and TCFr should come
#: out exactly equal to TCF, but the round trip through 100/E and back can land
#: a unit in the last place above it. The spec's second branch is "TCFr <= TCF",
#: so equality is under-performance; without this, float noise would report
#: over-performance instead. Both branches give the same TCFn at equality, so
#: the number is the same either way - but the label is not, and something will
#: eventually key off it.
PERFORMANCE_TOLERANCE = 1e-12


def adjustment_scale(elapsed_seconds: float) -> float:
    """AS = 100 / E (spec section 3, step 1)."""
    return ADJUSTMENT_SCALE_NUMERATOR / elapsed_seconds


def classify_performance(achieved: float, raced_under: float) -> Performance:
    """OVER when TCFr > TCF, UNDER when TCFr <= TCF (spec section 3, step 3).

    Exact equality is UNDER, per the spec's "<=".
    """
    if math.isclose(achieved, raced_under, rel_tol=PERFORMANCE_TOLERANCE, abs_tol=0.0):
        return Performance.UNDER
    return Performance.OVER if achieved > raced_under else Performance.UNDER


def blend_handicap(raced_under: float, achieved: float, weight: float) -> float:
    """Move a handicap ``weight`` of the way from TCF towards TCFr.

    The spec writes this two ways - `0.7 x TCF + 0.3 x TCFr` for club series,
    `TCF + 0.6 x (TCFr - TCF)` for regattas - but they are the same operation
    with different weights, so both layers share it.
    """
    return (1.0 - weight) * raced_under + weight * achieved


def next_tcf(raced_under: float, achieved: float, performance: Performance) -> float:
    """TCFn, the handicap for the boat's next race (spec section 3, step 4)."""
    weight = (
        OVER_PERFORMANCE_WEIGHT
        if performance is Performance.OVER
        else UNDER_PERFORMANCE_WEIGHT
    )
    return blend_handicap(raced_under, achieved, weight)


def compute_club_adjustment(
    race: RaceInput,
    *,
    minimum_finishers: int = 0,
    cap_extremes: bool = False,
    realign_to_base: bool = False,
) -> tuple[RaceResult, ...]:
    """Score a club race and work out everyone's handicap for the next one.

    Returns results in entry order, each carrying the corrected time and place
    from ``score_race`` plus the handicap fields.

    Boats that did not finish are excluded from the AS and TCF sums and carry
    their handicap forward unchanged, so a DNC cannot move anyone else's
    handicap. Their adjustment scale is 0.0 - computed, and genuinely zero.

    ``minimum_finishers`` is the optional threshold from section 9 of the spec:
    some club software declines to move any handicap in a race with fewer than
    three finishers, on the grounds that the fleet is too small for the result
    to mean much. The RYA's own text does not require it, so it defaults to 0,
    which is off. When a race falls below the threshold nothing is adjusted and
    the handicap fields stay None, which distinguishes "the adjustment did not
    run" from a boat that ran through it and earned no change.

    A race with no finishers at all is handled the same way as a below-threshold
    one - there is nothing to divide by - rather than raising.

    ``cap_extremes`` and ``realign_to_base`` switch on the two optional extra
    steps in ``nhc/options.py`` (capping extreme results, and realigning the
    finishers' new handicaps to their base numbers). Both are off by default,
    which is exactly the RYA calculation above. They don't run in a race that
    falls below ``minimum_finishers``, where nothing is adjusted at all.
    """
    if race.series_type is not SeriesType.CLUB:
        # Applying club rules to a regatta silently produces plausible-looking
        # numbers from the wrong formulas, so refuse rather than guess.
        raise InvalidInput(
            f"compute_club_adjustment needs a {SeriesType.CLUB.value} race, "
            f"got {race.series_type.value}; use compute_regatta_adjustment"
        )
    if minimum_finishers < 0:
        raise InvalidInput(f"minimum_finishers cannot be negative, got {minimum_finishers!r}")

    scored = score_race(race)
    finishers = race.finishers

    if not finishers or len(finishers) < minimum_finishers:
        return tuple(replace(result, next_tcf=result.tcf_used) for result in scored)

    # Step 2's ratio is the same for every boat in the race; only the boat's own
    # AS varies. Computing it once also makes it obvious that a non-finisher,
    # being absent from both sums, cannot influence anyone else's result.
    total_tcf = sum(entry.tcf_used for entry in finishers)
    total_scale = sum(adjustment_scale(entry.elapsed_seconds) for entry in finishers)
    ratio = total_tcf / total_scale

    # Optional step A: the elapsed time each achieved handicap is worked from.
    # Off, that's every finisher's real time; on, extremes are capped. The
    # ratio above always uses the real times.
    if cap_extremes:
        elapsed_used = capped_elapsed_times(finishers)
    else:
        elapsed_used = {entry.boat_id: entry.elapsed_seconds for entry in finishers}

    adjusted = []
    for result in scored:
        if not result.status.is_finisher:
            adjusted.append(
                replace(result, adjustment_scale=0.0, next_tcf=result.tcf_used)
            )
            continue

        used = elapsed_used[result.boat_id]
        scale = adjustment_scale(used)
        achieved = ratio * scale
        performance = classify_performance(achieved, result.tcf_used)
        adjusted.append(
            replace(
                result,
                adjustment_scale=scale,
                elapsed_seconds_used=used,
                achieved_handicap=achieved,
                performance=performance,
                next_tcf=next_tcf(result.tcf_used, achieved, performance),
            )
        )

    # Optional step B: rescale the finishers' new handicaps to their base numbers.
    if realign_to_base:
        return realign_to_base_numbers(adjusted, finishers)
    return tuple(adjusted)
