# Slice 19: a landing page that sells Race Times, and "Find my club"

**Status: built (2026-09-27), for the owner's review of the photo and the
wording. The owner's answers are at the end.**

## Goal
The service's own front page, `racetimes.co.uk`, is for two kinds of visitor:

1. **Someone from a club that might want Race Times.** Today they get a
   plain page of headings and bullet points. It should show them what Race
   Times does and make it easy to get in touch.
2. **A sailor looking for their own club's results.** Today the page tells
   them to ask their club for its address. It should let them find it.

Club sites (`<club>.racetimes.co.uk`) don't change, apart from anything the
owner chooses in question 3.

## What's there now
- `templates/clubs/service_home.html`: a heading, a paragraph, three short
  sections and a mailto link. `races/clubs.py` (the club middleware) renders
  it for `/` on the service's own address.
- The header's brand is a small sail icon (`static/img/sail.svg`, 1.6rem)
  and the words "Race Times", the same size on every page.
- Every page carries `X-Robots-Tag: noindex, nofollow` and `robots.txt` says
  `Disallow: /` (decided this morning; see question 1).
- `races/test_styles.py` checks that pages load only the site's own files,
  that every colour is a token in `static/css/site.css`, and that the tokens
  meet WCAG AA contrast.
- The test site on Render has `SINGLE_CLUB` set, so it has no service
  address: this page can be seen only locally and on production.

## What gets built

### 1. A proper landing page
In the same template, reworked. Everything is server-rendered HTML and the
site's one stylesheet: no new JavaScript, fonts or dependencies.

- **A hero section at the top,** full width:
  - a large Race Times logo: the sail icon at about 4-5rem with the name
    beside it, much bigger than in the header;
  - a one-line headline and a short subheading, for example
    "Race results and handicaps for your sailing club, done for you" /
    "NHC handicaps worked out after every race, results on every phone,
    and a race day page your committee will actually enjoy";
  - the photo (section 2) behind or beside the text;
  - two buttons: **Find my club** (jumps to section 4) and **Get Race Times
    for your club** (jumps to the contact section).
- **What a club gets:** the current bullet points as four or five cards,
  each with a heading, a sentence and a small icon (inline SVG, our own).
  For example: *Results on every phone*, *NHC handicaps, done for you*,
  *A race day page for the committee*, *Members do their own admin*,
  *Every correction on record*.
- **See it working:** two or three real screenshots from the user manual
  (`manual/images/`), such as the public series standings and the race day
  Finishing view on a phone, each with a caption. Real screenshots persuade
  better than any stock photo, and they're already made and kept up to date.
- **How it works,** in three steps: *Tell us about your club* > *We set up
  your site at yourclub.racetimes.co.uk* > *Your committee enters results;
  everyone sees them*.
- **Get Race Times for your club:** the contact email as a clear button,
  plus what happens next.
- **No invented claims:** no testimonials, customer numbers or prices
  until there are real ones.

### 2. The photo
- One photo of yacht racing, landscape, used in the hero.
- **Source:** a stock photo, for now (question 2): "Cowes Week 2019" by Peter
  Trimming, CC BY-SA 2.0, from Wikimedia Commons (Geograph). Unsplash's search
  couldn't be reached from the build machine; Commons records each photo's
  licence. CC BY-SA needs a credit, so the page credits it under the photo,
  with links to its page and the licence. Recorded in `docs/decisions.md`.
- **Made by** `scripts/landing_images/make.js`, which uses Chromium (as the
  manual's screenshots do) to resize the photo and crop the manual's
  screenshots, so nothing is added to Python.
- **Served from our own files** (`static/img/`), so the "loads only the
  site's own files" test keeps passing and visitors' browsers contact no
  one else:
  - resized to two widths, about 800 and 1600 pixels;
  - saved as WebP with a JPEG fallback (`<picture>` with `srcset`), each
    under about 200 KB;
  - `alt` text describing it.
- **Text over the photo** sits on a solid navy panel, so it reads the same
  whatever the photo, with colours the WCAG test already checks. No new
  colour was needed.

### 3. A bigger logo
- On the landing page: the large logo in the hero (section 1).
- In the header on the service's own address: the icon and name somewhat
  bigger (about 2.25rem instead of 1.6rem).
- Club sites' headers: see question 3.

### 4. Find my club
A search box on the landing page, just under the hero. It's for sailors who
know their club's name but not its address.

- **Search-as-you-type** with HTMX, as on the results home page's boat
  search: `hx-trigger="input changed delay:300ms, search"`, swapping in just
  the list of matches.
- **Without JavaScript,** the same box is a plain GET form that reloads the
  page with the matches: the same URL, `/?club=...`. `request.htmx` picks
  whether to send the whole page or just the matches, as `results/views.py`
  does.
- **What it searches:** clubs' names and addresses (subdomains), ignoring
  case, anywhere in the name ("harb" finds "Harbour Sailing Club"). It needs
  at least 2 characters. It lists **active clubs only**: a suspended club
  isn't shown.
- **Each match** shows the club's name and its address, e.g.
  `harbour.racetimes.co.uk`, as a link to that club's site. There are at
  most 10 matches, in name order.
- **No match:** "No club called that uses Race Times yet. Check with your
  club, or tell them about us" (linking to the contact section).
- **What it doesn't show:** nothing but name and address. No member counts,
  contact emails or anything else about a club.
- **Where the code goes:** the landing page moves out of the club middleware
  into a small view, `races/service_views.py`, which the middleware calls for
  `/` on the service's own address. The middleware keeps deciding which
  address is which.

### 5. Search engines
Not in this slice (question 1): every page, this one included, stays
noindex for now.

## Tests
- The landing page:
  - shows the headline, the contact email and the Find my club box;
  - loads only the site's own files, including the photo;
  - is still served only on the service's own address; a club's address
    still gets that club's home page.
- Find my club:
  - finds a club by part of its name and by its address, in any case;
  - leaves out suspended clubs;
  - needs 2 characters;
  - lists no more than 10;
  - shows the "no club" message;
  - returns only the matches over HTMX, and the whole page without it;
  - shows nothing about a club but its name and address.
- The bigger header logo is on the service's own pages only.

## Manual
The user manual is for clubs' own people, so it doesn't change, apart from a
line in "Joining a club" that you can find your club at racetimes.co.uk. Its
screenshots don't change. `docs/operating.md` gains a sentence saying active
clubs are listed in Find my club.

## Acceptance criteria
- A new visitor to `racetimes.co.uk` sees, without scrolling on a laptop: the
  large logo, the headline, the photo, and the two buttons.
- A sailor can type part of their club's name and follow a link to its site,
  with or without JavaScript.
- Suspended clubs are never listed, and nothing but a club's name and
  address is shown.
- The page loads nothing from any other website, and every colour passes
  WCAG AA.
- The photo's source and licence are recorded.
- All tests, Ruff and the manual build pass; the page is checked by hand in
  a browser at phone and laptop widths.

## Out of scope
- Pricing, sign-up or payment for clubs (the operator still sets clubs up).
- Clubs choosing not to be listed in Find my club: that needs a new field
  (a data model change), so it waits until a club asks. See question 4.
- A club's own domain (e.g. `results.exesc.org.uk`).
- Changing club sites' home pages.

## Suggested parts
One pull request: the landing page, photo, bigger logo and Find my club.

## Questions for the project owner
1. **Search engines.** This morning every site became noindex, the service's
   front page included. A page meant to win new clubs mostly finds them
   through search. **Recommended:** let search engines index the service's
   front page only. Every club site, and every other page on the service's
   address (the operator's pages, privacy, terms), stays noindex. Or keep
   everything noindex for now and change it at launch.
2. **The photo.**
   - **Recommended:** a photo of your own club's racing, if you have one you
     own or have permission to use. It's more genuine than stock.
   - Otherwise I'll choose a stock photo of cruiser or yacht racing from
     Unsplash or Pexels, show it to you before committing it, and record its
     licence.
3. **The logo on club sites.** **Recommended:** make it bigger on the
   service's own pages only. On club sites the club's name is the heading,
   and a bigger service logo would compete with it. Or make it bigger
   everywhere.
4. **Listing clubs.** **Recommended:** list every active club in Find my
   club. A club's site is public already, and there's no way to opt out yet;
   that can be added, with a new field, when a club asks. Or list no club
   until an opt-in field exists, which is a data model change for your
   approval.
5. **Words.** Are you happy for me to draft the headline, cards and "How it
   works" copy in the style above, for you to edit in review? Or do you have
   wording you'd like used?

**The owner's answers (2026-09-27):**
1. Search engines: leave them for now. Every page stays noindex.
2. Use a stock photo for now.
3. A bigger logo on the service's own pages only: agreed.
4. List every active club: agreed.
5. Draft the wording for the owner to edit in review.
