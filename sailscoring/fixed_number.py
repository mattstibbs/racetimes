"""Fixed-number series: Portsmouth Yardstick (slice 24).

Under NHC a boat's handicap moves after every race. Under a fixed-number
system a boat has one number for the whole series and nothing moves. The
Portsmouth Yardstick (PY) number and the RYA YTC number are whole numbers,
higher for a slower boat, and each scheme's published formula is the same::

    corrected time = elapsed time x 1000 / number

Everything else is the same as NHC and shared with it: the finishes a race
officer records, the ranking of corrected times (RRS A3 and A7), points
(A4, A5.2, A5.3 and the scoring penalty), and standings (A2.1, A8). So this
module is small. It has its own input and output types, rather than leaving
NHC fields empty, and it imports nothing from the NHC modules (``handicap``,
``regatta``, ``options``, ``realignment``, ``series``), nor do they import it.
``tests/test_fixed_number.py`` checks both directions.

The reference documents in ``docs/reference/`` are the RYA's sample notice of race
wording for Portsmouth Yardstick, which is silent on the formula and on
rounding, and the RYA YTC 2026 Policy and Procedures, whose section 6.2 gives
the formula. Both systems use the formula above (for Portsmouth Yardstick it is
the scheme's published one, the project owner's decision), and corrected times are
kept at full precision and never rounded before ranking, as under NHC: two
boats a fraction of a second apart are not tied, even if a page shows both the
same rounded time. If a later system needs times rounded before ranking, the
rounding goes here, for that system.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .domain import (
    RaceOutcome,
    RaceStatus,
    SeriesRace,
    _check_positive,
    check_series,
)
from .errors import InvalidInput
from .points import score_points
from .scoring import assign_positions
from .standings import BoatStanding, compute_standings


class FixedNumberSystem(StrEnum):
    """Which fixed-number system's formula to use."""

    PY = "PY"  # RYA Portsmouth Yardstick
    YTC = "YTC"  # RYA YTC (Yacht Time Correction), section 6.2 of its 2026 policy


#: The numerator of each system's formula: corrected time = elapsed x this /
#: number. Kept per system so the formula stays as the scheme writes it.
_NUMERATOR = {FixedNumberSystem.PY: 1000, FixedNumberSystem.YTC: 1000}


def fixed_number_corrected_time(
    elapsed_seconds: float, number: float, system: FixedNumberSystem
) -> float:
    """The scheme's corrected time, as written: elapsed x 1000 / number.

    Deliberately not "turn the number into a TCF, then multiply": dividing by
    the number directly keeps float noise out of ties, and a fixture can be
    checked against the formula exactly as the scheme states it. Full precision.
    """
    if not isinstance(system, FixedNumberSystem):
        raise InvalidInput(
            f"system must be one of {[s.value for s in FixedNumberSystem]}, "
            f"got {system!r}"
        )
    _check_positive(elapsed_seconds, "elapsed_seconds", "corrected time")
    _check_positive(number, "number", "corrected time")
    return elapsed_seconds * _NUMERATOR[system] / number


@dataclass(frozen=True, slots=True)
class FixedNumberBoat:
    """A boat and the number it races on for the whole series.

    ``number`` is required and must be positive and finite. The engine doesn't
    insist it is whole, since the formula works for any positive number; a
    site's own form can.
    """

    boat_id: str
    number: float
    name: str = ""

    def __post_init__(self) -> None:
        if not self.boat_id:
            raise InvalidInput("boat_id is required")
        _check_positive(self.number, "number", f"boat {self.boat_id}")


@dataclass(frozen=True, slots=True)
class FixedNumberSeries:
    """A set of races scored together on fixed numbers.

    ``races`` are the same ``SeriesRace`` an NHC series uses: they carry no
    handicap. There is no series type, progression, minimum finishers, capping
    or realignment, because a fixed-number series has nothing to apply them to.
    """

    boats: tuple[FixedNumberBoat, ...]
    races: tuple[SeriesRace, ...]
    system: FixedNumberSystem
    apply_a5_3: bool = False
    discards: int = 1
    discard_threshold: int = 0

    def __init__(
        self,
        boats: Sequence[FixedNumberBoat],
        races: Sequence[SeriesRace],
        system: FixedNumberSystem,
        apply_a5_3: bool = False,
        discards: int = 1,
        discard_threshold: int = 0,
    ) -> None:
        object.__setattr__(self, "boats", tuple(boats))
        object.__setattr__(self, "races", tuple(races))
        object.__setattr__(self, "system", system)
        object.__setattr__(self, "apply_a5_3", apply_a5_3)
        object.__setattr__(self, "discards", discards)
        object.__setattr__(self, "discard_threshold", discard_threshold)
        self.__post_init__()

    def __post_init__(self) -> None:
        check_series(
            self.boats,
            self.races,
            discards=self.discards,
            discard_threshold=self.discard_threshold,
        )
        if not isinstance(self.system, FixedNumberSystem):
            raise InvalidInput(
                f"system must be one of {[s.value for s in FixedNumberSystem]}, "
                f"got {self.system!r}"
            )

    @property
    def entry_count(self) -> int:
        """Boats entered in the series - the number RRS A5.2 scores against."""
        return len(self.boats)


@dataclass(frozen=True, slots=True)
class FixedNumberResult:
    """One boat in one race.

    ``number`` is the number the boat raced on, the same in every race. There
    is no next handicap, achieved handicap, performance or adjustment scale,
    because nothing is adjusted. ``scoring_penalty`` and ``penalty_points`` are
    as on ``RaceResult``: the penalty touches points only.
    """

    boat_id: str
    status: RaceStatus
    number: float
    elapsed_seconds: float | None
    corrected_time: float | None
    position: int | None
    points: float | None = None
    scoring_penalty: bool = False
    penalty_points: float | None = None


@dataclass(frozen=True, slots=True)
class FixedNumberOutcome:
    """Every race of a fixed-number series, scored, and the standings."""

    system: FixedNumberSystem
    races: tuple[RaceOutcome, ...]
    standings: tuple[BoatStanding, ...] = ()

    def race(self, race_id: str) -> RaceOutcome:
        for outcome in self.races:
            if outcome.race_id == race_id:
                return outcome
        raise KeyError(race_id)


def score_fixed_number_series(series: FixedNumberSeries) -> FixedNumberOutcome:
    """Score every race of a fixed-number series.

    Each finisher's corrected time comes from the formula and her number; the
    fleet is ranked on it; a boat with no recorded finish is scored DNC (RRS
    A2.2), as in an NHC series. The same number is used in every race, and
    nothing is fed forward from one race to the next, so each race is scored
    on its own.
    """
    outcomes = [
        RaceOutcome(race_id=race.race_id, results=_score_one_race(series, race))
        for race in series.races
    ]
    return FixedNumberOutcome(
        system=series.system,
        races=tuple(outcomes),
        standings=compute_standings(
            outcomes,
            discards=series.discards,
            discard_threshold=series.discard_threshold,
        ),
    )


def _score_one_race(
    series: FixedNumberSeries, race: SeriesRace
) -> tuple[FixedNumberResult, ...]:
    recorded = {finish.boat_id: finish for finish in race.finishes}

    corrected: dict[str, float] = {}
    for boat in series.boats:
        finish = recorded.get(boat.boat_id)
        if finish is not None and finish.status.is_finisher:
            corrected[boat.boat_id] = fixed_number_corrected_time(
                finish.elapsed_seconds, boat.number, series.system
            )

    # Lowest corrected time wins. sorted() is stable, so equal times keep the
    # boats' order; the ranking then gives them the same place (RRS A7).
    ranked = sorted(
        ((time, boat_id) for boat_id, time in corrected.items()),
        key=lambda pair: pair[0],
    )
    positions = assign_positions(ranked)

    results = []
    for boat in series.boats:
        finish = recorded.get(boat.boat_id)
        results.append(
            FixedNumberResult(
                boat_id=boat.boat_id,
                # RRS A2.2: a boat entered in the series is scored for the whole
                # series, so no recorded finish means DNC rather than absent.
                status=finish.status if finish else RaceStatus.DNC,
                number=boat.number,
                elapsed_seconds=finish.elapsed_seconds if finish else None,
                corrected_time=corrected.get(boat.boat_id),
                position=positions.get(boat.boat_id),
                scoring_penalty=finish.scoring_penalty if finish else False,
            )
        )
    return score_points(
        results,
        series_entry_count=series.entry_count,
        apply_a5_3=series.apply_a5_3,
    )
