"""NHC scoring engine.

A pure-Python implementation of the RYA National Handicap for Cruisers (NHC)
scoring and handicap-adjustment rules, plus RRS Appendix A series scoring.

This package deliberately depends on nothing but the standard library. It knows
nothing about Django, databases, HTTP or files, so it can be dropped into any
Python project (see ``nhc/README.md``). ``tests/test_package_purity.py``
enforces that; please keep it passing.

Source of truth for the calculations is ``docs/reference/`` - the RYA NHC
calculation spec for handicaps, and RRS Appendix A for points and standings.
Where this code and those documents disagree, the documents win.

Handicaps are carried at full precision and never rounded between races; see
the note in ``nhc/domain.py``.

The public interface is exported from here and is not yet complete; it is being
built out slice by slice against the fixtures in ``tests/fixtures/``. So far it
covers the domain types, race scoring, and club-series handicap adjustment.
Regatta adjustment, realignment and Appendix A points follow.
"""

from .domain import (
    Boat,
    Performance,
    RaceEntry,
    RaceInput,
    RaceResult,
    RaceStatus,
    RealignmentEntry,
    RealignmentResult,
    SeriesType,
)
from .errors import InvalidInput
from .handicap import adjustment_scale, compute_club_adjustment
from .scoring import corrected_time, score_race

__version__ = "0.0.0"

__all__ = [
    "Boat",
    "InvalidInput",
    "Performance",
    "RaceEntry",
    "RaceInput",
    "RaceResult",
    "RaceStatus",
    "RealignmentEntry",
    "RealignmentResult",
    "SeriesType",
    "adjustment_scale",
    "compute_club_adjustment",
    "corrected_time",
    "score_race",
]
