## Slice 0 - the scoring engine as a pure Python package. **Status: complete (2026-09-23)**

Acceptance criteria, from `docs/slices/00-scoring-engine.md`:

- [x] All fixtures in `tests/fixtures/` produce the expected results exactly.
      Includes the RYA's own published worked examples, SCEN-005 (club
      adjustment) and SCEN-006 (realignment), both reproducing to 3 d.p.
- [x] Changing any finish and re-scoring gives correct downstream handicaps.
      Tested as a sweep over all fourteen timed finishes in a four-race series,
      not a single worked example - see `tests/test_recalculation.py`.
- [x] Non-finishers are scored per RRS Appendix A and do not have their
      handicap adjusted. In a club series. A regatta *does* adjust them, by
      back-calculating an elapsed time, which is what spec section 4 requires.
- [x] Public interface documented in the package README. `tests/test_readme.py`
      runs the documented example and checks its output, and asserts every
      exported name appears in the text.

`nhc/` is 1,573 lines across ten modules, with 569 tests. It imports nothing
outside the standard library and does no I/O, enforced by
`tests/test_package_purity.py`.

**One partial gap against the stated scope.** The scope line reads "races with
start times", but the engine takes elapsed seconds and leaves deriving those
from a start and a finish to the caller. Every formula in the RYA spec works in
elapsed time, and the moment a race has more than one start - explicitly out of
scope here - the caller has to decide which start applies anyway. It is the
open question on clock times in `docs/decisions.md`, and it lands naturally in
slice 1 where races gain real start times.

Known gaps, all recorded in `docs/decisions.md`: RRS A6.1 and the scoring codes
beyond FINISHED/DNC/DNS/DNF that would let it fire; A2.1's discard schedule;
and the brief's "adjusted" option for non-finishers in a club series.

No Django, no database. Plain functions that take a series' race history (boats, base handicaps, starts, finishes) and return race handicaps, corrected times, results and standings. Build it test-first against your worked examples. This is where Claude Code shines: give it the reference docs and the fixtures, tell it the tests are the spec, and let it iterate until they pass. You review the logic, not the plumbing.

## Slice 1: walking skeleton. **Status: complete (2026-09-23)**

Acceptance criteria, from `docs/slices/01-walking-skeleton.md`:

- [x] A staff user can create boats, a series with its four settings, its
      entries and its races through the admin. Entries and races are inline on
      the series; `races/test_admin.py`.
- [x] A staff user can record a finish time or a code for every entered boat
      on one page, and an invalid row is rejected with a message without
      affecting other rows. Each row saves alone over HTMX, with a plain-POST
      fallback; `races/test_views.py`.
- [x] The results page shows each race's results and the series standings as
      the engine computes them. SCEN-005, loaded through the database as clock
      times, reproduces the RYA's published handicaps; `races/test_scoring.py`.
- [x] Changing a saved finish changes that race and every later race on the
      next page load. Nothing is stored, so there is nothing to go stale.
- [x] Enforced by the database: sail numbers unique ignoring case and spaces;
      a time or a code, never both; one finish per entry per race; race
      numbers unique within a series.
- [x] Finish entry and setup need a staff login; results do not.
- [x] Migrations use nothing database-specific. The app's tests and the
      migrations were also run against PostgreSQL 16 by hand; CI runs SQLite
      only.

Manual check: seeded the SCEN-005 fleet, entered race 2 through the
finish-entry page in headless Chromium, and read the results page back.

Worth knowing: the finish-time box is the browser's own time input, so it
shows 12- or 24-hour time depending on the browser's locale. What it submits is
always 24-hour, so this is a display question, not a data one.

A Django app with Boat, Series, Race and Finish models, admin-style forms for the race committee to enter finish times, and a results page that calls the engine. Django with HTMX would suit this well; it's server-rendered and form-heavy, with no real need for a JavaScript framework.

## Slice 2: corrections and audit. **Status: complete (2026-09-23)**

Acceptance criteria, from `docs/slices/02-corrections-and-audit.md`:

- [x] Every audited change is recorded with old and new values, who and when;
      nothing outside the audited fields is. `races/test_audit.py` changes each
      audited field through the finish-entry page or the admin, and pins the
      field list so a new one comes with a test.
- [x] A correction without a reason is rejected with a message and nothing is
      saved - finish rows, series settings, race rows, entries and base
      numbers. First entries and setup before any race is sailed need none.
      The database also refuses a correction row with no reason.
- [x] A save that changes nothing records nothing.
- [x] History survives deleting the finish, race or user it describes, and is
      deleted only with its series.
- [x] After a correction the finish row (and the admin) says which places,
      handicaps and standings moved. Tested as a sweep over all twelve
      finishes in a three-boat, four-race series.
- [x] The history page needs a staff login. Public results label amended races
      and standings, without who or why.
- [x] A change and its history rows are saved together or not at all, tested
      by making the recording fail after the change was written.
- [x] Migrations use nothing database-specific. The app's tests were also run
      against PostgreSQL 16 by hand; CI runs SQLite only.

Manual check: seeded a three-race series, then in headless Chromium corrected a
finish without and then with a reason, corrected a race start time in the
admin the same way, and read the history page and the public results back.

Follow-up, the same day: races with nothing recorded are no longer scored, a
regatta race waits for its first finish time instead of crashing the pages,
and the admin refuses start times after saved finishes and renumbers races
without colliding. See the two newest entries in `docs/decisions.md`.

Editing a finish and seeing everything downstream recalculate, with a history of what changed and who changed it. Race committees will need this on day one of real use, so it's worth doing early.

## Slice 3: member self-service. **Status: complete (2026-09-24)**

Acceptance criteria, from `docs/slices/03-member-self-service.md`:

- [x] Someone can sign up and cannot log in until the administrator approves
      the account, and is told why - but only if they give the right
      password, so the login never reveals which emails have signed up.
- [x] A member can register a boat, request a change, claim a boat on record
      and request a series entry, and see each request's status and note.
      None of these changes anything until approved.
- [x] The committee approves or rejects each kind. Approving applies exactly
      what was asked, records it in the change history under the committee
      member's name, and needs a reason where it is a correction. A request is
      decided once, and is validated again at approval time.
- [x] A member sees and acts on only their own boats and requests, tested by
      trying another member's by URL (a 404, not a 403).
- [x] The committee cannot see or change accounts or groups; the
      administrator can.
- [x] Every page is tested as each of the four roles (`races/test_roles.py`).
- [x] Migrations use nothing database-specific. The app's tests were also run
      against PostgreSQL 16 by hand; CI runs SQLite only.

Manual check: in headless Chromium, signed up, was told to wait, approved the
account as the administrator, registered a boat and asked to enter a series as
the member, approved both as the committee, and checked the committee's admin
has no accounts section.

Accounts for members, boat registration requests, and series entry. This is where auth and permissions appear, so write the role rules into the brief before starting it.

## Slice 4: notifications. **Status: complete (2026-09-24)**

Acceptance criteria, from `docs/slices/04-notifications.md`:

- [x] A race is provisional until published, and the public page says so.
- [x] Publishing emails the race's results to every owner of a boat entered in
      the series, one email each, and to nobody else.
- [x] After a published race's results change, the committee sees it was
      amended since the results were sent and can send updated results.
      Nothing is sent automatically. A correction to an earlier race or to the
      whole series amends it; a later race's does not.
- [x] Each email is sent when, and only when, its event happens, tested per
      email, including the "no duplicates" rule.
- [x] A rolled-back change sends nothing; a sending failure keeps the change,
      says so on the page, and offers to send again.
- [x] Password reset by email, never revealing whether an address has an
      account.
- [x] The user manual covers publishing results, the emails members receive,
      and resetting a password.
- [x] Migrations use nothing database-specific.

Manual check: the screenshot script publishes a race, corrects a finish and
sees it marked amended, in headless Chromium, against the running site; the
emails were read as the console printed them.

Still to do before members receive email on the live site: choose an email
provider and set it up on Render (`docs/deploying.md`, "Sending email").

Emailing results after a race is published.

## Slice 5: results webapp. **Status: complete (2026-09-24)**

Acceptance criteria, from `docs/slices/05-results-webapp.md`:

- [x] `results/` has no models, no migrations and only GET views, every page
      runs only SELECT queries, and `races` imports nothing from it;
      `results/test_read_only.py`.
- [x] Every page shows what `score_series` computes. SCEN-005, loaded through
      the database, reads back from the series page and every boat's page,
      including the next handicap; `results/test_scen_005.py`.
- [x] Search, choosing a race, following a boat and "More detail" each return
      a fragment over HTMX and the whole page without it, at the same URL,
      and the whole page holds the same fragment. A history restore gets the
      whole page.
- [x] Search matches sail numbers ignoring case and spaces and names ignoring
      case; an empty or unmatched search says so.
- [x] Series with no entries, no races, unscored races, or that the engine
      refuses show a message on every page instead of crashing.
- [x] An unknown series, boat, race number or followed boat is a 404.
- [x] Every page tested as each of the four roles; only the committee sees
      committee links.
- [x] No public page shows an owner's name, typed or from an account.
- [x] `/` and `/series/<pk>/` are served by `results`; nothing refers to
      `races:home` or `races:series_results`.
- [x] Usable at 375 px wide, checked in headless Chromium, with screenshots
      in the manual.
- [x] The manual gains "Finding your results"; the publishing page is updated
      for the new series page.

Manual check: in headless Chromium at 375 px, searched as I typed, opened a
boat, chose races and followed a boat on the series page (the URL kept both),
went back twice through the browser's history, opened "More detail", and did
the same with JavaScript off. No page scrolls sideways and no JavaScript
errors were logged.

Another Django app (in the same project) with an HTMX page that allows a racer to easily view race results.
## Slice 6: race-level entry. **Status: complete (2026-09-24)**

Acceptance criteria, from `docs/slices/06-race-entry.md`:

- [x] The committee puts boats on a race's start sheet, takes them off and
      records persons on board. Each row saves on its own over HTMX and with
      JavaScript off, and an invalid row changes nothing;
      `races/test_start_sheet.py`.
- [x] A finish for a boat not on the start sheet is refused, by the page and
      by `Finish.clean()`, and a boat with a result can't be taken off (the
      row says to correct it to DNC).
- [x] The data migration gives every past race a start sheet, and every
      race scores the same as before it.
- [x] A boat on the start sheet with nothing recorded shows as "Not
      recorded" (NR on the public tables) and scores exactly as a boat left
      off does.
- [x] Publishing and sending updated results are refused, naming the boats,
      while any boat on the start sheet has nothing recorded, including one
      added after publishing.
- [x] Emails on being put on and taken off a start sheet, and on removal
      from a series (one email, not one per race), each tested for when it
      is and isn't sent, rollback and sending failure.
- [x] Persons on board appears on no public page.
- [x] Start sheet changes add nothing to the change history and don't mark
      a race amended.
- [x] The start sheet page is tested as each of the four roles.
- [x] The database refuses a boat twice in one race and persons on board
      outside 1-99. The model refuses a boat from another series.
- [x] Migrations use nothing database-specific. The app's tests, including
      both migrations, were also run against PostgreSQL 16 by hand; CI runs
      SQLite only.
- [x] The manual gains "Race day: the start sheet and finishes", with
      screenshots, and the members' email page lists the three new emails.

Manual check: in headless Chromium at 375 px, ticked a boat and set persons
on board with JavaScript on, took it off again with JavaScript off, saved a
finish and read the publishing box's "Still to record" list, and read race 4
on the public series page. No page scrolls sideways and no JavaScript errors
were logged.

Found while building, and recorded in the spec: a saved finish can't be
cleared, so a boat with a result is corrected to DNC rather than taken off;
a late boat's first finish needs no reason (slice 2's rule), though it still
marks the race amended; and "Not recorded" is NR on the public tables so it
fits a phone.

A start sheet for every race: the committee records which boats in the
series are racing (the brief's user journey 3). Owners are emailed when their
boat is put on or taken off a start sheet, or removed from a series.

## Slice 7: visual styling. **Status: complete (2026-09-24)**

Acceptance criteria, from `docs/slices/07-visual-styling.md`:

- [x] Every page uses the new styles, checked in headless Chromium at
      1000 px and 375 px as the role that sees it. No page scrolls
      sideways at 375 px, and the boat page's results table now fits its
      box.
- [x] Behaviour is unchanged: every existing test passes with no change to
      what it asserts, and the same page checks pass with JavaScript off.
- [x] Every colour is a token. `races/test_styles.py` checks 38 text and
      background pairs against WCAG AA, and that no colour is written
      outside `:root`.
- [x] Every link, button and field reached with the keyboard shows a focus
      outline, checked by tabbing through each role's first page.
- [x] Buttons, race buttons and header links are at least 44 px tall at
      375 px.
- [x] Pages load only the site's own files, and the error page loads
      nothing; tested.
- [x] The Django admin and the emails are unchanged.
- [x] Every manual screenshot is regenerated. The manual's descriptions of
      how things look (the blue next-handicap box, a saved row turning
      green) still hold.

Manual check: screenshots of every page at both widths, as the public, a
member and the committee, with JavaScript on and off.

Found while checking: the base input style sat above each form's own
sizes, so it now lives in `:where()`. The finish time box was widened for
browsers that show a 12-hour clock with seconds.

Still true on a phone: the "My requests" table on My boats has five text
columns, so it scrolls sideways inside its own box, as wide tables are
designed to. The page itself does not.

A clean, simple, modern look for every page of the site: neutral nautical
colours, the device's own font, light only, and the Django admin left as it
is.

## Slice 8: other handicap systems. **Status: on hold (2026-09-24)**

Spec: `docs/slices/08-handicap-systems.md`, a draft parked by the project
owner before any code was written. It proposes data model changes, not yet
approved, and lists the open questions to answer before building.

A series chooses its handicap system: NHC as today, Portsmouth Yardstick or
RYA YTC. PY and YTC are fixed numbers, so nothing moves after a race. Places,
points and standings are RRS Appendix A under all three.

## Slice 9: the race day page. **Status: complete (2026-09-24)**

Acceptance criteria, from `docs/slices/09-race-day-page.md`:

- [x] One page per race, `/races/<pk>/`, with Start sheet and Finishing
      views, committee only. The two old addresses redirect to it, no link
      points at the old pages, and it's tested as each of the four roles.
- [x] The start sheet view passes every slice 6 test at its new address.
- [x] Tapping Finished records the site's local time in whole seconds
      (tested with a fixed clock) as an ADDED change with no reason. It's
      offered only on the race's date from its start time.
- [x] A tap before the start, on another day, or for a boat not racing is
      refused. A second tap changes nothing and says when the boat finished.
- [x] Finished boats are in order across the line, then codes. Two boats
      tapped in the same second stay in tap order.
- [x] Undo is offered for two minutes (tested at 1:59 and 2:01), needs no
      reason, and records a REMOVED change marked as an undo. It's refused on
      a published race, after two minutes, and for finishes saved before
      this slice.
- [x] Typed times and codes work from both lists, with and without
      JavaScript, under the usual correction rules.
- [x] Refreshing: 204 when nothing changed, the lists after a change, and
      no refresh while a form is open, checked with two browsers.
- [x] The race clock shows the site's time with the device clock 37 minutes
      fast. The page works fully with JavaScript off.
- [x] Scoring, publishing, "not recorded" and the emails are unchanged.
- [x] Usable at 768 px and 375 px, with no page scrolling sideways.
- [x] Migrations use nothing database-specific. The app's tests were also
      run against PostgreSQL 16 by hand; CI runs SQLite only.
- [x] The manual's race day page is rewritten, with new screenshots,
      including checking the clock against the officer's watch and Undo.

Manual check: in headless Chromium on a race dated today, a tablet tapped
boats while a phone saw them arrive by polling. The phone held a typed time
while its form was open for seven seconds, and refreshed once it closed. An
Undo put a boat back, and the page did the same with JavaScript off.

Existing tests moved to the new address. Six assertions tied to the old
pages' layout were updated to the new one; the commit message lists them.

One page per race replaces the start sheet and finish-entry pages: tick who
is racing, then tap **Finished** as each boat crosses the line.

## Slice 10: final results and export. **Status: complete (2026-09-25)**

Acceptance criteria, from `docs/slices/10-final-results-and-export.md`:

- [x] The committee declares a series final on its Final results page. It's
      refused, naming the races and boats, while a race with results is
      unpublished, amended since sent, or has a boat not recorded. Races not
      sailed are listed and don't block. Who, when and a "Declared final"
      history entry are recorded.
- [x] Every write path refuses a final series and writes nothing, tested
      path by path:
      - finish, tap, Undo and the start sheet, with and without HTMX;
      - publishing;
      - five admin changes (settings, a race's start, adding a race, adding
        and removing an entry);
      - approving an entry request.
- [x] A boat's base number and the series' name can still be changed.
- [x] A final series scores identically from its copy (SCEN-005, and a
      series with codes, ties and discards). A base number change after
      declaring leaves it exactly as declared, while another series moves.
- [x] Reopening needs a reason, unlocks the series and drops the copy.
      Declaring again makes a new copy and sends "Updated final standings".
- [x] The email:
      - goes once to each active owning account;
      - isn't sent on a rolled-back declaration or on reopening;
      - after a sending failure, the series stays final and the page offers
        Send again.
- [x] The series, home and boat pages label a final series Final.
- [x] The CSV:
      - anyone can download it, as UTF-8 with a byte-order mark;
      - it matches the series page and SCEN-005;
      - it keeps a final series' places;
      - it has no owner names or persons on board;
      - it says final or provisional, and handles an empty series.
- [x] `results/test_read_only.py` still passes. Both new pages are in the
      four-role test.
- [x] Migrations use nothing database-specific. The app's tests were also
      run against PostgreSQL 16 by hand; CI runs SQLite only.
- [x] The manual gains "Ending a series: final results", with four new
      screenshots. "Finding your results" gains the Final label and the
      download, and the email page lists the two new emails.

Manual check: in headless Chromium at 375 px, on the manual's sample data:
- declared the Summer series final, and read the Final label on the public
  page;
- downloaded the CSV and checked its byte-order mark and contents;
- saw the race day page locked;
- reopened the series with JavaScript off.

No page scrolls sideways. The email was read as it renders.

Found while checking: the race day page's "This series is final" note had
been placed inside the view buttons, which pushed the page sideways on a
phone. It now sits below them, and a test checks where it is.

The brief's user journey 5. The committee declares a series final: it is
locked, a copy of its results is kept, and the owners are emailed their
final places. Anyone can download any series as one CSV file.

## Slice 11: a service for many clubs. **Status: planned (2026-09-25)**

Spec: `docs/slices/11-multi-club-service.md`. It proposes a new data model
(clubs, memberships, invitations and an operator log, with a club on every
row), which needs the project owner's approval, and lists six open questions
to answer before building.

It turns the single-club site into a service that hosts many clubs:
- one database, with the club on every row;
- a subdomain per club;
- one login across clubs, with a role at each;
- clubs set up by the operator (the project owner);
- one email provider, Sentry and a health check;
- the UK GDPR essentials.

It is built and merged in five parts:
1. clubs and isolation;
2. people and roles per club;
3. the operator's pages;
4. running it in production;
5. data protection.

Production hosting is deferred to a later slice; the code stays independent
of any particular host.
