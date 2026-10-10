# Slice 29: page titles

**Status: complete (2026-10-11).** The project owner chose the style and the
home page's title before any code was written; see "The project owner's
answers" at the end.

## Goal
Two things the project owner asked for:

1. A page title style, at the top of every page, that makes it clear which
   page you are on.
2. A clearer title on a club's results home page: it should show that this is
   the main results page, and make it obvious which club it belongs to.

Presentation only, as slice 15 was: no model, migration, new dependency or
JavaScript. Page addresses don't change.

## What's there now
- Every page has a plain `<h1>` as the first thing in its content: navy text
  straight on the grey page, under any messages ("Saved", an error).
- Some race office and operator pages have a small link back up ("Race
  office &rsaquo; Boats") above the heading.
- The results home page is headed "Results". It has no `<title>` of its own,
  so its browser tab says only "Race Times".

## What gets built

### 1. The title band
A full-width white band directly under the navy header, with a thin line
under it. It holds the page's heading and nothing else, apart from:

- the link back up, on the pages that have one, above the heading;
- a smaller line under the heading, on the results home page only (below).

Messages and the page's content start beneath the band, on the grey page.

- `templates/base.html` gains the band, between the header and `<main>`:
  a `page_header` block holding `<div class="page-title">`, and inside it a
  `heading` block that each page fills.
- Every whole-page template moves its `<h1>` (and its link back, if it has
  one) from `{% block content %}` to `{% block heading %}`. The `<h1>` itself
  is unchanged, so no existing test of a heading changes.
- Templates whose heading depends on a condition (a confirmation link that
  worked or didn't, a password reset link, an invitation) put the condition
  in the heading block.
- `static/css/site.css`: `.page-title`, in the existing tokens. No new
  colour. Tighter padding on a phone.

**Exceptions:**
- The service's front page (`templates/clubs/service_home.html`) has its
  heading in the photo hero, so it empties `page_header` and has no band.
- The error page (`templates/500.html`) stands alone and loads nothing, so
  the band is copied into its inline styles and markup.
- Partials, emails and the WhatsApp messages have no page heading and don't
  change. Nor does the Django admin.

### 2. The results home page
- The heading is the club's name, with **Race results** as a smaller grey
  line under it:

  ```
  Demo Club
  Race results
  ```

- Its `<title>` becomes "Race results - Demo Club - Race Times".
- A long club name wraps inside the band; the page doesn't scroll sideways.
- Only this page has the smaller line. Other pages already name the club in
  the header.

## What doesn't change
- Every page's wording, apart from the home page's heading.
- The menu, the header and the footer.
- What an HTMX request gets back: a fragment never includes the band.

## Tests
New, in `races/test_page_titles.py`:
- every whole-page template has its `<h1>` in the heading block and nowhere
  else (or, for the service's front page, no band and a hero), so a new page
  can't leave the band out;
- no partial has an `<h1>`;
- on a page for the public, a member and the committee: one `<h1>`, in the
  band, after the header and before the content;
- the link back up is in the band, above the heading;
- a series page's description stays out of the band;
- a message shows under the band;
- the service's front page has no band; the operator's pages do; the error
  page copies it;
- the home page: the club's name, "Race results" under it, the `<title>`,
  and another club's home page naming that club and not Demo Club;
- a boat search over HTMX brings no title.

`races/test_styles.py` needs no new pair: navy, muted and accent on white are
already checked.

## User manual
- Every screenshot is regenerated. `scripts/manual_screenshots/shots.js`
  photographed `<main>` for whole pages; the title is no longer in it, so
  those shots now run from the band to the end of the content (`pageShot`).
- "Finding your results" says the front page is headed by the club's name
  and **Race results**, and that every page has its title in the band.
- The landing page's three screenshots (`static/img/landing/`) are cut from
  the manual's, so they are remade too. The hero photo isn't.

## Out of scope
- Breadcrumbs on pages that don't have a link back today.
- A collapsing menu on a phone, or any other change to the header.
- Rewording other pages' headings.
- A page of the site's own for "not found": that is still Django's.

## The project owner's answers (2026-10-11)
1. **The style:** a white title band under the header (over a blue band, or
   an accent bar under the heading with no band).
2. **The home page:** the club's name as the title, then "Race results"
   (over "Race results" above the name, or one line, "Demo Club race
   results").
3. **Limits:** presentation only.

Decided while building, as recommended in the plan the owner approved: the
link back up moves into the band with the heading.
