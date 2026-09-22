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

The public interface is exported from here and is not yet complete; it is being
built out slice by slice against the fixtures in ``tests/fixtures/``.
"""

__version__ = "0.0.0"

__all__: list[str] = []
