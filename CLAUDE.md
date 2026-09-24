# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About me (experience level, how to explain things)

I'm a capable amateur in Python; explain non-obvious decisions briefly in commit messages or comments.

## Stack and versions

Python 3.11, Django 5.2, SQLite for development and PostgreSQL (via `psycopg`) for production. Keep code and migrations compatible with both. HTMX 2.x for frontend interactivity (server-rendered Django templates and partials, not a JS SPA), with `django-htmx` middleware so views can check `request.htmx`. Avoid javascript (ask first if necessary). pytest (with `pytest-django`) is the test framework for the whole project - both the Django app and the scoring engine. Write tests as plain functions with bare `assert`s, not `unittest.TestCase` subclasses.

## Definition of done
New behaviour has tests. No linter errors. All tests pass. Migrations created. Manual checks completed.

## Guardrails (never / ask first)
Ask before changing the data model. Don't install new dependencies without asking.

- Fixtures in tests/fixtures/ are the specification. Never edit a fixture's
  expected values to make a test pass — if they disagree with the code, the
  code is wrong, or the fixture's provenance needs checking with me first.
- Do not generate new fixtures from the engine's own output.

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
.venv/bin/python manage.py runserver
.venv/bin/python manage.py makemigrations
```

Tests:

```bash
.venv/bin/python -m pytest                           # all tests
.venv/bin/python -m pytest tests                     # scoring engine only
.venv/bin/python -m pytest races                     # Django app only
.venv/bin/python -m pytest tests/test_fixtures.py::test_fixtures_load   # a single test
.venv/bin/python -m pytest -k "SCEN-005"              # by name (case-sensitive)
```

No linter is configured yet.

CI runs on every pull request (`.github/workflows/ci.yml`): the test suite on
Python 3.11 and 3.12, `manage.py check`, a check for missing migrations, and a
job that imports `nhc` with nothing installed, to prove the package really is
standard-library only.

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
  fixture I/O happens there, never inside `nhc/`.
- `config/` is the Django project (settings, root URLs, WSGI/ASGI). `races/` is the app: Boat, Series, SeriesEntry, Race and Finish models, set up through the Django admin; `races/scoring.py` replays a series through `nhc` on every request (nothing derived is stored); `races/audit.py` records every change to a score-affecting field as a `ScoringChange` row (who, when, old and new, and a reason for corrections), called explicitly from the finish view and the admin rather than via signals; a public results page, a committee-only HTMX finish-entry page and a committee-only history page per series. Roles (see `docs/brief.md`) are in `races/roles.py`: member = active account, race committee = staff in the "Race committee" group (created by migration 0005, with no permissions on accounts), administrator = superuser; use `committee_required` / `member_required`, never `is_staff` alone. Members change nothing directly: `races/member_views.py` creates `BoatRequest`/`EntryRequest` rows, and `races/approvals.py` applies one when the committee approves it on the Requests page, through the same audit code as the admin. `races/urls.py` is included at the site root. Project-level templates live in `templates/` (`base.html` loads HTMX and sends the CSRF token via `hx-headers`, so HTMX POSTs work without per-form tokens); HTMX is vendored at `static/js/htmx.min.js` (v2.0.10), not loaded from a CDN. `ping` is an example view demonstrating HTMX fragment responses. `races/testing.py` has builders for the app's tests.
- Hosting: `render.yaml` deploys `main` to Render on every push, running `build.sh` (collectstatic, migrate, `ensure_superuser`) and then `gunicorn`; see `docs/deploying.md`. With `DJANGO_DEBUG=0` the settings switch to production behaviour: WhiteNoise serves static files, cookies are HTTPS-only, and a missing `DJANGO_SECRET_KEY` stops the site starting.
- Settings are driven by environment variables (see `.env.example`; `.env` is gitignored but not loaded automatically, so export the variables yourself): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` (defaults on), `DJANGO_ALLOWED_HOSTS` (comma-separated), and `DATABASE_URL`. With `DATABASE_URL` unset, the database is `db.sqlite3` in the repo root; set it to a `postgres://...` URL to use PostgreSQL.


## How we work
- Read docs/brief.md and docs/plan.md for context before planning anything.
- Work on one slice at a time. The current slice spec is in docs/slices/.
- Do not start work beyond the current slice's scope.
- Record decisions in docs/decisions.md.
- When a slice's acceptance criteria are met, update its status in plan.md.
