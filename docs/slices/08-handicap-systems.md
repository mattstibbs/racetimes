# Slice 8: Other handicap systems

**Status: superseded (2026-10-02).** Nothing was built under this number.
Its work now lives in two other slices, and nothing is left here.

## What happened to it
- **2026-09-24.** Drafted to let a series be scored under Portsmouth
  Yardstick or RYA YTC as well as NHC, then parked by the project owner
  before any code was written.
- **2026-10-02.** Portsmouth Yardstick moved to slice 24
  (`docs/slices/24-portsmouth-number-series.md`), which also introduces the
  per-series **Handicap system** setting.
- **2026-10-02.** RYA YTC, the rest of the slice, moved to slice 25
  (`docs/slices/25-rya-ytc-and-engine-rename.md`), which also renames the
  scoring engine. Its scope, proposed data model, planned worked examples
  and open questions went with it unchanged.

## What was agreed here, and still holds
- **Other handicap systems**, not other points systems. RRS A4 low point
  scoring stays the only points system.
- **Worked out by hand.** With no reference worked examples for these
  systems in the repo, examples are prepared by hand, checked by the project
  owner, and only then become fixtures in `tests/fixtures/`. The engine is
  never used to produce them.

See `docs/decisions.md` (2026-09-24 and 2026-10-02) for the reasoning.
