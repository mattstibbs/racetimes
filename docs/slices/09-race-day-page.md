# Slice 9: The race day page

## Goal
On race day the committee works from two pages: the start sheet (slice 6),
then the finish-entry page, where every finish time is read off a watch and
typed in. That works at a desk afterwards, but not on the committee boat or
the club balcony with a tablet, as boats cross the line seconds apart.

This slice replaces both pages with one **race day page** for each race. The
committee ticks who is racing, then taps **Finished** as each boat crosses
the line. The time is stamped on the spot and can be corrected by typing.
Boats move from "still racing" to "finished" as they cross, so it is always
clear who is still out.

Scoring, the start sheet rules, the change history and publishing all work
exactly as they do now. This slice changes how finishes are *entered*, not
what they mean.

## Scope

### One page per race *(agreed with the project owner)*
- **The race day page**, at `/races/<pk>/`, committee only, replaces the
  start sheet page and the finish-entry page.
- **Old addresses keep working:** `/races/<pk>/entries/` and
  `/races/<pk>/finishes/` redirect to it, so bookmarks and the admin still
  land in the right place.
- **Every link that went to either page** now goes to the race day page: the
  admin's race rows, the series page's committee links and the change
  history page.
- **Two views of the same page:**
  - **Start sheet**: tick who is racing.
  - **Finishing**: record finishes and publish.
  
  The chosen view is kept in the address (`?view=start` or `?view=finish`),
  and switching is a plain link that HTMX swaps in place. The page opens on
  Finishing once any boat is on the start sheet, and on Start sheet before
  that.
- **The start sheet view** works exactly as the slice 6 page did: the same
  rows, the same emails and the same rules. It just lives on this page now.

### The Finishing view *(layout agreed with the project owner)*
- **At the top:** the race, its start time, and a **race clock** (see
  below), then the publishing box, unchanged from slice 4 and slice 6.
- **Still racing:** each boat on the start sheet with nothing recorded, one
  large row per boat, in sail-number order so rows don't jump around while
  someone is aiming at them.
  - Each row has a large **Finished** button.
  - It also has a **⋯** control that opens the typed form: a finish time,
    or a code (DNF, DNS, DNC). It's a plain `<details>`, so no JavaScript
    is needed.
- **Finished:** each boat with a time, in the order it crossed the line
  (by finish time), numbered 1, 2, 3. Two boats tapped within the same
  second share a time, so they are kept in the order they were tapped.
  *(Found while building.)*
  - Boats with a code come after, in sail-number order.
  - Each row shows the finish time and the elapsed time.
  - It's labelled as the order across the line, not the results: corrected
    times and places are on the results page, a link away.
  - Each row has an **Edit** control that opens the same typed form, with
    the reason box. Changing a saved finish is a correction and needs a
    reason, as today.
- **Not racing (scored DNC):** collapsed at the bottom, as today.
- **On a tablet or phone:** every button is at least 44 px tall (slice 7),
  and the Finished buttons bigger still, so they're hard to miss on a moving
  boat.

### Tapping Finished *(agreed with the project owner)*
- **Tapping Finished records the finish time** as the moment the tap reaches
  the site: the club's local time (Europe/London), in whole seconds. The
  boat moves to Finished straight away, with its time shown, so a wrong
  time can be seen and edited at once.
- **Race day only.** The button appears only on the race's own date, from its
  start time on. On any other day, and before the start, a boat's row offers
  only the typed form, which is how results from a paper sheet are entered
  afterwards.
- **A finish must still be after the start,** and the existing checks still
  apply. A tap that fails a check changes nothing, and the row says why.
- **Two taps on the same boat record one finish.** The database already
  refuses a second finish for the same boat. A second tap, from this device
  or another, is answered "already finished at 20:05:31", with nothing
  changed.
- **How accurate it is:** to about a second on a good connection. It relies
  on the site's clock, which is set from the internet and doesn't drift, but
  the race officer's watch might. The race clock on the page shows the
  site's time, so the committee can compare the two before the first boat
  finishes and type times instead if they disagree. *(Stated in the manual.)*

### Undoing a wrong tap *(agreed with the project owner)*
- **Undo for two minutes.** For two minutes after a finish is saved, its row
  in Finished has an **Undo** button. Undo deletes the finish, and the boat
  goes back to Still racing.
- **No reason needed.** Undo is for the tap that landed on the wrong boat a
  moment ago.
  - Undo isn't offered once the race's results are published. A published
    finish is corrected, with a reason, as today.
  - After two minutes it's corrected the same way.
- **Both stay in the change history:** the finish being added and it being
  removed, under the committee member's name. The history is still a
  complete record, and "amended since sent" still reads it correctly.
- **This relaxes one slice 2 rule on purpose:** "a saved finish can't be
  cleared" becomes "a saved finish can't be cleared, except by Undo within
  two minutes on an unpublished race". Recorded in `docs/decisions.md`.

### Two devices at once *(agreed with the project owner)*
- **The Finishing view refreshes itself every 5 seconds** (HTMX polling, no
  extra JavaScript), so a committee member on the line and another at the
  desk each see the other's taps.
- **The server answers "nothing changed"** (HTTP 204, which HTMX doesn't
  swap) unless a finish or a start sheet row has changed since that page's
  last refresh, so an idle page costs almost nothing.
- **A refresh never wipes what someone is typing:** it pauses while any
  row's ⋯ or Edit form is open. This uses a filter on the `hx-trigger`
  attribute, which HTMX evaluates itself.
- **Scope:** the Start sheet view doesn't refresh itself. It's set up before
  the race, usually from one device.

### The race clock *(agreed with the project owner: the one JavaScript
exception)*
- **What it shows:** the time of day by the site's clock, and the elapsed
  time since the start, ticking every second.
- **How:** a small hand-written script, `static/js/race-clock.js`, with no
  library.
  - The page is served with the site's current time. The script works out
    how far the device's clock is from it, so the clock shows the site's
    time, which is the time a tap will record, even if the tablet's own
    clock is wrong.
- **Without JavaScript,** the clock shows the time the page was loaded and
  doesn't tick. Everything else works the same.
- **Recorded in `docs/decisions.md`** as the project owner's approved
  exception to "avoid JavaScript".

### Data model *(proposed; needs the project owner's approval before any
migration is written)*
- **One new field**, `Finish.recorded_at`, a `DateTimeField` that can be
  empty and isn't editable. It's set when the finish is first saved, whether
  tapped or typed.
  - It's what the two-minute Undo is measured from.
  - Finishes saved before this slice have none, so they never offer Undo.
- **Why not read it from the change history?** A `ScoringChange` row names its
  race but not its boat, except inside its description text. Undo would
  then depend on matching text, which a boat rename would break.
- **Nothing else changes.** The migration uses nothing database-specific.

## Acceptance criteria
- **One page:**
  - `/races/<pk>/` shows the Start sheet and Finishing views, committee only.
  - The two old addresses redirect to it.
  - No link in the project still points at the old pages.
  - Tested as each of the four roles.
- **The Start sheet view** passes every slice 6 test, moved to the new
  address, unchanged in what it asserts.
- **Tapping Finished:**
  - Records the current local time in whole seconds (tested with a fixed
    clock), moves the boat to Finished, and records an ADDED change with no
    reason.
  - Is offered only on the race's date from its start time; on other days,
    only typed times are offered.
- **Refused taps:**
  - A tap before the start, on another day, or for a boat not on the start
    sheet is refused, and nothing changes.
  - A second tap on a finished boat changes nothing and says when it
    finished.
- **Finished order:** boats with times are in finishing order, followed by
  those with codes, and the order matches the finish times recorded.
- **Undo:**
  - Offered for two minutes after a finish is saved (tested with a fixed
    clock at 1:59 and 2:01).
  - Deletes the finish, needs no reason, and records a REMOVED change.
  - Isn't offered, and is refused if forced, on a published race, after two
    minutes, or for a finish saved before this slice.
- **Typed times and codes** work from both lists, with and without
  JavaScript, with the same validation, correction and reason rules as
  today.
- **Polling:**
  - A refresh with nothing changed gets a 204.
  - After a change on another device, it gets the updated lists.
  - No refresh is triggered while a row's form is open (checked in headless
    Chromium).
- **The race clock** shows the site's time even when the device's clock is
  wrong (tested in headless Chromium with a skewed browser clock). The page
  works fully with JavaScript off.
- **Scores:** scoring, publishing, the "not recorded" rules and the emails
  behave exactly as before. Their existing tests pass unchanged.
- **Tablet and phone:** usable at 768 px and 375 px wide, with no page
  scrolling sideways, checked in headless Chromium.
- **Migration:** uses nothing database-specific.
- **Manual:** the race day page in the manual replaces the old start sheet
  and finishes pages, with new screenshots. It covers comparing the race
  clock with the officer's watch, and Undo. The publishing page's
  directions are updated.

## Out of scope
- **Finishing a boat by typing its sail number** on a keypad. It's quicker in
  a big fleet, and a natural next step.
- **Sound, vibration or photos** at the line.
- **Working offline,** and queuing taps when the connection drops. A tap
  that fails says so and can be repeated or typed.
- **Adjusting for a known difference** between the site's clock and the
  officer's watch.
- **More than one start per race,** pursuit races, and finishes after
  midnight (unchanged from slice 1).
- **Undo for anything other than a finish,** and Undo after publishing.
- **Showing live provisional places** on the race day page (the results page
  already has them).
- **Changes to scoring, the start sheet rules, publishing or emails.**
