# racetimes

A race database and scoring system for sailing clubs running handicap series
and regattas.

Club racing is scored on handicap, so the boat that crosses the line first
usually is not the boat that wins. Under the RYA's National Handicap for
Cruisers (NHC) scheme each boat's handicap also moves after every race,
according to how it performed against the rest of the fleet — which makes
scoring a season by hand both tedious and easy to get wrong. This project does
it properly.

It is being built for two groups:

- **Race committee members**, who register boats, schedule races in a series,
  record finish times, and need the scoring, handicap tracking and series
  standings to come out correctly and automatically.
- **Club members**, who enter their boats and want to see their results.

## Status

| Slice | | |
| --- | --- | --- |
| 0 | Scoring engine | **Complete** |
| 1 | Walking skeleton: Django models, forms, results page | **Complete** |
| 2 | Corrections and audit trail | Not started |
| 3 | Member self-service and accounts | Not started |
| 4 | Emailing results | Not started |
| 5 | Results web app | Not started |

The scoring engine is finished and tested. The Django app is a walking
skeleton: the race committee sets up boats and series in the Django admin,
enters finish times on an HTMX page, and anyone can read the results, which are
recalculated through the engine on every request.

See [`docs/plan.md`](docs/plan.md) for what each slice covers.

## The scoring engine

[`nhc/`](nhc/) is a standalone Python package implementing the NHC handicap
rules and the parts of RRS Appendix A that scoring a series needs: corrected
times, finishing places, progressive handicaps, points, discards, series ties,
regattas and end-of-series realignment.

It depends on nothing but the standard library, does no I/O, and knows nothing
about Django — so it can be copied into any Python project. Give it the finish
times a race officer wrote down and it gives back a series table:

```
1. GBR1234   1   (2)   1   total 2
2. GBR5678   2    1   (4)  total 3
3. GBR9012   3   (4)   2   total 5
```

1,573 lines across 10 modules, 31 public names, 2,919 lines of tests. The RYA's
own published worked examples reproduce exactly.

**[Full documentation in `nhc/README.md`](nhc/README.md)**, including the
interface, the rules implemented, and what is deliberately not.

## Getting started

Requires Python 3.11 or later.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

Run the tests:

```bash
.venv/bin/python -m pytest
```

Run the development server:

```bash
.venv/bin/python manage.py migrate && .venv/bin/python manage.py runserver
```

There is nothing much to see there yet — that is slice 1.

Note that the test suite is pytest, not Django's runner. `manage.py test`
deliberately fails with a pointer, because after the move to pytest it
collected nothing and reported success, which is worse than failing.

## Layout

| Path | |
| --- | --- |
| `nhc/` | The scoring engine. Standard library only, no Django, no I/O |
| `tests/` | The engine's tests, and the scenario fixtures they run against |
| `races/` | The Django app: models, admin, results and finish-entry pages |
| `config/` | Django project settings, URLs, WSGI/ASGI |
| `templates/`, `static/` | Server-rendered templates; HTMX is vendored, not from a CDN |
| `docs/` | Brief, plan, slice specs, decisions, and the reference rules |

## Documentation

| | |
| --- | --- |
| [`docs/brief.md`](docs/brief.md) | The problem, the users, the domain and its rules |
| [`docs/plan.md`](docs/plan.md) | The slices, and which are done |
| [`docs/slices/`](docs/slices/) | What each slice covers and how it is judged complete |
| [`docs/decisions.md`](docs/decisions.md) | Decisions taken and why, plus the questions still open |
| [`docs/deploying.md`](docs/deploying.md) | Hosting the test site on Render, which redeploys on every push to `main` |
| [`docs/reference/`](docs/reference/) | The RYA NHC calculation spec and the Racing Rules of Sailing |

The reference documents are the source of truth for every calculation. Where
the code and those documents disagree, the documents win — and where the
fixtures disagreed with them, the fixtures were the things that changed.

## Stack

Python 3.11, Django 5.2, HTMX 2.x. SQLite for development, PostgreSQL in
production via `DATABASE_URL`. Settings come from environment variables; see
[`.env.example`](.env.example).

CI runs the suite on Python 3.11 and 3.12, checks for missing migrations, and
imports `nhc` on a machine with nothing installed, to keep it honest about
having no dependencies.
