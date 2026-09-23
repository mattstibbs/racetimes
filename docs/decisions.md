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

## 2026-09-22 - Tie detection uses a tolerance, but only for float noise

**Context.** RRS A7 ties boats on equal corrected times. Corrected time is
`E x TCF`, and handicaps like 0.8 have no exact binary representation, so a
genuine dead heat can miss exact equality by a unit in the last place.

**Decision.** `TIE_TOLERANCE_SECONDS = 1e-9`. Two corrected times within a
nanosecond are the same time.

**Consequence.** The number is deliberately far below any timing system's
resolution, so it absorbs representation error and nothing else. It is *not* a
"near enough to call it a tie" rule - boats a hundredth of a second apart are
two different times, and a test pins that. Candidates are compared against the
first member of a tie group rather than their neighbour, so a long run of
near-equal times cannot drift a tolerance-width at a time into one large tie;
a test pins that too.

Tied boats share the better place and consume the one below, so a two-way tie
for first scores 1, 1, 3. That is the ranking half of A7. The other half -
adding the tied places' points and dividing them equally - needs a points
system and belongs to the Appendix A layer.

---

## 2026-09-22 - One RaceResult type, with "not computed" distinct from zero

**Context.** The spec's model has both `score_race` and
`compute_club_adjustment` returning `RaceResult[]`, but scoring computes only
the corrected time and place, while adjustment computes the handicap fields.

**Decision.** Keep the single result type and make the handicap fields optional,
defaulting to None. `score_race` leaves them None; the adjustment pass fills
them in.

**Consequence.** None means "this call did not compute it", which stays distinct
from the 0.0 adjustment scale a boat that did not finish genuinely earns. The
alternative - a second, narrower result type - would have meant two near
identical shapes and a conversion between them.

`score_race` takes a `RaceInput` rather than the spec's bare entry list, so the
race's invariants (no duplicate boats, a non-empty fleet) are guaranteed before
any arithmetic runs. Results come back in entry order rather than finishing
order, so a caller can zip them against the input; sort on `position` for a
results table.

---

## 2026-09-22 - The minimum-finisher threshold is an option, defaulting to off

**Context.** Spec section 9 flags it as unconfirmed: some third-party club
software declines to move any handicap in a race with fewer than three
finishers, on the grounds that so small a fleet says little about anyone's
form. The RYA's own text does not require it.

**Decision.** `compute_club_adjustment(race, minimum_finishers=0)`. Zero is off,
which is the RYA's behaviour; a club that wants the threshold passes 3.

**Consequence.** Below the threshold, nothing is adjusted and the handicap
fields stay None rather than being computed and discarded. None means "the
adjustment did not run", which stays distinct from a boat that ran through it
and earned no change - the sole-finisher case in SCEN-004, where TCFr comes out
equal to TCF and the handicap legitimately does not move. Scoring is unaffected:
a below-threshold race still has corrected times and finishing places. Only
finishers count towards the threshold.

A race with no finishers at all takes the same path rather than raising. There
is nothing to divide by, and a race everyone retired from is a real thing that
should not crash the scorer.

---

## 2026-09-22 - Performance classification needs a tolerance too

**Context.** Spec section 3 step 3 classifies on `TCFr > TCF`, with equality
falling to the under-performance branch. In the degenerate single-finisher case
the sums collapse and TCFr should come out exactly equal to TCF - but the round
trip through `100/E` and back can land a unit in the last place above it, which
a bare `>` reports as over-performance.

**Decision.** `PERFORMANCE_TOLERANCE = 1e-12`, relative. Values that close are
equal, and equality is UNDER.

**Consequence.** Both branches give the same TCFn at exact equality, so the
number is unaffected either way - but the label is not, and something will
eventually key off it. SCEN-004 pins the behaviour.

---

## 2026-09-22 - compute_club_adjustment refuses a regatta race

Club and regatta rules use different blend weights and only regattas clamp to
the Base Number. Applying the club formulas to a regatta produces
plausible-looking numbers that are quietly wrong, so the function raises
`InvalidInput` pointing at `compute_regatta_adjustment` rather than guessing.

---

## 2026-09-22 - Race points are a third pass, and need the series entry count

**Context.** RRS A5.2 scores every boat that did not finish at "one more than
the number of boats entered in the series". A single race does not contain that
number.

**Decision.** `score_points(results, *, series_entry_count, apply_a5_3=False)`
is a third pass over the results, filling in `RaceResult.points`, which stays
None until then. The entry count is a required keyword argument rather than
inferred from the boats present.

**Consequence.** Inferring it would quietly under-score every non-finisher in a
race with absentees - a wrong answer that looks entirely reasonable. Note RRS
A2.2: a boat that has entered any race in a series is scored for the whole
series, so in a complete series every entrant appears in every race, DNC if
absent, and the count does equal the number of results. The engine still will
not assume that, because a caller mid-series may not have built the full list.

Points are floats throughout, since A7 ties produce halves and a field that
changes type depending on whether anyone tied would be worse than one that is
always a float.

---

## 2026-09-22 - A5.2 follows the 2025-2028 wording, not the older split

**Context.** In the 2025-2028 rules, A5.2 scores every non-finisher alike -
"did not sail the course, retired or was disqualified" all get series entries
plus one. Earlier editions scored DNC differently from boats that came to the
line, and software written against those still does.

**Decision.** Follow the edition in `docs/reference/`. A5.3, which restores a
softer score for boats that at least came to the starting area, is available as
`apply_a5_3=True` and defaults to off, because the rule applies only if the
notice of race or sailing instructions say so.

**Consequence.** Boats that came to the starting area are taken to be every
boat except the DNCs, which is what DNC means in A10: "did not come to the
starting area". If the club's existing software splits DNC out by default, that
is a compatibility difference to raise rather than quietly match.

---

## 2026-09-22 - A6.1 is not implemented, because it cannot fire yet

A6.1 moves every boat behind up a place when a boat is disqualified, retires
after finishing, or is scored Did not sail the course. All three are boats that
took a finishing place and then lost it. The engine models FINISHED, DNC, DNS
and DNF; none of those ever held a place to vacate, so the rule is a no-op
today. It becomes real as soon as DSQ, RET, OCS or NSC are modelled - see the
open question on scoring codes, which this now blocks on.

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

## 2026-09-22 - A series is scored by replaying it, never by updating in place

**Context.** The brief's central invariant: handicaps are never edited
directly, and correcting any finish must recalculate every later race in the
series.

**Decision.** `score_series(series)` replays from the start every time. Each
race is scored on the handicaps the previous race produced. There is no
incremental update path.

**Consequence.** Correction is free - change a finish, call it again. An
incremental path would be faster and would eventually drift out of step with a
full replay, which is the quietest class of bug a scoring system can have.
Replaying a dozen races for a fleet of thirty is microseconds of arithmetic;
there is nothing here worth optimising.

Two things the caller no longer supplies, because the rules supply them. A
boat's handicap per race is derived rather than entered - which is why the new
`Finish` type carries only a boat, a time or a code, i.e. what a race officer
actually writes down. And a boat with no recorded finish in a race is scored
DNC, per RRS A2.2: a boat that has entered any race in a series is scored for
the whole series. That also makes A5.2's entry count equal the number of
results, as it should be.

Races replay in the order given rather than sorted by date. A race's date is
the caller's business, and two races on one evening still have an order.

---

## 2026-09-22 - "Carries over / resets" means where the series starts

**Context.** The brief makes handicap progression configurable per series -
"carries over / resets" - and user journey 1 sets a new series to reset. It was
not obvious whether reset meant the published Base Number or the previous
series' realignment output.

**Decision.** `HandicapProgression.RESET` starts every boat on its
`base_number`; `CARRY_OVER` starts every boat on its `current_tcf`. Progression
picks the starting point for race one and nothing else - after that, both
follow the same chain.

**Consequence.** The ambiguity dissolves rather than being resolved: the engine
never needs to know whether a carried-over handicap is last season's drift or a
realigned club number, because whoever sets `current_tcf` decides. Running
realignment (spec section 5) and storing its output as `current_tcf` is how a
club gets realigned carry-over.

---

## 2026-09-22 - Standings: A8.1 ignores discards, A8.2 counts them

**Context.** RRS A2.1 totals a boat's race scores excluding her worst, and A8
breaks the resulting ties in two stages. The stages disagree about discarded
scores on purpose: A8.1 says "no excluded scores shall be used", A8.2 says
"these scores shall be used even if some of them are excluded scores".

**Decision.** Ranking is a three-level sort key, all lower-is-better: the
series total, then the counted scores sorted best to worst, then every race's
score in reverse series order so the last race is compared first.

**Consequence.** Getting the two rules the wrong way round would break ties
backwards in a way no single-boat test could catch, so there is a test built
specifically to tell a correct implementation from a plausible wrong one: two
boats with equal totals and identical counted scores, separated only by A8.2
on a score one of them discarded. An implementation that let discards into
A8.1 hands that series to the other boat.

A2.1's other subtlety is that equal worst scores are broken by excluding the
race sailed *earliest*. The total is identical either way, so only the race
shown in brackets reveals whether it is right; a test pins the race id rather
than the total.

Points are always multiples of 0.5 - whole places, halved across A7 ties - so
totals are exactly representable and compared exactly. Unlike the handicap
arithmetic, no tolerance is needed.

Boats still tied after both stages share a place and consume the ones below,
as with A7 in a single race.

---

## 2026-09-22 - Discards are a plain count, and misconfiguration is visible

**Context.** A2.1's default is one discard, but a notice of race may set none,
two, or "a specified number of scores excluded if a specified number of races
are scored" - the familiar "no discard until four races" arrangement.

**Decision.** `Series.discards` is an integer, defaulting to 1. The
races-sailed schedule is not implemented.

**Consequence.** A series that has sailed fewer races than the discard count
excludes all of them and every boat totals zero. That is the literal reading,
and it makes the misconfiguration obvious rather than producing a subtly wrong
table. The fleet is still ranked, because A8.2 breaks the resulting tie on the
last race using the excluded scores.

The schedule form is a genuine gap against A2.1 and is worth adding when a real
notice of race needs it; it is a small change to which races count, not to how
they are ranked.

---

## 2026-09-22 - Realignment scales the whole fleet by one factor

**Context.** Spec section 5: after the final race of a club series,
`CN = (sum(BN) / sum(EH)) x EH` pulls drifted handicaps back towards the
published Base Numbers.

**Decision.** `realign_series(entries)` implements it directly, plus two
helpers that join it to the rest: `realignment_entries(series, outcome)` pairs
each boat's base number with the handicap the series left it on, and
`realigned_boats(series, results)` returns the same boats ready to start the
next series, base numbers untouched and only `current_tcf` moved.

**Consequence.** Every boat is scaled by the same factor, so the fleet keeps
its internal spread exactly - a boat rated 10% faster than another before
realignment is still 10% faster after. What moves is the overall level, and it
moves so that the realigned numbers total the base numbers again. Both
properties are pinned by tests, because they are the clearest statement of what
the formula is *for* and would survive a refactor that quietly broke the
arithmetic.

Together with the progression decision, this closes the loop: realign, store
the result as `current_tcf`, and start the next series on CARRY_OVER. A test
sails that whole round trip.

Not to be confused with the regatta clamp in section 4, which limits how far
one boat may move from its own base number in a single race. Realignment is
fleet-wide and happens between series.

---

## 2026-09-22 - Regatta adjustment, and how it differs from a club series

**Context.** Spec section 4. A regatta is short and standalone, so the rules
differ from a club series in three ways that all pull the same direction:
find the right handicaps fast, and do not let one race distort them.

**Decision.** `compute_regatta_adjustment(race)` implements all four steps.
Whether it is the regatta's first race is read from
`RaceInput.is_first_race_of_regatta` rather than passed separately, so there is
one source of truth.

**Consequence.** Three differences worth knowing, each with a test that would
fail if the club rules leaked in:

- **Every boat is in the sums.** A club series excludes non-finishers. A
  regatta back-calculates an elapsed time for them - the top finishers' average
  for a boat that never sailed, the median finisher's for one that retired -
  so they count. A test asserts that adding an absent boat *does* move everyone
  else's handicap, which is the exact opposite of the club test beside it.
- **The blend is stronger.** 60% and 50%, against the club's 30% and 15%; and
  on the first race, 60% for everyone with no over/under distinction at all.
  `performance` is reported as None there rather than computed, because a
  classification that did not drive the weight would mislead.
- **Handicaps are clamped** to within 10% of each boat's own Base Number, at
  every race including the first.

The clamp creates a trap: spec section 6 keeps the pre-clamp TCFn visible so
the arithmetic can be checked, which means `next_tcf` is not the number a boat
actually races on. `RaceResult.effective_next_tcf` returns the clamped value
when there is one, and `score_series` uses it to carry handicaps forward.

`RaceResult.elapsed_seconds_used` is new: the E the adjustment worked from,
which for a back-calculated boat is not the recorded time (there is none). It
is what makes the back-calculation auditable, and a scorer will want to check
it.

There is no published RYA vector for regattas as there is for club series, so
these expectations are hand-derived from the formulas and computed
independently of the engine.

---

## 2026-09-22 - A regatta series always starts on base numbers

**Context.** Section 4 opens "All boats start on their Base Number". The
series-level `progression` setting says otherwise when left on its default,
CARRY_OVER.

**Decision.** For a regatta, `score_series` starts every boat on its base
number and ignores `progression`. `minimum_finishers`, a club-series option, is
refused outright on a regatta rather than ignored.

**Consequence.** The asymmetry is deliberate. Ignoring `progression` is
unavoidable, since CARRY_OVER is the default and a caller who never thought
about it would otherwise get a regatta scored against the wrong rule; the
behaviour is documented on `Series`. `minimum_finishers`, by contrast, has to
be set on purpose, so silently dropping it would hide a real misunderstanding -
a regatta has no fleet-size threshold, because every boat is in the sums
regardless.

---

## 2026-09-23 - The recalculation criterion is tested as a sweep, not an example

**Context.** Slice 0's acceptance criteria include "changing any finish and
re-scoring gives correct downstream handicaps". One worked example would
satisfy the letter of it and prove very little.

**Decision.** `tests/test_recalculation.py` takes "any finish" literally and
sweeps all fourteen timed finishes in a four-boat, four-race series, one at a
time. For each, it asserts that earlier races are byte-identical, the corrected
race changes, every later race changes, and the handicap chain still holds -
each race scored on exactly what the previous one produced.

**Consequence.** What this really guards is a future optimisation. Replaying a
series is cheap now, so the temptation to cache or to update in place will come
later, and its failure mode is a handicap that is *stale* rather than wrong:
invisible in any single-race test, and surfacing weeks afterwards in the
standings. Three tests exist only to catch that class of bug - putting a
corrected finish back restores the original results exactly, scoring an
unrelated series in between changes nothing, and scoring does not write back to
the boats it was given.

One test asserts the opposite of a ripple, deliberately. In a club series DNC
and DNS are scored alike - both excluded from the sums, both carrying their
handicap forward, both scoring entries plus one under A5.2 - so swapping one
for the other changes the recorded code and not a single number. Under A5.3 it
does change the points, which is the rule that distinguishes them.

A5.3 has a quiet arithmetic coincidence worth recording, because it made a
test of mine fail for the right reason: when a boat is the *only* absentee, it
scores the same either way. As a DNC it scores entries + 1; as a DNS it scores
"everyone came" + 1, and those are the same number. The scores only diverge
once a second boat is missing.

---

## Open questions

Carried from the slice 0 planning pass. These need answers before the affected
step, not before any code is written.

- **DNF in a club race.** Spec section 3 step 1 computes AS "for every boat that
  finished"; step 2 says the sums run over "every boat that started". A DNF boat
  started but has no elapsed time, so the two sentences disagree. Implemented
  and tested as: excluded from both sums, handicap carried forward unchanged.
  Still worth confirming with the club. See also the next question, which is
  the brief's per-series "adjusted / not adjusted" switch.
- **"Adjusted" non-finishers.** The brief makes handicap adjustment for boats
  that do not finish configurable per series: "adjusted / not adjusted". Only
  "not adjusted" is implemented, because it is the only behaviour the RYA spec
  defines for a club series - section 3 has non-starters carry forward and be
  excluded from the sums. The reference docs contain exactly one mechanism for
  giving a non-finisher a usable elapsed time, the regatta back-calculation in
  section 4 step 1, so "adjusted" would mean borrowing that into a club series.
  Coherent, but a rule decision for the club rather than an implementation
  detail, so it is not guessed at.
- **Who counts as having "taken part"?** Spec section 5 opens by realigning
  "every boat that took part in that series", but the note on its formula says
  the sums run over "every boat in the series being realigned". A boat that
  entered and never sailed is arguably not the first, and including it shifts
  the ratio for everyone else. `realignment_entries` includes every entered
  boat and returns a plain sequence, so the stricter reading is a filter away.
- **Scoring codes.** The spec's status enum has FINISHED/DNC/DNS/DNF; the
  brief's glossary adds OCS, RET and DSQ; RRS A10 lists fourteen. Which subset
  for v1? This now gates two things. RRS A6.1 (boats moving up when one ahead
  is disqualified or retires after finishing) cannot fire without DSQ/RET/NSC.
  And those codes break an invariant the domain types currently hold: a boat
  disqualified after finishing *does* have an elapsed time, whereas today only
  a FINISHED boat may carry one. Whether such a boat's handicap is adjusted is
  not addressed by the RYA spec at all.
- **Elapsed time vs start/finish clock times.** Slice 0's scope says the input
  is "races with start times, finishes", but every formula in the RYA spec
  takes elapsed seconds, and that is what the engine takes: deriving elapsed
  from a start and a finish is left to the caller. The reasoning is that once a
  race has more than one start - out of scope for slice 0 - the caller has to
  choose which start applies anyway, so the conversion belongs where the starts
  are modelled. This is the one partial gap against slice 0's stated scope, and
  it is worth settling in slice 1, where races gain real start times and the
  answer shapes the Django model rather than the engine.

---
