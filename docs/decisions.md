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

## 2026-09-22 - Tests are written against stdlib unittest (SUPERSEDED)

> Superseded the same day by "pytest is the project's test framework" below.
> Kept for the reasoning, which still explains what the switch gave up.

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

## 2026-09-22 - pytest is the project's test framework

**Context.** The earlier stdlib-unittest decision was made to satisfy
`CLAUDE.md`'s `manage.py test` instruction without imposing a test dependency on
anyone vendoring `nhc`. Direction since: pytest is wanted in the stack outright,
for both the Django app and the engine.

**Decision.** pytest with `pytest-django`, configured in `pytest.ini`. Tests are
plain functions with bare `assert`s. `races/tests.py` moved off
`django.test.TestCase` onto pytest-django's `client` fixture; neither view
touches the database, so no `django_db` marker is needed and no test database
is created.

**Consequence.** Scenario tests get `@pytest.mark.parametrize`, which is the
real win: each of the six scenarios reports as its own named test rather than
disappearing into one `subTest` block. The cost, accepted knowingly, is that
`nhc`'s tests now need pytest installed, so vendoring the package no longer
brings a runnable suite with it. The package itself stays standard-library
only - the purity test still enforces that, and it is the constraint that
actually matters.

`manage.py test` is now a trap: pytest-style functions are not
`unittest.TestCase` subclasses, so Django's runner collects nothing and exits 0
with "Ran 0 tests ... OK". That is a false green, and worse in CI than a
failure. `config/test_runner.py` is wired in as `TEST_RUNNER` so the old command
exits non-zero with a pointer to the pytest invocations instead.

**Fixture plumbing.** `tests/scenario_loader.py` reads the YAML and exposes the
scenarios as module-level lists, because `parametrize` needs them at import
time and conftest fixtures only exist once a test is running.
`tests/conftest.py` wraps the same objects as fixtures for tests that would
rather take them as arguments. `tests/test_fixtures.py` checks the fixtures are
well-formed - unique ids, statuses within the spec's vocabulary, positive
handicaps, finishers with positive elapsed times - because a typo in the
fixtures silently moves the target the engine is built against.

---

## 2026-09-22 - Handicaps carry full precision; rounding is display only

**Context.** Spec section 7 says to keep full floating-point precision through
all TCF/TCFr/TCFn calculations and round only for display. But the RYA publishes
its tables at 3 d.p., which makes 3 d.p. look canonical, and a club's existing
software may well round between races. The two give different answers over a
six-race series, because the error compounds.

**Decision.** Full precision throughout. Nothing in `nhc/` rounds a handicap,
and nothing rounds between races. Callers round when they show a number to a
person.

**Consequence.** Results may differ in the third decimal place from software
that rounds as it goes. If the target club's scoring package turns out to round
between races, that is a compatibility requirement to raise explicitly rather
than something to quietly match - spec section 9 already flags it as a question
to confirm. `test_full_precision_is_preserved_through_construction` pins the
behaviour using the SCEN-006 canary value, 0.88050096, which sits a millionth
above the 3 d.p. rounding boundary.

---

## 2026-09-22 - Domain types validate on construction

**Context.** Spec section 7 lists inputs to reject outright: a non-positive TCF
or Base Number, a boat marked FINISHED with no usable elapsed time, a regatta
entry with no Base Number to clamp against.

**Decision.** The types in `nhc/domain.py` are frozen dataclasses that validate
in `__post_init__`, so an invalid race cannot be constructed. Non-finite values
are rejected alongside non-positive ones: a NaN handicap propagates silently
through every fleet-wide sum and emerges as a whole race of NaN with nothing to
say where it began. Errors are `InvalidInput`, which subclasses `ValueError` so
a Django form can catch it without importing from `nhc`.

**Consequence.** Failures surface where the bad data enters rather than several
formulas later. Two deliberate departures from the spec's suggested data model,
which explicitly invites adaptation to idiomatic types:

- `position` is `int | None`, not `int | "DNC"`. A magic string in a numeric
  field is awkward, and `status` already records why there is no position.
- A non-finisher's elapsed time normalises to `None`. The spec writes E = 0 for
  a DNC and the fixtures follow it, but `null` is what a caller would naturally
  pass; accepting both and storing one means the rest of the engine tests one
  thing rather than two.

`RaceResult` carries no points field. Points are an RRS Appendix A concern,
need a series entry count that a single race does not have, and belong to a
separate layer.

---

## Open questions

Carried from the slice 0 planning pass. These need answers before the affected
step, not before any code is written.

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

---

## 2026-09-22 - PyYAML and pypdf added as test/dev-only dependencies

**Context.** `CLAUDE.md` guards against new dependencies. Two were needed: the
scenario fixtures are YAML and nothing in the stack read YAML, and the RRS PDF
is font-subset encoded with no `pdftotext` on this machine, so Appendix A is not
greppable without a library.

**Decision.** Both go in a new `requirements-dev.txt`, which pulls in
`requirements.txt` and is never installed in production. Approved explicitly
rather than assumed.

**Consequence.** The fixtures stay as YAML and keep their comments, which now
carry the spec rationale and the revision note - the main reason not to convert
them to JSON and drop the dependency. Neither package may be imported by `nhc/`;
the purity test fails by name if either is.
