# nhc

A pure-Python scoring engine for sailing race series handicapped under the RYA
National Handicap for Cruisers (NHC) scheme.

It takes a series' race history - boats with base handicaps, races, and each
boat's finish time or scoring code - and returns race handicaps, corrected
times, race results and series standings. It has no dependencies beyond the
standard library, and no knowledge of Django, databases or I/O, so it can be
imported into any Python project.

## Status

In progress. The domain types and their validation are in place; the
calculations follow. The public interface is being built out against the
fixtures in `tests/fixtures/`, and this README documents it in full once it
stabilises (an acceptance criterion of `docs/slices/00-scoring-engine.md`).

So far, importable from `nhc`:

| Name | What it is |
| --- | --- |
| `Boat` | A boat's base number (BN) and the handicap it carries into its next race |
| `RaceEntry` | One boat's participation in one race: status, the TCF it raced under, elapsed time |
| `RaceInput` | A race ready to score: series type plus its entries |
| `RaceResult` | What the engine computes per boat per race |
| `RealignmentEntry` / `RealignmentResult` | End-of-series realignment in and out |
| `RaceStatus`, `SeriesType`, `Performance` | The closed sets of values, as `StrEnum`s |
| `InvalidInput` | Raised on construction for input the spec says to reject |
| `score_race(race)` | Corrected times and finishing places for one race |
| `corrected_time(elapsed, tcf)` | `C = E x TCF` on its own |
| `compute_club_adjustment(race, *, minimum_finishers=0)` | Scores a club race and computes everyone's handicap for the next one |
| `adjustment_scale(elapsed)` | `AS = 100 / E` on its own |

Every type is a frozen dataclass that validates itself, so an invalid race
cannot be built. `InvalidInput` subclasses `ValueError`.

## Precision

Handicaps are carried at full floating-point precision and are never rounded
between races, per section 7 of the RYA spec. The published RYA tables are at
3 d.p., but that is a display convention - rounding as you go compounds across
a series. Round at the edges, when showing a number to a person.

## Source of truth

- Handicap calculation: `docs/reference/RYA_nhc_calculation_spec.md`
- Points, discards and series ties: RRS Appendix A, in
  `docs/reference/2025-2028-RRS-with-Changes-and-Corrections.pdf`

Where this implementation and those documents disagree, the documents win. The
fixtures encode the documents' own published worked examples (SCEN-005 and
SCEN-006); a failure there is a defect in the engine, never a fixture to adjust.
