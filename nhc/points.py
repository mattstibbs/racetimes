"""Race points under RRS Appendix A.

Separate from the handicap calculation, which the RYA spec is explicit about:
points are out of scope for its formulas (section 7). The source of truth here
is Appendix A of the Racing Rules of Sailing 2025-2028, in ``docs/reference/``.

The rules that apply to a single race:

* **A4** Low Point System - first scores 1, second 2, and so on.
* **A5.2** A boat that did not sail the course, retired or was disqualified
  scores one more than the number of boats **entered in the series**. Note this
  is the 2025-2028 wording: it covers every non-finisher alike. Earlier editions
  split DNC from the rest, and software written against those still does.
* **A5.3** An option the notice of race or sailing instructions may invoke,
  which softens A5.2 for boats that at least turned up.
* **A7** Tied boats share the points for their place and the places immediately
  below, divided equally.

A6.1 - boats moving up a place when a boat ahead is disqualified or retires
after finishing - is not implemented, because it cannot fire with the statuses
the engine currently models. It needs DSQ, RET and NSC, which are boats that
took a finishing place and then lost it. DNC, DNS and DNF never held one.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Sequence

from .domain import RaceResult, RaceStatus
from .errors import InvalidInput


def score_points(
    results: Sequence[RaceResult],
    *,
    series_entry_count: int,
    apply_a5_3: bool = False,
) -> tuple[RaceResult, ...]:
    """Fill in each boat's points for one race.

    ``series_entry_count`` is the number of boats entered in the series, which
    A5.2 uses to score every boat that did not finish. It has to be passed in:
    a single race cannot know it, and guessing it from the boats present would
    quietly under-score every non-finisher in a race with absentees. Note A2.2 -
    a boat that has entered any race in a series is scored for the whole series
    - so in a complete series every entrant appears in every race, DNC if
    absent, and the count equals the number of results.

    ``apply_a5_3`` invokes the A5.3 option, which the notice of race or sailing
    instructions must state. Under it a boat that came to the starting area but
    did not sail the course, retired or was disqualified is scored one more than
    the number of boats that **came to the starting area**, rather than one more
    than the series entry count; a boat that never came to the starting area
    still scores the latter. Boats that came are taken to be every boat except
    the DNCs, which is what DNC means in A10: "did not come to the starting
    area".

    Returns results in the order given, with ``points`` filled in.
    """
    if series_entry_count < 1:
        raise InvalidInput(
            f"series_entry_count must be at least 1, got {series_entry_count!r}"
        )
    if series_entry_count < len(results):
        raise InvalidInput(
            f"series_entry_count ({series_entry_count}) is smaller than the number "
            f"of boats in the race ({len(results)}); every boat racing is entered "
            f"in the series"
        )

    # How many boats share each finishing place. A place with more than one boat
    # is an A7 tie.
    boats_at_place = Counter(r.position for r in results if r.position is not None)

    came_to_starting_area = sum(1 for r in results if r.status is not RaceStatus.DNC)

    scored = []
    for result in results:
        if result.position is not None:
            points = points_for_place(result.position, boats_at_place[result.position])
        elif apply_a5_3 and result.status is not RaceStatus.DNC:
            points = float(came_to_starting_area + 1)
        else:
            points = float(series_entry_count + 1)
        scored.append(replace(result, points=points))

    return tuple(scored)


def points_for_place(place: int, boats_tied: int = 1) -> float:
    """Points for a finishing place under A4, shared across a tie under A7.

    A4 alone is simply the place: first scores 1. A7 adds that boats with equal
    corrected times take the points for their place and the places immediately
    below, added together and divided equally - so two boats tied for first
    share (1 + 2) / 2 = 1.5 each, and the next boat is third on 3 points. The
    places below a tie are consumed, not reused.

    Averaging consecutive integers from ``place`` upwards is the same as
    ``place + (boats_tied - 1) / 2``, which avoids building the list.
    """
    if place < 1:
        raise InvalidInput(f"place must be at least 1, got {place!r}")
    if boats_tied < 1:
        raise InvalidInput(f"boats_tied must be at least 1, got {boats_tied!r}")
    return place + (boats_tied - 1) / 2.0
