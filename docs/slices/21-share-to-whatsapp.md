# Slice 21: share results to WhatsApp

**Status: planned (2026-09-27). Waiting on the project owner's answers at the
end.**

## Goal
Most clubs already have a WhatsApp group, and that's where sailors look for
news. When the committee publishes a race's results or declares a series
final, the site offers a **Share to WhatsApp** button. On a phone it opens
WhatsApp with a short message already written, for example the podium and a
link to the results. The committee member picks the club's group and presses
send.

This is option A from the planning discussion. It sends nothing itself, has
no WhatsApp account, API, cost or data model change, and adds no dependency
or JavaScript. Automatic messages to each follower through Meta's WhatsApp
Business Platform (option B, the way Geneva Airport's flight updates work)
would be a later slice if clubs ask for it; see "Out of scope".

## What's there now
- Race day page, `templates/races/_publishing.html`: the publishing card says
  Provisional, Published, or "Amended since results were sent", with
  **Publish results** and **Send updated results** buttons. Publishing emails
  the owners (`races/publishing.py`, `races/notifications.py`).
- Final results page, `templates/races/final.html`: **Declare final** emails
  every owner their boat's final place (`races/final.py`).
- The public series page is `/series/<pk>/`, and `?race=<number>` opens a
  particular race (`results/views.py`).
- Public pages show boats (name and sail number), never owners' names.

## How it works
A WhatsApp "click to chat" link: `https://wa.me/?text=<message>`, with the
message URL-encoded. With no phone number in it, WhatsApp asks which chat to
send it to. On a phone it opens the WhatsApp app; on a computer it opens
WhatsApp Web or the desktop app. If the person doesn't have WhatsApp, they
see WhatsApp's own page saying so. Nothing leaves Race Times: the link runs
in the person's own browser, and the message only goes anywhere if they
press send.

It's an ordinary link (`<a href>`), not a form, so it needs no JavaScript and
no view of its own.

## What gets built

### 1. Where the buttons appear
All three are for the committee only, since they're on committee pages.

| Where | When it shows | Button |
|---|---|---|
| Race day page, publishing card | The race is published and the results were sent | **Share to WhatsApp** |
| Race day page, publishing card | The race is published but amended since results were sent | **Share updated results to WhatsApp**, beside **Send updated results** |
| Final results page | The series is final | **Share final standings to WhatsApp** |

- Not while a race is provisional. Publishing is the committee saying "these
  are the results"; sharing before that would spread results that may
  change.
- The link is built on the server when the page is rendered, so it always
  holds the results as they stand at that moment.
- Styled as the site's existing secondary link button (`a.button.secondary`,
  already in `static/css/site.css`), so no new colours. No WhatsApp logo: it's a trademark, and the words
  are clear enough. (See question 4.)
- After **Publish results** succeeds, the page already reloads onto the
  publishing card, so the share button is right there at the moment the
  committee wants it.

### 2. The messages
Plain text, short enough to read in a group chat, with WhatsApp's own
`*bold*` for the heading. Built from what `races.scoring.score_series`
computes, like the emails. Boat names and sail numbers only, never owners.

**Race results:**
```
*Spring Series, race 3* (Sun 14 Sep): results are published.

1. Blue Moon (GBR 1234)
2. Kestrel (4521)
3. Wild Thing (GBR 88)

Full results: https://harbour.racetimes.co.uk/series/12/?race=3
```

**Updated results:** as above, with "results have been corrected" instead of
"results are published".

**Final standings:**
```
*Spring Series* is final.

1. Blue Moon (GBR 1234), 7 pts
2. Kestrel (4521), 11 pts
3. Wild Thing (GBR 88), 14 pts

Final standings: https://harbour.racetimes.co.uk/series/12/
```

- The top three places (question 1). Fewer if fewer boats scored; boats tied
  on a place share it, as on the results page.
- A race with no results to show (everyone DNC, say) just says the results
  are published, with the link.
- The link is the club's own address, built with
  `request.build_absolute_uri`, so it's always the right club's site.
- The message text lives in a template, `templates/races/share/*.txt`, like
  the emails, so the wording is easy to change.

### 3. Where the code goes
- `races/sharing.py`: `race_message(race, results, request)`,
  `final_message(series, results, request)` and
  `whatsapp_url(message)`. Plain functions that render the template and
  URL-encode it (`urllib.parse.quote`).
- `race_day_views._publishing_context` and `series_views._final_context` add
  the URL to their context. The HTMX swap of the publishing card
  (`oob`) carries it too, so after a finish is corrected the button switches
  to "Share updated results" without a reload.

No model, migration, setting, dependency or JavaScript.

## Tests
- Each button shows only in the states in the table above, and never while
  provisional or before the series is final.
- The message:
  - names the series, race number and date, and the top three boats in
    order, with sail numbers;
  - handles fewer than three scored boats, ties, and a race with nothing to
    show;
  - carries the final points on the final standings;
  - never contains an owner's name, typed or from an account;
  - links to the club's own address, and `?race=<n>` for a race.
- The URL starts `https://wa.me/?text=` and decodes back to exactly the
  message (so line breaks, `&`, `#`, `*` and non-English letters survive).
- The publishing card swapped in over HTMX after a correction carries the
  "updated" button.
- Isolation: `races/test_isolation.py`'s checks still pass. A message for
  one club's race never names another club's boats or address.
- Roles: the public and members never see the buttons (the pages are
  committee-only already; the tests confirm it).
- `races/test_styles.py` still passes: a link to wa.me loads nothing.

## Manual
- `manual/committee/publishing-results.md`: a short section, "Sharing results
  to WhatsApp": where the button is, that it opens WhatsApp for you to choose
  the group, and that nothing is sent until you press send.
- `manual/committee/ending-a-series.md`: the same for final standings.
- Screenshots: the publishing card with the share button, retaken by
  `scripts/manual_screenshots/`. No screenshot of WhatsApp itself.

## Acceptance criteria
- After publishing a race, the committee can share its results to a WhatsApp
  group in two taps on a phone, and again after correcting it.
- After declaring a series final, the committee can share the final
  standings the same way.
- Messages hold only what the public results page shows, and link to the
  club's own site.
- No model, migration, dependency or JavaScript is added.
- All tests, Ruff and the strict manual build pass; checked by hand on a
  phone-sized browser (the link opens `wa.me` with the message filled in).

## Out of scope
- **Automatic WhatsApp messages** (option B): anyone follows a series by
  messaging Race Times, and gets a message when results are published. That
  needs a Meta Business account, verified business, approved templates,
  per-message costs, a webhook and a new model for followers. A slice of its
  own, if clubs want it.
- Posting to a group or a WhatsApp Channel automatically: WhatsApp's API
  doesn't allow it.
- Other apps (Facebook, email lists). The message is plain text, so a "Copy
  message" button could come later (question 3).
- Sharing from public pages (question 2).

## Suggested parts
One pull request.

## Questions for the project owner
1. **What's in the message?** **Recommended:** the top three and a link, as
   above. It gives the group chat something to talk about without being a
   wall of text. Or just the heading and a link.
2. **Who gets the button?** **Recommended:** the committee only, on the race
   day and final results pages. The committee decides when results are
   ready. Or also a **Share** link on the public series page, so any sailor
   can share (it would show for provisional results too, labelled as such).
3. **Copy message too?** **Recommended:** not now. Or add a **Copy message**
   box beside the button for clubs that post elsewhere; a copy button needs
   a line of JavaScript (a plain text box the person selects by hand needs
   none).
4. **WhatsApp's logo on the button?** **Recommended:** words only, in our
   own style. Meta allows its logo on "click to chat" buttons under its brand
   rules, but it adds a green that's not one of our colour tokens and an
   image to keep. Or use the logo.
