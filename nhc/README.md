# nhc

A pure-Python scoring engine for sailing race series handicapped under the RYA
National Handicap for Cruisers (NHC) scheme.

It takes a series' race history - boats with base handicaps, races, and each
boat's finish time or scoring code - and returns race handicaps, corrected
times, race results and series standings. It has no dependencies beyond the
standard library, and no knowledge of Django, databases or I/O, so it can be
imported into any Python project.

## Status

Skeleton. The public interface is being built out against the fixtures in
`tests/fixtures/`; this README documents it once it stabilises (an acceptance
criterion of `docs/slices/00-scoring-engine.md`).

## Source of truth

- Handicap calculation: `docs/reference/RYA_nhc_calculation_spec.md`
- Points, discards and series ties: RRS Appendix A, in
  `docs/reference/2025-2028-RRS-with-Changes-and-Corrections.pdf`

Where this implementation and those documents disagree, the documents win. The
fixtures encode the documents' own published worked examples (SCEN-005 and
SCEN-006); a failure there is a defect in the engine, never a fixture to adjust.
