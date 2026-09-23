# Slice 2: Corrections and audit

## Goal
A race committee can correct anything that feeds a score, see straight away
which results moved as a result, and later look back at who changed what, when
and why. Anyone reading the public results can see that a race was amended.

Recalculation itself is already done: slice 1 stores nothing derived, so a
corrected finish shows its full effect on the next page load. This slice adds
the record of the change, and shows its effect at the moment it's saved.

## Scope

### What is audited
Everything that changes a score, and nothing else. Old and new values are both
recorded.

| Record     | Audited                                         | Not audited (display only)          |
|------------|-------------------------------------------------|-------------------------------------|
| Finish     | added, `status`, `finish_time`                  | -                                   |
| Race       | added, removed, `number` (replay order), `start_time` | `date` (elapsed time is same-day, so it moves no number) |
| Series     | `series_type`, `discards`, `minimum_finishers`, `apply_a5_3` | `name`                  |
| SeriesEntry| added, removed (changes the A5.2 entry count)   | -                                   |
| Boat       | `base_number`                                   | sail number, name, make, model, owner, lengths |

The list of audited fields lives in one place in code, so adding a field later
is one line and a test.

### Corrections and reasons
A change is a **correction** if it alters something that has already fed into
a result. That means changing a saved finish; changing a race's start time or
number, or removing the race, once the race has finishes; or changing a
series' settings or entries, or the base number of a boat entered in it, once
the series has any finishes.

- A correction needs a **reason** (free text, for example "protest upheld" or
  "misread the sheet"). If it's missing, the save is rejected with a message
  and nothing changes.
- Anything else is recorded without a reason. That covers entering a finish for
  the first time and setting up a series before any race has been sailed.
- Saving a form without changing anything records nothing and needs no reason.

### Data model (needs your approval; see Guardrails in CLAUDE.md)
One new model, `ScoringChange`, which is added to only and never edited:

- `timestamp`, which is set automatically.
- `user`, a foreign key to the user, set to null if the user is deleted. There
  is also `user_name`, a copy of the username, so the record still says who
  made the change after the account has gone.
- `series`, which is deleted along with its series. A boat's base-number change
  writes one row for each series the boat is entered in, so every series'
  history is complete without looking anywhere else. If the boat isn't entered
  in any series, it gets one row with no series.
- `race`, set to null if the race is deleted. It's used to mark a race as
  amended and to filter the history.
- `kind`, which is one of finish, race, series, entry or boat.
- `action`, which is added, changed or removed.
- `description`, which says what was changed as it read at the time, for
  example "GBR 1234 Zephyr, Race 3". It is kept as text because the record may
  since have been renamed or deleted.
- `changes`, the old and new value of each field, formatted for display, for
  example `{"Finish time": ["14:32:10", "14:23:10"]}`. This is a JSONField,
  which works on SQLite and PostgreSQL alike.
- `is_correction` and `reason`. There is a check constraint so that a
  correction always has a reason.

It deliberately has no foreign key to Finish. The history has to outlive the
rows it describes, and deleting a race removes its finishes along with it.

Changes are recorded by the code that saves them, in the finish-entry view and
in admin hooks, not by model signals. A signal can't see who made the change or
why. A single helper in `races/audit.py` saves the change and its
`ScoringChange` rows in one transaction, so there is never one without the
other.

### Screens
- **Finish entry.** A row that already has a saved finish also shows a reason
  box. Once the row has been corrected, it shows what changed as a result, for
  example: "Corrected. Race 3 places changed; handicaps changed in races 4-6;
  standings changed." This is worked out by scoring the series before and after
  the save and comparing the two, which costs microseconds, and the comparison
  is not stored.
- **Admin.** The Boat and Series forms, including the entry and race rows on
  the Series form, get a "Reason for change" box. It is required only when the
  save is a correction. Removing a race, entry or series from the admin's
  change list goes through the same recording code. After a correction, a
  message on the admin page says which results changed, using the same
  comparison.
- **History (staff only).** One page per series, newest first. Each change
  shows when it was made, who made it, which race and boat, the old and new
  values, and the reason. It can be filtered to a single race. It's linked from
  the finish-entry page and from the series in the admin.
- **Results (public).** A race with a correction is labelled "Amended" with the
  date of its latest correction. If the series' settings, entries or a boat's
  base number have been corrected, the standings are labelled the same way.
  The public page never shows who made a change or why.

## Acceptance criteria
- Every change listed in the table above is recorded, with its old and new
  values, who made it and when. Nothing outside the table is recorded.
- A correction without a reason is rejected with a message, and nothing is
  saved. A first entry or setup before any race has been sailed needs no
  reason.
- A save that changes nothing records nothing.
- History survives the deletion of the finish, race, entry or user it
  describes. It is deleted only when its series is deleted.
- After a finish is corrected, the row shows which races and standings the
  correction changed. It is tested as a sweep across a multi-race series, not
  a single example.
- The history page needs a staff login. The public results page labels amended
  races and standings, and doesn't show who made a change or why.
- The change and its history rows are saved together or not at all. This is
  tested by forcing a failure part-way through.
- Migrations use nothing specific to SQLite or PostgreSQL.

## Out of scope
- Undoing or reverting a change from the history page. A correction is made by
  entering the right value again, which is itself recorded.
- Recreating past results as they stood at some earlier date. The history
  makes this possible later, because replaying a series always gives the same
  answer, but it isn't built here.
- Clearing a saved finish back to "nothing saved". The way to correct one is to
  record the right code, for example DNC.
- Backfilling history for finishes saved before this slice.
- Two staff users editing the same row at the same time, where the later save
  wins.
- Auditing boat details that don't affect a score. The admin's own History
  button already shows who changed those, and when.
- Member accounts and roles (slice 3), and emailing results (slice 4).
