"""The data the scoring engine takes in and gives back.

These types mirror the suggested data model in section 6 of
``docs/reference/RYA_nhc_calculation_spec.md``, which invites adaptation to
idiomatic types. Two places take it up on that:

* ``position`` is ``int | None`` rather than the spec's ``int | "DNC"``. A magic
  string in a numeric field is awkward to work with, and the boat's ``status``
  already records why it has no position.
* Sequences are stored as tuples, so a constructed object cannot be mutated
  behind the caller's back.

Everything here is a frozen dataclass that validates itself on construction, so
an invalid race cannot be built at all - the error surfaces at the point the bad
data enters, not several formulas later as a stray NaN.

PRECISION. Handicaps are carried as full-precision floats and are never rounded
between races. Section 7 of the spec is explicit: rounding to whole seconds or
to three decimal places is a display convention only. The RYA publishes its
tables at 3 d.p., which makes rounding look canonical, but rounding TCFn before
feeding it into the next race compounds the error across a series. Round at the
edges, when showing a number to a person; never in here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .errors import InvalidInput


class RaceStatus(StrEnum):
    """How a boat's race ended (spec section 6).

    A StrEnum so members compare equal to the plain strings used in the
    fixtures and in any JSON crossing the boundary, while still being a closed
    set that a typo cannot slip past.

    This is the subset the handicap calculation needs. RRS A10 defines a further
    ten abbreviations (OCS, RET, DSQ, NSC and the rest); those affect points,
    not handicaps, and belong with the Appendix A scoring layer.
    """

    FINISHED = "FINISHED"
    DNC = "DNC"
    DNS = "DNS"
    DNF = "DNF"

    @property
    def is_finisher(self) -> bool:
        return self is RaceStatus.FINISHED


class SeriesType(StrEnum):
    """Which adjustment rules apply: spec section 3 (club) or section 4 (regatta)."""

    CLUB = "CLUB"
    REGATTA = "REGATTA"


class Performance(StrEnum):
    """Whether a boat beat its handicap in a race (spec section 3, step 3).

    OVER when TCFr > TCF, UNDER when TCFr <= TCF. Note that exact equality is
    UNDER: the spec's second branch is "<=", not "<".
    """

    OVER = "OVER"
    UNDER = "UNDER"


def _check_positive(value: float | None, field: str, context: str) -> None:
    """Reject anything that would poison the arithmetic downstream.

    Non-finite values matter as much as non-positive ones: a NaN handicap
    propagates silently through every sum in the fleet and comes out the far end
    as a whole race of NaN results, with nothing to say where it started.
    """
    if value is None:
        raise InvalidInput(f"{context}: {field} is required")
    if not math.isfinite(value):
        raise InvalidInput(f"{context}: {field} must be a finite number, got {value!r}")
    if value <= 0:
        raise InvalidInput(f"{context}: {field} must be greater than zero, got {value!r}")


@dataclass(frozen=True, slots=True)
class Boat:
    """A boat as the engine sees it (spec section 6).

    ``base_number`` is the published RYA rating, fixed. ``current_tcf`` is the
    handicap the boat carries into its next race, which drifts away from the
    base number as the series progresses and is pulled back towards it by
    end-of-series realignment (spec section 5).
    """

    boat_id: str
    base_number: float
    current_tcf: float
    name: str = ""

    def __post_init__(self) -> None:
        if not self.boat_id:
            raise InvalidInput("boat_id is required")
        _check_positive(self.base_number, "base_number", f"boat {self.boat_id}")
        _check_positive(self.current_tcf, "current_tcf", f"boat {self.boat_id}")


@dataclass(frozen=True, slots=True)
class RaceEntry:
    """One boat's participation in one race (spec section 6).

    ``tcf_used`` is the handicap this boat actually raced under, which is not
    necessarily its current one - re-scoring a corrected finish replays the
    series, and each race must be scored on the handicaps that applied at the
    time.

    ``base_number`` is optional because the club-series calculation never needs
    it. Regattas do, for the +/-10% clamp in spec section 4 step 4, and
    ``RaceInput`` enforces its presence there rather than here, since whether it
    is required depends on the race, not on the entry.
    """

    boat_id: str
    status: RaceStatus
    tcf_used: float
    elapsed_seconds: float | None = None
    base_number: float | None = None

    def __post_init__(self) -> None:
        if not self.boat_id:
            raise InvalidInput("boat_id is required")

        context = f"entry for boat {self.boat_id}"
        if not isinstance(self.status, RaceStatus):
            raise InvalidInput(
                f"{context}: status must be one of "
                f"{[s.value for s in RaceStatus]}, got {self.status!r}"
            )
        _check_positive(self.tcf_used, "tcf_used", context)

        if self.status.is_finisher:
            # Spec section 7: FINISHED with elapsed <= 0 is invalid input.
            _check_positive(self.elapsed_seconds, "elapsed_seconds", context)
        elif self.elapsed_seconds:
            # A non-finisher with a time is a data-entry mistake, and a costly
            # one: the time would look usable and quietly skew the whole fleet's
            # adjustment.
            raise InvalidInput(
                f"{context}: status is {self.status.value} but an elapsed time "
                f"of {self.elapsed_seconds!r} was recorded"
            )
        else:
            # Both None and 0 are used to mean "no time recorded" - the spec
            # writes E = 0 for a DNC, the fixtures follow it, and null is the
            # natural thing for a caller to pass. Normalise to None so the rest
            # of the engine has one thing to test rather than two.
            object.__setattr__(self, "elapsed_seconds", None)

        if self.base_number is not None:
            _check_positive(self.base_number, "base_number", context)


@dataclass(frozen=True, slots=True)
class RaceInput:
    """A single race, ready to score (spec section 6).

    ``is_first_race_of_regatta`` selects the regatta's first-race blend (spec
    section 4, step 3). The spec says it is ignored for club series, so it is
    accepted and ignored rather than rejected.
    """

    series_type: SeriesType
    entries: tuple[RaceEntry, ...]
    is_first_race_of_regatta: bool = False

    def __init__(
        self,
        series_type: SeriesType,
        entries: Sequence[RaceEntry],
        is_first_race_of_regatta: bool = False,
    ) -> None:
        # Written out longhand so any sequence can be passed in and stored as a
        # tuple. A frozen dataclass forbids plain attribute assignment, hence
        # object.__setattr__ - the standard escape hatch for exactly this.
        object.__setattr__(self, "series_type", series_type)
        object.__setattr__(self, "entries", tuple(entries))
        object.__setattr__(self, "is_first_race_of_regatta", is_first_race_of_regatta)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.series_type, SeriesType):
            raise InvalidInput(
                f"series_type must be one of {[s.value for s in SeriesType]}, "
                f"got {self.series_type!r}"
            )
        if not self.entries:
            raise InvalidInput("a race needs at least one entry")

        seen: set[str] = set()
        for entry in self.entries:
            if entry.boat_id in seen:
                raise InvalidInput(f"boat {entry.boat_id} is entered twice in the same race")
            seen.add(entry.boat_id)

        if self.series_type is SeriesType.REGATTA:
            # Spec section 7: a regatta entry with no Base Number cannot be
            # clamped, so the base number is required there.
            missing = [e.boat_id for e in self.entries if e.base_number is None]
            if missing:
                raise InvalidInput(
                    "regatta entries need a base_number for the +/-10% clamp; "
                    f"missing for: {', '.join(sorted(missing))}"
                )

    @property
    def finishers(self) -> tuple[RaceEntry, ...]:
        """Entries with a usable elapsed time.

        These are the boats that appear in the AS and TCF sums of spec section
        3, step 2. Everyone else carries their handicap forward untouched.
        """
        return tuple(e for e in self.entries if e.status.is_finisher)


@dataclass(frozen=True, slots=True)
class RaceResult:
    """What the engine computes for one boat in one race (spec section 6).

    ``next_tcf`` is the handicap for the boat's next race. For a non-finisher it
    equals the handicap raced under, unchanged. ``next_tcf_clamped`` is regatta
    only and stays None for club races, so the pre-clamp value remains visible
    for anyone checking the arithmetic against the spec.

    Points are deliberately absent. They are an RRS Appendix A concern, need the
    series entry count that a single race does not have, and are produced by a
    separate layer.
    """

    boat_id: str
    status: RaceStatus
    tcf_used: float
    elapsed_seconds: float | None
    corrected_time: float | None
    position: int | None
    adjustment_scale: float
    achieved_handicap: float | None
    performance: Performance | None
    next_tcf: float
    next_tcf_clamped: float | None = None


@dataclass(frozen=True, slots=True)
class RealignmentEntry:
    """One boat's input to end-of-series realignment (spec section 5).

    ``ending_handicap`` is the boat's TCFn after the final race of the series
    just finished.
    """

    boat_id: str
    base_number: float
    ending_handicap: float

    def __post_init__(self) -> None:
        if not self.boat_id:
            raise InvalidInput("boat_id is required")
        context = f"realignment entry for boat {self.boat_id}"
        _check_positive(self.base_number, "base_number", context)
        _check_positive(self.ending_handicap, "ending_handicap", context)


@dataclass(frozen=True, slots=True)
class RealignmentResult:
    """A boat's realigned club number (CN), the TCF it starts the next series on."""

    boat_id: str
    realigned_tcf: float
