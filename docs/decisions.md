# Decisions

Running log of decisions that shaped the code and would not be obvious from
reading it. Newest last. Each entry: what was decided, why, and what it costs.

---

## 2026-09-22 - The reference spec beats the fixtures

**Context.** `tests/fixtures/nhc_test_scenarios.yaml` asserted a per-race
absolute clamp of +/-0.020 on club-series handicaps, and a rank-based nudge
("winners trend up"). Neither appears anywhere in
`docs/reference/RYA_nhc_calculation_spec.md`. Four expectations were
unreachable by any correct implementation of the spec.

**Decision.** The spec wins; the fixtures were regenerated from its section 3
formulas. `docs/brief.md` already names the reference documents as the source
of truth, so this is that rule applied rather than a new one.

**Consequence.** The +/-10% of Base Number clamp still exists, but it is a
regatta rule (spec section 4, step 4) and must not leak into club-series
scoring. The RYA's own published worked examples now live in the fixtures as
SCEN-005 (section 8) and SCEN-006 (section 5), and both reproduce to 3 d.p. A
failure in those two is a defect in the engine, never a fixture to adjust.

---

## 2026-09-22 - Tests are written against stdlib unittest

**Context.** `CLAUDE.md` mandates `manage.py test`. The fixture file was
headed "PyTest Configuration Matrix". The engine itself is meant to be a
standalone package that anyone can vendor.

**Decision.** Write the engine's tests against stdlib `unittest`. Django's test
runner discovers `tests/` without configuration (verified: `manage.py test`
picks them up), and the same files run unchanged under `python -m unittest` and
under `pytest`, which collects `unittest.TestCase` classes natively.

**Consequence.** No test-framework dependency is imposed on anyone vendoring
the package, and the repo convention is honoured. The cost is giving up pytest's
parametrisation and bare-`assert` rewriting; fixture-driven scenarios will use
`subTest` instead, which is more verbose but localises failures just as well.

---

## 2026-09-22 - The engine is standard-library only, enforced by a test

**Context.** Slice 0 requires "a pure Python package ... No Django, no
database, no I/O" that is easy to drop into any Python project. That promise
erodes silently - one convenience import and the package stops being portable.

**Decision.** `nhc/` imports nothing outside the standard library, and
`tests/test_package_purity.py` enforces it: an AST scan of every source file
checks each top-level import against `sys.stdlib_module_names`, and a
subprocess import check proves `nhc` loads with no Django present and no
settings configured. The subprocess matters because the suite itself may be
running under Django, where an in-process check would prove nothing.

**Consequence.** Any future third-party import in `nhc/` fails the build by
name. I/O - including reading the YAML fixtures - stays on the test side of the
boundary, never inside the package.

---

## 2026-09-22 - Fixtures live in tests/fixtures/

`docs/slices/00-scoring-engine.md` names `tests/fixtures/` in its acceptance
criteria; the file was at `tests/nhc_test_scenarios.yaml`. Moved to match the
spec rather than amending the spec.

---

## Open questions

Carried from the slice 0 planning pass. These need answers before the affected
step, not before any code is written.

- **Rounding between races.** Spec section 7 says carry full precision; the
  published tables are 3 d.p. Rounding TCFn to 3 d.p. between races will drift
  from full precision over a six-race series. SCEN-006 BOAT_3 lands on
  0.88050096, a millionth above the rounding boundary, and is the canary.
- **DNF in a club race.** Spec section 3 step 1 computes AS "for every boat that
  finished"; step 2 says the sums run over "every boat that started". A DNF boat
  started but has no elapsed time, so the two sentences disagree. Current
  assumption, encoded in SCEN-004: excluded from both sums, handicap carried
  forward unchanged. Matches the brief's per-series "adjusted / not adjusted"
  switch.
- **Minimum-finisher threshold.** Spec section 9 flags the 3-finisher rule as
  unconfirmed. Intended as an option defaulting to off rather than a guess.
  SCEN-004 (one finisher) is exactly this case.
- **Equality classification.** When TCFr == TCF exactly, the spec's
  "TCFr <= TCF" branch makes it UNDER, but a bare `>` comparison in floating
  point can flip it to OVER. Needs a tolerance. Cosmetic today - both branches
  give the same TCFn at equality - but not once anything keys off the label.
- **Regatta scoring in slice 0?** All five user journeys in the brief are club
  series; the spec devotes a full section to regattas. Sequenced last.
- **Scoring codes.** The spec's status enum has FINISHED/DNC/DNS/DNF; the
  brief's glossary adds OCS, RET, DSQ; RRS A10 lists fourteen. Which subset for
  v1?
- **Elapsed time vs start/finish clock times.** Slice 0's scope says the input
  is "races with start times, finishes", but every formula takes elapsed
  seconds. Does the engine derive elapsed from start + finish, or does the
  caller? Shapes the public interface.
