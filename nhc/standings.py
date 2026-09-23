"""Series standings under RRS A2.1 and A8.

Three rules do the work:

* **A2.1** A boat's series score is the total of her race scores excluding her
  worst. The notice of race or sailing instructions may change the number
  excluded. If a boat has two or more equal worst scores, the ones sailed
  *earliest* are the ones excluded. Lowest series score wins.
* **A8.1** On a series-score tie, list each boat's scores best to worst and
  compare position by position; the first difference breaks it in favour of the
  better score. Excluded scores are not used.
* **A8.2** If a tie survives that, compare the tied boats' scores in the last
  race, then the next-to-last, and so on. These scores *are* used even if
  excluded.

Note the two rules disagree about discarded scores on purpose: A8.1 ignores
them, A8.2 counts them. Getting that backwards would break ties the wrong way
round in a way no test of a single boat would catch.

Points are always multiples of 0.5 - whole places, halved across A7 ties - so
totals are exactly representable and compared exactly. No tolerance is needed
here, unlike in the handicap arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .errors import InvalidInput


@dataclass(frozen=True, slots=True)
class RaceScore:
    """One boat's points in one race, and whether they were discarded."""

    race_id: str
    points: float
    discarded: bool


@dataclass(frozen=True, slots=True)
class BoatStanding:
    """A boat's line in the series table.

    ``scores`` is in series order, so it prints straight across a results table;
    a discarded score is conventionally shown in brackets.
    """

    boat_id: str
    position: int
    total: float
    scores: tuple[RaceScore, ...]

    @property
    def counted_points(self) -> tuple[float, ...]:
        """Points that counted, in series order."""
        return tuple(s.points for s in self.scores if not s.discarded)

    @property
    def discarded_race_ids(self) -> tuple[str, ...]:
        return tuple(s.race_id for s in self.scores if s.discarded)


def compute_standings(races, *, discards: int = 1) -> tuple[BoatStanding, ...]:
    """Rank a series' boats, lowest total wins.

    ``races`` is a sequence of scored ``RaceOutcome``s in series order.

    ``discards`` is how many of each boat's worst scores to exclude. One is the
    A2.1 default, but a notice of race almost always changes it - commonly to
    none until some number of races have been sailed. A series that has sailed
    fewer races than the discard count excludes all of them and every boat
    totals zero; that is the literal reading of the rule and it surfaces the
    misconfiguration rather than hiding it.

    Returns standings in finishing order. Boats that remain tied after both
    tie-breaks share a position and consume the ones below, as elsewhere.
    """
    if discards < 0:
        raise InvalidInput(f"discards cannot be negative, got {discards!r}")

    race_list = list(races)
    boat_ids = _boat_ids(race_list)
    if not boat_ids:
        return ()

    excluded = min(discards, len(race_list))

    rows = {}
    for boat_id in boat_ids:
        points = [_points_for(race, boat_id) for race in race_list]
        discarded_indices = _indices_to_discard(points, excluded)
        rows[boat_id] = tuple(
            RaceScore(
                race_id=race.race_id,
                points=value,
                discarded=index in discarded_indices,
            )
            for index, (race, value) in enumerate(zip(race_list, points))
        )

    ranked = sorted(boat_ids, key=lambda boat_id: _ranking_key(rows[boat_id]))

    standings = []
    index = 0
    while index < len(ranked):
        key = _ranking_key(rows[ranked[index]])
        last = index
        while last + 1 < len(ranked) and _ranking_key(rows[ranked[last + 1]]) == key:
            last += 1

        place = index + 1
        for boat_id in ranked[index : last + 1]:
            scores = rows[boat_id]
            standings.append(
                BoatStanding(
                    boat_id=boat_id,
                    position=place,
                    total=_total(scores),
                    scores=scores,
                )
            )
        index = last + 1

    return tuple(standings)


def _boat_ids(race_list) -> tuple[str, ...]:
    """Boats in the series, in the order the first race lists them.

    Every race must cover the same boats. A boat entered in a series is scored
    for the whole series (A2.2), so a race missing one means the caller built
    the outcomes by hand and got it wrong.
    """
    if not race_list:
        return ()

    first = tuple(result.boat_id for result in race_list[0].results)
    expected = set(first)
    for race in race_list[1:]:
        present = {result.boat_id for result in race.results}
        if present != expected:
            missing = sorted(expected - present)
            extra = sorted(present - expected)
            raise InvalidInput(
                f"race {race.race_id} does not cover the same boats as "
                f"{race_list[0].race_id}: missing {missing}, unexpected {extra}"
            )
    return first


def _points_for(race, boat_id: str) -> float:
    for result in race.results:
        if result.boat_id == boat_id:
            if result.points is None:
                raise InvalidInput(
                    f"race {race.race_id}: boat {boat_id} has no points; "
                    f"score_points must run before standings"
                )
            return result.points
    raise InvalidInput(f"race {race.race_id} has no result for boat {boat_id}")


def _indices_to_discard(points: Sequence[float], excluded: int) -> frozenset[int]:
    """Which races a boat discards.

    Worst scores go first. A2.1 settles equal worst scores by excluding the
    race sailed earliest, which is what the index tiebreak in the sort key
    does - highest points first, and among equals the lowest index.
    """
    if excluded <= 0:
        return frozenset()
    order = sorted(range(len(points)), key=lambda i: (-points[i], i))
    return frozenset(order[:excluded])


def _total(scores: Sequence[RaceScore]) -> float:
    return sum(score.points for score in scores if not score.discarded)


def _ranking_key(scores: Sequence[RaceScore]):
    """Sort key putting the series winner first.

    Three levels, each lower-is-better, matching A2.1 then A8.1 then A8.2:

    1. the series total;
    2. the counted scores sorted best to worst, compared position by position -
       A8.1, which explicitly excludes discarded scores;
    3. every race's score in reverse series order, so the last race is compared
       first - A8.2, which explicitly includes discarded scores.
    """
    counted = tuple(sorted(s.points for s in scores if not s.discarded))
    all_scores_latest_first = tuple(s.points for s in reversed(scores))
    return (_total(scores), counted, all_scores_latest_first)
