# Slice 15: general UI improvements

**Status: complete (2026-09-26). The owner agreed every recommendation
(see the end).**

## Goal
A round of small improvements the project owner asked for after using the
site: less clutter on the results pages, clearer table headings, boats named
the way people know them, and a menu whose names and order say what each
page is for.

Every item is presentation only: no model, migration, new dependency or
JavaScript. Page addresses don't change, so bookmarks and links in emails
keep working.

## Naming rule
Menu items, page titles and headings capitalise **the first word only**, as
the rest of the site does ("My boats", "Club members", "My account"). The
owner confirmed this. Where the owner's list wrote "Club Results" or "Club
Members", this spec applies the rule.

## What gets built

### 1. No "My boats" on the results home page
- `templates/results/home.html` loses the "My boats" section, for everyone.
  People reach their boats from **My boats** in the menu.
- `results/views.py:home` stops looking up the person's boats.
- **Tests:** `results/test_views.py` has a test that a member sees their
  boats on the home page; it becomes "nobody sees a My boats section on the
  home page".
- **Manual:** `getting-started/finding-results.md` says your boats are on the
  front page; it points to **My boats** in the menu instead. No screenshot
  changes: `results-home.png` is taken logged out.

### 2. Table headings that stand out
- In `static/css/site.css`, the `th` rule changes from muted grey, 0.8rem,
  semi-bold to the main text colour (`var(--text)`), 0.9rem, bold. No new
  colours; the existing contrast test still covers it.
- Wide results tables already scroll sideways inside `.table-scroll`, so the
  bigger text can't widen the page on a phone. A long heading may wrap to
  two lines, which is fine.
- **Check:** in a browser at 375px wide, the series standings, a race's
  results with More detail, and a boat's page.
- The rule styles every table on the site (question 1).

### 3. The series page's links
Today the series page has "Download (CSV) · Final results · History" under
its title, and "Race day page · History" under each race's heading and date.
They become:

| Where | What | Who |
|---|---|---|
| Under the series title | **Finalise results** (was "Final results") | Committee |
| The race's heading and date | **Race day page**, unchanged | Committee |
| Directly under the race's results table, after its footnotes | **Race history** (was "History") | Committee |
| At the very bottom, below "Follow a boat" | **Download (CSV)** · **Series history** (was "History") | CSV: everyone; Series history: committee |

- Templates: `templates/results/series.html`, `_series_body.html`,
  `_race.html`. The bottom line sits inside `#series-body`, so picking a race
  or following a boat keeps it.
- **Tests:** `results/test_export.py` checks the CSV link's markup and is
  updated; new tests check each link's place and who sees it.
- **Manual:**
  - `getting-started/finding-results.md` says the CSV link is "near the top";
    it becomes "at the bottom". `results-final.png`'s description mentions
    the link; the image itself ends at the standings, so only the
    description changes.
  - `committee/ending-a-series.md` tells the committee to follow **Final
    results** near the top; it becomes **Finalise results**.
- Questions 2 and 3 cover the link once a series is final, and the admin's
  matching links.

### 4. "Discarded scores are in brackets."
- Shown only when the series' **Discards** setting is 1 or more, even before
  any score is actually in brackets. With 0, it isn't shown at all.
- In italics.
- Both places it appears: the series standings (`_series_body.html`) and
  each series on a boat's page (`boat.html`, per series).
- The other notes under tables ("NR: Not recorded…", "* Provisional…")
  are unchanged.
- **Tests:** both pages, with discards 0 and 1.

### 5. The capping footnote
Under a race's results, with the options on and **More detail** on:

> Handicaps adjusted with: extreme-result capping, realignment to base handicaps.
>
> † Result capped as extreme when working out the next handicap.

- Two paragraphs, not one; the † sentence loses "(shown with More detail)".
- The † line shows **only with More detail on**, where the column carrying
  the † is visible. With detail off, only "Handicaps adjusted with: …".
- **Tests:** `races/test_nhc_series_options.py`, updated for the wording, the
  separate line and detail on and off.
- The manual's two mentions of the † still describe it correctly.

### 6. Boats named "Name (Sail number)"
- `Boat.__str__` becomes `"Kittiwake (GBR 1234)"`; with no name, just the
  sail number. Everything that names a boat through it follows: the results,
  the boat's page, Follow a boat, My boats, search results, Change requests,
  emails and the admin's choices of boat. (Kittiwake is a made-up name, as
  in the test data; no real boat is named here.)
- **Unchanged, deliberately:**
  - **The race day page** (start sheet and finishing) keeps the sail number
    in bold first: the committee reads sail numbers off boats on the water
    (owner's decision).
  - **The CSV download** keeps separate "Sail number" and "Boat" columns.
  - **The admin's list of boats** keeps its separate columns.
  - Log lines, which name ids, not boats.
- **Follow a boat** lists boats by name (then sail number, for boats with the
  same name or none). Other lists keep their order.
- **Tests:** a test of `Boat.__str__`, with and without a name; the Follow a
  boat order; and every test that looked for "sail number name" text,
  updated. The engine fixtures are unaffected.
- **Manual:** screenshots showing boats are regenerated.

### 7. The Members page becomes "Club members"
- Page title, heading and menu link: **Club members**.
- The "Download everything the club holds (ZIP)…" line moves from the top to
  the very bottom.
- The page's sections keep their headings, **Waiting to join (n)** and
  **Members (n)**.
- **Manual:** `committee/members-and-roles.md` and
  `committee/reviewing-requests.md` name the **Members** page; they become
  **Club members**, and the download "at the top" becomes "at the bottom".
  `members-page.png` is regenerated. `docs/operating.md` likewise.

### 8. "Account" becomes "My account"
- Menu link, page title and heading: **My account**.
- Headings on the page: "Your clubs" → **My club memberships**; "Your data"
  → **My data**; "Delete your account" → **Delete my account**. The
  paragraphs under them keep speaking to the reader ("everything Race Times
  holds about you").
- The delete page (`delete_account.html`): title and heading **Delete my
  account**; its last link **Back to my account**.
- **Manual:** `getting-started/joining-a-club.md` names the Account page
  three times.
- **Privacy notice and terms** (`templates/legal/`) say "your Account page";
  they become "your My account page". Only a name changes, but both are
  drafts waiting for the legal review, so the change is noted in the open
  requirement in `docs/decisions.md`.
- `docs/operating.md` names it once.

### 9. "Requests" becomes "Change requests"
- Menu link and page title: **Change requests**. Heading: **Change requests
  from members**.
- The admin's list of members' requests says they're decided "on the Change
  requests page".
- The notice at the top of pages keeps its action, "Review requests".
- **Manual:** `committee/reviewing-requests.md` names the page four times,
  including a section heading.

### 10. The My boats page's links
Under each boat, on two lines:

> Register to enter a series
>
> Request a change to this boat's information

- While a request for the boat is waiting, the second line still says so in
  place of the link.
- Under the boats, **Register a boat** becomes **Register a new boat**.
- The committee's Change requests page still calls that kind of request
  "Register a boat", as its screenshots show.
- Question 4 covers the headings of the pages these links open.

### 11-14. The menu
A new first item, **Club results**, links to the club's results home page,
as the club's name does. **My boats** moves to just before **My account**,
and **Change requests** to just before **My boats**. **Setup (admin)**
becomes **Club setup** on club sites.

| Who | Menu |
|---|---|
| The public | Club results · Log in · Sign up |
| Logged in, not yet a member | Club results · Join this club (or Waiting to join) · My account · Log out |
| Member | Club results · My boats · My account · Log out |
| Race committee | Club results · Club setup · Change requests · My boats · My account · Log out |
| Club administrator | Club results · Club setup · Club members · Change requests · My boats · My account · Log out |

- "Join this club" / "Waiting to join" is My boats' slot, so it moves with it.
- **The operator's menu**, on the service's own address, is unchanged:
  Clubs · Operator log · Accounts (admin) · Log out. It never had "Setup
  (admin)".
- **Phones:** the administrator's menu is seven items. The header already
  wraps; it's checked at 375px wide and, if crowded, tidied with CSS only.
  No hidden "hamburger" menu, which would need JavaScript.
- **Manual:** **Setup (admin)** in `committee/reviewing-requests.md` and
  `committee/scoring-rules.md` becomes **Club setup**. Text that talks about
  "the admin" itself is unchanged.
- **Tests:** each role's menu, in order, and the operator's unchanged.

## Also
- **Screenshots:** every manual screenshot showing a table, a boat's name,
  the menu or a renamed page is regenerated with
  `scripts/manual_screenshots/run.sh`, and the scripts' selectors updated for
  the new names.
- **Docs:** `docs/decisions.md` (the naming rule, the boat name format and
  why race day keeps sail numbers first); `docs/plan.md`; `CLAUDE.md` where
  it names pages.
- `races/test_isolation.py` and `races/test_roles.py` refer to pages by URL
  name, so they're unaffected by renaming, but run as always.

## Acceptance criteria
- Each of items 1-14 behaves as described, for each role, with tests.
- No page's address changes; no model, migration, dependency or script is
  added.
- At 375px wide, the results pages scroll only inside their tables, and the
  menu wraps without overlapping.
- The manual's text, links and screenshots match the site;
  `mkdocs build --strict` passes.
- All existing tests pass, updated only where they checked wording or order
  this slice changes.

## Out of scope
- A collapsible or "hamburger" menu.
- Restyling the Django admin's own pages.
- Emails' wording, beyond boat names (item 6).
- Other notes under tables (only the discards note becomes italic).

## Questions for the project owner
1. **Which tables get the bolder headings?** The `th` rule styles every
   table: results, but also Club members, My boats' requests, the series
   history and the operator's pages. **Recommended: all of them**, so the
   site looks consistent. Or results tables only, with a separate class.
2. **The "Finalise results" link once a series is final.** It goes to the
   page where the committee can reopen the series. **Recommended:** it reads
   **Reopen results** while the series is final, so it always says what it
   will do. Or "Finalise results" always.
3. **The admin's series page** has the same pair, "Scoring history · Final
   results". **Recommended:** rename to **Series history · Finalise
   results** (or "Reopen results", per question 2), to match the site. And
   the committee's `ending-a-series.md` mention of the admin's **History**
   row changes with it.
4. **The headings of the pages the My boats links open.**
   **Recommended:** "Register a boat" → **Register a new boat**, matching
   its link; leave "Enter Kittiwake (GBR 1234) in a series" and "Request a
   change: Kittiwake (GBR 1234)", which name the boat.

**The owner's answers (2026-09-26):**
1. **All tables** get the bolder headings.
2. **Reopen results** while a series is final; **Finalise results** otherwise.
3. **Yes:** the admin's series page reads **Series history · Finalise results**
   (or **Reopen results**), and the manual follows.
4. **Register a new boat** as that page's heading; the other two pages keep
   theirs.
