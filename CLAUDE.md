# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About me (experience level, how to explain things)

I'm a capable amateur in Python; explain non-obvious decisions briefly in commit messages or comments.

## Stack and versions

Python 3.11, Django 5.2, SQLite for development and PostgreSQL (via `psycopg`) for production. Keep code and migrations compatible with both. HTMX 2.x for frontend interactivity (server-rendered Django templates and partials, not a JS SPA), with `django-htmx` middleware so views can check `request.htmx`. Avoid javascript (ask first if necessary).

## Definition of done
New behaviour has tests. No linter errors. All tests pass. Migrations created. Manual checks completed.

## Guardrails (never / ask first)
Ask before changing the data model. Don't install new dependencies without asking.


## Commands (run, test, lint, migrate)

Setup (uses a local `.venv`, which is gitignored):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
.venv/bin/python manage.py test                      # all tests
.venv/bin/python manage.py test races.tests.SomeTest.test_name   # a single test
.venv/bin/python manage.py makemigrations
```

No linter is configured yet.

## Architecture

- `config/` is the Django project (settings, root URLs, WSGI/ASGI). `races/` is the app (no models yet; `races/urls.py` is included at the site root). Project-level templates live in `templates/` (`base.html` loads HTMX and sends the CSRF token via `hx-headers`, so HTMX POSTs work without per-form tokens); HTMX is vendored at `static/js/htmx.min.js` (v2.0.10), not loaded from a CDN. `home` and `ping` are example views demonstrating HTMX fragment responses.
- Settings are driven by environment variables (see `.env.example`; `.env` is gitignored but not loaded automatically, so export the variables yourself): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` (defaults on), `DJANGO_ALLOWED_HOSTS` (comma-separated), and `DATABASE_URL`. With `DATABASE_URL` unset, the database is `db.sqlite3` in the repo root; set it to a `postgres://...` URL to use PostgreSQL.


## How we work
- Read docs/brief.md and docs/plan.md for context before planning anything.
- Work on one slice at a time. The current slice spec is in docs/slices/.
- Do not start work beyond the current slice's scope.
- Record decisions in docs/decisions.md.
- When a slice's acceptance criteria are met, update its status in plan.md.
