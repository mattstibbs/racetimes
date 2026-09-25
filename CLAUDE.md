# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About me (experience level, how to explain things)

I'm a capable amateur in Python; explain non-obvious decisions briefly in commit messages or comments.

## Stack and versions

Python 3.11, Django 5.2, SQLite for development and PostgreSQL (via `psycopg`) for production. Keep code and migrations compatible with both. HTMX 2.x for frontend interactivity (server-rendered Django templates and partials, not a JS SPA), with `django-htmx` middleware so views can check `request.htmx`. Avoid javascript (ask first if necessary). pytest (with `pytest-django`) is the test framework for the whole project - both the Django app and the scoring engine. Write tests as plain functions with bare `assert`s, not `unittest.TestCase` subclasses.

## Definition of done
New behaviour has tests. No linter errors. All tests pass. Migrations created. Manual checks completed. User-facing changes update the user manual (`manual/`), including its screenshots.

## Guardrails (never / ask first)
Ask before changing the data model. Don't install new dependencies without asking.

- Fixtures in tests/fixtures/ are the specification. Never edit a fixture's
  expected values to make a test pass — if they disagree with the code, the
  code is wrong, or the fixture's provenance needs checking with me first.
- Do not generate new fixtures from the engine's own output.
- Log lines name ids, never names or email addresses (e.g. "user 42", not
  "Pat Jones"). The log formatter redacts anything email-shaped
  (`races/logs.py`), but it can't spot a name.

## Testing
- pytest. Fixtures in tests/fixtures/ are the specification for the scoring
  engine — see Guardrails.


## Commands (run, test, lint, migrate)

Setup (uses a local `.venv`, which is gitignored):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createcachetable   # once: the failed-login counts live there
.venv/bin/python manage.py runserver
.venv/bin/python manage.py makemigrations
```

Tests:

```bash
.venv/bin/python -m pytest                           # all tests
.venv/bin/python -m pytest tests                     # scoring engine only
.venv/bin/python -m pytest races results             # Django apps only
.venv/bin/python -m pytest tests/test_fixtures.py::test_fixtures_load   # a single test
.venv/bin/python -m pytest -k "SCEN-005"              # by name (case-sensitive)
```

User manual (MkDocs; see `docs/deploying-manual.md`):

```bash
.venv/bin/pip install -r requirements-docs.txt
.venv/bin/mkdocs serve                     # preview at http://127.0.0.1:8000
.venv/bin/mkdocs build --strict            # what CI and Read the Docs run
scripts/manual_screenshots/run.sh          # regenerate manual/images/ (needs Node.js + Playwright)
```

No linter is configured yet.

CI runs on every pull request (`.github/workflows/ci.yml`): the test suite on
Python 3.11 and 3.12, `manage.py check`, `manage.py check --deploy` with
production settings, a check for missing migrations, a job that imports `nhc` with nothing installed, to prove the package really is
standard-library only, and a strict build of the user manual.

Do not use `manage.py test`. pytest-style tests are plain functions, so Django's
runner collects none of them and exits 0 with "Ran 0 tests ... OK" - a false
green. `config/test_runner.py` is wired in as `TEST_RUNNER` to fail loudly with
a pointer instead.

## Architecture

- `nhc/` is the scoring engine: a standalone, standard-library-only package
  implementing the RYA NHC handicap rules and RRS Appendix A scoring. It must not
  import Django, third-party packages, or do any I/O - it takes plain Python data
  and returns plain Python data, so it can be vendored into any project.
  `tests/test_package_purity.py` enforces this. Its reference documents are in
  `docs/reference/` and they win over any contrary assumption; the fixtures in
  `tests/fixtures/` encode the RYA's own published worked examples.
- Engine tests live in `tests/`. `tests/scenario_loader.py` reads the YAML fixtures
  and exposes them as module-level lists so tests can `@pytest.mark.parametrize`
  over them; `tests/conftest.py` wraps the same objects as pytest fixtures. All
  fixture I/O happens there, never inside `nhc/`. `tests/test_manual.py` is the
  one non-engine test there: it checks the user manual's links and contents.
- Clubs (slice 11): Race Times serves many clubs from one database. `races/clubs.py` middleware finds `request.club` from the host (`<subdomain>.<SERVICE_DOMAIN>`, or the `SINGLE_CLUB` setting on an address with no club, which is how the Render test site, 127.0.0.1 and the tests reach Demo Club). Every club-owned model has `Model.objects.for_club(club)`, and every page, form and admin view looks up club rows through it (or through a row already found that way). `races/test_isolation.py` checks every URL, id, admin page and email for another club's data, and fails if a request-facing module queries a club model without `for_club`. A row's `club` is never editable in a form. The admin (`races/admin_site.py`, `ClubScopedAdmin`) shows only the current club; on the service's own address only the operator (superuser) gets in. Test builders default to Demo Club (`races.testing.default_club()`); to test several clubs, `make_club()` and set `HTTP_HOST="<subdomain>.localhost"`. The operator's pages (slice 11 part 3, `races/operator_views.py` at `/operator/`) exist only on the service's own address (`request.club is None`, tested with `settings.SINGLE_CLUB = ""` and `HTTP_HOST="localhost"`) and only for a superuser; they create and suspend clubs and invite administrators (`races/invitations.py`: a signed 7-day link to the club's address), and log every action as an `OperatorAction`. Clubs and memberships aren't in the Django admin. See `docs/operating.md`.
- `config/` is the Django project (settings, root URLs, WSGI/ASGI). `races/` is the app: Club, Boat, Series, SeriesEntry, Race, RaceEntry and Finish models, set up through the Django admin; `races/scoring.py` replays a series through `nhc` on every request (nothing derived is stored); `races/audit.py` records every change to a score-affecting field as a `ScoringChange` row (who, when, old and new, and a reason for corrections), called explicitly from the finish view and the admin rather than via signals; a committee-only race day page per race (slice 9, `races/race_day.py` and `/races/<pk>/`: a Start sheet view and a Finishing view where a **Finished** button stamps the site's local time, with a two-minute Undo, 5-second HTMX polling that answers 204 when nothing changed, and `static/js/race-clock.js`, the one approved hand-written script; `race_day.now` is the clock to fix in tests) and a committee-only history page per series. The old finish-entry and start sheet addresses redirect to the race day page. Roles (see `docs/brief.md`) are per club (slice 11 part 2): a `ClubMembership` gives a person a role at one club (member, committee or administrator) once approved, and `races/roles.py` answers `is_member/is_committee/is_club_administrator(user, club)` from it. Use `member_required` / `committee_required` / `club_administrator_required`: the public is sent to log in, and a logged-in person without the role gets a 403, never a login redirect, which would loop. `is_staff`, the old "Race committee" group and superuser status grant nothing at a club; a superuser is the service's operator. Sign-up confirms the email with a signed link (`races/membership_views.py`) and asks to join the club; club administrators decide on the Members page (`/members/`). Test builders `make_member/make_committee/make_administrator` create an approved Demo Club membership (`club=`, `role=`, `status=` to vary it; `join()` adds another club), and `make_operator()` a superuser with none. Members change nothing directly: `races/member_views.py` creates `BoatRequest`/`EntryRequest` rows, and `races/approvals.py` applies one when the committee approves it on the Requests page, through the same audit code as the admin. Email (slice 4) goes only through `races/notifications.send`, which sends after the transaction commits and turns a failure into a logged warning on the page rather than an error; templates are `templates/emails/*.txt`, first line the subject. `races/publishing.py` publishes a race's results and decides "amended since sent" from the change history. `races/final.py` (slice 10) declares a series final and reopens it: a final series is locked (every write path calls `final.check_open`, or `check_series_open` to read the series fresh) and `races/scoring.score_series` rebuilds its results from `Series.final_results`, a JSON copy of the engine's output, instead of replaying; this is the one place derived results are stored. Declaring and reopening are history rows of kind FINAL, which neither mark races amended nor move the standings' "Last updated". `races/start_sheet.py` (slice 6) keeps each race's start sheet (`RaceEntry`): only a boat on it can have a finish, every boat on it needs a time or a code before publishing, and a boat on it with nothing recorded is still scored DNC but shown as "Not recorded". Start sheet changes are not audited, since none moves a score. The test builder `record()` puts the boat on the start sheet first. `races/urls.py` is included at the site root. Project-level templates live in `templates/` (`base.html` loads HTMX and sends the CSRF token via `hx-headers`, so HTMX POSTs work without per-form tokens); HTMX is vendored at `static/js/htmx.min.js` (v2.0.10), not loaded from a CDN. The look (slice 7) is one hand-written stylesheet, `static/css/site.css`: every colour is a token in its `:root`, and `races/test_styles.py` checks the tokens meet WCAG AA contrast, that no colour is written anywhere else, and that pages load only the site's own files. `templates/500.html` copies the look inline and loads nothing. `ping` is an example view demonstrating HTMX fragment responses. `races/testing.py` has builders for the app's tests.
- `results/` is the public results app (slice 5): the home page (boat search, latest results, every series), a series page and a boat page, at `/`, `/series/<pk>/` and `/boats/<pk>/`. It only reads: no models, GET-only views, and it shows what `races.scoring.score_series` computes and nothing else. The CSV download at `/series/<pk>/results.csv` (slice 10) is built from the same results by `races/series_csv.py`, which the club's data export uses too. It imports from `races`; `races` never imports from it (it links to it by URL name only). `results/test_read_only.py` enforces all of this. Each HTMX interaction goes to the same URL as its full page; `results/views.py:_render` returns just the targeted fragment when `request.htmx` names it. Public pages never show owners' names.
- User manual: `manual/` is for the site's users (members, race committee, administrator), organised by role and written in plain CommonMark plus tables so it stays portable; `mkdocs.yml` lists its pages and `.readthedocs.yaml` publishes it. `docs/` is developer documentation and is not part of it. `tests/test_manual.py` checks every link, image and contents entry; screenshots come from `scripts/manual_screenshots/` against throwaway sample data.
- Hosting (slice 12): `render.yaml` describes two sites. The free test site deploys `main` on every push, running `build.sh` (collectstatic, then `release.sh`: migrate, createcachetable, `ensure_superuser`) and then `gunicorn`; see `docs/deploying.md`. Production (`racetimes-production`, Frankfurt, `racetimes.co.uk`) deploys only when Deploy is pressed, runs `release.sh` as its pre-deploy step, and has a nightly cron job (`backup/`: pg_dump, gpg-encrypted, to S3-compatible storage; `backup/restore.sh` reads one back). `docs/production.md` is its runbook; `scripts/check_live.py` (standard library only) checks the live site; `manage.py series_summary` compares a restored database with production. `races/test_production.py` pins the Blueprint's production settings. `www.<SERVICE_DOMAIN>` redirects to the service's address (`races/clubs.py`). With `DJANGO_DEBUG=0` the settings switch to production behaviour: WhiteNoise serves static files, HTTPS is enforced (redirect, HSTS for `SECURE_HSTS_SECONDS`, secure cookies), and a missing `DJANGO_SECRET_KEY` stops the site starting.
- Running in production (slice 11 part 4): `races/health.py` answers `/health/` first in `MIDDLEWARE`, on any address, over plain HTTP. Every email is built in `races/notifications.email_to` (or `forms.ClubPasswordResetForm`, for Django's password reset), which sends it as "<Club> via Race Times" from `DEFAULT_FROM_EMAIL` with Reply-To the club's contact email (`notifications.sender`); `races/test_email_sender.py` fails if anything else builds an email. `races/logs.py`: `ClubMiddleware` stores the club's subdomain for log lines (`WARNING [demo] ...`) and tags Sentry with it; the log formatter and Sentry's `before_send` redact email addresses. Sentry starts only when `SENTRY_DSN` is set. `races/throttle.py` locks an account or an address for 15 minutes after 10 failed logins, using the database cache (`CACHES`); the client's address counts `TRUSTED_PROXIES` from the right of `X-Forwarded-For`. Tests fix its clock with `throttle.now`.
- Data protection (slice 11 part 5): `/privacy/` and `/terms/` (drafts) on every address, linked from the footer; messages live in the session, so the only cookies are `sessionid` and `csrftoken` (`races/test_legal.py` checks every page). `races/account_views.py`: `/account/`, `races/my_data.py` (a person's JSON download, across their clubs) and `races/account_deletion.py` (every text field holding their login becomes "a deleted account", then the account goes; refused for a club's only administrator and the operator). These account pages are the one place another club's name appears, as the person's own (`OWN_DATA` in `races/test_isolation.py`). `races/club_export.py`: the club's ZIP of CSVs, for its administrators (Members page) and the operator (logged; works while suspended). `races/series_csv.typed()` guards typed text against spreadsheet formulas. `races/club_deletion.py`: the operator deletes a suspended club, series before boats (`SeriesEntry.boat` is PROTECT). `races/conftest.py` makes CSRF tokens fixed in tests, so a check that a name is *not* on a page can't be tripped by a random token.
- Settings are driven by environment variables (see `.env.example`; `.env` is gitignored but not loaded automatically, so export the variables yourself): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` (defaults on), `DJANGO_ALLOWED_HOSTS` (comma-separated), `DATABASE_URL`, and the `EMAIL_*` settings (unset, emails are printed to the console). With `DATABASE_URL` unset, the database is `db.sqlite3` in the repo root; set it to a `postgres://...` URL to use PostgreSQL.


## How we work
- Read docs/brief.md and docs/plan.md for context before planning anything.
- Work on one slice at a time. The current slice spec is in docs/slices/.
- Do not start work beyond the current slice's scope.
- Record decisions in docs/decisions.md.
- When a slice's acceptance criteria are met, update its status in plan.md.
