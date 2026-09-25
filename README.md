# racetimes

**Race Times**: race results, NHC handicaps and series standings for sailing
clubs, offered as a hosted service at `racetimes.co.uk`. Each club has its own
site, such as `demo.racetimes.co.uk`.

Club racing is scored on handicap, so the boat that crosses the line first
usually is not the boat that wins. Under the RYA's National Handicap for
Cruisers (NHC) scheme each boat's handicap also moves after every race,
according to how it performed against the rest of the fleet — which makes
scoring a season by hand both tedious and easy to get wrong. This project does
it properly.

It is built for:

- **Race committees**, who set up boats and series, run race day from a
  tablet, and need scoring, handicaps and standings to come out right
  automatically.
- **Club members**, who register their boats, enter series, and want to see
  and be emailed their results.
- **The operator** (the project owner), who runs the service for many clubs.

## What it does

- **Scoring:** every race is scored under NHC and RRS Appendix A, and results
  are recalculated from the finishes on every page. A correction to any finish
  flows through to every later race and the standings, and is recorded with
  who, when and why.
- **Race day:** one page per race for the committee. Tick who's racing, tap
  **Finished** as each boat crosses the line (with a two-minute undo), with a
  race clock, on a laptop or tablet.
- **Publishing:** races are provisional until published. Publishing emails
  every owner their results, and after a correction the committee chooses
  when to send the updated results.
- **Members:** sign up, register boats, ask to enter series. Nothing changes
  until the committee approves it.
- **Public results:** each club's home page, series pages with standings,
  and each boat's own page with its next handicap. They work on a phone.
- **End of season:** a series is declared final, which locks it, keeps a copy
  of its results, and emails the owners. Any series downloads as a CSV file.
- **Many clubs:** one database, each club at its own address, with its data
  kept apart and tested for it on every page. Roles are per club: one login
  can be a member at one club and on the committee at another. Emails come
  from the club, and replies go to it.
- **Ready for production:** HTTPS only, a health check, error reports
  (Sentry) and logs that say which club without naming anyone, and a limit
  on failed logins.
- **Data protection:** a privacy notice and terms (drafts, for legal
  review), essential cookies only, people download or delete their own data,
  and a club downloads everything it holds before leaving.

## Status

| Slice | | |
| --- | --- | --- |
| 0 | Scoring engine | **Complete** |
| 1 | Walking skeleton: Django models, finish entry, results page | **Complete** |
| 2 | Corrections and audit trail | **Complete** |
| 3 | Member self-service and accounts | **Complete** |
| 4 | Emailing results | **Complete** |
| 5 | Public results web app | **Complete** |
| 6 | Race-level entry: a start sheet for every race | **Complete** |
| 7 | Visual styling | **Complete** |
| 8 | Other handicap systems (Portsmouth Yardstick, RYA YTC) | On hold |
| 9 | The race day page | **Complete** |
| 10 | Final results and CSV export | **Complete** |
| 11 | Race Times as a service for many clubs | **Complete** |
| 12 | Production hosting at `racetimes.co.uk` | Built; the launch steps in `docs/production.md` are next |

Production runs on Render in Frankfurt, deployed by hand, beside the free test
site, which runs Demo Club with sample data. See [`docs/plan.md`](docs/plan.md) for what each
slice covers, and [`docs/decisions.md`](docs/decisions.md) for open
requirements, such as the legal review needed before the first paying club.

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

1,573 lines across 10 modules, 31 public names, and about 3,000 lines of
tests. The RYA's own published worked examples reproduce exactly.

**[Full documentation in `nhc/README.md`](nhc/README.md)**, including the
interface, the rules implemented, and what is deliberately not.

## Getting started

Requires Python 3.11 or later.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

Run the tests (about 1,300 of them, engine and app):

```bash
.venv/bin/python -m pytest
```

Run the development server:

```bash
.venv/bin/python manage.py migrate && .venv/bin/python manage.py createcachetable
.venv/bin/python manage.py runserver
```

Then open **<http://demo.localhost:8000/>**. Each club has its own address,
and every current browser sends `*.localhost` to your own machine with no
setup. The migrations create Demo Club; `http://localhost:8000/` is the
service's own front page. To log in, create a superuser
(`manage.py createsuperuser`): that's the service's operator. At
`http://localhost:8000/operator/` it can create clubs and invite someone to
run each one; the invitation email, with its link, is printed in the
server's console. See `docs/operating.md`. Or load the user manual's sample
data, as `scripts/manual_screenshots/run.sh` does.

Note that the test suite is pytest, not Django's runner. `manage.py test`
deliberately fails with a pointer, because after the move to pytest it
collected nothing and reported success, which is worse than failing.

## Layout

| Path | |
| --- | --- |
| `nhc/` | The scoring engine. Standard library only, no Django, no I/O |
| `tests/` | The engine's tests and the scenario fixtures they run against, plus a check of the user manual's links |
| `races/` | The Django app: clubs and memberships, models, admin, race day, publishing, final results, change history, member accounts and requests, emails |
| `results/` | The public results pages and the series CSV download. Read-only: no models, GET only |
| `config/` | Django project settings, URLs, WSGI/ASGI |
| `templates/`, `static/` | Server-rendered templates, one hand-written stylesheet, HTMX (vendored, not from a CDN), and the race clock script |
| `manual/` | The user manual, published on Read the Docs |
| `scripts/manual_screenshots/` | Regenerates the manual's screenshots against throwaway sample data |
| `docs/` | Brief, plan, slice specs, decisions, deployment notes and the reference rules |

## Documentation

| | |
| --- | --- |
| [`docs/brief.md`](docs/brief.md) | The problem, the users, the domain and its rules, and who can do what |
| [`docs/plan.md`](docs/plan.md) | The slices, and which are done |
| [`docs/slices/`](docs/slices/) | What each slice covers and how it is judged complete |
| [`docs/decisions.md`](docs/decisions.md) | Decisions taken and why, open questions, and open requirements |
| [`manual/`](manual/index.md) | The user manual, for members, the race committee and club administrators |
| [`docs/deploying-manual.md`](docs/deploying-manual.md) | Publishing the user manual on Read the Docs |
| [`docs/production.md`](docs/production.md) | Running production at `racetimes.co.uk`: set-up, deploying, backups and restoring, alerts |
| [`docs/deploying.md`](docs/deploying.md) | Hosting the test site on Render, which redeploys on every push to `main`; how clubs and roles work there; email, error reports and the production settings |
| [`docs/reference/`](docs/reference/) | The RYA NHC calculation spec and the Racing Rules of Sailing |
| [`CLAUDE.md`](CLAUDE.md) | How the code is organised, and the project's rules for working on it |

The reference documents are the source of truth for every calculation. Where
the code and those documents disagree, the documents win — and where the
fixtures disagreed with them, the fixtures were the things that changed.

## Stack

Python 3.11, Django 5.2, HTMX 2.x. SQLite for development, PostgreSQL in
production via `DATABASE_URL`. Settings come from environment variables; see
[`.env.example`](.env.example).

CI runs on every pull request:
- the suite on Python 3.11 and 3.12;
- `manage.py check` and a check for missing migrations;
- `manage.py check --deploy` with production settings;
- an import of `nhc` on a machine with nothing installed, to keep it honest
  about having no dependencies;
- a strict build of the user manual.
