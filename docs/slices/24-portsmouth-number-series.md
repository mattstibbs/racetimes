# Slice 24: Portsmouth Number series

**Status: part A (the engine) complete, part B (the site) in progress
(2026-10-02).** Part A is `nhc/fixed_number.py` and its shared-code moves
(PR #50); the site doesn't use it yet. The project owner
has approved the data model changes, answered every open question, and
checked worked examples PY-1 and PY-2 (see "The project owner's answers" at
the end). Nothing is left to answer.

**Changed 2026-10-02.** "The engine" was rewritten at the project owner's
request: Portsmouth Yardstick is a module of its own inside the package,
beside the NHC code, where the first draft added optional fields to the NHC
types.

## Goal
Every series today is scored under the RYA's National Handicap for Cruisers
(NHC): a boat starts on its base number, and its handicap moves after every
race. Many clubs also race a fleet on fixed Portsmouth Numbers, including
numbers the club sets itself (a gaffer or classic class, for example). This
slice lets the race committee choose, per series, between NHC and Portsmouth
Yardstick, so that such a fleet can be scored as its own series.

Places, points, discards and standings are worked out the same way under
both (RRS Appendix A). Only the corrected time, and whether handicaps move,
differ.

This is the whole of the Portsmouth Yardstick work first drafted in slice 8,
which is now superseded. Its other half, RYA YTC, is slice 25
(`docs/slices/25-rya-ytc-and-engine-rename.md`), which builds on the
handicap system setting this slice introduces. This slice doesn't
depend on slice 23 (the discard threshold and the scoring penalty), and
either can be built first.

## What's there now
- Every series is NHC. `Boat.base_number` (the NHC base number) is required.
- A fleet with its own start time, course and results is already a separate
  series: a race belongs to one series and has one start time.

## The rule
Portsmouth Yardstick (PY) is the RYA's fixed-number system. A boat races on
a Portsmouth Number (PN): a whole number (1072, for example), higher for a
slower boat.

- **Corrected time = elapsed time x 1000 / PN.** This is the scheme's
  published formula. The reference document in the repo doesn't state it;
  the project owner decided to build on it.
- **The number is fixed.** Nothing moves after a race: there is no
  adjustment, no minimum-finisher threshold, no regatta adjustment and no
  realignment.
- **Everything else is shared with NHC:** elapsed time from the start and
  finish clock times, as today; the same codes (FINISHED, DNC, DNS, DNF,
  and slice 23's scoring penalty, if that is built); RRS A4, A5.2 and A5.3,
  A7 ties, A8 standings and discards (with slice 23's threshold, if that is
  built); and the start sheet and publishing rules.
- **Full precision, with rounding for display only**, as NHC does today
  (the project owner's decision, since the reference document is silent).
  This decides ties: two boats a fraction of a second apart are not tied,
  even when the pages show them the same corrected time. See PY-2.
- A club may use the RYA's published numbers or set its own for boats the
  RYA doesn't list. Either way the number is typed in.

**Worked out by hand.** No worked example for PY is in the repo. The worked
examples below were prepared by hand and checked by the project owner, and
only then do they become fixtures in `tests/fixtures/`, with their provenance
recorded. The engine is never used to produce them.

## The reference document
`docs/reference/PY_Notice_of_Race_and_Sailing_Instructions_Advice.pdf`: the
RYA Portsmouth Yardstick Scheme's sample wording for a notice of race. It
is guidance for organisers, not binding, and it is about how an event says
it uses PY, not how PY is calculated. What it says that matters here:

- **Which numbers.** An event uses the RYA's national list, or its own list,
  and gives a class that isn't listed a trial number. So numbers typed in by
  the committee, including the club's own, are what the scheme expects.
- **Changing a number during an event.** The notice of race chooses one of
  two rules: "PN's shall not be adjusted for the duration of the event", or
  the race committee may adjust a number, in which case the adjustment
  "shall apply to all subsequent races" and "shall not be retrospectively
  applied to finished races". The site can only do the first (see "A
  number that changes during a series").
- **A different configuration.** A notice of race may let a boat race under
  a different configuration, on a different PN, for the rest of a series,
  again from that race on and not retrospectively. The site holds one PN for
  a boat.
- **Fleets split by PN** ("PY 1" up to 700, "PY 2" from 701 to 1000, and so
  on) are an option for a big entry. On the site, each fleet is its own
  series (see below).
- **It doesn't give the formula** for a corrected time, and says nothing
  about rounding one.

## A PN fleet is its own series
A class with its own start time, course and prize list (a gaffer or classic
class racing alongside the cruisers, for example) already has to be a
separate series: a race belongs to one series and has one start time. So a
club racing an NHC fleet and a PN fleet on the same day sets up two series
with races on the same dates. No "fleets within a race" are needed.

## Setting up a series (committee, in the race office and the admin)
- A series gains a **Handicap system** setting: NHC or Portsmouth Yardstick.
  Existing series become NHC and score exactly as before, and NHC is the
  default for a new series.
- Settings that only mean something under NHC are refused, with a message on
  the form, when Portsmouth Yardstick is chosen. This is how a minimum
  finishers threshold on a regatta is already handled: refused, not ignored
  silently.
  - **Series type** must be "Club series". A regatta is NHC's section 4
    adjustment. A fixed-number regatta is just a club series.
  - **Minimum finishers** must be 0.
  - **Cap extreme results** and **Realign to base handicaps** must be off.
- Changing the system of a series that has races sailed is a correction.
  It's in the change history and needs a reason (slice 2).
- The rules live in `races/office_forms.SeriesForm`, which the race office
  and the admin already share.

## Boats' numbers
- A boat gains an optional **PN**, next to its NHC base number.
- **The NHC base number becomes optional.** A boat that
  only ever races on a PN has no NHC base number, and typing a made-up one
  in to get past the form would put a false number on the boat's page. A
  boat needs at least the number of each series it is entered in.
- A boat can only be entered in a series if it has that series' number. The
  race office and the admin refuse the entry, and approving a member's entry
  request refuses it with the reason. Changing a series' system is refused
  while any boat entered in it has no number for the new system, naming
  those boats. Clearing a number is refused while the boat is entered in a
  series that uses it.
- The scoring code checks this too. A boat with a missing number gives the
  "can't be scored" message the results pages already show, instead of
  crashing the page (the "no user action should crash a page" rule).
- **Changing a PN behaves like changing the NHC base number today.** It is
  audited, needs a reason once the boat has sailed a race under that system,
  and rescores every series that uses it, including past ones that aren't
  final. Portsmouth Numbers are revised every year, so the manual says to
  change a boat's number between series, not during one. Keeping each
  series' own copy of the number is out of scope.
- **Members** can give a PN when they register a boat or request a change to
  one, like the base number today. As before, nothing reaches the boat until
  the committee approves it.

## A number that changes during a series *(the project owner's decision, 2026-10-02)*
The reference document's sample wording lets a notice of race allow a PN to
change during a series, for later races only: the committee adjusts it, or
the boat changes configuration, and finished races keep the old number. The
site can't do that. A boat has one PN, and changing it rescores every race
she has sailed in any series that isn't final.

This is out of scope, as it is for YTC's temporary numbers in slice 25. The
manual says so plainly: the site suits a notice of race that says "PN's
shall not be adjusted for the duration of the event"; a number is changed
between series; and if it is changed during one, the boat's earlier races in
that series are rescored on the new number. A committee that needs the
earlier results to stand waits until the series is declared final before
changing it. Supporting "from this race on" needs a number per race, or
numbers with dates, for both systems, and would be a slice of its own.

## What people see
- The handicap column on every table is headed with the series' system
  ("TCF" for NHC, "PN" for Portsmouth Yardstick): on the committee's pages
  (the race day page, the race office and a series' history), the public
  home, series and boat pages, the results emails and the CSV.
- The series page says which system the series is scored under.
- **The boat page's "next handicap" box is NHC only.** Under Portsmouth
  Yardstick it says "Sails on PN 1072 for the whole series" instead. The
  "More detail" columns about handicap adjustment (achieved handicap,
  performance, next TCF) are shown only for NHC series.
- A correction in a Portsmouth Yardstick series says which places and points
  moved, as today, but never "handicaps moved", because none can.

## The engine (`nhc/`)
Portsmouth Yardstick goes into the same package as NHC, in a module of its
own beside the NHC code. It is not threaded through the NHC types as a
setting. (Changed 2026-10-02 at the project owner's request; the first draft
added optional fields to `nhc.Boat` and `nhc.Series`. See
`docs/decisions.md`.)

### The three parts of the package after this slice
| Part | Modules | Used by |
|---|---|---|
| NHC: handicaps that move | `handicap.py`, `regatta.py`, `options.py`, `realignment.py`, `series.py` | NHC series |
| Fixed-number systems | `fixed_number.py` (new) | Portsmouth Yardstick series, and RYA YTC in slice 25 |
| Shared: RRS Appendix A and the common types | `scoring.py` (ranking), `points.py`, `standings.py`, `domain.py`, `errors.py` | Both |

The fixed-number module and the NHC modules don't import each other. Each
calls the shared code.

### The NHC calculation doesn't change
- `nhc.Boat`, `nhc.Series`, `nhc.RaceEntry` and `nhc.RaceResult` gain no
  field, and lose none. A boat in an NHC series still must have a base
  number, checked when the boat is built, as today.
- `score_series` and everything it calls behave exactly as before. Every
  existing fixture and test passes unchanged.
- The only edits to existing engine code are the three small moves under
  "What the two kinds of series share", which change where code lives and
  not what it does.

### The new module, `nhc/fixed_number.py`
It has its own small input and output types, so nothing about a fixed-number
series is "an NHC field left empty":

- **`FixedNumberSystem`**: which system's formula to use. One value, `PY`,
  in this slice. Slice 25 adds `YTC`.
- **`FixedNumberBoat(boat_id, number, name="")`**: `number` is required and
  must be a positive, finite number, checked when the boat is built. The
  engine doesn't insist it is whole, since the formula works for any
  positive number; the site's own form does (see Data model).
- **`FixedNumberSeries(boats, races, system, apply_a5_3=False,
  discards=1)`**: `races` are the same `SeriesRace` and `Finish` an NHC
  series uses, which already carry no handicap. It has no series type,
  progression, minimum finishers, capping or realignment, because a
  fixed-number series has none. (It also takes slice 23's discard threshold,
  if that is built.)
- **`score_fixed_number_series(series)`** returns a `FixedNumberOutcome`:
  the system, each race's results and the standings.
- **`FixedNumberResult`**: one boat in one race, with `boat_id`, `status`,
  `number` (the number she raced on), `elapsed_seconds`, `corrected_time`,
  `position` and `points`. It has no next handicap, achieved handicap,
  performance or adjustment scale. (It also carries slice 23's scoring
  penalty fields, if that is built.)
- **`fixed_number_corrected_time(elapsed_seconds, number, system)`**: the
  published formula, as written. For `PY`, elapsed x 1000 / number, not the
  number turned into a TCF first. That keeps float noise out of ties, and
  the fixtures can be checked against the formula as written.

How a race is scored: each finisher's corrected time comes from the formula
and her number; the fleet is ranked on it; a boat with no recorded finish is
scored DNC (RRS A2.2), as in an NHC series. The same number is used in every
race. Nothing is fed forward from one race to the next.

Corrected times are not rounded before ranking. If a later system needs
them rounded, the rounding goes in this module, for that system, and the NHC
calculation is untouched.

### What the two kinds of series share
- **Ranking** (RRS A3 and A7): the code that turns corrected times into
  places, with equal times sharing a place, is the one NHC uses today. It is
  a private helper in `scoring.py` now, and gets a public name so the new
  module can call it.
- **A race's finishes and a race's results** (`SeriesRace`, `RaceOutcome`):
  neither carries a handicap, so both kinds of series use them. They move
  from `series.py` to `domain.py`, so the new module needn't import the NHC
  replay to reach them. They are still exported from the package under the
  same names, so no caller changes.
- **Points** (`score_points`) and **standings** (`compute_standings`): used
  as they are. They read only a result's boat, status, place and points, so
  they work on either kind of result. Their type hints widen to say so;
  their behaviour doesn't change.
- **The checks every series needs** (at least one boat, no boat or race
  twice, no finish for a boat that isn't entered, no negative discards)
  move from `nhc.Series` into one helper in `domain.py` that both kinds of
  series call. The NHC messages and behaviour don't change.
- So anything added to Appendix A scoring, such as slice 23's discard
  threshold and scoring penalty, works for both without being written twice.

### What the site's bridge does (`races/scoring.py`)
- It chooses by the series' handicap system: an NHC series is built and
  scored as today, a PY series as a `FixedNumberSeries`.
- A boat with no number for its series can't be built (the engine raises
  `InvalidInput`), which the results pages already turn into the "can't be
  scored" message.
- The NHC-only settings can't reach a fixed-number series, because it has
  nowhere to put them. The series form refuses them. If a row gets past the
  form with one set, the results pages show the "can't be scored" message;
  they never show results that quietly ignore the setting.
- It gives the templates one place to read "the handicap this boat raced
  on" (a TCF or a PN), so they don't reach into either engine type.
- A final series' stored copy (`races/final.py`) records which kind of
  outcome it holds, and is rebuilt as that kind.

### Kept as now
- Standard-library only, with no I/O. `tests/test_package_purity.py` keeps
  passing unchanged, and covers the new module.
- The package README documents every new name, and `tests/test_readme.py`
  keeps checking that every exported name is in it.
- The package keeps its name, `nhc`, in this slice. It is renamed
  `sailscoring` in slice 25, in a pull request of its own, so this slice's
  changes aren't mixed with a rename of every import.

## Data model *(approved 2026-10-02)*
- `Series.handicap_system`: a choice of `NHC` or `PY`, default `NHC`. `PY`
  matches the engine's `FixedNumberSystem.PY`. `NHC` has no engine value: it
  means the series is scored by the NHC functions.
- `Boat.py_number`: optional positive whole number. Portsmouth Numbers are
  whole numbers, and the RYA lists run roughly 500 to 1500 or more, so the
  model allows 1 to 9999 and the form doesn't guess tighter limits.
- `Boat.base_number`: becomes optional.
- `BoatRequest.py_number`, so members can supply it, and
  `BoatRequest.base_number` optional to match.
- Audited fields (slice 2): `Series.handicap_system` and `Boat.py_number`
  join the pinned list in `races/test_audit.py`.
- A final series' stored results (`Series.final_results`) record the system
  and, for a PY series, the number each boat raced on. Results stored before
  this slice name no system, and load as NHC.
- One schema migration. It has no data migration: existing series default
  to NHC and every existing boat keeps its base number. It uses nothing
  database-specific.

## User manual
- A new committee page, "Handicap systems", covering what each system is,
  how to choose one for a series, where a boat's numbers go, why a PN is
  changed between series rather than during one (and what happens if it is
  changed during one), and how to run a PN fleet as its own series alongside
  an NHC one.
- Updated pages: setting up a series, registering a boat (both the
  committee's and the member's), "How results are worked out", and "Finding
  your results" (the box on the boat page and the column heading).
  Screenshots are regenerated where they change, using a PN series in the
  sample data.

## Worked examples *(checked by the project owner, 2026-10-02)*
Worked by hand with exact fractions in a calculator, not with the engine.

### PY-1: a two-race Portsmouth Yardstick series
Three boats, no discards (to keep the standings obvious), RRS A5.2.

| Boat | PN |
|---|--:|
| A | 1010 |
| B | 1072 |
| C | 935 |

**Race 1.** Everyone finishes.

| Boat | Elapsed (s) | Corrected = E x 1000 / PN | Place | Points |
|---|--:|--:|--:|--:|
| B | 4150 | 3871.269 | 1 | 1 |
| A | 3930 | 3891.089 | 2 | 2 |
| C | 3700 | 3957.219 | 3 | 3 |

C was first over the line but is third on corrected time: the fastest boat
has the lowest number.

**Race 2.** A retires (DNF).

| Boat | Elapsed (s) | Corrected | Place | Points |
|---|--:|--:|--:|--:|
| B | 3800 | 3544.776 | 1 | 1 |
| C | 3500 | 3743.316 | 2 | 2 |
| A | DNF | - | - | 4 (3 entries + 1, A5.2) |

**Handicaps.** Every boat sails race 2 on the same number it sailed race 1.

**Standings.** B 2 points (1st), C 5 (2nd), A 6 (3rd).

### PY-2: a tie, and a near miss
One race, four boats entered, no discards, RRS A5.2. Everyone finishes.

| Boat | PN | Elapsed (s) | Corrected = E x 1000 / PN | Shown as | Place | Points |
|---|--:|--:|--:|--:|--:|--:|
| D | 960 | 3840 | 4000.000 | 1:06:40 | 1= | 1.5 |
| E | 1100 | 4400 | 4000.000 | 1:06:40 | 1= | 1.5 |
| F | 1010 | 4131 | 4090.099 | 1:08:10 | 3 | 3 |
| G | 1072 | 4385 | 4090.485 | 1:08:10 | 4 | 4 |

- **D and E tie.** Their corrected times are exactly equal, so under RRS A7
  they share the points for first and second: (1 + 2) / 2 = 1.5 each. The
  next boat is third, not second.
- **F and G don't.** Their corrected times are 0.386 of a second apart. The
  pages round both to 1:08:10, but places are decided on the full value, so
  F is third and G fourth. This is the owner's decision on rounding: full
  precision, rounded for display only.

**Standings.** D and E are level on 1.5 points. RRS A8.1 and A8.2 can't
separate them, because each has only that one score, so they share first
place. F is third on 3 points and G fourth on 4.

### An NHC fixture re-run as a check
Every existing fixture passes unchanged with the new setting left at its
default.

## Acceptance criteria
- Each fixture, as checked by the project owner, is reproduced exactly by
  the engine and, loaded through the database as clock times, by the series
  page and every boat's page (as SCEN-005 is in slice 5). No fixture is
  produced from the engine's output.
- Every existing fixture and test passes unchanged, and every existing
  series scores the same after the migration.
- Under PN no handicap moves, whatever the finishes. Tested as a sweep over
  every finish in a multi-race series, like slice 0's recalculation test:
  changing any finish changes only that race's places and points, and the
  standings.
- The series form refuses a regatta, a minimum finishers threshold, capping
  or realignment on a PN series. The engine's fixed-number series has no
  such settings, and a row that gets past the form with one set shows the
  "can't be scored" message.
- The NHC types (`nhc.Boat`, `nhc.Series`, `nhc.RaceEntry`,
  `nhc.RaceResult`) have the same fields as before this slice.
- `nhc/fixed_number.py` imports nothing from the NHC modules
  (`handicap.py`, `regatta.py`, `options.py`, `realignment.py`,
  `series.py`), and they import nothing from it. A test checks both
  directions, as `tests/test_package_purity.py` checks the package's
  imports.
- The checks every series shares give the same messages for an NHC series
  as before, and the same for a fixed-number series.
- A boat without the series' number can't be entered, by the race office,
  the admin or approving a request, and a series can't be switched to a
  system some of its boats have no number for. Both name the boats. A
  missing number that gets past both shows a message on every page, not a
  crash.
- Changing a series' system or a boat's PN is recorded in the change
  history, and both fields are in the pinned list of audited fields. It
  needs a reason when it is a correction, and a save that changes nothing
  records nothing.
- A final series is locked against both, and a series declared final before
  this slice still shows its stored results.
- The handicap column is headed with the series' system everywhere, and the
  boat page shows the fixed-number sentence instead of the next-handicap
  box. Tested on each page, in the emails and in the CSV, and checked in
  headless Chromium at 375 px.
- A correction in a PN series never says handicaps moved.
- A member can give a PN in a boat registration or change request, and it
  reaches the boat only when approved.
- `nhc/` still imports nothing outside the standard library, and its README
  documents every new name.
- The migration uses nothing database-specific (SQLite and PostgreSQL).
- The manual gains "Handicap systems" and the updated pages, with
  screenshots.

## Out of scope
- **Other points systems** (Bonus Point, high point). RRS A4 low point
  stays the only one.
- **RYA YTC, IRC, ECHO, a typed-in fixed TCF, and any other handicap
  system.** YTC is slice 25.
- **A series that mixes systems, or scores the same races under two systems
  at once** (common at clubs as "NHC and PY results"). Easy to ask for
  next: it is two series over the same races.
- **PN adjustments:** Portsmouth Yardstick's personal handicaps, or a club
  number that moves after each race by a formula. Also average-lap racing
  and the RYA's PY return forms.
- **Rounding corrected times before ranking.**
- **A PN that changes during a series for later races only**, whether the
  committee adjusts it or the boat changes configuration. See "A number that
  changes during a series".
- **Importing the RYA's published PN list.** Numbers are typed in.
- **Two fleets scored together, or two starts in one race** (a second
  division starting later and scored with the first).
- **A per-series copy of a boat's number**, so a PN change mid-year doesn't
  rescore earlier series. Worth doing if a club finds it happening; it's a
  data model change.
- **Scoring codes beyond those already built.**
- The brief's API and file export (user journey 5).

## The project owner's answers *(2026-10-02)*
- **The data model: approved.** `Series.handicap_system`,
  `Boat.py_number`, `BoatRequest.py_number`, and `Boat.base_number` and
  `BoatRequest.base_number` becoming optional.
- **The NHC base number becomes optional**, so a boat that only races on a
  PN doesn't need an invented one.
- **No rounding before ranking.** Corrected times are compared at full
  precision and rounded only for display, as NHC. The reference document is
  silent on it.
- **In the engine, Portsmouth Yardstick is a module of its own** beside the
  NHC code (see "The engine").

## Answered after the reference document was added *(2026-10-02)*
- **The formula.** The reference document doesn't state it. The slice is
  built on corrected time = elapsed x 1000 / PN, the scheme's published
  formula and the same form the RYA YTC document gives for YTC (its section
  6.2).
- **A number that changes during a series** is out of scope, with a note in
  the manual, as for YTC's temporary numbers.

## The worked examples *(checked 2026-10-02)*
The project owner checked PY-1 and PY-2 and found them right. They go into
`tests/fixtures/` as written above when the slice is built.

Worked by hand, not with the engine; the arithmetic was re-checked with
plain Python (no engine code). The project owner checked and approved
them on 2026-10-02. That is the provenance to record in the fixture file.
