# Slice 26: more scoring codes (DSQ, RET, OCS, NSC) and RRS A6.1

**Status: built (2026-10-10), both parts.** The project owner
has answered the six questions, approved the data model change and checked
the worked examples (see "The project owner's answers" at the end). Nothing
is left to answer.

## Goal
A race committee can record that a boat was disqualified, retired, was over
the line at the start, or did not sail the course, and keep the finish time
it wrote down for her. The boats behind her move up a place (RRS A6.1).

Today the only way to record any of these is DNF, which loses the boat's
finish time and says something that isn't true.

## What's there now
- The engine's `RaceStatus` and the site's `Finish.Status` have four values:
  FINISHED, DNC, DNS and DNF.
- A finish is a time or a code, never both: the engine raises `InvalidInput`
  for a non-finisher with an elapsed time (`sailscoring/domain.py`,
  `_check_elapsed_time`), and the database has the check constraint
  `finish_time_xor_code`.
- Places come from ranking the FINISHED boats on corrected time
  (`score_race`, `fixed_number.py`). Every other boat scores one more than
  the series entries (A5.2), or one more than the boats that came to the
  starting area if she wasn't DNC and the series uses A5.3.
- The README and `sailscoring/points.py` list A6.1 and these codes as not
  implemented.

## The rules
From the RRS 2025-2028 in `docs/reference/`:

- **A10** defines the codes:
  - **DSQ**: disqualification.
  - **RET**: retired.
  - **OCS**: did not start; on the course side of the starting line at her
    starting signal and failed to start.
  - **NSC**: did not sail the course (other than DNC, DNS, OCS and DNF).
- **A5.2:** a boat that did not sail the course, retired or was disqualified
  scores one more than the number of boats entered in the series. That is
  the score DNF, DNS and DNC already get.
- **A5.3**, where the series uses it: a boat that came to the starting area
  scores one more than the number that came. All four new codes are boats
  that came.
- **A6.1:** "If a boat is disqualified from a race, or retires after
  finishing, or is scored Did not sail the course, each boat with a worse
  finishing place shall be moved up one place."

In a handicap race, places come from corrected times. So A6.1 means: a boat
with one of these codes is left out of the ranking, and the boats that
finished are ranked as if she weren't there. An OCS boat never started, so
she never had a place; the effect on the others is the same.

## What gets built

### Recording a code
- The **Result** list on the race day page, and wherever a finish is
  corrected, gains four choices:
  - DSQ - disqualified
  - RET - retired
  - OCS - over the line at the start
  - NSC - did not sail the course
- **A boat with one of these four codes may keep a finish time.** The usual
  case: the committee taps **Finished** as she crosses the line, and a
  protest, a declaration or a look at the start recording changes her result
  later. Choosing the code leaves her time in the box. The time is optional:
  a boat that retires on the first beat has none.
- **DNC, DNS and DNF still can't have a time**, as today. A boat with a
  finish time finished, so "did not finish" can't be right; if she retired
  after finishing, that is RET.
- **FINISHED still needs a time**, as today.
- **The scoring penalty tick** stays for FINISHED boats only.
- Changing a result to or from a code is a correction like any other: in the
  change history, with a reason once the result was saved, and it marks
  published results "amended since sent". No new audited field: `status` and
  `finish_time` are audited already.
- **Reinstating a boat** (a disqualification overturned) is one correction
  back to Finished. Her time is still there, so nothing is retyped.
- On the Finishing view, a boat with a code and a time is listed with the
  codes, not in the order across the line, and shows both: "DSQ, crossed the
  line at 19:02:11".
- Undo, the start sheet, "Not recorded" and the publishing gate don't
  change: every boat on the start sheet still needs a time or a code.

### Scoring
- A boat with any of the four codes has **no place and no corrected time**,
  and scores as a DNF does (A5.2, or A5.3 as a boat that came to the
  starting area).
- The other boats are ranked without her, ties and all (A7), which is A6.1.
- A scoring penalty on another boat is worked out on the place she ends up
  with (worked example CODE-4).
- A DSQ can be discarded like any other score. DNE, the disqualification
  that can't be, is out of scope.
- **Handicaps (NHC):** a boat with a code is treated exactly as a DNF is,
  with or without a time. She is left out of the adjustment's sums and her
  handicap carries forward unchanged.
- **Regattas:** a regatta back-calculates an elapsed time for every
  non-finisher. The four codes are treated as DNF is (the median finisher's
  corrected time), with or without a recorded time.
- **End-of-series realignment:** a boat with any of the four codes took
  part, as a DNF boat did.
- Portsmouth Yardstick and YTC series: the same places and points. Nothing
  else to decide, since numbers don't move.

### Showing it
- Wherever a code shows today, the new ones show the same way: the race
  table, the series table, the boat page, the results email, the WhatsApp
  race message and the CSV.
- The kept finish time and elapsed time show to everyone, in the race
  table's **More detail** columns and in the CSV, with the corrected time
  blank. They are what the committee recorded, and showing them lets an
  owner see the time wasn't lost.
- A line under a table explains each new code that appears in it, as SCP's
  does: "DSQ: Disqualified. Boats behind her moved up a place (RRS A6.1)."
- A series declared final before this slice shows its stored results
  unchanged. A copy made after it can hold the new codes; nothing in the
  copy's shape changes.

### The engine
- `RaceStatus` gains `DSQ`, `RET`, `OCS` and `NSC`. `is_finisher` stays
  "FINISHED only", so everything that ranks or sums finishers leaves the new
  codes out without being touched.
- A new property (say `may_keep_time`) is true for the four. For them
  `elapsed_seconds` is optional on `Finish` and `RaceEntry`: None or 0 means
  no time, anything else must be a positive finite number. DNC, DNS and DNF
  with a time still raise `InvalidInput`.
- `RaceResult` and `FixedNumberResult` carry the recorded `elapsed_seconds`
  through, with `corrected_time` and `position` None.
- `score_points` needs no change in logic: the new codes aren't DNC, so they
  already count as boats that came to the starting area.
- Two places test for DNF by name and need the new codes beside it:
  `regatta._elapsed_times` and `realignment.realignment_entries`.
- `RaceResult.capped` compares the recorded time with the time used. In a
  regatta a coded boat would now have both, and they differ, so `capped`
  must be true for finishers only.
- The README: the four codes and A6.1 move from "Not implemented" to
  documented; DNE, UFD, BFD, ZFP, RDG and DPI stay there.

### Data model *(approved 2026-10-10)*
- `Finish.Status` gains four choices. The column is already 10 characters.
- The check constraint `finish_time_xor_code` is replaced by one that says:
  - FINISHED: a time is required;
  - DNC, DNS, DNF: no time;
  - DSQ, RET, OCS, NSC: either.
- `Finish.clean()` says the same in words.
- One schema migration, no data migration. Every existing row satisfies the
  new constraint, since it is looser than the old one.

## Built in two parts
Each its own pull request, as slices 24 and 25 were.

- **Part A: the engine.** The statuses, the relaxed time rule, the regatta
  and realignment branches, the fixtures and the README. The site doesn't
  offer the codes yet.
- **Part B: the site.** The model and migration, the form, the pages, the
  email, the WhatsApp message, the CSV and the manual.

## Worked examples *(checked by the project owner, 2026-10-10)*
Worked by hand from the rules above, not with the engine. The RRS publishes
no worked example of A6.1, so these are the specification. That is the
provenance to record in the fixture file.

Each is a Portsmouth Yardstick race with every boat on 1000, so a boat's
corrected time is her elapsed time and no handicap arithmetic is involved.
Six boats are entered in the series, A to F. F stays at home (DNC).

**CODE-1: A6.1 under A5.2.** A DNF scores 6 + 1 = 7.

| Boat | Elapsed | As sailed | B disqualified after finishing |
|---|--:|---|---|
| A | 50:00 | 1st, 1 | 1st, 1 |
| B | 51:00 | 2nd, 2 | DSQ, **7** |
| C | 52:00 | 3rd, 3 | **2nd, 2** |
| D | 53:00 | 4th, 4 | **3rd, 3** |
| E | 54:00 | 5th, 5 | **4th, 4** |
| F | - | DNC, 7 | DNC, 7 |

B keeps her recorded 51:00. A, ahead of her, doesn't move.

**CODE-2: the same race under A5.3.** Five boats came to the starting area
(everyone but F), so B scores 5 + 1 = **6**. F still scores 7. The others
are as in CODE-1.

**CODE-3: with a tie.** As CODE-1, but C and D both take 52:00, and B
retires after finishing (RET).

| Boat | Elapsed | As sailed | B retired after finishing |
|---|--:|---|---|
| A | 50:00 | 1st, 1 | 1st, 1 |
| B | 51:00 | 2nd, 2 | RET, **7** |
| C | 52:00 | 3rd equal, (3 + 4) / 2 = 3.5 | **2nd equal, (2 + 3) / 2 = 2.5** |
| D | 52:00 | 3rd equal, 3.5 | **2nd equal, 2.5** |
| E | 54:00 | 5th, 5 | **4th, 4** |
| F | - | DNC, 7 | DNC, 7 |

**CODE-4: with a scoring penalty.** CODE-1's race, and D takes a scoring
penalty: 20% of the DNF score, 7, is 1.4.

- As sailed, D is 4th: 4 + 1.4 = 5.4.
- With B disqualified, D is 3rd: 3 + 1.4 = **4.4**.

**CODE-5: each code, with and without a time.** A5.2.

| Boat | Recorded | Place | Points |
|---|---|--:|--:|
| A | Finished, 50:00 | 1 | 1 |
| B | OCS, crossed the line at 51:00 | - | 7 |
| C | NSC, crossed the line at 52:00 | - | 7 |
| D | RET, no time | - | 7 |
| E | Finished, 54:00 | 2 | 2 |
| F | DNC | - | 7 |

Under A5.3, B, C and D came to the starting area and score **6**; F scores 7.

**CODE-6: in a series.** A boat scores 1, 7 (DSQ) and 2 in a six-boat
series. With no discards her total is **10**. With one discard the 7 is
excluded and her total is **3**.

## Acceptance criteria

**Both parts**
- Every worked example above, as checked by the project owner, is a fixture
  in `tests/fixtures/` with its provenance recorded. No fixture is produced
  from the engine's output.
- Every existing fixture and test passes unchanged, and every existing
  series scores the same after the migration.
- `ruff check .` and `ruff format --check .` pass.

**Part A, the engine**
- The fixtures reproduce exactly, under A5.2 and A5.3.
- With a boat changed from FINISHED to any of the four codes, every boat
  with a worse place moves up one, no boat ahead moves, and ties are shared
  afresh.
- A boat with one of the four codes scores the same with a time as without.
- DNC, DNS or DNF with a time, a scoring penalty on a coded boat, and a
  zero, negative or non-finite time on a coded boat each raise
  `InvalidInput`.
- Handicaps: in a club series and in a regatta, every boat's next handicap
  is identical whether a boat is recorded with one of the four codes (with
  or without a time) or as DNF. Tested as a sweep over a series, like
  `tests/test_recalculation.py`.
- Realignment includes a boat whose only results are any of the four codes.
- `capped` is false for a coded boat with a time, in a club series and in a
  regatta.
- `sailscoring/` still imports nothing outside the standard library, and
  its README documents the new statuses.

**Part B, the site**
- The four codes can be recorded with and without a time from the race day
  page, with and without JavaScript. A time with DNC, DNS or DNF, and a
  scoring penalty with any code, are refused by the form, the model and the
  database.
- Changing Finished to a code keeps the time; changing it back needs no
  retyping. Both are in the change history with a reason, and mark a
  published race amended.
- CODE-1 to CODE-6, loaded through the database, read back from the series
  page and each boat's page.
- The codes show on the race table, the series table, the boat page, the
  results email, the WhatsApp race message and the CSV, each with its
  explanation where the page has room for one.
- A final series is locked against the change, and one declared final
  before this slice shows its stored results unchanged.
- The migration uses nothing database-specific (SQLite and PostgreSQL).
- The manual is updated, with screenshots: the race day page (the new codes
  and the kept time), "How results are worked out" (the codes, A6.1, and
  what happens to handicaps), and "Finding your results".
- The new choices are checked in headless Chromium at 375 px.

## Out of scope
- **The other A10 codes:** DNE (a disqualification that can't be
  discarded), UFD and BFD (flag disqualifications), ZFP (the 20% Z flag
  penalty), RDG (redress, and A6.2) and DPI (discretionary penalty).
- **Protests and hearings.** The site records the outcome; it doesn't run a
  protest, a declaration form or a time limit.
- **A second discard rule, other points systems, multiple starts:** as
  before.

## The project owner's answers *(2026-10-10)*
1. **The data model: approved.** Four new choices on `Finish.Status`, and
   the "time or code, never both" constraint loosened so DSQ, RET, OCS and
   NSC may keep a finish time. One schema migration, no data migration.
2. **A coded boat's time doesn't feed the NHC handicaps.** She is treated
   as a DNF is: left out of the sums, handicap carried forward. The RYA spec
   gives only FINISHED boats a usable time, so this adds no rule of our own;
   it is one rule for all four codes; and an OCS or NSC time isn't a fair
   measure anyway (a head start, or a shorter course). The alternative,
   counting a DSQ's or a RET's time as slice 23 does a penalised boat's, was
   turned down.
3. **Regattas: all four codes are back-calculated as DNF is** (the median
   finisher's corrected time), since each was on the water racing. The RYA
   spec doesn't mention them.
4. **Realignment: all four codes count as having taken part,** OCS
   included, though by the rules she "did not start": the boat sailed the
   race.
5. **Everyone sees the kept time,** in More detail and the CSV, with the
   corrected time left blank.
6. **The worked examples CODE-1 to CODE-6 are correct.** They go into
   `tests/fixtures/` as written above when part A is built.
