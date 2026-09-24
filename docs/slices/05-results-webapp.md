# Slice 5: Results webapp

## Goal
A racer can find out how they did, quickly, on a phone at the bar after the
race: where they finished, where they stand in the series, and what handicap
they sail on next time. Today's results page answers all of that, but it is
one long page per series built for the committee's checking, with eight
columns per race and every race stacked one after another. This slice adds a
second Django app, `results/`, that is only for reading results, and is built
around the racer rather than the series.

Nothing is stored and nothing can be changed from it: it reads the same
scores `races/scoring.py` computes on every request, so it can never disagree
with the committee's pages.

## Scope

### A separate app that reads, never writes
- A new app, `results/`, in the same project, added to `INSTALLED_APPS` and
  included in `config/urls.py`.
- It imports from `races` (the models, `scoring.score_series`,
  `publishing.amended_since_sent`) and `races` never imports from it. It has
  no models, no forms that save, and no POST views.
- Every page is public, like today's results. The pages look the same to
  every role, except that the committee also sees its "Enter finishes" and
  "History" links, as today.
- Every page is a normal page at its own URL that works with JavaScript off.
  HTMX only swaps part of the page in place: each HTMX request goes to the
  same URL as the full page, and the view returns just the fragment when
  `request.htmx` is set. Links and forms use `hx-push-url`, so the back
  button and a shared link both land on what was on screen.

### The pages

**Results home** (`/results/`)
- **Find a boat**: one box that searches sail number and boat name as you
  type (HTMX, a short delay after typing stops), and is an ordinary search
  form without JavaScript. Sail numbers match ignoring case and spaces, as the
  database already treats them, so "gbr1234" finds "GBR 1234".
- **Latest results**: the most recently sailed race of each series with
  results, newest first, each with its top three and a link to the race.
- **All series**, newest first by their latest race date, so this season's
  series come before last year's without adding a date to Series.
- A logged-in member also sees **My boats**, linking to their own boats'
  pages.

**Series** (`/results/series/<pk>/`)
- The standings, with a row of race buttons above the race results. Choosing
  a race swaps in that race's results without reloading the page (HTMX); the
  URL becomes `?race=<number>`. It opens on the latest race with results.
- **Follow a boat**: choosing a boat from a list highlights its row in the
  standings and in every race, and is kept in the URL (`?boat=<pk>`) so the
  race buttons keep it.
- On a narrow screen a race shows place, boat, corrected time and points,
  with the rest (finish, elapsed, handicap, next handicap) one tap away under
  **More detail**. Done with CSS and a plain link, not JavaScript.
- The same labels as today: provisional until published, published with the
  date, amended since published, amended on a date.

**Boat** (`/results/boats/<pk>/`)
- The page a racer bookmarks. Name, sail number, make and model; the owner
  shown as today (`owner_display`).
- For each series the boat is entered in, newest first: its standing
  (position and points), then one row per race: place or code, points,
  corrected time, the handicap it sailed on and the handicap it takes into
  the next race, and whether the race is provisional.
- **Next handicap**, stated plainly at the top for each series still being
  sailed: "Sails race 5 on 0.978". This is the number racers ask the
  committee for most, and until now it was the last column of the last
  table.
- A boat entered in no series says so, and still has a page.

### Replacing today's public page *(proposed, awaiting approval)*
- The site's home page shows the results home, and `/series/<pk>/`
  redirects permanently to `/results/series/<pk>/` (keeping `#race-N` as
  `?race=N`), so every link already sent in an email keeps working.
- `Series.get_absolute_url` and the emails point at the new page from now on.
- The committee's finish-entry and history pages link to the new page.
- Today's `races/series_results.html` and its view are removed, so there is
  one public results page to keep correct, not two.

### Data model
None. No new fields, no migrations. "Latest race", "current series" and
"next handicap" are all worked out from what is already stored.

## Acceptance criteria
- `results/` imports nothing that writes, and `races` imports nothing from
  `results`; a test checks both, like `tests/test_package_purity.py` does for
  the engine.
- Every page shows exactly the positions, points, times and handicaps that
  `score_series` computes, tested against a scored series (SCEN-005 loaded
  through the database, as `races/test_scoring.py` does), including the boat
  page's "next handicap".
- Each HTMX interaction (search, choosing a race, following a boat) returns
  a fragment to an HTMX request and the whole page to a plain request at the
  same URL, and the whole page shows the same thing.
- Search matches sail numbers ignoring case and spaces, and boat names
  ignoring case; an empty or unmatched search says so rather than listing
  every boat.
- A series with no entries, no races, unscored races, or that the engine
  refuses, shows its message on every page instead of crashing (the "no user
  action should crash a page" decision).
- An unknown series, boat or race number is a 404.
- Every page is tested as each of the four roles (`races/test_roles.py`), and
  only the committee sees committee links.
- Old `/series/<pk>/` links, with and without `#race-N`, reach the same
  results on the new page.
- The pages are usable at phone width: checked in headless Chromium at
  375 px wide, with screenshots in the manual.
- The user manual gains a "Finding your results" page for members and the
  public, with screenshots, and the committee pages' links to results are
  updated.

## Out of scope
- The brief's API and file export (user journey 5): a later slice.
- Charts of a boat's handicap over time. A table first; a chart would want
  JavaScript or a charting dependency, which needs asking about.
- Refreshing a page on its own on race day (HTMX polling). Easy to add later
  if the committee enters finishes live; not asked for yet.
- Comparing two boats side by side, and results across series combined
  (e.g. a club championship).
- Anything that changes data, including members correcting their own boats'
  details from the boat page: that stays a request, through "My boats".

## Questions for the project owner
1. **Replace or add?** The plan says "another app". This spec proposes it
   *replaces* today's public page (with redirects), rather than the site
   having two public results pages that can drift apart. Agreed?
2. **Home page.** Should `/` show the results home, as proposed, or stay as
   it is with a link to `/results/`?
3. **Owner names on the public boat page.** Today's page shows boats by sail
   number and name only. The boat page proposes adding the owner's name.
   Fine for a club site, or keep owners off the public pages?
4. **Race-day refresh.** Worth including now (the open race page re-fetches
   its table every minute or so), or leave it out as above?
