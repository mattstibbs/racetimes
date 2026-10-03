# History

What changed in Race Times, newest first. Each "version" is a slice: a
self-contained piece of work with its own spec in
[`docs/slices/`](docs/slices/), built and merged as one or more pull
requests. There are no release numbers; the slice number is the version.
Dates are when the slice was completed.

The plan for what comes next is in [`docs/plan.md`](docs/plan.md).

## Upcoming

- **Slice 12 launch.** The production site is built; the launch steps in
  [`docs/production.md`](docs/production.md) are still to do, along with the
  legal review of the privacy notice and terms.

## Slice 25: RYA YTC series, and the engine renamed (2026-10-02)

- The scoring engine package is renamed from `nhc` to `sailscoring`, since it
  now scores more than one handicap system. No change in behaviour.
- A series can be scored under RYA YTC (Yacht Time Correction), the RYA's
  fixed-number system for cruisers.
- Slice 8, the original draft of this work, is superseded.

## Slice 24: Portsmouth Number series (2026-10-02)

- The committee chooses a **Handicap system** per series: NHC, or Portsmouth
  Yardstick with fixed numbers, including numbers the club sets itself.
- Places, points and discards are worked out the same way under both.
- Afterwards: NHC handicap columns are headed TCF, and fixed-number checks use
  approved fixtures (2026-10-03).

## Slice 23: discard threshold and scoring penalty (2026-10-02)

- A series can say "no discard until N races have been scored" (RRS A2.1).
- A boat that finishes and accepts a scoring penalty keeps her place but
  scores extra points (RRS 44.3(c)); the race day page has a tick beside the
  boat for it.
- Built as two pull requests, one for each rule.

## Slice 22: rename a club (2026-09-27)

- The operator can rename a club or change its contact email. The change is
  logged and the club's administrators are emailed. The club's address never
  changes.

## Slice 21: share results to WhatsApp (2026-09-27)

- Once a race is published, or a series declared final, the committee gets a
  **Share to WhatsApp** button that opens WhatsApp with the podium and a link
  already written. The site itself sends nothing.

## Slice 20: Python 3.13 (2026-09-27)

- The site runs on Python 3.13 (CI also tests 3.14). The scoring engine stays
  compatible with 3.11 and later.

## Slice 19: service landing page (2026-09-27)

- The service's own front page now shows what Race Times does and how to get
  in touch, and **Find my club** lets a sailor search for their club's
  results by name or address.

## Slice 18: the race office (2026-09-27)

- Club committees set up boats, series, races and entries on the site's own
  pages (**Race office**), with Coming up showing the next races. Nothing on
  a club's site points to the Django admin any more; it remains for the
  operator.

## Slice 17: code tidy-up and linting (2026-09-27)

- Ruff added as linter and formatter, run in CI. The code was tidied with no
  change in behaviour.

## Slice 16: change your password (2026-09-26)

- **My account** lets a signed-in person change their password. Other
  sessions are logged out and an email confirms the change.

## Slice 15: general UI improvements (2026-09-26)

- Less clutter on the results pages, clearer table headings, boats shown as
  "Name (Sail number)", and a menu whose names and order say what each page
  is for.

## Slice 14: optional NHC steps (2026-09-26)

- Club series can cap extreme results and realign handicaps to base after
  each race, as options apart from the RYA's own NHC calculation.

## Slice 13: operator approves people joining a club (2026-09-26)

- The operator can approve or turn down people waiting to join a club, for
  clubs whose administrator hasn't yet accepted their invitation or is away.

## Slice 12: production hosting (built 2026-09-25)

- Production configuration at `racetimes.co.uk` on Render (Frankfurt), deployed
  by hand, beside the free test site that runs Demo Club.
- Nightly encrypted off-site database backups, with a restore script.
- A production runbook, live-site checks, and `www` redirecting to the
  service's address.
- Not yet done: the launch steps and legal review.

## Slice 11: Race Times as a service for many clubs (2026-09-25)

Built in five parts.

1. Clubs, kept apart: each club has its own address, boats, series and data.
2. Roles per club: member, committee or administrator, approved by the club's
   administrators.
3. The operator's pages: create, suspend and invite administrators for clubs.
4. Running in production: health check, HTTPS only, every email sent from its
   club, Sentry error reports, and a lock-out after repeated failed logins.
5. Data protection: privacy notice and terms (drafts), essential cookies
   only, download or delete your own data, and a club's full data export.

## Slice 10: final results and export (2026-09-25)

- The committee can declare a series final, which locks it and labels its
  standings as the final places. It can be reopened.
- Results can be downloaded as a CSV.

## Slice 9: the race day page (2026-09-24)

- One page per race for use afloat: tick who is racing, then tap **Finished**
  as each boat crosses the line. The time is stamped on the spot, with a
  two-minute Undo and live updates.

## Slice 8: other handicap systems (parked)

- Portsmouth Yardstick and RYA YTC were specified, then parked and later
  superseded by slices 24 and 25. Nothing was built.

## Slice 7: visual styling (2026-09-24)

- A clean, modern stylesheet built on colour tokens that meet WCAG AA
  contrast, with no change to how pages behave.

## Slice 6: race-level entry (2026-09-24)

- Every race has a start sheet. Only boats on it can have a finish, and every
  boat on it needs a time or a code before results can be published.

## Slice 5: public results web app (2026-09-24)

- A `results` app for racers: boat search, latest results, a series page and
  a boat page, readable on a phone. It only reads and never shows owners'
  names.

## Slice 4: notifications (2026-09-24)

- Emails for published results (and corrections), changes to boats and
  entries, decisions on requests and accounts, and password resets.

## Slice 3: member self-service (2026-09-24)

- Member accounts. Members register boats and ask for changes or series
  entries; the committee approves or rejects each request.

## Slice 2: corrections and audit (2026-09-23)

- Any score-affecting change is recorded (who, when, old and new values, and
  a reason for corrections). The committee sees which results moved, and
  public results show when a race has been amended.

## Slice 1: walking skeleton (2026-09-23)

- The first end-to-end path in Django: set up boats and a series, record
  finishes, and view public results, with every number coming from the
  scoring engine.

## Slice 0: scoring engine (2026-09-23)

- `nhc/` (since renamed `sailscoring/`), a standalone, standard-library-only Python package implementing the
  RYA NHC handicap rules and RRS Appendix A scoring, tested against the RYA's
  published worked examples.
