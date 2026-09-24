# Slice 6: Race-level entry

## Goal
The brief's user journey 3: on race day, a committee member records which
boats in the series are actually racing, and each boat's owner is told. Today
a boat is entered in a *series* and nothing more, so the finish-entry page
lists every boat in the series and any boat without a finish silently scores
DNC. Nobody can tell "stayed at home" from "raced, and we forgot to write it
down", so a missing finish can be published without anyone noticing.

This slice gives every race a start sheet. Only boats on it can have a
finish recorded, and every boat on it must have a finish time or a code
before the results can be published. A boat not on it stayed at home and
scores DNC, as today.

## Scope

### Who does what *(agreed with the project owner)*
- **Only the race committee** records who is racing. Members cannot enter a
  race, not even by request: it happens on race day, at the club, and
  approving requests would slow it down. A member who wants to race tells the
  committee, as they do now.
- **Every race has a start sheet.** There is one way of working, not two.
  Races already sailed are given theirs by a data migration (see Data
  model).

### The start sheet page (`/races/<pk>/entries/`, committee only)
- Lists every boat entered in the series, sorted by sail number. Each row has
  a **Racing** checkbox and a **Persons on board** box (optional, 1 to 99).
  Each row saves on its own over HTMX, like the finish-entry page, with a
  plain-POST fallback that works without JavaScript.
- A count at the top: "8 of 12 boats racing".
- It links to the finish-entry page and back, and it is linked from the race
  in the admin and from the finish-entry page.
- A boat can't be taken off the start sheet once it has a finish or code
  recorded for that race. The row says why, and the finish has to be removed
  first, which is already a recorded correction. This matches the rule that a
  series entry with finishes can't be removed.

### Entering finishes
- The finish-entry page has a row with input boxes only for boats on the
  start sheet. Each boat with nothing saved shows **Not recorded yet**. The
  other boats in the series are listed below them, collapsed under "Not
  racing (scored DNC)", and have no input boxes. A race with an empty start
  sheet says so and links to it.
- A finish or code can only be saved for a boat on the start sheet. If the
  committee tries any other boat (through the plain-POST fallback or a stale
  page), the page refuses and links to the start sheet. A boat that turns out
  to have raced is added to the start sheet first, which takes one click.

### Scoring and publishing *(agreed with the project owner: "must be recorded")*
- The engine's input doesn't change. A boat with no finish is passed to it as
  DNC, as today. The engine only knows its four statuses, and the scoring
  rules for a boat that raced but has nothing recorded belong to the club,
  not to this code.
- What changes is what people see and what the committee is allowed to do:
  - While a boat on the start sheet has nothing recorded, the race's results
    show that boat as **Not recorded** instead of DNC. This applies to the
    committee's pages and the public ones (the series page, the boat page
    and the latest results on the home page). The race is already labelled
    provisional there, because it can't be published yet.
  - **Publish results** and **Send updated results** are refused while any
    boat on the start sheet has nothing recorded. The page names the boats.
    A boat added after the race was published (one that was forgotten)
    blocks sending updated results the same way, until its finish is
    recorded. That finish is a correction, so the race shows as amended
    since it was sent, as it does today.
- `races/scoring.py` still decides which races are scored the same way: a
  race with boats on its start sheet but no finishes yet is "not sailed
  yet", as today. A start sheet on its own records nothing.

### Persons on board *(agreed with the project owner)*
- Recorded per boat per race on the start sheet. It's optional, and it has
  no effect on scoring.
- Shown to the committee only, on the start sheet and the finish-entry page.
  Public pages don't show it, because it describes the people on board, and
  the public pages already show no owners' names.

### Confirmation email *(agreed with the project owner)*
- When the committee puts a boat on a start sheet, the boat's owning account
  (active accounts only, as with every other email) receives one email:
  "GBR 42 Kittiwake is entered in race 3 of Autumn 2026 on Wednesday 1
  October". It links to the series page.
- It is sent through `races/notifications.send`, so it goes after the change
  commits. A failure shows as a warning on the page and the boat stays on the
  start sheet.
- One email per boat, sent when the box is ticked. Changing the persons on
  board or saving the row again sends nothing more. Taking a boat off sends
  nothing (see Out of scope). If a boat is taken off and then put back on, it
  gets a second email. That is rare, and a correct email is better than
  storing extra data to prevent it.
- A boat with no owning account, or whose account is inactive, gets no email.
  The row says "no email: no owner account" so the committee knows to tell
  them.

### Change history
- Putting a boat on the start sheet, taking it off, and changing persons on
  board are **not** recorded in the change history (`ScoringChange`). None of
  them can move a place, a handicap or a point: a boat on the start sheet
  with no finish is scored exactly as one left off it. The history stays
  "every change that could move a score", and "amended since sent" stays
  correct because it reads that history.
- Recording a finish for a boat added after publishing is audited as it
  already is.

### Data model *(proposed; needs the project owner's approval before any
migration is written)*
- A new model, `RaceEntry`:
  - `race`, a foreign key to `Race`. Deleted with its race.
  - `entry`, a foreign key to `SeriesEntry`. Deleted with its series entry
    (only possible when the entry has no finishes).
  - `persons_on_board`, a `PositiveSmallIntegerField` that can be left empty,
    checked to be between 1 and 99.
  - The database enforces one row per boat per race (a unique constraint on
    race and entry). The race and the entry must belong to the same series.
    That is checked in the form and in `clean()`, because a database
    constraint can't reach across the two tables.
- **Why not a flag on `Finish`?** A `Finish` is a time or a code, and the
  database enforces that. A row meaning "racing, nothing recorded yet" would
  break that rule and every query that relies on it.
- `Finish` itself does not change. "A finish needs its boat on the start
  sheet" is checked in the finish form and in `Finish.clean()`. The database
  can't check it without `Finish` pointing at a `RaceEntry` instead of a race
  and an entry, which would rewrite every query and the change history for
  no gain visible to anyone.
- **A data migration** puts every boat that has a finish in a race on that
  race's start sheet, with persons on board left empty and no emails sent.
  Boats with no finish stay off, so they score DNC as they do now. Every
  existing race therefore scores exactly as before, and every existing
  finish meets the new rule. Undoing the migration deletes those rows.
- No other fields change. The migrations use nothing database-specific.

## Acceptance criteria
- The committee can put boats on a race's start sheet, take them off, and
  record persons on board. Each row saves on its own over HTMX, and saves
  with JavaScript off. An invalid row is refused with a message and doesn't
  affect the other rows.
- A finish for a boat not on the start sheet is refused, by the finish-entry
  page and by `Finish.clean()`, and a boat with a finish recorded can't be
  taken off it. The test builders in `races/testing.py` put a boat on the
  start sheet when they record a finish for it, so existing tests keep
  describing races that could really happen.
- The data migration gives an existing series a start sheet for every race.
  Every race then scores the same positions, points and handicaps as it did
  before the migration, and no email is sent.
- A boat on the start sheet with nothing recorded shows as "Not recorded" on
  the committee's pages and every public page, and scores exactly as DNC
  does. This is tested by comparing a race where a boat is on the start
  sheet with nothing recorded against the same race with that boat left off,
  which must give identical positions, points and handicaps.
- Publishing and sending updated results are refused, with the boats named,
  while any boat on the start sheet has nothing recorded, including a boat
  added after publishing.
- The confirmation email is sent when, and only when, a boat is put on a
  race's start sheet, and not when its row is saved again: only to an active owning
  account, never on a rolled-back change. A sending failure keeps the boat
  on the start sheet and says so. Each case is tested, as in slice 4.
- Persons on board appears on no public page, tested on every public page.
- Start sheet changes add nothing to the change history, and a published race
  is not marked amended by them.
- The start sheet page is tested as each of the four roles
  (`races/test_roles.py`). Only the committee and the administrator can open
  it, and anyone else gets a 403 or a redirect to log in, as for the
  finish-entry page.
- The database refuses two rows for the same boat in the same race, and
  persons on board outside 1-99. The model refuses a boat from another
  series.
- The migration uses nothing database-specific.
- The user manual gains a committee page, "Race day: the start sheet and
  finishes", with screenshots, and the members' email page lists the new
  email.

## Out of scope
- Members entering, or asking to enter, a race themselves.
- An email when a boat is taken off a start sheet. It would be sent on
  race day, often by mistake, and a boat taken off by mistake is usually
  put straight back on.
- Copying the previous race's start sheet. Easy to add later if the committee
  finds ticking boats slow.
- Scoring a boat on the start sheet with nothing recorded as anything but DNC
  (DNS, for instance). If the club wants that, it's a rule decision, and it
  would change the engine's input.
- Scoring codes beyond FINISHED, DNC, DNS, DNF, and multiple starts per race.
- Using persons on board for anything (crew-weight rules, safety lists or
  exports).
- The brief's API and file export (user journey 5).
