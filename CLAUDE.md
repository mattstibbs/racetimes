# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

Python 3.11, Django 5.2, SQLite for development and PostgreSQL (via `psycopg`) for production. Keep code and migrations compatible with both.

## Commands

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

- `config/` is the Django project (settings, root URLs, WSGI/ASGI). `races/` is the app, currently empty (no models, views or URLs yet) and already in `INSTALLED_APPS`.
- Settings are driven by environment variables (see `.env.example`; `.env` is gitignored but not loaded automatically, so export the variables yourself): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` (defaults on), `DJANGO_ALLOWED_HOSTS` (comma-separated), and `DATABASE_URL`. With `DATABASE_URL` unset, the database is `db.sqlite3` in the repo root; set it to a `postgres://...` URL to use PostgreSQL.
