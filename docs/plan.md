## Slice 0 - the scoring engine as a pure Python package. **Status: complete (2026-09-23)**

Acceptance criteria, from `docs/slices/00-scoring-engine.md`:

- [x] All fixtures in `tests/fixtures/` produce the expected results exactly.
      Includes the RYA's own published worked examples, SCEN-005 (club
      adjustment) and SCEN-006 (realignment), both reproducing to 3 d.p.
- [x] Changing any finish and re-scoring gives correct downstream handicaps.
      Tested as a sweep over all fourteen timed finishes in a four-race series,
      not a single worked example - see `tests/test_recalculation.py`.
- [x] Non-finishers are scored per RRS Appendix A and do not have their
      handicap adjusted. In a club series. A regatta *does* adjust them, by
      back-calculating an elapsed time, which is what spec section 4 requires.
- [x] Public interface documented in the package README. `tests/test_readme.py`
      runs the documented example and checks its output, and asserts every
      exported name appears in the text.

`nhc/` is 1,573 lines across ten modules, with 569 tests. It imports nothing
outside the standard library and does no I/O, enforced by
`tests/test_package_purity.py`.

**One partial gap against the stated scope.** The scope line reads "races with
start times", but the engine takes elapsed seconds and leaves deriving those
from a start and a finish to the caller. Every formula in the RYA spec works in
elapsed time, and the moment a race has more than one start - explicitly out of
scope here - the caller has to decide which start applies anyway. It is the
open question on clock times in `docs/decisions.md`, and it lands naturally in
slice 1 where races gain real start times.

Known gaps, all recorded in `docs/decisions.md`: RRS A6.1 and the scoring codes
beyond FINISHED/DNC/DNS/DNF that would let it fire; A2.1's discard schedule;
and the brief's "adjusted" option for non-finishers in a club series.

No Django, no database. Plain functions that take a series' race history (boats, base handicaps, starts, finishes) and return race handicaps, corrected times, results and standings. Build it test-first against your worked examples. This is where Claude Code shines: give it the reference docs and the fixtures, tell it the tests are the spec, and let it iterate until they pass. You review the logic, not the plumbing.

## Slice 1: walking skeleton. **Status: specced (2026-09-23), not started.** Spec: `docs/slices/01-walking-skeleton.md`
A Django app with Boat, Series, Race and Finish models, admin-style forms for the race committee to enter finish times, and a results page that calls the engine. Django with HTMX would suit this well; it's server-rendered and form-heavy, with no real need for a JavaScript framework.

## Slice 2: corrections and audit. 
Editing a finish and seeing everything downstream recalculate, with a history of what changed and who changed it. Race committees will need this on day one of real use, so it's worth doing early.

## Slice 3: member self-service. 
Accounts for members, boat registration requests, and series entry. This is where auth and permissions appear, so write the role rules into the brief before starting it.

## Slice 4: notifications. 
Emailing results after a race is published.

## Slice 5: results webapp.
Another Django app (in the same project) with an HTMX page that allows a racer to easily view race results.