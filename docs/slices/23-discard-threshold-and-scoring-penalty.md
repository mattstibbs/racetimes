# Slice 23: a discard threshold and the scoring penalty

**Status: complete (2026-10-02).** Part A was built in #48 and part B in #49.
The project owner had answered the open questions, approved both data model changes, and
checked the worked examples (see "The project owner's answers" at the end).
Nothing is left to answer.

## Goal
Two rules that club notices of race and sailing instructions commonly rely
on, and that Race Times can't score today:

- **A. "No discard until N races."** A series excludes each boat's worst
  score only once a stated number of races have been scored (RRS A2.1).
- **B. The scoring penalty.** A boat that finishes and accepts a scoring
  penalty keeps her place but scores extra points (RRS 44.3(c): 20% of the
  score for Did Not Finish).

The two parts don't depend on each other. Each can be approved, built and
merged on its own, as its own pull request. Suggested order: A (smaller),
then B.

## What's there now
- `Series.discards` is a fixed count. `nhc/standings.py` excludes
  `min(discards, races scored)` scores, so a one-discard series drops every
  boat's only score after race 1.
- The engine and `Finish.Status` know four outcomes: FINISHED, DNC, DNS and
  DNF. A boat that finishes always scores the points for her place. The
  package README lists penalty codes as not implemented.

---

## Part A: no discard until N races

### The rule
RRS A2.1 lets the notice of race say "a specified number of scores will be
excluded if a specified number of races are scored". The common form is
"one discard once four races have been sailed".

### What gets built
- A series' **Scoring rules** gain a second box under **Discards**:
  **"No discards until this many races are scored"**, a whole number, 0 by
  default. 0 means the discards always apply, which is today's behaviour, so
  no existing series changes.
- While fewer races than that are scored, no score is excluded. From that
  many races on, the series' discards apply exactly as today.
- **"Scored" means races with results**, the same races the standings
  already count (`races/scoring._scorable_races`). A race not yet sailed, or
  held back, doesn't count towards the number.
- The form refuses a threshold that isn't larger than the number of
  discards (when it isn't 0), because at that point every score would be
  excluded and every boat would total zero.
- The series page, the race office and the CSV say it in words: "1 discard
  once 4 races are scored". The "Discarded scores are in brackets" note only
  shows once discards apply.
- Changing it is a change to a score-affecting series setting: it's in the
  change history and needs a reason once races are sailed, as **Discards**
  does today. A final series is locked, as now.

### The engine
- `nhc.Series` and `compute_standings` gain `discard_threshold: int = 0`.
  With fewer races than the threshold, nothing is excluded. A negative
  threshold, or one from 1 up to `discards`, raises `InvalidInput`.
- Nothing else changes: A2.1's "earliest equal worst score" rule and the A8
  tie-breaks work on whatever is, or isn't, excluded.
- The README's "Not implemented" entry "A discard schedule" is reworded: one
  threshold is implemented (`discard_threshold`); a schedule with several
  steps ("1 after 4 races, 2 after 8") still isn't.

### Data model *(approved 2026-10-02)*
- `Series.discard_threshold`: `PositiveSmallIntegerField`, default 0, for
  new series as well as existing ones.
- One schema migration, no data migration.

### Worked example DT-1 *(checked by the project owner, 2026-10-02)*
Three boats entered, 1 discard, threshold 4, RRS A5.2 (a boat that doesn't
finish scores 4). The scores, race by race:

| Boat | R1 | R2 | R3 | R4 | R5 |
|---|--:|--:|--:|--:|--:|
| A | 1 | 1 | 4 (DNC) | 1 | 2 |
| B | 2 | 2 | 1 | 2 | 3 |
| C | 3 | 3 | 2 | 3 | 1 |

The standings after the third, fourth and fifth races (N-1, N and N+1):

| Boat | After 3 | After 4 | After 5 |
|---|---|---|---|
| A | 6, nothing excluded | 3, excluding R3 | 5, excluding R3 |
| B | 5, nothing excluded | 5, excluding R1 | 7, excluding R5 |
| C | 8, nothing excluded | 8, excluding R1 | 9, excluding R1 |

- **After three races** nothing is excluded and B leads A by 5 points to 6.
- **After the fourth**, each boat's worst score goes and A leads by 3 points
  to 5. B and C each have equal worst scores, so the earliest (R1) is the
  one excluded.
- **After the fifth**, each boat still excludes one score, worked out afresh:
  B's worst is now her 3 in R5, so R1 counts again (2 + 2 + 1 + 2 = 7). C
  has three equal worst scores (R1, R2 and R4), and the earliest goes. A
  leads B by 5 points to 7.

---

## Part B: the scoring penalty

### The rule
Sailing instructions can say that a boat breaking a named rule (touching a
moored or anchored boat, for example) declares it and "accepts a 20% Scoring
Penalty under RRS 44.3(c)". The rule, from the RRS 2025-2028 in
`docs/reference/`:

- Her score is the score she would have had, **made worse by 20% of the
  score for Did Not Finish**, rounded to the nearest tenth of a point (0.05
  upward).
- **Other boats' scores don't change**, so two boats can have the same
  score, and a penalised boat can score more than the boat behind her.
- The penalty **can't make her score worse than Did Not Finish**.
- RRS A10 records it as **SCP**.

"The score for Did Not Finish" is whatever a DNF scores in that race: one
more than the series entries under A5.2, or one more than the boats that
came to the starting area when the series uses A5.3. A DNF score is always a
whole number, so 20% of it is always an exact number of tenths (7 gives 1.4)
and the rounding clause never has anything to round.

### What gets built
- On the race day page's Finishing view, and wherever a finish is corrected,
  a boat with a finish time has a **Scoring penalty** tick. It can't be
  ticked for a boat with a code: she has no place to worsen.
- Ticking it changes only that boat's **points** in that race. Her finish
  time, corrected time and place stay, and so do every other boat's.
- **One scoring penalty per boat per race.** It is a tick, not a count. RRS
  44.3 allows a penalty for each of several incidents in one race; that
  isn't built (see Out of scope).
- **Her handicap moves as any finisher's does.** She sailed the course, so
  her elapsed time is in the NHC adjustment like everyone else's.
- It is a score-affecting change: recorded in the change history, with a
  reason when it is a correction, and it marks published results "amended
  since sent" like any other correction.
- Results show it: "SCP" beside the boat's points in the race table, the
  series table, the boat page, the results email and the CSV, and a line
  under the table saying what SCP means. Points show one decimal place when
  they have one ("4.4").
- **The WhatsApp message** for a race (slice 21,
  `templates/races/share/race.txt`) lists places and no points, so a
  penalised boat's line ends "(SCP)", for example "3. Kestrel (123) (SCP)".
  Without it she would be listed third with nothing to say she scored worse
  than the boat in fourth. The link to the full results explains the code.
  The final standings message shows totals only and doesn't change.
- A penalised score can be discarded like any other.

### The engine
- `nhc.Finish` and `RaceEntry` gain `scoring_penalty: bool = False`.
  `InvalidInput` if it is set on a boat that didn't finish.
- `RaceResult` gains `scoring_penalty` and `penalty_points` (None when there
  is no penalty). `score_points` works out the place points as today (A4,
  shared across an A7 tie), then adds the penalty and caps the result at
  that race's DNF score.
- **Tenths of a point.** `nhc/standings.py` relies on every score being a
  multiple of 0.5, which a float holds exactly, so totals are compared
  exactly. Tenths aren't exact in a float (0.1 + 0.2). Totals and the A8
  tie-break keys are therefore worked out in whole tenths (integers), and
  turned back into points only for output. Every existing fixture and test
  must pass unchanged.
- Allowed in club series and regattas alike: it touches points, never the
  handicap formulas.
- The README's "Not implemented" list is updated: SCP is implemented; the
  other codes (OCS, RET, DSQ, DNE, RDG and the rest) still aren't.

### Data model *(approved 2026-10-02)*
- `Finish.scoring_penalty`: `BooleanField`, default False.
- A check constraint: a scoring penalty only on a FINISHED row.
- A final series' stored results (`Series.final_results`) gain the two new
  result fields. Results stored before this slice have neither, and load as
  "no penalty".
- One schema migration, no data migration.

### Worked examples *(checked by the project owner, 2026-10-02)*
Worked by hand, not with the engine.

**SP-1: RRS A5.2.** Six boats entered. A DNF scores 7, so the penalty is
20% of 7 = 1.4.

| Boat | Outcome | Place | Points |
|---|---|--:|--:|
| A | Finished | 1 | 1 |
| B | Finished | 2 | 2 |
| C | Finished, scoring penalty | 3 | 3 + 1.4 = **4.4** |
| D | Finished | 4 | 4 |
| E | DNF | - | 7 |
| F | DNC | - | 7 |

C keeps third place and D's score doesn't change, so D now scores better
than C.

**SP-2: the same race with A5.3.** Five boats came to the starting area
(everyone but F), so a DNF scores 6 and the penalty is 20% of 6 = 1.2. C
scores 3 + 1.2 = **4.2**, E scores 6, F (DNC) scores 7.

**SP-3: the cap.** Six boats entered, all finish, A5.2. The sixth boat takes
a penalty: 6 + 1.4 = 7.4, which is worse than a DNF's 7, so she scores **7**.

**SP-4: with a tie.** A5.2, six entered. Two boats tie for second on
corrected time and would each score (2 + 3) / 2 = 2.5. One takes a penalty:
she scores 2.5 + 1.4 = **3.9**, the other 2.5.

**SP-5: in a series.** A boat scores 1, 4.4 (SCP) and 2. With no discards
her total is **7.4**. With one discard the 4.4 is excluded and her total is
**3**.

**SP-6: level on tenths.** Six boats entered, two races, no discards, A5.2.
A DNF scores 7, so each penalty is 1.4. Everyone finishes both races.

| Boat | Race 1 | Race 2 | Total |
|---|--:|--:|--:|
| A | 1st, scoring penalty: 1 + 1.4 = 2.4 | 3rd, scoring penalty: 3 + 1.4 = 4.4 | 6.8 |
| B | 2nd, scoring penalty: 2 + 1.4 = 3.4 | 2nd, scoring penalty: 2 + 1.4 = 3.4 | 6.8 |
| C | 3rd: 3 | 1st: 1 | 4 |
| D | 4th: 4 | 4th: 4 | 8 |
| E | 5th: 5 | 5th: 5 | 10 |
| F | 6th: 6 | 6th: 6 | 12 |

A and B are level on 6.8, so RRS A8.1 decides: each boat's scores best to
worst are A's 2.4, 4.4 and B's 3.4, 3.4. They differ at the first score, and
A's 2.4 is the better one, so A is ahead.

| Place | Boat | Total |
|--:|---|--:|
| 1 | C | 4 |
| 2 | A | 6.8 |
| 3 | B | 6.8 |
| 4 | D | 8 |
| 5 | E | 10 |
| 6 | F | 12 |

Two things this example pins down:

- **The totals are exactly equal.** A computer adding 2.4 and 4.4 as
  ordinary decimal fractions gets a hair over 6.8, and 3.4 + 3.4 gets 6.8
  exactly. An engine that compared those would call B the outright leader of
  the two and never reach the tie-break. This is why the engine counts in
  whole tenths.
- **A8.1 comes before A8.2.** A8.2 (the last race) would favour B, who
  scored 3.4 to A's 4.4 in race 2. It is only used if A8.1 leaves a tie, and
  here it doesn't.

---

## Acceptance criteria

**Both parts**
- Every worked example above, as checked by the project owner, becomes a
  fixture in `tests/fixtures/` with its provenance recorded, and is
  reproduced exactly by the engine and, loaded through the database, by the
  series page and each boat's page. No fixture is produced from the engine's
  output.
- Every existing fixture and test passes unchanged, and every existing
  series scores the same after each migration.
- Each new score-affecting field (`Series.discard_threshold`,
  `Finish.scoring_penalty`) is in the pinned list of audited fields, is
  recorded in the change history, and needs a reason when it is a
  correction. A save that changes nothing records nothing.
- A final series is locked against both, and a series declared final before
  this slice still shows its stored results.
- Migrations use nothing database-specific (SQLite and PostgreSQL).
- `nhc/` still imports nothing outside the standard library, and its README
  documents every new name.
- The manual is updated, with screenshots: "A series' scoring rules" (the
  threshold), "How results are worked out" (the scoring penalty), the race
  day page (the tick), "Finding your results" (SCP), and "Publishing
  results" (the "(SCP)" mark in the WhatsApp message).
- New controls are checked in headless Chromium at 375 px.

**Part A**
- With a threshold of N, no score is excluded while fewer than N races are
  scored, and the discards apply from the Nth. Tested at N-1, N and N+1
  (DT-1 after its third, fourth and fifth races).
- A threshold of 0 behaves exactly as today.
- The form and the engine refuse a threshold from 1 up to the number of
  discards.
- Removing a race's results so the count falls below N brings the excluded
  scores back, on the next page load.

**Part B**
- A penalised boat's points are her place points plus 20% of that race's DNF
  score, capped at the DNF score, under A5.2 and under A5.3. No other boat's
  place or points change, and no place changes.
- The tick is refused on a boat with a code, by the form, the model and the
  engine.
- Handicaps after the race are identical with and without the tick.
- A series total that includes tenths is exact, and two boats level on
  tenths are tied and go to the A8 tie-breaks (SP-6).
- SCP shows wherever the boat's points for that race are shown, including
  the email and the CSV.
- The WhatsApp message for a race marks a penalised boat "(SCP)", and is
  unchanged for a race with no penalty.

## Out of scope
- **Other scoring codes:** OCS, RET, DSQ, DNE (a disqualification that can't
  be discarded), RDG and the rest, and RRS A6.1 (boats moving up when one
  ahead is disqualified). SCP is the only one added.
- **Other penalties:** a penalty of a stated number of points or a different
  percentage, the Z flag penalty (ZFP, also 20%), time penalties, and
  discretionary penalties.
- **More than one scoring penalty for a boat in one race.** RRS 44.3 allows
  one for each incident. It would need a count where this slice has a tick,
  which is a data model change.
- **A discard schedule with several steps** ("1 after 4 races, 2 after 8").
  Part A is one count and one threshold. A schedule would need a different
  data model, so it is a later slice if a club needs it.
- **A minimum number of races to constitute a series** (RRS A1).
- **Other points systems** (Bonus Point, high point). RRS A4 low point
  stays the only one.
- **Other handicap systems.** Portsmouth Yardstick is slice 24, and RYA YTC
  slice 25.

## The project owner's answers *(2026-10-02)*
1. **The data model: approved**, both fields (`Series.discard_threshold` and
   `Finish.scoring_penalty`).
2. **20% only.** RRS 44.3(c) lets sailing instructions state a different
   number of points. Only the 20% default is built, with no series setting;
   one is added if a club needs it.
3. **A penalised boat's handicap moves as any finisher's does**, since the
   penalty is about a rule, not her speed. The RYA's NHC spec says nothing
   either way.
4. **The 2025-2028 rules** in `docs/reference/` (tenths of a point), not an
   older edition's whole number of places.
5. **One threshold, not a schedule.** "1 discard after 4 races, 2 after 8"
   is out of scope.
6. **A tick, not a count:** one scoring penalty per boat per race.
7. **The threshold defaults to 0 for new series too**, so nothing changes
   unless the committee sets it. A new one-discard series still excludes
   every boat's only score after race 1, as today.
8. **The WhatsApp race message marks a penalised boat "(SCP)".**

## The worked examples *(checked 2026-10-02)*
The project owner checked DT-1 (five races) and SP-1 to SP-6 and found them
right. They go into `tests/fixtures/` as written above when each part is
built.

Worked by hand, not with the engine, and re-worked by hand when the spec
was reviewed. The project owner checked and approved them on 2026-10-02.
That is the provenance to record in the fixture file.
