# Slice 0: Scoring engine

## Goal
A pure Python package that scores a handicap series under NHC rules. This should be easily into any Python project.

## Scope
- Input: boats with base TCF, races with start times, finishes (time or code)
- Output: race handicap per boat per race, corrected times, race results,
  series standings with discards
- No Django, no database, no I/O

## Acceptance criteria
- All fixtures in tests/fixtures/ produce the expected results exactly
- Changing any finish and re-scoring gives correct downstream handicaps
- Non-finishers are scored per RRS Appendix A and do not have their
  handicap adjusted
- Public interface documented in the package README

## Out of scope
- Multiple starts per race (single start only for now)
- Pursuit races