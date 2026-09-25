# Slice 10: Final results and export

## Goal
The brief's user journey 5: "At the end of a race series, the race committee
administrator initiates the final scoring calculation for the entire series.
This generates final places in the series based on scores accrued by the
boats during the season. These results are displayed on screen as well as
being exportable in a file."

Today a series is never finished. Its standings are recalculated on every
page load, so they can move at any time, and a later correction to a boat's
base number would even change a season that ended years ago. This slice lets
the race committee **declare a series final**:
- its standings become the final places, labelled as such;
- it is locked, so nothing in it can change;
- a copy of its results is kept, so they stay exactly as declared;
- the owners are emailed their final places.

Anyone can **download** any series' standings and race results as a CSV
file.

## Scope

### Declaring a series final *(agreed with the project owner)*
- **Where:** a new committee-only page per series, **Final results**, at
  `/series/<pk>/final/`. It's linked from the series results page's
  committee links and from the series in the admin. It sits in the `races`
  app, because `results/` never writes.
- **What the page shows before declaring:**
  - the standings as they stand now;
  - a checklist of what still blocks declaring;
  - a **Declare final** button.
- **Declaring is refused while any of these is true.** The page names the
  races and boats:
  - a race with results isn't published yet;
  - a published race has been amended since its results were sent (slice 4);
  - a boat on a start sheet has nothing recorded (slice 6).
- **Races not sailed don't block.** A race with nothing recorded is already
  left out of the scoring (an earlier decision), for example one cancelled
  for weather. The page lists them as "not sailed: left out of the final
  standings", so nobody is surprised.
- **Declaring:**
  - records who declared it and when;
  - saves the copy of the results (see below);
  - adds a "Declared final" entry to the series' change history;
  - emails the owners.

  All of it is saved together or not at all. The email is sent after saving,
  as every email is (slice 4).

### Locked *(agreed with the project owner)*
While a series is final, **nothing that could move its results can change**:
- **Finishes:** saving, tapping Finished and Undo on the race day page, and
  corrections.
- **Start sheets:** putting a boat on or taking it off, and persons on board.
  None of these moves a score, but the start sheet is part of the record,
  and publishing already depends on it being complete.
- **Races:** adding, deleting and changing them (date, start time, number),
  and publishing or sending updated results.
- **Entries and settings:** entering or removing a boat, and the series'
  settings, in the admin and through a member's entry request. An entry
  request for a final series is refused when approved, with a note that
  says why. The lock is checked before the "give a reason" check, so the
  committee is told the series is final rather than asked for a reason.
  *(Found while building.)*

Each is refused with the message "This series is final. Reopen it to make
changes.", on the page or the admin form. **Nothing is written.**

The one check lives in `races/final.py` and every write path calls it, like
the audit code. It is tested path by path, the same way slice 2 tests every
audited field.

**What stays open:**
- **Boats can still be changed**, including their base number. A boat sails
  in other series too, and the copy (below) keeps the final series as it
  was.
- **Series names** can still be changed. A name moves no score.

### Reopening
- **Who:** the committee, on the Final results page. **Reopen** needs a
  reason, which is recorded in the change history, as for a correction.
- **After reopening:**
  - the copy is dropped, and the series is scored live again;
  - the public pages go back to showing the standings as they stand now,
    not final;
  - the owners aren't emailed.
- **Declaring it final again** makes a new copy, and emails the owners
  again, labelled as updated final standings.

### The copy of the final results *(agreed with the project owner)*
- **Why a copy is needed:** results are never stored; every page replays the
  series through the engine (slice 1). A boat's base number is shared by
  every series it sails in, so a later correction would replay a final
  series differently. So for a final series, and only a final series, the
  engine's output is kept.
- **What's saved:** the engine's full result for the series (every race's
  results and the standings) as JSON, in the database, when it is declared
  final. JSON works the same in SQLite and PostgreSQL.
- **Scoring a final series:** `races/scoring.score_series` rebuilds the
  engine's result objects from the copy instead of replaying. The pages, the
  CSV and the emails all get their numbers from `score_series`, so they
  can't disagree with each other, and none of them needs to know where the
  numbers came from.
- **Testing the copy:** a series declared final and then read back scores
  identically to the live replay. It is tested on SCEN-005 loaded through
  the database, and on a series with codes, ties and discards.
- **Recorded as a decision:** this deliberately bends slice 1's "nothing
  derived is stored", for final series only. `docs/decisions.md` records it
  alongside the slice 1 decision.
- **What the copy doesn't hold:** boat names and sail numbers. They come
  from the boat as it is now, so a renamed boat shows its current name. The
  copy is of the results, not of the boats.

### What people see
- **The series page:**
  - A **Final** badge next to "Series Standings", and "Declared final on 12
    October 2026".
  - The places in the standings are the final places.
  - The per-race "Provisional" labels can't appear, because every race is
    published by then.
  - The "Last updated" note under the standings stays as it is.
- **The home page's list of series** marks final series as Final.
- **The boat page** marks a final series' results as final.
- **The committee** sees the declaring history on the change history page:
  "Declared final", "Reopened: <reason>".

### The email *(agreed with the project owner)*
- One email to each owner of a boat entered in the series, through
  `races/notifications`, sent after the declaration is saved.
- It gives the final standings as a short table, and says the owner's
  boat's place, with a link to the series page.
- On re-declaring, the subject says "updated final standings".
- It goes only to active owning accounts, as every email does.
- **If sending fails,** the series stays final, the page says the email
  wasn't sent, and it offers **Send again**. This works the same as
  publishing a race (slice 4).
- The members' email page in the manual lists the new email.

### The CSV download *(agreed with the project owner)*
- **Where:** a **Download (CSV)** link on every public series page, for
  anyone, final or not. It's served at `/series/<pk>/results.csv` by the
  `results` app. It's a GET that only reads, so it keeps to `results`'
  read-only rules.
- **One file, `<series name> results.csv`, in three blocks:**
  - **A heading block:** the series name, "Final standings (declared 12
    October 2026)" or "Provisional standings as at <date and time>", the
    scoring settings, and the date downloaded.
  - **The standings:** place, sail number, boat name, each race's points
    (discards in brackets, as on the page), and total.
  - **Each race in turn:**
    - a line naming the race, its date, and whether it's published;
    - then a row per boat: place, sail number, boat, finish time, elapsed,
      handicap used, corrected time, points, and code (DNF, DNC and so on);
    - "Not recorded" for a boat on the start sheet with nothing yet, as on
      the page.
- **Format details:**
  - Times as `H:MM:SS` and handicaps to three decimal places, so it reads
    the same as the page.
  - UTF-8 with a byte-order mark, so Excel shows accented boat names
    correctly.
- **Never in the file:** owner names and persons on board, as on every
  public page.
- **No new dependency:** Python's own `csv` module.

### Data model *(proposed; needs the project owner's approval before any
migration is written)*
All four fields are on `Series`, and none of them is editable in the admin
form:
- `declared_final_at`: `DateTimeField`, can be empty. Empty means not
  final.
- `declared_final_by_name`: `CharField`, can be blank. Who declared it,
  kept as text, like the change history does, so it survives the account
  being deleted.
- `final_results`: `JSONField`, can be empty. The copy.
- `final_results_sent_at`: `DateTimeField`, can be empty. When the final
  standings email went. Empty after a failed send, which is what offers
  **Send again**.

One migration, with nothing database-specific. Every existing series starts
not final.

*(Found while building.)* The same migration adds a choice, `FINAL`, to the
change history's kinds, for "Declared final" and "Reopened". Neither moves a
score, so neither should mark races "amended since sent" or move the
standings' "Last updated" date. Their own kind lets both leave them out.
Adding a choice changes no column.

## Acceptance criteria
- **Declaring:**
  - The committee can declare a series final on its Final results page.
    It's refused, naming the races and boats, while a race with results is
    unpublished, amended since sent, or has a boat not recorded.
  - Races not sailed are listed and don't block.
  - Declaring records who and when, and adds a "Declared final" entry to the
    history.
- **Locked:** every write path listed under "Locked" refuses a change to a
  final series with the message, and writes nothing. It's tested path by
  path: the race day page (finish, tap, Undo, start sheet), publishing, the
  admin (series settings, races, entries), and approving an entry request.
- **Still open:** a boat's base number, and the series' name, can still be
  changed.
- **The copy:**
  - A final series scores identically from the copy and from a live replay
    (SCEN-005 through the database, and a series with codes, ties and
    discards).
  - Changing a boat's base number after declaring leaves the final series'
    places, points and handicaps exactly as declared, while a series that
    isn't final changes.
- **Reopening:**
  - Needs a reason and records it.
  - Unlocks the series and drops the copy, so it scores live again.
  - Declaring it final again makes a new copy and sends the "updated" email.
- **The email:**
  - Sent to each active owning account of a boat entered, once per
    declaring, and not when reopening.
  - Not sent on a rolled-back declaration.
  - A failure keeps the series final and offers **Send again**.
  - Each case is tested, as in slice 4.
- **Labels:** the series page, the home page and the boat page label a final
  series Final, and say when it was declared.
- **The CSV:**
  - Downloadable from every series page by anyone, as UTF-8 with a BOM.
  - Its standings and race rows match what the series page shows (tested on
    SCEN-005, and on a final series after a base number change).
  - It contains no owner names or persons on board.
  - It says final or provisional.
  - A series with no races or no entries gives a file that says so, not an
    error.
- **Read-only:** `results/test_read_only.py` still passes. The CSV view is
  GET-only and runs only SELECTs.
- **Roles:** the Final results page is tested as each of the four roles, and
  only the committee and the administrator can open it.
- **Migration:** uses nothing database-specific. The app's tests are run
  against PostgreSQL 16 by hand, as before.
- **Manual:**
  - A new committee page, "Ending a series: final results", with
    screenshots.
  - "Finding your results" gains the Final label and the download.
  - The members' email page lists the final standings email.

## Out of scope
- The brief's API.
- Excel (`.xlsx`) or PDF export. The CSV opens in every spreadsheet
  program.
- Carrying handicaps over from a final series into the next one. That's the
  earlier "carries over / resets" setting, still deferred.
- Declaring a single race final. Publishing already covers races.
- Archiving or hiding old series.
- Prizes, trophies or prize-giving lists.
- A snapshot of boat names and sail numbers.
