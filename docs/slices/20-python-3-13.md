# Slice 20: move to Python 3.13

**Status: approved by the owner (2026-09-27).**

## Goal
Run Race Times on Python 3.13 instead of 3.11, before 3.11's support ends.
Nothing a user sees changes.

## Why now, and why 3.13
- **3.11 is already on security fixes only, and its support ends in October
  2027.** 3.13 is supported until October 2029.
- **Everything the site depends on supports 3.13:** Django 5.2, psycopg,
  gunicorn, whitenoise, Sentry, django-htmx and dj-database-url all list it.
- **Not 3.14 yet:** gunicorn, the production web server, doesn't list 3.14
  yet. CI tests on 3.14 too, so we'll know when the step from 3.13 is safe.
- **Checked before starting:** the full suite (1573 tests) passed on Python
  3.13.12 with nothing changed.

## The scoring engine keeps its promise
`nhc/README.md` promises the engine works on "Python 3.11 or later", so it
can be copied into other projects. So:
- **The engine (`nhc/`) and its tests (`tests/`) stay 3.11-compatible.**
  Ruff targets 3.11 for those two folders and 3.13 for everything else, so
  it never suggests syntax that 3.11 can't run in them.
- **CI runs the engine's tests on 3.11,** in their own job. The engine job
  that imports `nhc` with nothing installed stays on 3.11, the oldest
  version it promises.

## What changes
- `render.yaml`: `PYTHON_VERSION` 3.11.9 → 3.13.12, for the test site and
  production. The backup job runs in its own Docker image and doesn't use
  Python, so it doesn't change.
- `.github/workflows/ci.yml`:
  - the full suite on 3.13 and 3.14, instead of 3.11 and 3.12;
  - a new job running the engine's tests (`pytest tests`) on 3.11;
  - the lint, deploy check and manual jobs on 3.13.
- `.readthedocs.yaml`: the manual builds on 3.13.
- `pyproject.toml`: Ruff targets 3.13, with `nhc/` and `tests/` kept at 3.11.
  Any modernisations Ruff then suggests elsewhere are applied; they're all
  automatic rewrites.
- Docs: CLAUDE.md, the README, `docs/deploying-manual.md`, and a decision
  record. Local setup uses `python3.13`.

## Not changing
- Django stays on 5.2 (its long-term support release). No dependency is
  upgraded or added, and there's no model or migration change.

## Deploying
The first deploy of each site builds a fresh environment on 3.13. If
production misbehaves, Render's **Rollback** returns to the previous deploy in
one click, and there's nothing in the database to undo.

## Acceptance criteria
- The full suite passes on 3.13 and 3.14 in CI, and the engine's tests pass
  on 3.11.
- `ruff check .` and `ruff format --check .` pass with the new targets.
- `manage.py check --deploy` passes with production settings on 3.13.
- The site runs locally on 3.13, checked by hand in a browser.
- After deploying, `scripts/check_live.py` passes against production.
