# nhc

A scoring engine for sailing race series handicapped under the RYA National
Handicap for Cruisers (NHC) scheme.

Give it a series' boats and the finish times a race officer wrote down, and it
returns corrected times, finishing places, points, handicaps for the next race,
and the series table. It implements the NHC handicap rules and the parts of RRS
Appendix A that scoring a series needs.

It depends on nothing but the Python standard library (3.11 or later), and
knows nothing about Django, databases, HTTP or files - it takes plain Python
data and returns plain Python data, so it can be copied into any project.
`tests/test_package_purity.py` enforces that.

## Quick start

```python
from nhc import Boat, Finish, RaceStatus, Series, SeriesRace, score_series

boats = [
    Boat("GBR1234", base_number=0.985, current_tcf=0.985, name="Arcona 340"),
    Boat("GBR5678", base_number=0.843, current_tcf=0.843, name="Achilles 24"),
    Boat("GBR9012", base_number=1.135, current_tcf=1.135, name="1D35"),
]

races = [
    SeriesRace("Race 1", [
        Finish("GBR1234", RaceStatus.FINISHED, elapsed_seconds=4320),
        Finish("GBR5678", RaceStatus.FINISHED, elapsed_seconds=5100),
        Finish("GBR9012", RaceStatus.FINISHED, elapsed_seconds=3840),
    ]),
    SeriesRace("Race 2", [
        Finish("GBR1234", RaceStatus.FINISHED, elapsed_seconds=4400),
        Finish("GBR5678", RaceStatus.FINISHED, elapsed_seconds=5000),
        Finish("GBR9012", RaceStatus.DNF),
    ]),
    # GBR5678 has no finish recorded here, so it is scored DNC (RRS A2.2).
    SeriesRace("Race 3", [
        Finish("GBR1234", RaceStatus.FINISHED, elapsed_seconds=4250),
        Finish("GBR9012", RaceStatus.FINISHED, elapsed_seconds=3900),
    ]),
]

outcome = score_series(Series(boats=boats, races=races, discards=1))

for standing in outcome.standings:
    scores = "  ".join(
        f"({s.points:g})" if s.discarded else f" {s.points:g} "
        for s in standing.scores
    )
    print(f"{standing.position}. {standing.boat_id}  {scores}  total {standing.total:g}")
```

```
1. GBR1234   1   (2)   1   total 2
2. GBR5678   2    1   (4)  total 3
3. GBR9012   3   (4)   2   total 5
```

Discarded scores are in brackets. `outcome.ending_handicaps` gives each boat's
handicap after the final race.

## How it works

A series is scored by **replaying it from the start**. Each race is scored on
the handicaps the previous race produced, and the handicaps it produces become
the next race's. Two consequences:

- **You never set a handicap.** It is derived from where the series started
  plus everything that has happened since. `Finish` carries only a boat, and a
  time or a code - what a race officer actually writes down.
- **Corrections are free.** Change a finish, call `score_series` again, and
  every later race is recalculated. There is no incremental update path, on
  purpose: one that drifted out of step with a full replay would be a very
  quiet bug.

A boat with no recorded finish in a race is scored DNC, because RRS A2.2 scores
a series entrant for the whole series whether she turns up or not.

## Public interface

### Describing a series

| Name | What it is |
| --- | --- |
| `Boat(boat_id, base_number, current_tcf, name="")` | A boat's published rating (BN) and the handicap it carries into its next race |
| `Finish(boat_id, status, elapsed_seconds=None)` | One recorded outcome: a time, or a scoring code |
| `SeriesRace(race_id, finishes)` | One race's finishes. No handicaps - they are derived |
| `Series(boats, races, series_type=CLUB, progression=CARRY_OVER, minimum_finishers=0, apply_a5_3=False, discards=1, cap_extremes=False, realign_to_base=False)` | The races, the boats, and the rules they are scored under |
| `SeriesType` | `CLUB` or `REGATTA` |
| `HandicapProgression` | `CARRY_OVER` starts a series on each boat's `current_tcf`; `RESET` starts it on `base_number` |
| `RaceStatus` | `FINISHED`, `DNC`, `DNS`, `DNF` |

Races are replayed in the order given. The engine does not sort by date: a
date is yours to manage, and two races on one evening still have an order.

### Scoring a series

| Name | What it is |
| --- | --- |
| `score_series(series)` | Replays the series and scores every race in it |
| `SeriesOutcome` | `.races`, `.standings`, `.starting_handicaps`, `.ending_handicaps`, `.race(race_id)` |
| `RaceOutcome` | `.race_id` and `.results` for one race |
| `RaceResult` | One boat in one race - see below |
| `BoatStanding` | `.position`, `.total`, `.scores`, `.counted_points`, `.discarded_race_ids` |
| `RaceScore` | `.race_id`, `.points`, `.discarded` |
| `Performance` | `OVER` or `UNDER` - whether a boat beat its handicap |

`RaceResult` carries, per boat: `status`, `tcf_used`, `elapsed_seconds`,
`corrected_time`, `position`, `points`, `adjustment_scale` (AS),
`achieved_handicap` (TCFr), `performance`, `next_tcf` (TCFn),
`next_tcf_clamped`, `elapsed_seconds_used`, `realignment_factor`,
`effective_next_tcf`, and `capped`.

A `None` handicap field means *this pass did not compute it*, which is distinct
from a genuine zero - a boat that did not finish earns an `adjustment_scale` of
`0.0`, while a race below the finisher threshold leaves it `None`.

### Scoring one race at a time

Useful if you are not replaying a whole series - to re-check a single race, or
to drive the steps yourself.

| Name | What it is |
| --- | --- |
| `RaceEntry(boat_id, status, tcf_used, elapsed_seconds=None, base_number=None)` | One boat in a race, with the handicap it raced under |
| `RaceInput(series_type, entries, is_first_race_of_regatta=False)` | A race ready to score |
| `score_race(race)` | Corrected times and finishing places |
| `compute_club_adjustment(race, *, minimum_finishers=0, cap_extremes=False, realign_to_base=False)` | Scores a club race and computes next handicaps |
| `compute_regatta_adjustment(race)` | The same for a regatta |
| `score_points(results, *, series_entry_count, apply_a5_3=False)` | RRS Appendix A race points |
| `compute_standings(races, *, discards=1)` | The series table |

`score_points` needs `series_entry_count` because A5.2 scores every
non-finisher at *one more than the number of boats entered in the series*, and
a single race cannot know that number. Inferring it from the boats present
would quietly under-score non-finishers in any race with absentees.

### Between series

| Name | What it is |
| --- | --- |
| `realign_series(entries)` | `CN = (sum BN / sum EH) x EH`, pulling drifted handicaps back |
| `realignment_entries(series, outcome)` | Builds that input from a scored series |
| `realigned_boats(series, results)` | The same boats, ready for the next series |
| `RealignmentEntry` / `RealignmentResult` | Its input and output |

To carry realigned handicaps into the next series:

```python
results = realign_series(realignment_entries(series, outcome))
next_series = Series(boats=realigned_boats(series, results), races=[...])
```

### The formulas on their own

| Name | What it is |
| --- | --- |
| `corrected_time(elapsed_seconds, tcf)` | `C = E x TCF` |
| `adjustment_scale(elapsed_seconds)` | `AS = 100 / E` |
| `points_for_place(place, boats_tied=1)` | A4 points, shared across an A7 tie |
| `clamp_to_base_number(tcf, base_number)` | Holds a handicap within 10% of a base number |

### Optional extra steps for a club series

Some clubs publish with a fuller method than the RYA's (HalSail documents it;
Medway Cruising Club uses it). It adds two steps, each off unless a series asks
for it, and each in `options.py` on its own:

| Name | What it is |
| --- | --- |
| `cap_extremes=True` | Step A. A finisher whose corrected time is more than one sample standard deviation from the fleet's mean has its achieved handicap worked from the band-edge time instead. Needs at least 3 finishers. The fleet ratio, times, places and points don't change |
| `realign_to_base=True` | Step B. Every finisher's TCFn is scaled by one factor so their total equals their base numbers' total. Skipped if a finisher has no base number |
| `capped_elapsed_times(finishers)` | Step A on its own: the time each finisher's achieved handicap is worked from |
| `realignment_factor(finishers, next_tcfs)` | Step B's factor: sum of base numbers over sum of TCFn |
| `realign_to_base_numbers(results, finishers)` | Step B applied to a race's results |

A capped result shows as `elapsed_seconds_used` differing from
`elapsed_seconds` (`RaceResult.capped`), and a realigned one carries its
`realignment_factor`. Both are refused on a regatta, which has its own formulas
and clamps to base numbers instead. With both off, results are exactly the
RYA's.

### Errors

`InvalidInput` is raised for input the spec says to reject - a non-positive or
non-finite handicap, a boat marked `FINISHED` with no usable time, a regatta
entry with no base number to clamp against. It subclasses `ValueError`, so code
that already handles bad input generically catches it without importing from
`nhc`.

Every type validates itself on construction, so an invalid race cannot be built
and a mistake surfaces where the bad data enters rather than several formulas
later.

## Three things worth knowing

**Handicaps are never rounded.** Full floating-point precision is carried
through every calculation and between races, per section 7 of the RYA spec. The
RYA publishes its tables at 3 decimal places, but that is a display convention -
rounding as you go compounds across a series. Round when you show a number to a
person, not before. If the club's existing software rounds between races, its
results will differ in the third decimal, and that is worth raising with them
rather than quietly matching.

**In a regatta, `next_tcf` is not the number that counts.** Regattas clamp a
new handicap to within 10% of the boat's base number, and the spec keeps the
pre-clamp value visible so the arithmetic can be checked. Use
`effective_next_tcf`, which returns the clamped value when there is one.

**A club series and a regatta differ more than they look.** A club series
excludes non-finishers from the handicap sums entirely; a regatta
back-calculates an elapsed time for them so they count, blends harder (60/50
against 30/15), and clamps. `compute_club_adjustment` refuses a regatta race
and vice versa, because applying the wrong rules produces plausible numbers
that are quietly wrong.

## Rules implemented

| Rule | Where |
| --- | --- |
| Corrected time, `C = E x TCF` | `scoring.py` |
| Club handicap adjustment (spec s3) | `handicap.py` |
| Optional capping of extreme results, and realignment to base numbers (HalSail's fuller method) | `options.py` |
| Regatta adjustment, back-calculation and clamp (spec s4) | `regatta.py` |
| End-of-series realignment (spec s5) | `realignment.py` |
| RRS A4 low point, A5.2, A5.3, A7 ties | `points.py` |
| RRS A2.1 discards, A8.1 and A8.2 countback | `standings.py` |
| Replaying a series, RRS A2.2 | `series.py` |

The RYA's own published worked examples are in `tests/fixtures/` as SCEN-005
(club adjustment) and SCEN-006 (realignment), and both reproduce exactly. A
failure there is a defect in this package, never a fixture to adjust.

## Not implemented

- **RRS A6.1**, boats moving up a place when one ahead is disqualified or
  retires after finishing. It cannot fire with the four statuses modelled here,
  since none of them ever held a finishing place. It needs `DSQ`, `RET` or
  `NSC`.
- **Scoring codes beyond `FINISHED`, `DNC`, `DNS` and `DNF`.** RRS A10 defines
  fourteen. Adding the ones that finish and are then penalised would change an
  invariant here, since such a boat *does* have an elapsed time.
- **A discard schedule.** `discards` is a fixed count; A2.1 also allows "a
  specified number excluded if a specified number of races are scored", the
  familiar *no discard until four races*.
- **Adjusting handicaps for non-finishers in a club series.** The brief makes
  this a per-series choice, but the RYA spec defines only the "not adjusted"
  behaviour for club racing.
- **Multiple starts per race, and pursuit races**, both out of scope for this
  slice.

There is no published RYA worked example for regattas as there is for club
series, so the regatta rules are validated against a reading of section 4
rather than against the RYA's own numbers.

## Source of truth

- Handicaps: `docs/reference/RYA_nhc_calculation_spec.md`
- Points, discards and series ties: RRS Appendix A, in
  `docs/reference/2025-2028-RRS-with-Changes-and-Corrections.pdf`

Where this implementation and those documents disagree, the documents win.

Decisions taken along the way, and the questions still open, are in
`docs/decisions.md`.
