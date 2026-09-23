"""Regatta handicap adjustment (RYA spec section 4).

A regatta is short and standalone: a handful of races over a weekend, everyone
starting on their published Base Number. Three things make it different from a
club series.

**Every boat is in the sums.** A club series excludes non-finishers entirely.
A regatta back-calculates an elapsed time for them so they still count, on the
reasoning that over two days of racing a retirement should not simply vanish.

**The blend is stronger and less asymmetric.** Club racing moves a handicap 30%
of the way towards the achieved handicap when a boat over-performs and 15% when
it under-performs. A regatta moves 60% and 50%, because it has only a few races
to find the right numbers. On the first race there is no distinction at all:
everyone moves 60%.

**Handicaps are clamped.** After every race, a boat's new handicap is held to
within 10% of its own Base Number, so a single freak result cannot rate a boat
out of contention. The pre-clamp value stays visible on the result; use
``RaceResult.effective_next_tcf`` for the number that counts.
"""

from __future__ import annotations

from dataclasses import replace

from .domain import Performance, RaceInput, RaceResult, RaceStatus, SeriesType
from .errors import InvalidInput
from .handicap import adjustment_scale, blend_handicap, classify_performance
from .scoring import corrected_time, score_race

#: Blend weights (spec section 4, step 3). The first race of a regatta uses the
#: over-performance weight for every boat, whatever they actually did.
OVER_PERFORMANCE_WEIGHT = 0.6
UNDER_PERFORMANCE_WEIGHT = 0.5
FIRST_RACE_WEIGHT = 0.6

#: The clamp, as a fraction of the boat's own Base Number (spec section 4,
#: step 4). Applied at every race of the regatta, not only the first.
CLAMP_LOWER = 0.9
CLAMP_UPPER = 1.1

#: How many finishers the DNC/DNS back-calculation averages over, at most.
TOP_FINISHERS_AVERAGED = 3


def compute_regatta_adjustment(race: RaceInput) -> tuple[RaceResult, ...]:
    """Score a regatta race and work out everyone's handicap for the next one.

    Whether this is the regatta's first race is read from
    ``race.is_first_race_of_regatta``.

    Raises ``InvalidInput`` if nobody finished: the back-calculation has no
    corrected times to work from, and spec section 7 asks for an explicit error
    rather than a division by an empty set.
    """
    if race.series_type is not SeriesType.REGATTA:
        raise InvalidInput(
            f"compute_regatta_adjustment needs a {SeriesType.REGATTA.value} race, "
            f"got {race.series_type.value}; use compute_club_adjustment"
        )

    finishers = race.finishers
    if not finishers:
        raise InvalidInput(
            "a regatta race needs at least one finisher: the elapsed times of "
            "boats that did not finish are back-calculated from the corrected "
            "times of those that did, and there are none"
        )

    elapsed_used = _elapsed_times(race, finishers)

    # Unlike a club race, the sums run over the whole fleet - every boat now has
    # a usable elapsed time, real or back-calculated.
    total_tcf = sum(entry.tcf_used for entry in race.entries)
    total_scale = sum(adjustment_scale(elapsed_used[entry.boat_id]) for entry in race.entries)
    ratio = total_tcf / total_scale

    adjusted = []
    for result in score_race(race):
        used = elapsed_used[result.boat_id]
        scale = adjustment_scale(used)
        achieved = ratio * scale

        if race.is_first_race_of_regatta:
            # Spec section 4, step 3: "all boats, no over/under distinction".
            # Reporting a classification here would be misleading, since it
            # would not be the one driving the weight.
            performance = None
            weight = FIRST_RACE_WEIGHT
        else:
            performance = classify_performance(achieved, result.tcf_used)
            weight = (
                OVER_PERFORMANCE_WEIGHT
                if performance is Performance.OVER
                else UNDER_PERFORMANCE_WEIGHT
            )

        unclamped = blend_handicap(result.tcf_used, achieved, weight)
        adjusted.append(
            replace(
                result,
                elapsed_seconds_used=used,
                adjustment_scale=scale,
                achieved_handicap=achieved,
                performance=performance,
                next_tcf=unclamped,
                next_tcf_clamped=clamp_to_base_number(unclamped, _base_number(result, race)),
            )
        )

    return tuple(adjusted)


def clamp_to_base_number(tcf: float, base_number: float) -> float:
    """Hold a handicap to within 10% of the boat's Base Number (step 4)."""
    return min(max(tcf, CLAMP_LOWER * base_number), CLAMP_UPPER * base_number)


def _base_number(result: RaceResult, race: RaceInput) -> float:
    for entry in race.entries:
        if entry.boat_id == result.boat_id:
            # RaceInput already refuses a regatta entry without one.
            return entry.base_number
    raise InvalidInput(f"no entry for boat {result.boat_id}")


def _elapsed_times(race: RaceInput, finishers) -> dict[str, float]:
    """Every boat's elapsed time, real or back-calculated (step 1).

    A non-finisher is given the elapsed time it *would* have needed to record a
    particular corrected time: the average of the top finishers' for a boat that
    never started, the median finisher's for one that started and retired. The
    reasoning is that not starting is treated as a notional mid-to-good result
    while retiring is treated as a notional average one, and dividing by the
    boat's own TCF converts that corrected time back into an elapsed time it
    could plausibly have sailed.
    """
    finisher_corrected = sorted(
        corrected_time(entry.elapsed_seconds, entry.tcf_used) for entry in finishers
    )
    top_average = _mean(finisher_corrected[:TOP_FINISHERS_AVERAGED])
    median = _median(finisher_corrected)

    times = {}
    for entry in race.entries:
        if entry.status.is_finisher:
            times[entry.boat_id] = entry.elapsed_seconds
        elif entry.status is RaceStatus.DNF:
            times[entry.boat_id] = median / entry.tcf_used
        else:
            # DNC and DNS: the boat never sailed the course.
            times[entry.boat_id] = top_average / entry.tcf_used
    return times


def _mean(values) -> float:
    return sum(values) / len(values)


def _median(sorted_values) -> float:
    """Middle value, or the average of the two middle ones (step 1)."""
    count = len(sorted_values)
    middle = count // 2
    if count % 2:
        return sorted_values[middle]
    return _mean(sorted_values[middle - 1 : middle + 1])
