"""Replaying a whole series (RYA spec section 3, applied race by race).

A series is scored by replaying it from the start. Each race is scored on the
handicaps that applied at the time, and the handicaps it produces become the
next race's. That is what makes the brief's central invariant work: handicaps
are never edited directly, so correcting a finish half way through a season and
re-running ``score_series`` recalculates every later race automatically. There
is no incremental update path, and deliberately so - one that drifted out of
step with a full replay would be a very quiet bug.

Two things the caller does not have to supply, because the rules supply them:

* A boat's handicap for each race. It is derived from where the series started
  and what has happened since.
* A finish for every boat in every race. RRS A2.2 says a boat that has entered
  any race in a series is scored for the whole series, so a boat with no
  recorded finish in a race is scored DNC.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .domain import Boat, Finish, RaceEntry, RaceInput, RaceResult, RaceStatus, SeriesType
from .errors import InvalidInput
from .handicap import compute_club_adjustment
from .regatta import compute_regatta_adjustment
from .points import score_points
from .standings import BoatStanding, compute_standings


class HandicapProgression(StrEnum):
    """Where a series starts each boat's handicap.

    The brief makes this configurable per series. CARRY_OVER starts every boat
    on the handicap it already holds - whatever the last series left it on, or
    the realigned club number if end-of-series realignment has been run.
    RESET starts every boat on its published Base Number, discarding any drift.

    The engine does not need to know which of those a carried-over handicap is,
    which is what keeps this simple: whoever sets ``Boat.current_tcf`` decides.
    """

    CARRY_OVER = "CARRY_OVER"
    RESET = "RESET"


@dataclass(frozen=True, slots=True)
class SeriesRace:
    """One race within a series: who finished, and when.

    Carries no handicaps. They are derived by the replay.
    """

    race_id: str
    finishes: tuple[Finish, ...]

    def __init__(self, race_id: str, finishes: Sequence[Finish] = ()) -> None:
        object.__setattr__(self, "race_id", race_id)
        object.__setattr__(self, "finishes", tuple(finishes))
        self.__post_init__()

    def __post_init__(self) -> None:
        if not self.race_id:
            raise InvalidInput("race_id is required")
        seen: set[str] = set()
        for finish in self.finishes:
            if finish.boat_id in seen:
                raise InvalidInput(
                    f"race {self.race_id}: boat {finish.boat_id} has two recorded finishes"
                )
            seen.add(finish.boat_id)


@dataclass(frozen=True, slots=True)
class Series:
    """A set of races scored together, with the rules they are scored under.

    ``races`` are replayed in the order given, and that order is the series
    order. The engine does not sort by date, because a race's date is the
    caller's business and two races on one evening still have an order.

    ``progression`` is ignored for a regatta: spec section 4 requires every boat
    to start a regatta on its published Base Number, so that is what happens
    regardless. ``minimum_finishers`` is a club-series option and is refused on
    a regatta rather than silently ignored.
    """

    boats: tuple[Boat, ...]
    races: tuple[SeriesRace, ...]
    series_type: SeriesType = SeriesType.CLUB
    progression: HandicapProgression = HandicapProgression.CARRY_OVER
    minimum_finishers: int = 0
    apply_a5_3: bool = False
    discards: int = 1

    def __init__(
        self,
        boats: Sequence[Boat],
        races: Sequence[SeriesRace] = (),
        series_type: SeriesType = SeriesType.CLUB,
        progression: HandicapProgression = HandicapProgression.CARRY_OVER,
        minimum_finishers: int = 0,
        apply_a5_3: bool = False,
        discards: int = 1,
    ) -> None:
        object.__setattr__(self, "boats", tuple(boats))
        object.__setattr__(self, "races", tuple(races))
        object.__setattr__(self, "series_type", series_type)
        object.__setattr__(self, "progression", progression)
        object.__setattr__(self, "minimum_finishers", minimum_finishers)
        object.__setattr__(self, "apply_a5_3", apply_a5_3)
        object.__setattr__(self, "discards", discards)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not self.boats:
            raise InvalidInput("a series needs at least one boat")
        if not isinstance(self.progression, HandicapProgression):
            raise InvalidInput(
                f"progression must be one of {[p.value for p in HandicapProgression]}, "
                f"got {self.progression!r}"
            )
        if not isinstance(self.series_type, SeriesType):
            raise InvalidInput(
                f"series_type must be one of {[s.value for s in SeriesType]}, "
                f"got {self.series_type!r}"
            )

        if self.discards < 0:
            raise InvalidInput(f"discards cannot be negative, got {self.discards!r}")
        if self.minimum_finishers < 0:
            # Caught here as well as in compute_club_adjustment, so a bad series
            # fails when it is built rather than when it is scored.
            raise InvalidInput(
                f"minimum_finishers cannot be negative, got {self.minimum_finishers!r}"
            )
        if self.minimum_finishers and self.series_type is SeriesType.REGATTA:
            raise InvalidInput(
                "minimum_finishers is a club-series option; a regatta races too "
                "few times to skip an adjustment, and every boat is in the sums"
            )

        boat_ids = [boat.boat_id for boat in self.boats]
        duplicates = {i for i in boat_ids if boat_ids.count(i) > 1}
        if duplicates:
            raise InvalidInput(f"boat entered twice in the series: {', '.join(sorted(duplicates))}")

        race_ids = [race.race_id for race in self.races]
        duplicate_races = {i for i in race_ids if race_ids.count(i) > 1}
        if duplicate_races:
            raise InvalidInput(f"duplicate race_id: {', '.join(sorted(duplicate_races))}")

        entered = set(boat_ids)
        for race in self.races:
            unknown = sorted({f.boat_id for f in race.finishes} - entered)
            if unknown:
                raise InvalidInput(
                    f"race {race.race_id} records finishes for boats that are not "
                    f"entered in the series: {', '.join(unknown)}"
                )

    @property
    def entry_count(self) -> int:
        """Boats entered in the series - the number RRS A5.2 scores against."""
        return len(self.boats)


@dataclass(frozen=True, slots=True)
class RaceOutcome:
    """One race's scored results, in series order."""

    race_id: str
    results: tuple[RaceResult, ...]


@dataclass(frozen=True, slots=True)
class SeriesOutcome:
    """Every race of a series, scored.

    ``starting_handicaps`` is what the series began on, which depends on the
    progression setting. It is held as pairs rather than a dict so the whole
    object is genuinely immutable.
    """

    races: tuple[RaceOutcome, ...]
    starting_handicaps: tuple[tuple[str, float], ...]
    standings: tuple[BoatStanding, ...] = ()

    @property
    def ending_handicaps(self) -> dict[str, float]:
        """Each boat's handicap after the final race.

        This is the EH that end-of-series realignment takes as its input (spec
        section 5). A series with no races yet ends where it started.
        """
        if not self.races:
            return dict(self.starting_handicaps)
        return {result.boat_id: result.next_tcf for result in self.races[-1].results}

    def race(self, race_id: str) -> RaceOutcome:
        for outcome in self.races:
            if outcome.race_id == race_id:
                return outcome
        raise KeyError(race_id)


def score_series(series: Series) -> SeriesOutcome:
    """Replay a series from the start and score every race in it.

    Each race is scored on the handicaps that applied at the time, and produces
    the handicaps for the next one. Boats with no recorded finish in a race are
    scored DNC, per RRS A2.2.
    """
    handicaps = _starting_handicaps(series)
    starting = tuple(sorted(handicaps.items()))

    outcomes = []
    for index, race in enumerate(series.races):
        results = _score_one_race(series, race, handicaps, is_first_race=index == 0)
        outcomes.append(RaceOutcome(race_id=race.race_id, results=results))
        # Feed this race's handicaps into the next. This single line is the
        # whole point of the module. effective_next_tcf rather than next_tcf,
        # because a regatta clamps and it is the clamped number a boat races on.
        handicaps = {result.boat_id: result.effective_next_tcf for result in results}

    return SeriesOutcome(
        races=tuple(outcomes),
        starting_handicaps=starting,
        standings=compute_standings(outcomes, discards=series.discards),
    )


def _starting_handicaps(series: Series) -> dict[str, float]:
    # Spec section 4: "All boats start on their Base Number" in a regatta, so
    # the progression setting does not apply there.
    reset = (
        series.progression is HandicapProgression.RESET
        or series.series_type is SeriesType.REGATTA
    )
    return {
        boat.boat_id: (boat.base_number if reset else boat.current_tcf)
        for boat in series.boats
    }


def _score_one_race(
    series: Series,
    race: SeriesRace,
    handicaps: dict[str, float],
    *,
    is_first_race: bool,
) -> tuple[RaceResult, ...]:
    recorded = {finish.boat_id: finish for finish in race.finishes}

    entries = []
    for boat in series.boats:
        finish = recorded.get(boat.boat_id)
        entries.append(
            RaceEntry(
                boat_id=boat.boat_id,
                # RRS A2.2: a boat entered in the series is scored for the whole
                # series, so no recorded finish means DNC rather than absent.
                status=finish.status if finish else RaceStatus.DNC,
                tcf_used=handicaps[boat.boat_id],
                elapsed_seconds=finish.elapsed_seconds if finish else None,
                base_number=boat.base_number,
            )
        )

    race_input = RaceInput(
        series_type=series.series_type,
        entries=entries,
        is_first_race_of_regatta=is_first_race,
    )
    if series.series_type is SeriesType.REGATTA:
        results = compute_regatta_adjustment(race_input)
    else:
        results = compute_club_adjustment(
            race_input, minimum_finishers=series.minimum_finishers
        )
    return score_points(
        results,
        series_entry_count=series.entry_count,
        apply_a5_3=series.apply_a5_3,
    )
