# Slice 1: Walking skeleton

## Goal
The thinnest end-to-end path through the real app: a race committee sets up
boats and a series, records finishes after each race, and anyone can see the
results - with every number coming from the `nhc` engine built in slice 0.

## Scope

### Data model
Decided in the slice 1 planning pass; reasoning in `docs/decisions.md`.

- **Boat**
  - `sail_number` - text, required. Unique ignoring case and spaces: a
    normalised copy (upper-case, spaces removed) is stored alongside and
    carries the unique constraint, so "gbr 1234" and "GBR1234" collide.
  - `name`, `make`, `model`, `owner_name` - text, optional.
  - `length_overall_m`, `waterline_length_m` - metres to 2 d.p., optional.
    Recorded only; nothing calculates with them.
  - `base_number` - the published NHC base handicap, exact decimal to 3 d.p.,
    required, greater than zero. Converted to float only when handed to the
    engine.
- **Series**
  - `name`
  - `series_type` - club (default) or regatta.
  - `discards` - whole number, default 1 (RRS A2.1).
  - `minimum_finishers` - whole number, default 0 (off, the RYA behaviour).
    Must be 0 for a regatta; validated on the form so the results page can
    never fail on it.
  - `apply_a5_3` - yes/no, default no (RRS A5.2 scoring).
  - No progression setting: every series starts on base numbers (reset).
- **SeriesEntry** - a boat entered in a series. One per boat per series. A boat
  with entries cannot be deleted.
- **Race** - belongs to a series; `number` (unique within the series, sets the
  replay order), `date`, `start_time` (clock time, whole seconds). One start
  per race.
- **Finish** - one per series entry per race. `status` is FINISHED, DNC, DNS or
  DNF; `finish_time` is a clock time in whole seconds. A database check
  constraint enforces "a time or a code, never both": FINISHED if and only if
  there is a finish time. It references the SeriesEntry rather than the Boat,
  so a finish can only exist for a boat entered in the series, and an entry
  with finishes cannot be removed. Its race must belong to the entry's series,
  and its finish time must be later than the race's start time (validated).

Elapsed time is `finish_time - start_time` on the race's date. A finish earlier
than the start is rejected rather than read as the next day.

### Scoring adapter
`races/scoring.py` turns a Series and its rows into an `nhc.Series` and calls
`score_series`, with races in `number` order and `HandicapProgression.RESET`.
An entered boat with no Finish row for a race is passed as having no finish, so
the engine scores it DNC (RRS A2.2). Results are computed on every request and
never stored.

### Screens
- **Setup (Django admin, staff only):** boats; series with their entries and
  races editable inline.
- **Finish entry (HTMX, staff only):** one page per race listing every boat
  entered in the series. Each row has a clock-time box and a status dropdown,
  saves on its own, and shows its own validation errors without affecting other
  rows. A saved row shows elapsed time, race handicap and corrected time. Boats
  with no row saved show as DNC.
- **Results (public):** a list of series; for each series, the standings (with
  discarded scores in brackets) and a results table per race - position, boat,
  elapsed time, race handicap, corrected time, points.

Display rounding only: handicaps to 3 d.p., times to whole seconds as h:mm:ss.
Nothing is rounded before it reaches the engine.

### Settings
`TIME_ZONE = "Europe/London"`, so timestamps display in club time. The clock
times entered for starts and finishes carry no timezone and are stored exactly
as typed.

## Acceptance criteria
- A staff user can create boats, a series with its four settings, its entries
  and its races through the admin.
- A staff user can record a finish time or a code for every entered boat in a
  race on one page. An invalid row is rejected with a message and no other row
  is affected.
- The results page shows each race's results and the series standings exactly
  as the engine computes them. The RYA's SCEN-005 worked example, loaded
  through the database as clock times, reproduces its published handicaps.
- Changing a saved finish changes that race and every later race on the next
  page load.
- Enforced by the database: normalised sail numbers are unique; a finish is a
  time or a code, never both; one finish per entry per race; race numbers are
  unique within a series.
- Finish entry and setup require a staff login; results do not.
- Migrations use nothing specific to SQLite or PostgreSQL.

## Out of scope
- Scoring codes beyond FINISHED, DNC, DNS, DNF (OCS, RET, DSQ need engine work
  and a club decision on DSQ handicaps).
- Handicap carry-over between series, and realignment.
- Race-level entries; multiple starts per race; pursuit races; finishes after
  midnight; entering elapsed times directly.
- The per-series "adjusted" option for non-finishers (not in the engine).
- Correction history and audit (slice 2); member accounts and roles (slice 3);
  confirmation and results emails (slice 4); the API; export of results.
