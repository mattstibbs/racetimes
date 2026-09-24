# Slice 8: Other handicap systems

**Status: draft. Open questions below must be answered before building.**

## Goal
Every series today is scored under the RYA's National Handicap for Cruisers
(NHC): a boat starts on its base number, and its handicap moves after every
race. Many clubs also race, or instead race, under a fixed-number system,
where a boat keeps the same number all series and nothing moves. This slice
lets the race committee choose, per series, one of three handicap systems:

- **NHC**, exactly as today, and still the default for every existing series.
- **Portsmouth Yardstick (PY)**, the RYA's fixed-number system.
- **RYA YTC** (Yacht Time Correction), the RYA's fixed-number system for
  cruisers, run with the RORC Rating Office.

Places, points, discards and standings are worked out the same way under all
three (RRS Appendix A). Only the corrected time, and whether handicaps move,
differ.

## Scope

### What the project owner asked for *(agreed with the project owner)*
- **Other handicap systems**, not other points systems. RRS A4 low point
  scoring stays the only points system.
- **Portsmouth Yardstick and RYA YTC.** IRC, ECHO and a typed-in fixed TCF
  are not in this slice.
- **Worked out by hand.** No reference documents or worked examples for
  either system exist in the repo yet. The spec is written from the
  published rules. I prepare hand-worked examples (see "Worked examples"),
  the project owner checks them, and only then do they become fixtures in
  `tests/fixtures/`, with their provenance recorded. The engine is never
  used to produce them.

### How the two systems score *(to be confirmed against reference documents)*
- **Portsmouth Yardstick:** corrected time = elapsed time × 1000 / PN, where
  PN is the boat's Portsmouth Number (for example 1072). A higher number is
  a slower boat. The number doesn't change during a series.
- **RYA YTC:** also a fixed number that doesn't change during a series.
  Secondary sources say the corrected time is elapsed time × 1000 / YTC
  number, the same as PY. That is **not yet confirmed** (open question 2),
  and the engine code for YTC waits until it is.
- **Everything else is shared with NHC:** elapsed time from the start and
  finish clock times, as today; the four codes (FINISHED, DNC, DNS, DNF);
  RRS A4, A5.2/A5.3, A7 ties, A8 standings and discards; and the slice 6
  start sheet and publishing rules.
- **Nothing moves after a race.** There is no adjustment, no minimum
  finishers threshold, no regatta adjustment and no realignment.
- **Full precision, with rounding for display only**, as NHC does today,
  unless the reference documents say to round corrected times first (open
  question 3). This decides ties, so it matters.

### Setting up a series (committee, in the admin)
- A series gains a **Handicap system** setting: NHC, Portsmouth Yardstick or
  RYA YTC. Existing series become NHC and score exactly as before.
- Settings that only mean something under NHC are refused, with a message on
  the form, when another system is chosen. This is how a minimum finishers
  threshold on a regatta is already handled: refused, not ignored silently.
  - **Series type** must be "Club series". A regatta is NHC's section 4
    adjustment. A fixed-number regatta is just a club series.
  - **Minimum finishers** must be 0.
- Changing the system of a series that has races sailed is a correction.
  It's in the change history and needs a reason (slice 2).

### Boats' numbers
- A boat gains two optional numbers: a **PY number** and a **YTC number**,
  next to its NHC base number. A boat can have any or all of them.
- A boat can only be entered in a series if it has that series' number. The
  admin refuses the entry, and approving a member's entry request refuses it
  with the reason. Changing a series' system is refused while any boat
  entered in it has no number for the new system, naming those boats.
- The scoring code checks this too. A boat with a missing number (for
  example, one cleared after it was entered) gives the "can't be scored"
  message that slice 5 already shows, instead of crashing the page (the
  "no user action should crash a page" rule).
- **Changing a number behaves like the NHC base number today.** It is
  audited, needs a reason once the boat has sailed a race under that system,
  and rescores every series that uses it, including past ones. PY numbers are
  revised every year, so the manual says to change a boat's number between
  series, not during one. Keeping each series' own copy of the number is out
  of scope (see Out of scope).
- **Members** can give both numbers when they register a boat or request a
  change to one, like the base number today. As before, nothing reaches the
  boat until the committee approves it.

### What people see
- The handicap column on every table is headed with the series' system
  ("TCF" for NHC, "PY" or "YTC" for the others), on the committee's pages,
  the public series, boat and home pages, and in the results emails.
- The series page says which system the series is scored under.
- **The boat page's "next handicap" box is NHC only.** Under PY or YTC it
  says "Sails on PY 1072 for the whole series" instead. The "More detail"
  columns about handicap adjustment (achieved handicap, performance, next
  TCF) are shown only for NHC series.
- A correction in a PY or YTC series says which places and points moved, as
  today, but never "handicaps moved", because none can.

### The engine (`nhc/`)
- It stays standard-library only, with no I/O. `tests/test_package_purity.py`
  keeps passing unchanged.
- `nhc.Series` gains a handicap system setting, NHC by default, so every
  existing caller and fixture behaves exactly as before. Every existing test
  passes unchanged.
- Under PY or YTC, each race is scored on the boat's fixed number, every
  boat's handicap for the next race is that same number, and the NHC-only
  fields of a result (adjustment scale, achieved handicap, performance) are
  left empty (None), which already means "not computed". The engine refuses
  REGATTA or a minimum finishers threshold with a fixed-number system, as it
  already refuses a threshold on a regatta.
- The corrected time is worked out the way the published formula is written
  (elapsed × 1000 / number), not by first turning the number into a TCF.
  That keeps float noise out of ties, and the fixtures can be checked
  against the formula as written.
- The package README documents the new setting, and `tests/test_readme.py`
  keeps checking that every exported name is in it.
- The package keeps its name, `nhc`. Renaming it would touch every import
  for no change in behaviour. Recorded in `docs/decisions.md`.

### Data model *(proposed; needs the project owner's approval)*
- `Series.handicap_system`: a choice of `NHC`, `PY`, `YTC`, default `NHC`.
  Its values match the engine's new enum, as `series_type` does.
- `Boat.py_number`: optional positive whole number. Portsmouth Numbers are
  whole numbers, and the RYA lists run roughly 500 to 1500 or more, so the
  model allows 1 to 9999 and the form doesn't guess tighter limits.
- `Boat.ytc_number`: optional. Its type waits on open question 2: a whole
  number if YTC uses the PY form, a decimal like the NHC base number if it
  is a TCF.
- `BoatRequest` gains the same two fields, so members can supply them.
- Audited fields (slice 2): `Series.handicap_system`, `Boat.py_number` and
  `Boat.ytc_number` join the pinned list in `races/test_audit.py`.
- One schema migration. It has no data migration: existing series default
  to NHC. It uses nothing database-specific.

### User manual
- A new committee page, "Handicap systems", covering what each system is,
  how to choose one for a series, where a boat's numbers go, and why a PY
  number is changed between series rather than during one.
- Updated pages: setting up a series, registering a boat (both the
  committee's and the member's), and "Finding your results" (the box on the
  boat page and the column heading). Screenshots are regenerated where they
  change, using a PY series in the sample data.

## Worked examples *(to be checked by the project owner before they become fixtures)*
Worked by hand with exact fractions in a calculator, not with the engine.

### PY-1: a two-race Portsmouth Yardstick series
Three boats, no discards (to keep the standings obvious), RRS A5.2.

| Boat | PN |
|---|--:|
| A | 1010 |
| B | 1072 |
| C | 935 |

**Race 1.** Everyone finishes.

| Boat | Elapsed (s) | Corrected = E × 1000 / PN | Place | Points |
|---|--:|--:|--:|--:|
| B | 4150 | 3871.269 | 1 | 1 |
| A | 3930 | 3891.089 | 2 | 2 |
| C | 3700 | 3957.219 | 3 | 3 |

C was first over the line but is third on corrected time: the fastest boat
has the highest number.

**Race 2.** A retires (DNF).

| Boat | Elapsed (s) | Corrected | Place | Points |
|---|--:|--:|--:|--:|
| B | 3800 | 3544.776 | 1 | 1 |
| C | 3500 | 3743.316 | 2 | 2 |
| A | DNF | - | - | 4 (3 entries + 1, A5.2) |

**Handicaps.** Every boat sails race 2 on the same number it sailed race 1.

**Standings.** B 2 points (1st), C 5 (2nd), A 6 (3rd).

### PY-2, YTC-1 and YTC-2 *(to be written after the open questions)*
- **PY-2:** a tie on corrected time, and a pair that differs by less than a
  second. This shows whether corrected times are rounded before comparing
  (open question 3).
- **YTC-1, YTC-2:** the same shape as PY-1 and PY-2, once the YTC formula
  and number format are confirmed (open question 2).
- **One NHC fixture re-run as a check:** every existing fixture passes
  unchanged with the new setting left at its default.

## Acceptance criteria
- Each new fixture, as checked by the project owner, is reproduced exactly
  by the engine and, loaded through the database as clock times, by the
  series page and every boat's page (as SCEN-005 is in slice 5).
- Every existing fixture and test passes unchanged, and every existing
  series scores the same after the migration.
- Under PY or YTC, no handicap moves, whatever the finishes. Tested as a
  sweep over every finish in a multi-race series, like slice 0's
  recalculation test: changing any finish changes only that race's places
  and points, and the standings.
- The engine and the series form refuse a regatta or a minimum finishers
  threshold with a fixed-number system.
- A boat without the series' number can't be entered, by the admin or by
  approving a request, and a series can't be switched to a system some of
  its boats have no number for. Both name the boats. A missing number that
  gets past both shows a message on every page, not a crash.
- Changing a series' system or a boat's number is recorded in the change
  history. It needs a reason when it is a correction, and a save that
  changes nothing records nothing.
- The handicap column is headed with the series' system everywhere, and the
  boat page shows the fixed-number sentence instead of the next-handicap
  box. Tested on each page, and checked in headless Chromium at 375 px.
- A member can give PY and YTC numbers in a boat registration or change
  request, and they reach the boat only when approved.
- `nhc/` still imports nothing outside the standard library, and its README
  documents the new setting.
- The migration uses nothing database-specific.
- The manual gains "Handicap systems" and the updated pages, with
  screenshots.

## Out of scope
- Other points systems (Bonus Point, high point); only RRS A4 low point.
- IRC, ECHO, a typed-in fixed TCF, or any system not named above.
- A series that mixes systems, or scores the same races under two systems
  at once (common at clubs as "NHC and PY results"). Easy to ask for next:
  it is two series over the same races.
- PY's personal handicaps, average-lap racing and the RYA's PY return
  forms.
- Importing the RYA's published PY or YTC lists. Numbers are typed in.
- Keeping a per-series copy of a boat's number, so a PY change mid-year
  doesn't rescore earlier series. Worth doing if the club finds it
  happening; it's a data model change.
- Multiple starts per race, and scoring codes beyond FINISHED, DNC, DNS and
  DNF.
- The brief's API and file export (user journey 5).

## Open questions *(to answer before building)*
1. **The data model.** Approve the fields above (`Series.handicap_system`,
   `Boat.py_number`, `Boat.ytc_number`, and the two request fields)?
2. **The YTC formula and number format.** I couldn't reach the RORC or RYA
   sites from here (blocked by the network proxy). Search results say
   "elapsed × 1000 / YTC number", but I'd want it from the source. Could you
   add the RYA YTC rules or FAQ (the RORC Rating Office's "YTC FAQ" PDF) and
   an example YTC certificate to `docs/reference/`?
3. **Rounding.** Does the RYA's PY guidance (and YTC's) say to round
   corrected times to the nearest second before ranking? If it does, the
   engine rounds first for these systems, and two boats a fraction of a
   second apart tie. Adding the RYA's PY scheme booklet to `docs/reference/`
   would settle it.
4. **The default for new series.** Search results also say the RYA replaced
   NHC with YTC as its supported cruiser handicap in 2025. Should a *new*
   series default to YTC instead of NHC? (Existing series stay NHC either
   way.)
5. **Worked example PY-1.** Is it right? Once it's checked, and PY-2 and the
   YTC examples are written and checked, they go into `tests/fixtures/`.
