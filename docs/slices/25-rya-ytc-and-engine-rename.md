# Slice 25: RYA YTC series, and renaming the scoring engine

**Status: complete (2026-10-02). Part A (the rename) is PR #52
and part B (RYA YTC) is PR #53.**
Part B is the RYA YTC work moved here from slice 8, which was parked by the
project owner on 2026-09-24 and is now superseded. Its reference document is
in `docs/reference/`, and the owner has answered its questions, approved its
data model changes and checked worked examples YTC-1 and YTC-2 (see "The
project owner's answers" at the end). Nothing is left to answer.

## Goal
Two pieces of work, each its own pull request:

- **A. Rename the scoring engine.** The package is called `nhc`, after the
  one handicap system it scored when it was written. After slice 24 it also
  scores Portsmouth Yardstick, and part B adds a third system, so the name
  no longer says what the package does. Part A renames it `sailscoring`. It
  changes no behaviour.
- **B. RYA YTC series.** After slice 24, a series is scored under NHC, where
  a boat's handicap moves after every race, or under Portsmouth Yardstick, a
  fixed-number system. Part B adds a third choice: **RYA YTC** (Yacht Time
  Correction), the RYA's fixed-number system for cruisers, run with the RORC
  Rating Office.

**Order.** This slice is built after slice 24, which introduces the
per-series **Handicap system** setting that part B adds a choice to. Part A
goes first.

## What's there now
- The engine is one package, `nhc/`, standard-library only, with its tests
  in `tests/`. It holds the NHC handicap rules, and the RRS Appendix A
  points and standings that every handicap system shares.
- The app imports it in two modules (`races/scoring.py` and
  `races/final.py`) and one test module. The engine's own tests import it in
  about a dozen files.
- Nothing stored in the database carries the package's name. A final
  series' stored results (`Series.final_results`) hold field names and
  values only.

---

## Part A: rename the scoring engine

### One engine, not one library per system
Slice 0 asked for "a pure Python package that scores a handicap series under
NHC rules", with no Django, no database and no I/O. Portsmouth Yardstick and
YTC go into the same package, not into libraries of their own, because about
half of it isn't NHC at all: places, points, ties, discards and standings
are RRS Appendix A, and every system needs them unchanged. A library per
system would either copy those rules, or depend on a third shared library.
See `docs/decisions.md`.

The independence slice 0 promised is not about the name: it is that the
package imports nothing outside the standard library and does no I/O. That
promise is kept, and is still enforced by a test and by CI.

### What gets built
- **The package directory `nhc/` becomes `sailscoring/`** (with `git mv`,
  so its history follows), and every import changes with it (`import
  sailscoring`):
  - the app: `races/scoring.py`, `races/final.py` and
    `races/test_nhc_series_options.py`;
  - the engine's tests in `tests/`, including `tests/scenario_loader.py`;
  - `tests/test_package_purity.py` and `tests/test_readme.py`, which name
    the package's folder;
  - `pyproject.toml` (Ruff's Python 3.11 target for the package);
  - `.github/workflows/ci.yml` (the job that imports the package with
    nothing installed).
- **No `nhc` name is left behind** as an alias. Nothing outside this
  repository is known to import it.
- **The public interface doesn't change.** Every exported name (`Series`,
  `score_series`, `Boat` and the rest) keeps its name and its behaviour.
  Only the name they are imported from changes.
- **The package README and docstrings** are reworded to describe an engine
  for handicap series under several systems, with NHC as one of them.
- **Current documents** are updated: `CLAUDE.md`, the repository
  `README.md`, the note in `requirements-dev.txt`, and code comments that
  point at `nhc/...` files.
- **History is left as written.** Completed slice specs and past entries in
  `docs/decisions.md` say `nhc`, which is what the package was called then.
  A new decisions entry records the rename.

### What keeps the name NHC
"NHC" stays wherever it means the RYA's scheme, not the package:

- the series settings `Series.nhc_cap_extremes` and
  `Series.nhc_realign_to_base`, and their migration;
- the fixtures `tests/fixtures/nhc_test_scenarios.yaml` and
  `mcc_full_nhc_method.yaml`;
- the test modules `tests/test_nhc_options.py` and
  `races/test_nhc_series_options.py`;
- `docs/reference/RYA_nhc_calculation_spec.md`;
- every mention of NHC on the site, in emails and in the manual.

### Data model
None. No migration.

---

## Part B: RYA YTC series

### What the project owner asked for *(agreed with the project owner, slice 8)*
- **Other handicap systems**, not other points systems. RRS A4 low point
  scoring stays the only points system.
- **RYA YTC.** IRC, ECHO and a typed-in fixed TCF are not in this slice.
- **Worked out by hand.** The reference document has the formula but no
  worked race. The hand-worked examples (see "Worked examples") were
  checked by the project owner, and only then do they become fixtures in
  `tests/fixtures/`, with their provenance recorded. The engine is never
  used to produce them.

### The reference document
`docs/reference/RYA-YTC-Policy-and-Procedures-2026.pdf` (RYA YTC, powered by
the RORC Rating Office: 2026 Policy and Procedures, valid from 1 January
2026, version 1). The project owner first added the 2024 edition and then
replaced it with this one. Nothing below differs between the two: the 2026
changes are to how the Rating Office works out a number (a long keel
factor, a bow thruster allowance, which boats can have a certificate), and
the site only ever has the number typed in.

What it says that matters here:

- **The formula** (section 6.2): Corrected Time = Elapsed Time x 1000 / YTC.
- **A YTC number is a whole number.** The example certificate (Appendix C,
  still the 2024 certificate in the 2026 edition) shows 873.
- **A certificate carries two numbers:** "YTC Rating" (873 in the example)
  and "Non Spinnaker YTC Rating (White Sail)" (899). A boat racing without a
  spinnaker or other downwind sail gets an allowance (section 7.2), so her
  number is higher and her corrected time lower.
- **A club may set its own numbers for club racing** (sections 1.4 and
  4.4): the certificate's number is "the basic number for club events", and
  a club's handicapping team may adjust it as it sees fit.
- **A certificate lasts a calendar year**, and a new one replaces the old
  (section 3.4). A boat's number can therefore change between seasons, or
  during one if the boat's data change (section 2.3).
- **A temporary number's results aren't altered retrospectively** (section
  4.6). The site doesn't do this: see "Temporary numbers" below.
- **It says nothing about rounding** corrected times.

### How YTC scores
- **A fixed number** that doesn't change during a series: corrected time =
  elapsed time x 1000 / YTC number.
- **Everything else is shared with the other systems:** elapsed time from
  the start and finish clock times; the same codes; RRS A4, A5.2/A5.3, A7
  ties, A8 standings and discards; and the slice 6 start sheet and
  publishing rules.
- **Nothing moves after a race.** There is no adjustment, no minimum
  finishers threshold, no regatta adjustment and no realignment.
- **Full precision, with rounding for display only**, as NHC does today
  (the project owner's decision, since the reference document is silent).
  This decides ties: two boats a fraction of a second apart are not tied,
  even when the pages show them the same corrected time. See YTC-2.

### Setting up a series
- The **Handicap system** setting from slice 24 gains a third choice, RYA
  YTC.
- A YTC series refuses the NHC-only settings exactly as a fixed-number
  series does there: series type must be "Club series", minimum finishers
  must be 0, and the optional NHC steps must be off.
- Changing a series' system once races are sailed is a correction, as there.
- **NHC stays the default** for a new series. The committee chooses YTC
  series by series.

### A boat's two YTC numbers *(the project owner's decision, 2026-10-02)*
- A boat gains two optional numbers, next to its other numbers: a **YTC
  number** and a **non-spinnaker YTC number**. They are the two on her
  certificate, or the club's own adjusted numbers. A boat can have either,
  both or neither.
- Both are typed in, as whole numbers. The site doesn't work one out from
  the other: the allowance depends on the boat's sails (section 7.2), and
  the certificate already states both.
- **Changing a number behaves like changing a Portsmouth Number in slice
  24.** It is audited, needs a reason once the boat has raced on *that*
  number, and rescores every series where she is entered on it, including
  past ones that aren't final.
- **Clearing a number** is refused while the boat is entered on it in a
  series.
- **Members** can give both numbers when they register a boat or request a
  change to one. As before, nothing reaches the boat until the committee
  approves it.

### Choosing the number on a series entry *(the project owner's decision, 2026-10-02)*
Which of her two numbers a boat races on is chosen when she is entered in a
YTC series, and belongs to that entry. So the same boat can be on her YTC
number in one series and her non-spinnaker number in another, at the same
time.

- **In the race office**, the page that enters boats in a YTC series asks,
  for each boat, which number she races on. It offers only the numbers the
  boat has. A boat with one number is entered on it, and a boat with neither
  can't be entered: the page says which boats and why.
- **A member's entry request** for a YTC series asks the same question, and
  the committee sees the answer on the Change requests page. Approving it is
  refused, with the reason, if the boat no longer has that number.
- **The choice is for the whole series.** It can't differ from race to race
  (see Out of scope).
- **Changing it** is done on the series' page in the race office, per entry.
  It rescores every race the boat has sailed in that series, so it is in the
  change history, and needs a reason once the series has results, like any
  other correction. A final series is locked.
- **Switching a series to YTC** puts each boat already entered on her YTC
  number, or on her non-spinnaker number if that is the only one she has. It
  is refused while any boat entered has neither, naming those boats.
- **Outside a YTC series the choice means nothing.** It isn't shown, and it
  is reset when a series is switched away from YTC.
- The scoring code checks too: an entry whose boat has no such number (one
  that got past the forms) gives the "can't be scored" message, not a crash.

### Temporary numbers *(the project owner's decision, 2026-10-02)*
The reference document says a temporary YTC number, issued while a boat's
real one is worked out, "shall not be altered; also, any results using this
number shall not be altered retrospectively" (section 4.6). The site can't
do that during a series: a boat has one number of each kind, and changing it
rescores every race she has sailed on it in any series that isn't final.

This is out of scope, and the manual says so plainly: if a boat's temporary
number is replaced part-way through a series, her earlier races in that
series are rescored on the new number. A committee that needs the earlier
results to stand keeps the temporary number until the series is declared
final, and changes it afterwards. Honouring section 4.6 properly needs a
number per race, or numbers with dates, which is a further data model
change.

### What people see
- The handicap column is headed "YTC" in a YTC series, everywhere slice 24
  heads it for the series' system, and shows the number the boat raced on.
- **A boat on her non-spinnaker number is marked "NS"** beside that number,
  with a line under the table saying what it means. This is on the public
  series, race and boat pages, the results emails and the CSV, and in the
  race office's list of a series' entries.
- **The race day page marks her too**, on the Start sheet and the Finishing
  view, so the committee on the water knows which boats shouldn't be flying
  a spinnaker.
- The series page names the system, and the boat page shows the
  fixed-number sentence in place of the next-handicap box: "Sails on YTC 873
  for the whole series", or "Sails on her non-spinnaker YTC 899 for the
  whole series".
- A member's My boats page shows both numbers.
- The WhatsApp messages show no handicaps, so they don't change.

### The engine (`sailscoring/`)
- It stays standard-library only, with no I/O.
- YTC is another fixed-number system, so it goes into the module slice 24
  adds for them (`fixed_number.py`), and touches nothing in the NHC code:
  - `FixedNumberSystem` gains `YTC`.
  - `fixed_number_corrected_time` gains YTC's formula, worked out the way
    section 6.2 writes it: elapsed x 1000 / number.
  - Corrected times are not rounded before ranking.
- **The engine knows nothing about spinnakers.** `FixedNumberBoat`,
  `FixedNumberSeries` and `FixedNumberResult` need no new field: a boat's
  `number` is whichever of her two numbers her entry chose, and the site's
  bridge (`races/scoring.py`) is what picks it.
- Ranking, points and standings are the shared Appendix A code, unchanged.
- The package README documents the new choice.

### Data model *(approved 2026-10-02)*
- `Series.handicap_system` gains the choice `YTC`. `NHC` stays the default.
- `Boat.ytc_number` and `Boat.ytc_number_non_spinnaker`: each an optional
  positive whole number, 1 to 9999, like a Portsmouth Number in slice 24.
- `SeriesEntry.ytc_number_used`: a choice of `SPINNAKER` (the default) or
  `NON_SPINNAKER`. This is the first setting a series entry has had.
- `BoatRequest` gains both numbers, and `EntryRequest` gains
  `ytc_number_used`, so members can supply them.
- Audited fields (slice 2): the two boat numbers and
  `SeriesEntry.ytc_number_used` join the pinned list in
  `races/test_audit.py`.
- A final series needs nothing new stored. Its stored results already hold
  the number each boat raced on (slice 24), and its entries are locked, so
  "NS" is still read from the entry.
- The club's data export and a person's own data download include the new
  fields.
- One schema migration. It has no data migration: every existing entry
  takes the default, which means nothing outside a YTC series. It uses
  nothing database-specific.

### User manual
- The committee's "Handicap systems" page (new in slice 24) gains RYA YTC:
  the two numbers on a certificate, where they go on a boat, that a club may
  set its own, and what happens when a temporary number is replaced during a
  series.
- Updated pages: setting up a series, entering boats in a series (the choice
  of number), registering a boat and entering a series (both the
  committee's and the member's), the race day page ("NS"), and "Finding
  your results". Screenshots are regenerated where they change.

### Worked examples *(checked by the project owner, 2026-10-02)*
Worked by hand from the formula in section 6.2 of the reference document,
corrected time = elapsed x 1000 / YTC number, not with the engine. Corrected
times are shown to three decimal places; places are decided on the full
value.

#### YTC-1: a two-race series, with one boat on her non-spinnaker number
Three boats entered, no discards (to keep the standings obvious), RRS A5.2
(a boat that doesn't finish scores 4).

| Boat | YTC number | Non-spinnaker YTC number | Entered on | Races on |
|---|--:|--:|---|--:|
| A | 873 | 899 | her non-spinnaker number | 899 |
| B | 940 | none | her YTC number | 940 |
| C | 1010 | none | her YTC number | 1010 |

A's two numbers are the ones on the reference document's example
certificate.

**Race 1.** Everyone finishes.

| Boat | Elapsed (s) | Number | Corrected = E x 1000 / number | Place | Points |
|---|--:|--:|--:|--:|--:|
| A | 3600 | 899 | 4004.449 | 1 | 1 |
| C | 4080 | 1010 | 4039.604 | 2 | 2 |
| B | 3820 | 940 | 4063.830 | 3 | 3 |

**Race 2.** B retires (DNF).

| Boat | Elapsed (s) | Number | Corrected | Place | Points |
|---|--:|--:|--:|--:|--:|
| A | 3500 | 899 | 3893.215 | 1 | 1 |
| C | 3980 | 1010 | 3940.594 | 2 | 2 |
| B | DNF | 940 | - | - | 4 (3 entries + 1, A5.2) |

**Numbers.** Every boat sails race 2 on the number she sailed race 1.

**Standings.** A 2 points (1st), C 4 (2nd), B 7 (3rd).

**The same series with A entered on her YTC number, 873.** Only A's
corrected times change: 3600 x 1000 / 873 = 4123.711 in race 1, and
3500 x 1000 / 873 = 4009.164 in race 2.

| Boat | Race 1 | Race 2 | Total | Place |
|---|--:|--:|--:|--:|
| C | 1st: 1 | 1st: 1 | 2 | 1 |
| A | 3rd: 3 | 2nd: 2 | 5 | 2 |
| B | 2nd: 2 | DNF: 4 | 6 | 3 |

So which number A's entry chooses decides the series: she wins it on 899 and
is second on 873. A test that loads this example through the database, with
both numbers on the boat, proves the site scores her on the number her entry
chose, and that changing the entry's choice gives the second table.

#### YTC-2: a tie, and a near miss
One race, four boats entered, no discards, RRS A5.2. Everyone finishes. All
four are entered on their YTC numbers.

| Boat | YTC number | Elapsed (s) | Corrected = E x 1000 / number | Shown as | Place | Points |
|---|--:|--:|--:|--:|--:|--:|
| D | 900 | 3600 | 4000.000 | 1:06:40 | 1= | 1.5 |
| E | 950 | 3800 | 4000.000 | 1:06:40 | 1= | 1.5 |
| F | 1010 | 4190 | 4148.515 | 1:09:09 | 3 | 3 |
| G | 940 | 3900 | 4148.936 | 1:09:09 | 4 | 4 |

- **D and E tie.** Their corrected times are exactly equal, so under RRS A7
  they share the points for first and second: (1 + 2) / 2 = 1.5 each. The
  next boat is third, not second.
- **F and G don't.** Their corrected times are 0.421 of a second apart. The
  pages round both to 1:09:09, but places are decided on the full value, so
  F is third and G fourth. This is the owner's decision on rounding: full
  precision, rounded for display only.

**Standings.** D and E are level on 1.5 points. RRS A8.1 and A8.2 can't
separate them, because each has only that one score, so they share first
place. F is third on 3 points and G fourth on 4.

---

## Acceptance criteria

**Part A**
- Every existing fixture and test passes with only its import lines
  changed. No assertion and no expected value changes.
- `import sailscoring` works and `import nhc` fails: the old name is gone,
  with no alias.
- `tests/test_package_purity.py` and CI's "imports with nothing installed"
  job run against the new name, and still prove the package is
  standard-library only and imports without Django.
- `tests/test_readme.py` still finds every exported name in the package
  README.
- No migration is created (`makemigrations --check` passes), and every
  series scores the same before and after.
- A series declared final before the rename still shows its stored results.
- `ruff check .` and `ruff format --check .` pass, with the package still
  targeting Python 3.11.
- A search of the repository for the word `nhc` finds only the scheme's
  name (the list under "What keeps the name NHC") and history (completed
  slice specs and past decisions).
- No page, email or manual page changes, so the manual and its screenshots
  are untouched.

**Part B**
- Each new fixture, as checked by the project owner, is reproduced exactly
  by the engine and, loaded through the database as clock times, by the
  series page and every boat's page.
- Every existing fixture and test passes unchanged, and every existing
  series scores the same after the migration.
- Under YTC, no handicap moves, whatever the finishes. Tested as a sweep
  over every finish in a multi-race series.
- The series form refuses the NHC-only settings on a YTC series, as slice
  24 has it for Portsmouth Yardstick.
- The NHC types and the NHC modules are untouched by part B, and slice 24's
  test that the fixed-number module and the NHC modules don't import each
  other still passes.
- A boat is scored on the number her entry chose: the same boat entered on
  her YTC number in one series and her non-spinnaker number in another is
  scored on each, and changing one entry's choice changes only that series.
- A boat can't be entered in a YTC series on a number she doesn't have, by
  the race office, the admin or approving a request, and a series can't be
  switched to YTC while a boat entered has neither number. Both name the
  boats. A number can't be cleared while the boat is entered on it. A
  missing number that gets past all of these shows a message on every page,
  not a crash.
- Switching a series to YTC puts each entry on the boat's YTC number, or her
  non-spinnaker number if it is her only one. Switching away resets the
  choice.
- Changing either of a boat's YTC numbers, or an entry's choice of number,
  is recorded in the change history, and all three fields are in the pinned
  list of audited fields. It needs a reason when it is a correction, and a
  save that changes nothing records nothing. A final series is locked
  against all three.
- Changing a number a boat has never raced on needs no reason, even if she
  has raced on her other one.
- The handicap column is headed "YTC" everywhere, a boat on her
  non-spinnaker number is marked "NS" wherever her handicap is shown and on
  the race day page, and the boat page shows the fixed-number sentence.
  Checked in headless Chromium at 375 px.
- A member can give both YTC numbers in a boat registration or change
  request, and choose the number in an entry request. Neither reaches the
  boat or the series until approved.
- The club's data export and a person's data download include the new
  fields.
- The engine still imports nothing outside the standard library, and its
  README documents the new choice.
- The migration uses nothing database-specific.
- The manual's "Handicap systems" and the updated pages cover YTC, with
  screenshots.

## Out of scope
- **Restructuring the engine.** Part A renames the package and rewords its
  documentation. It moves no module and changes no function.
- **Publishing the package** (to PyPI or anywhere else). It is still copied
  into a project as a folder.
- Portsmouth Yardstick: slice 24.
- Other points systems (Bonus Point, high point); only RRS A4 low point.
- IRC, ECHO, a typed-in fixed TCF, or any system not named above.
- A series that mixes systems, or scores the same races under two systems
  at once. It is two series over the same races.
- Importing the RYA's published YTC list. Numbers are typed in.
- Working out a non-spinnaker number from a boat's YTC number. Both are
  typed in from the certificate.
- A choice of number race by race. A boat is on one number for the whole
  series.
- Keeping a per-series copy of a boat's number.
- Keeping the results sailed on a temporary YTC number as they were when
  the number is replaced (section 4.6 of the reference document). See
  "Temporary numbers".
- Rounding corrected times before ranking.
- The YTC scheme's collection of race timings data, for checking that
  boats perform to their numbers (section 8 of the reference document), and
  pursuit races.
- Multiple starts per race, and scoring codes beyond those already built.
- The brief's API and file export (user journey 5).

## The project owner's answers *(2026-10-02)*
- **The new name is `sailscoring`.** It says what the package does for any
  handicap system, and can't be confused with the app's own
  `races/scoring.py`. Part A has no open question left.
- **A boat holds both YTC numbers, and a series entry chooses which one she
  races on.** The alternative, one number per boat with the committee typing
  whichever applies, couldn't put the same boat in a spinnaker series and a
  white-sail series at the same time.
- **The data model: approved.** The `YTC` choice on
  `Series.handicap_system`, `Boat.ytc_number`,
  `Boat.ytc_number_non_spinnaker`, `SeriesEntry.ytc_number_used`, and the
  matching fields on `BoatRequest` and `EntryRequest`.
- **No rounding before ranking.** Corrected times are compared at full
  precision and rounded only for display, as NHC.
- **Temporary numbers are out of scope**, with a note in the manual.
- **NHC stays the default for a new series.**

## Settled by the reference document
- **The formula** is elapsed x 1000 / YTC number (section 6.2), as the draft
  assumed from secondary sources.
- **The number format** is a whole number (Appendix C).
- **The edition** is the current one, 2026.

## The worked examples *(checked 2026-10-02)*
The project owner checked YTC-1 and YTC-2 and found them right. They go into
`tests/fixtures/` as written above when part B is built.

Worked by hand, not with the engine; the arithmetic was re-checked with
plain Python (no engine code). The project owner checked and approved
them on 2026-10-02. That is the provenance to record in the fixture file.
