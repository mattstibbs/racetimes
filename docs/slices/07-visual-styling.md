# Slice 7: Visual styling

## Goal
The site works, but it still looks like the walking skeleton it started as:
browser-default buttons and inputs, blue underlined links everywhere, and no
sense of which part of a page matters most. This slice gives every page of
the site a clean, simple, modern look that a sailing club would be happy to
point its members at. How pages behave stays exactly as it is.

## Scope

### The look *(agreed with the project owner)*
- **Neutral nautical colours.** A deep navy header bar, one sea-blue accent
  for links, buttons and the current choice, and white cards on a light grey
  page. None of it is tied to any one club.
- **Light only.** No dark mode.
- **The device's own font** (`system-ui`: San Francisco on Apple devices,
  Roboto on Android, Segoe UI on Windows). Nothing is downloaded, so there
  is no new asset or dependency.
- **The site's own pages only.** The Django admin, used for setup, keeps its
  standard look.

### How it's built
- **One stylesheet**, `static/css/site.css`, rewritten around a short list of
  CSS custom properties (design tokens) at the top: colours, spacing, corner
  radius and shadow. Every colour on the site comes from those tokens, so the
  look can be changed later in one place, for example to a club's own
  colours.
- **No framework, no JavaScript, no new dependency, no web font and no
  request to another site.** Everything is served from `static/`, like HTMX.
- **Templates change only where layout needs it.**
  - `base.html` gains a full-width header band and a `<main>` element, each
    with an inner column.
  - Buttons get a class for their role: a primary action (Publish, Approve,
    Save, Find) and a secondary one (Reject, Log out).
  - Every class, id and `hx-` attribute that HTMX, the tests or the
    screenshot script relies on stays as it is.
- **A small favicon**: an SVG sail in the accent colour, stored in `static/`.
  It gives the browser tab something better than a blank page, and doubles
  as the mark beside the site's name. *(My suggestion, which the project
  owner went ahead with; a one-file asset, not a dependency.)*

### What changes on screen
- **Header:** the site name ("Race Times") on the navy band, with the
  navigation links in white. On a phone it wraps neatly instead of squashing.
- **Typography:** a clear type scale for page titles, section headings and
  body text, with comfortable line lengths. Headings no longer compete with
  the results.
- **Buttons and form fields:** consistent sizes, padding and corners, with a
  visible hover and pressed state. Every link, button and field shows a
  clear focus outline when reached with the keyboard.
- **Tables:** a light header row, subtle row separators, right-aligned
  numbers in tabular figures, and the followed boat still highlighted.
- **Cards:** the home page's latest results, the committee's requests and the
  publishing box become white cards with a soft border and shadow.
- **Status colours:** the existing states get one consistent set of colours,
  each with a matching background: saved (green), error (red), provisional or
  amended (amber) and published (green).
  - Row and card states: `saved`, `has-errors`.
  - Notes: `.note`.
  - Labels: `.provisional`, `.published`, `.amended`.
  - Page messages: `ul.messages`. Errors show in red here, not in the same
    green as successes.
- **"Follow a boat" moves below the results** on the series page, after the
  standings and the chosen race, so the results come first, on a phone
  especially. It is still part of the section HTMX swaps, so choosing a
  boat highlights it in the tables above. *(Asked for by the project owner
  while building.)*
- **"Find a boat" moves to the bottom of the home page**, after the latest
  results and every series, so the results come first. A search without
  JavaScript reloads the page, so the form's address ends in `#find-a-boat`
  to bring the browser back down to the matches. *(Asked for by the
  project owner while building.)*
- **The race picker** on the series page becomes a row of pill-shaped
  buttons, with the chosen race filled in.
- **The finish-entry and start sheet rows** keep their grid, tidied up so the
  columns line up and the saved and error states are easier to spot.
- **Phones:** buttons, the race picker and header links are at least 44 px
  tall at 375 px wide, so they are easy to tap.
- **The boat page's results table fits a 375 px screen.** Today it overflows
  its box by 2–6 px. *(The known issue left over from slice 5, fixed here
  because it's a styling fix.)*
- **The error page** (`500.html`) matches the new look. It keeps its styles
  inline and loads nothing, so it still can't fail for the same reason as
  the page that broke.

### Every page restyled
- **Public:** results home, series, boat.
- **Accounts:** log in, sign up, "waiting for approval", and the four
  password reset pages.
- **Members:** my boats, register a boat, change a boat, enter a series.
- **Committee:** requests, finish entry, start sheet, change history.
- **The error page.**

### Data model
None. No models, no migrations.

## Acceptance criteria
- Every page listed above uses the new styles. Each is checked in headless
  Chromium at 1000 px and 375 px wide, and no page scrolls sideways at
  375 px, the boat page's results table included.
- Behaviour is unchanged: every existing test passes with no change to what
  it asserts, and every page still works with JavaScript off.
- Every colour comes from the tokens at the top of `site.css`. A test reads
  those tokens and checks each text colour against the background it's used
  on:
  - body text, links and labels at least 4.5:1 (WCAG AA);
  - large headings and the borders of buttons and inputs at least 3:1.
- Every link, button and form field shows a visible focus outline, checked
  by moving through a page with the keyboard in headless Chromium.
- Buttons, race picker buttons and header links are at least 44 px tall at
  375 px wide, checked in headless Chromium.
- The site makes no request to any other site: `base.html` and `500.html`
  load only files from `static/`, tested.
- The Django admin and the emails look exactly as before.
- Every screenshot in the user manual is regenerated, and any manual text
  that describes how something looks (a colour, "the box at the top") still
  matches.

## Out of scope
- Dark mode *(the project owner's choice)*.
- Restyling the Django admin *(the project owner's choice)*.
- A club logo or club colours. The tokens make this a small later change.
- Web fonts and icon sets.
- HTML emails (they stay plain text).
- A print stylesheet for pinning results on the clubhouse noticeboard.
  Worth considering next: it's small and plain CSS.
- Animations, and any layout change that needs JavaScript.
- New features or changes to any page's content or wording, except where
  the manual has to follow a visual change.
