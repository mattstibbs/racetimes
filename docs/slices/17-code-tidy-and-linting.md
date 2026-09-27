# Slice 17: code tidy-up and linting

**Status: complete (2026-09-27). The owner agreed the plan: Ruff,
88-character lines, split `forms.py` as well as `views.py`, and lint fixes
only in `nhc/`.**

## Goal
A review of the whole codebase for clean, readable code, and a linter and
formatter so that it stays that way. Nothing a user sees changes: no model,
migration, template or manual change. The test suite passes after every
commit and is the proof that behaviour is unchanged.

## Linting: Ruff
Ruff (`ruff check`) is the linter and `ruff format` the formatter, configured
in `pyproject.toml`. Rules: pycodestyle (E, W), pyflakes (F), import order
(I), bugbear (B), pyupgrade (UP), Django (DJ), simplify (SIM), comprehensions
(C4) and Ruff's own (RUF), for Python 3.11 at 88 characters.

- `RUF012` (mutable class attributes) is off: it flags every Django `Meta`
  list and `ModelAdmin` option.
- `E501` (line too long) is off: the formatter wraps code, and what is left is
  long strings and URLs, which read worse broken up.
- `migrations/` is left alone: Django generates it.
- CI gains a `lint` job running `ruff check .` and `ruff format --check .`.
- The one-off formatting commit is listed in `.git-blame-ignore-revs`, so
  `git blame` skips it.

## Review findings to act on

### Structure
1. Split `races/views.py` (legal pages, race day, final results, change
   requests, publishing) into one `*_views.py` per area, like the rest of the
   app. URL names don't change.
2. Remove the slice 1 `ping` example view.
3. Test modules import fixtures and helpers from each other. Shared fixtures
   move to `races/conftest.py`, shared helpers to `races/testing.py`.
4. Split `races/forms.py` by area: audited admin forms, account forms, the
   operator's forms, and members' forms.

### Long or repetitive functions
1. `races/scoring.score_series`: pull out the race results and the standings,
   and share loading the rows with `engine_outcome`.
2. `_finishing_context`: pull out building the rows and ordering them across
   the line.
3. The race day views' repeated preamble (find the race, find the entry,
   check it isn't final) and `" ".join(error.messages)`: small helpers.
4. Explicit keyword arguments instead of `**extra` through the race day
   context functions.
5. `races/series_csv.series_csv`: split into its sections.

### Comments and readability
- One-line module docstrings where missing.
- Constants and class attributes above the code that uses them.

### Not changing
- `nhc/`: lint fixes only. The fixtures are its specification, and its long
  functions are mostly documentation and numbered steps.
- The data model, templates and the user manual.
