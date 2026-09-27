# Slice 18: the race office (club users leave the Django admin)

**Status: planned (2026-09-27). Waiting on the owner's answers to the
questions at the end.**

## Goal
Nobody at a club uses the Django admin any more. Everything the race
committee does there today gets a page of its own, built like the rest of the
site (the site's stylesheet, plain server-rendered forms, HTMX where it
helps), and the club's menu is rearranged around it.

The Django admin looks and behaves differently from every other page. It
talks in Django's words ("Add series +", "Save and continue editing"), puts a
whole series on one long form with two inline tables sharing one reason box,
and has its own login, messages and history. A race officer shouldn't need
to learn a second website to set up a series.

No model or migration (subject to question 4), no new dependency, no
hand-written JavaScript. The operator keeps the Django admin on the service's
own address for accounts (question 3).

## What club users do in the admin today
Found by reading `races/admin.py`, `races/admin_forms.py`,
`templates/admin/index.html` and the manual:

| Job | Where today | Who |
|---|---|---|
| See what's waiting (requests, people joining) | Admin front page notices (also on every site page) | Committee, administrator |
| List and search boats | Boats list: sail number, name, make, model, base number, owner | Committee |
| Add or edit a boat, set its owner | Boat form, with a reason box; owner emailed; "what this changed" message | Committee |
| Delete a boat | Admin delete (refused once it's in a series: `PROTECT`) | Committee |
| Create a series, set its scoring rules | Series form, "Scoring rules" section | Committee |
| Enter boats in a series, remove them | Series form, entries inline (autocomplete); owners emailed; removal refused once the boat has results | Committee |
| Add, renumber, re-time or remove races | Series form, races inline; swapping two numbers works | Committee |
| Reach a race's Race day page | Link in each race row | Committee |
| Reach Series history, Finalise / Reopen results | Links in the series form's "Corrections" section | Committee |
| Delete a series | Admin delete (takes its races, finishes and history with it) | Committee |
| Look back at decided requests | Read-only Boat requests / Entry requests lists | Committee |
| See who changed a boat's name, make etc. | Admin's own History button (Django's log) | Committee |

Everything else a club user does (race day, publishing, final results,
change requests, club members, My boats, My account) is already on the site.

## Page architecture

### The race office
A new committee-only area, **Race office**, at `/office/`, replaces
**Club setup** (the admin) in the menu (name: question 1). All its pages use
`committee_required` and look up rows through `for_club`.

```
Race office  /office/
├── Waiting for you             (the existing notices, with their links)
├── Coming up                   next races: date, series, Race N, Race day page
├── Series                      each series: name, type, races, boats entered, Final?
│   └── New series
└── Boats                       link, with the number of boats

Boats        /office/boats/              list + search
├── Add a boat                  /office/boats/new/
└── A boat                      /office/boats/<pk>/   edit (and delete, question 5)

A series     /office/series/<pk>/
├── Settings                    summary + Change settings  → /office/series/<pk>/settings/
├── Races                       table + Add a race         → /office/series/<pk>/races/new/
│     each: Race day page · Change → /office/races/<pk>/ · Remove → /office/races/<pk>/remove/
├── Boats entered               list + Enter boats         → /office/series/<pk>/entries/
│     each: Remove                                         → /office/entries/<pk>/remove/
└── Links: Results (public page) · Series history · Finalise / Reopen results

New series   /office/series/new/
```

- **Coming up** lists races from today onwards across the club's open series,
  soonest first, at most 5, each linking to its Race day page. Today's race is
  marked **Today**. This is the quickest way onto the water on race night; the
  manual's race day page currently sends people through the admin.
- **The public series page** keeps its committee links (Finalise results,
  Series history, Race day page) and gains **Set up this series**, to the
  race office's page for it. The race office's series page links back with
  **Results**.
- The existing committee pages (Change requests, Series history, Finalise
  results, the race day page) stay where they are. Their addresses don't
  change.

### The menu
Recommended (question 1), same length as today:

| Who | Menu |
|---|---|
| The public | Club results · Log in · Sign up (unchanged) |
| Logged in, not yet a member | unchanged |
| Member | unchanged |
| Race committee | Club results · **Race office** · Change requests · My boats · My account · Log out |
| Club administrator | Club results · **Race office** · Club members · Change requests · My boats · My account · Log out |
| The operator (service's address) | unchanged: Clubs · Operator log · Accounts (admin) · Log out |

**Race office** goes where **Club setup** was. Slice 15's order is otherwise
kept.

## What gets built

### 1. The race office page
- `races/office_views.py` (new, one module for the area, like the others),
  template `templates/races/office/home.html`.
- The **Waiting for you** section reuses `context_processors.waiting_notices`;
  with nothing waiting it says "Nothing waiting."
- **Series** are listed open ones first (newest first), then final ones.
- `templates/admin/index.html` (the notices on the admin's front page) is
  removed; nobody at a club sees that page any more.

### 2. Boats
- **List** (`/office/boats/`): sail number, name, make, model, base number,
  owner, as the admin's list; sorted by sail number. A search box filters by
  sail number, name or owner, with HTMX answering from the same URL with just
  the table (the `_render` pattern in `results/views.py`), and working as a
  plain GET form without it.
- **Add a boat / change a boat** (`/office/boats/new/`, `/office/boats/<pk>/`):
  a site form built from `BoatAdminForm`'s fields, renamed `BoatForm` and
  moved to a new `races/office_forms.py`. It keeps everything the admin does:
  - sail number unique in the club, ignoring case and spaces;
  - owner chosen from the club's approved members, or an owner name typed for
    a boat with no account;
  - the base number audited (`audit.record`), with the owner emailed about
    every change (`notifications.boat_updated`, both owners when ownership
    changes);
  - after a correction, "what this changed" for each series the boat is in
    (`audit.describe_effect`), as a message.
- **The reason box** is shown only when the boat has results in some series
  (`audit.series_has_finishes` for any of its series), so adding a boat or
  fixing a new one's typo doesn't show a box that doesn't apply. It's still
  required only for a correction, as now.
- **Delete** (question 5).

### 3. Series
- **New series** and **Change settings**: `SeriesForm` (from
  `SeriesAdminForm`), same fields, same help text, grouped under **Scoring
  rules** as in the admin. Same rules: a regatta with a finisher threshold is
  refused; a final series allows only its name to change, and says why.
- The reason box, as for boats, only once the series has results.
- After a correction: "Correction recorded." and what it changed, as now.
- **Delete** (question 5).

### 4. Races
- **Add a race**: number (defaults to the next unused one), date, start time.
- **Change**: the same fields, one race at a time. Changing a number to one
  that's already used is refused ("Race 3 already exists in this series."),
  so swapping two races takes three changes via a spare number. The admin's
  "parking" code (`RaceInlineFormSet`) exists only for saving many rows at
  once and goes. Renumbering is rare, and a clear refusal is simpler than a
  swap feature.
- **Remove**: a confirmation page. A race with results needs a reason, and
  its finishes' removal is recorded (`audit.changes_to_delete`), as in the
  admin.
- Every race change is audited as now (`number`, `start_time`).

### 5. Entries
- **Enter boats** (`/office/series/<pk>/entries/`): a list of the club's boats
  not yet entered, each with a checkbox, and one **Enter** button. Owners are
  emailed (`notifications.entered_in_series`). Long lists get the same search
  filter as the boats list. Checkboxes are plain HTML, no script.
- **Remove**: a confirmation page. Refused with the admin's existing message
  when the boat has results ("...leave it entered: races it misses are scored
  DNC"). Otherwise audited and the owner emailed
  (`notifications.removed_from_series`), with a reason when the series has
  results (the A5.2 entry count moves).

### 6. Every write path stays locked for a final series
Each new form and view calls `final.check_series_open` as the admin's do.
While a series is final, its race office page hides Change / Remove / Add /
Enter and says "This series' results are final. Reopen results to change it."

### 7. Decided requests
The admin's read-only request lists go. The Change requests page's
**Recently decided** already shows the last 50; it gains a line "Showing the
50 most recent." when there are more. (A full archive is out of scope; the
club's data export has every request.)

### 8. The Django admin at a club's address
- `ClubAdminSite.has_permission` is false at every club address, and any
  `/admin/...` address at a club **redirects to `/office/`** (question 6), so
  old bookmarks and links in the manual land somewhere useful. `/office/`
  then sends the public to log in and gives anyone without the role a 403.
- `BoatAdmin`, `SeriesAdmin`, the inlines, `BoatRequestAdmin`,
  `EntryRequestAdmin`, `ClubScopedAdmin`, `ReasonInAdminHistoryMixin` and
  `admin_forms.py` go (question 3). `races/admin.py` keeps only the
  operator's account admin.
- The race day page's "No boats are entered in this series yet. Enter them
  in the admin." links to the series' **Enter boats** page instead.

## Tests
Plain pytest functions, mostly in new `races/test_office.py` (pages, menu,
permissions) and `races/test_office_forms.py` (validation, audit, emails):
- **Roles:** for every new URL, the public is sent to log in; a member, a
  person waiting to join and a committee member of another club get 403; the
  committee and administrator get the page. `races/test_roles.py` lists them.
- **Isolation:** every new URL added to `races/test_isolation.py`, with
  another club's boat, series, race and entry ids giving 404. Its
  every-module check covers `office_views.py` and `office_forms.py`.
- **Everything the admin tests checked, moved to the new pages:** the audit
  of every audited field through the new forms (`races/test_audit.py`),
  reasons required for corrections only, the "what this changed" messages,
  owner emails (`races/test_notifications.py`), the final-series locks
  (`races/test_final.py`), the regatta/finisher refusal, sail number
  uniqueness, owner choices limited to approved members, and entry removal
  refused with results.
- **New behaviour:** the reason box appears only once there are results;
  next race number; renumbering to a used number refused; Coming up lists
  only today onwards, at most 5, open series only; boat search with and
  without HTMX; the menu for each role.
- **The admin at a club:** `/admin/` and `/admin/races/series/` redirect to
  `/office/` for everyone; the operator still reaches the account admin on
  the service's address.
- Tests that went through the admin to set things up switch to the test
  builders or the new pages. `races/test_admin.py` is rewritten for what's
  left (the operator's account admin).

## Manual
- **New pages** under Race committee, before "Race day":
  - **The race office**: the page, Coming up, Waiting for you.
  - **Setting up boats**: adding, changing, owners, the reason box.
  - **Setting up a series**: new series, races, entering boats, removing
    things, what a final series allows.
  The manual has never described setup, because it was "the admin".
- **Updated:** `scoring-rules.md` (Change settings, not Club setup > Series),
  `race-day.md`, `publishing-results.md`, `ending-a-series.md`,
  `reviewing-requests.md`, `members-and-roles.md` (the admin's front page
  notices become the race office's), `index.md`, `mkdocs.yml`.
- **Screenshots:** `front-page-committee.png` and
  `front-page-administrator.png` become the race office's notices;
  `series-scoring-rules.png` is retaken from the new settings page; new ones
  for the race office, boats list, a boat's form, a series' page and Enter
  boats. `scripts/manual_screenshots/shots.js` stops visiting `/admin/`.

## Also
- `docs/decisions.md`: club users leave the admin (superseding slice 1's
  "setup in the admin"), the page architecture, the reason box shown only
  when it applies, renumbering, and the owner's answers.
- `docs/plan.md`: the slice's entry and status.
- `CLAUDE.md`: the Clubs and `races/` bullets describe the race office
  instead of `ClubScopedAdmin`; `docs/operating.md` likewise.

## Acceptance criteria
- A race committee member can do every job in the table above without
  opening the Django admin, and at a club's address the admin redirects to
  the race office.
- Every score-affecting change made on the new pages is in the history, with
  a reason where it's a correction; owners get the same emails as before.
- A final series can't be changed through any new page.
- Every new page passes the isolation and role checks.
- No model, migration, dependency or JavaScript is added (unless question 4
  is answered "yes").
- The manual's text, links and screenshots match the site; `mkdocs build
  --strict` passes; `ruff check .` and `ruff format --check .` pass; all
  tests pass.
- Checked by hand in a browser, as a committee member: set up a new series
  from nothing (boats, series, races, entries), run a race day from Coming
  up, correct a base number and a start time with reasons; every page at
  375px wide.

## Out of scope
- The operator's use of the Django admin for accounts (the service's own
  address). Replacing that is a later slice if wanted.
- Importing boats or races in bulk (e.g. from a spreadsheet), or copying a
  series.
- Starts for more than one fleet in a race (the model has one start time).
- Changing how scores, roles, requests or the race day page work.
- A full archive page of decided requests.
- Dropping Django's old admin log table (`django_admin_log`); its rows stay.

## Suggested parts
The slice is large, so it's built and checked in three parts, each leaving
the site working (the admin stays reachable until part 3):
1. **Boats**: the race office page (with Waiting for you and Series list
   linking to the admin for now), boats list, add, change.
2. **Series**: series page, settings, races, entries, Coming up.
3. **Switch over**: the menu, the admin redirect and removal, the manual and
   screenshots.

## Questions for the project owner
1. **The name and the menu.** **Recommended: "Race office"**, replacing
   **Club setup** in the menu, so the menu stays seven items at most. It's
   where race night starts (Coming up) as well as setup, which "Club setup"
   doesn't suggest. Alternatives: keep the name **Club setup**; or no hub
   page and separate **Series** and **Boats** menu items (eight for an
   administrator, crowded on a phone).
2. **Build it in three parts?** **Recommended: yes**, as above, each part
   reviewed before the next. Or all at once.
3. **The admin's boat, series and request pages for the operator.** Today
   the operator can browse every club's boats and series in the admin on the
   service's address. **Recommended: remove them too**; the operator has
   each club's data export, and fewer admin pages means less to keep in
   step with the site. Or keep them for the operator only.
4. **History of changes that move no score** (a boat's name, make, model,
   owner, lengths; a series' name; a race's date). Today only Django's own
   admin log records those, with who and when but not old and new values.
   **Recommended: don't replace it**: the score history stays as slice 2
   decided, and the boat's owner is already emailed with the old and new
   values of every change. Or record them too, which needs a data model
   change (a new kind of history row).
5. **Deleting boats and series.** The admin lets the committee delete a boat
   (only one never entered in a series) and delete a whole series with all
   its races, results and history. **Recommended:** delete a boat only if
   it's never been entered in a series, and delete a series only if no race
   in it has a result, each with a confirmation page. A series with results
   is kept (it can be made final instead). Or allow deleting any series, as
   now, behind a confirmation that says what will be lost.
6. **Old admin addresses at a club.** **Recommended: redirect** anything
   under `/admin/` at a club to the race office. Or answer "Not found".
