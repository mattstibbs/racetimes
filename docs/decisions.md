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

**Update 2026-09-23.** This regeneration would not happen unilaterally today.
The guardrails in `CLAUDE.md` now make the fixtures the specification: a
disagreement with the reference docs goes to the project owner to check the
fixture's provenance before any expected value changes, and fixtures are never
generated from the engine's own output.

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

## 2026-09-23 - Slice 1: the committee enters clock times, not elapsed times

**Context.** Left open from slice 0: the engine takes elapsed seconds, and
deriving them was deferred to where races gain real start times.

**Decision.** A Race stores a date and a start time; a Finish stores the clock
time the boat crossed the line. The app computes elapsed time; the engine is
unchanged. Both are plain times of day in whole seconds, with no timezone.

**Consequence.** The race officer types what is on the finish sheet, with no
mental arithmetic on the water. One start time is shared by the whole race, so
a wrong start shifts every boat - but it is one field to fix, not thirty.
A finish earlier than the start is rejected rather than read as the next day,
so races past midnight are not supported. Direct elapsed-time entry, for sheets
that only record elapsed, is deferred.

---

## 2026-09-23 - Slice 1: only the engine's four statuses

**Decision.** FINISHED, DNC, DNS and DNF. OCS, RET and DSQ are deferred.

**Consequence.** No engine change in slice 1. A boat disqualified after
finishing has to be recorded as DNF for now. Adding codes later is a change to
the field's choices and a migration, but the open question on scoring codes
still stands: DSQ needs the engine to accept a time on a non-finisher, and a
club decision on whether that boat's handicap is adjusted.

---

## 2026-09-23 - Slice 1: series entry only, no race entry

**Context.** RRS A5.2 scores non-finishers on the number of boats entered in
the *series*, and A2.2 scores an absent entrant DNC. Both need series
membership recorded; neither needs race membership.

**Decision.** A `SeriesEntry` model links a boat to a series. A Finish belongs
to a SeriesEntry and a Race, not to a Boat directly. A boat with no finish in a
race is simply absent and the engine scores it DNC.

**Consequence.** A finish cannot exist for a boat outside the series, and an
entry with finishes cannot be removed. User journey 3 (entering boats per race)
is not built; its only effect beyond scoring is a confirmation email, which is
slice 4. If race entry returns, it must answer whether an entered boat with no
finish is DNC or DNS.

---

## 2026-09-23 - Slice 1: every series starts on base numbers

**Context.** The brief's "carries over / resets" setting. Carry-over needs a
source for each boat's starting handicap, and the brief forbids editing
handicaps directly.

**Decision.** Reset only. Series has no progression field yet; the adapter
always passes `HandicapProgression.RESET`.

**Consequence.** Matches user journey 1. Carry-over needs club answers first:
what counts as the previous series, whether to realign before carrying over,
and who "took part" for realignment. Adding the field later is one migration
defaulting existing series to reset. A typed-in starting handicap was rejected:
it is direct editing, and one typo would skew every other boat through the
fleet-wide sums.

---

## 2026-09-23 - Slice 1: admin for setup, a custom HTMX page for finishes

**Decision.** Boats, series, entries and races are managed in the Django admin.
Finish entry is its own HTMX page where each row saves independently. Both need
a staff login; results are public.

**Consequence.** Setup costs a few lines per model, and the effort goes on the
screen used every race night. Proper roles wait for slice 3.

---

## 2026-09-23 - Slice 1: boat fields, and sail numbers unique ignoring case

**Decision.** Boat has sail number (required), name, make, model, owner name,
length overall and waterline length (metres, 2 d.p., optional), and base number
(exact decimal, 3 d.p., required, above zero). Uniqueness is a unique
constraint on an expression: the sail number upper-cased with spaces removed.

**Consequence.** "GBR 1234" and "gbr1234" cannot both be registered, which is
how "unique sail number" usually fails in practice. The base number is a
decimal so the value shown is the value typed; it becomes a float only at the
engine boundary.

*Revised during implementation.* The plan was a stored normalised copy with a
plain unique constraint. An expression constraint does the same job without
the extra column, and Django's form validation checks expression constraints,
so a duplicate is reported against the sail number box in the admin rather than
failing on save. Both SQLite and PostgreSQL support it; the app's tests pass on
both.

---

## 2026-09-23 - Slice 1: all four engine series settings are stored

**Decision.** Series stores series type (default club), discards (default 1),
minimum finishers (default 0) and A5.3 (default off) - the engine's defaults.

**Consequence.** Minimum finishers with a regatta is refused by the engine, so
it is validated on the form instead, where it can be fixed, rather than
surfacing as an error on the results page.

---

## 2026-09-23 - Slice 1: results are computed on request, never stored

**Decision.** Every results view replays the series through the engine from
the stored finishes. There are no result or handicap tables.

**Consequence.** There is nothing to go stale, so a corrected finish shows its
full downstream effect on the next page load - slice 2 gets recalculation for
free. The cost is a replay per request, which is microseconds of arithmetic.

---

## 2026-09-23 - Slice 2: audit everything that changes a score, in our own table

**Context.** The plan's line is "a history of what changed and who changed
it". A finish is the obvious thing to correct, but a race's start time, a
series' discards or a boat's base number move results just as far. Django
admin's built-in log records who and when, but not old and new values.

**Decision.** Every field that changes a score is audited, with its old and new
values. The fields are listed in one place in the code. History goes in a
hand-rolled `ScoringChange` table, not in django-simple-history, so there is
no new dependency and we store only what a committee will look at. Changes are
recorded by the code that saves them, not by signals, because a signal can't
see who made the change or why. The history has no foreign key to the rows it
describes, so it outlives them. It is deleted only with its series.

**Consequence.** Every place a score-affecting value is saved (the finish view
and each admin hook) has to call the recording helper. A place that doesn't
call it is a gap in the audit, so the tests go through every audited field.
Details that don't affect a score, such as a boat's name, are covered only by
the admin's own History button.

---

## 2026-09-23 - Slice 2: a correction needs a reason; a first entry does not

**Decision.** A change is a correction if it alters something that has already
fed into a result, and a correction must have a reason. Entering a finish for
the first time, and setting up a series before any race has been sailed, need
none. A save that changes nothing records nothing.

**Consequence.** Race night stays quick, because the reason box only matters
when fixing something. The public results page labels an amended race using
the same flag, so "amended" means the same thing everywhere. Who made the
change, and why, are shown only to staff.

---

## 2026-09-23 - Slice 2: what a correction changed is judged on what people see

**Context.** After a correction the committee is told which places, handicaps
and standings moved. The comparison scores the series before and after the
save, and nothing about it is stored.

**Decision.** Handicaps are compared at 3 d.p. and places on position and
points, which is what the results page shows. A start time that moves every
boat by the same amount leaves the handicaps unchanged at 3 d.p., and the
message says so: "No places, handicaps, or standings were affected by this change."

**Consequence.** The message never claims a change that nobody could see on
the results page. The engine still works in full precision; only this summary
rounds. The same rule is behind a finding from the sweep test: a correction can
reorder places in several races and still leave every boat's total the same,
so "standings changed" is reported only when a position or total actually
moved.

---

## 2026-09-23 - Slice 2: how the recording is wired

**Decision.** Each form works out what its save would record during validation:
by then the instance holds the new values while the database still holds the
old ones. A correction without a reason is added as a form error, so the admin
and the finish row show it the way they show any other validation message.
Rows in the series form read the series form's reason box, because every
formset on the page is bound to the same POST. The finish view writes the
finish and its history inside one `transaction.atomic()`. The admin already
wraps each save in a transaction.

**Consequence.** Adding a new audited field means one line in
`AUDITED_FIELDS` and one test. A new *place* that saves an audited field, such
as a future API, must call `audit.changes_to_save` and `audit.record` itself.
Anything that bypasses forms, like `QuerySet.update()` or the Django shell, is
not recorded; the committee has no route to either.

---

## 2026-09-23 - A race with nothing recorded is not scored yet

**Context.** Scheduling races ahead of time, as user journey 1 does, left
every unsailed race scored with every boat DNC on entries + 1 points. In a club
series that race then became every boat's discard, which is wrong mid-season.
In a regatta it crashed the results and finish-entry pages, because the engine
refuses a regatta race with no finisher (spec section 4 back-calculates the
others from the finishers).

**Decision.** Agreed with the project owner. A race with no result saved - no
time and no code - is left out of scoring and shown as "No results recorded
yet". It counts as sailed as soon as any result is saved, a code included. In
a regatta, a race with results but no finish time is held back with an
explanation, and so is every race after it, because each race sails on the
handicaps the one before produces. The results shown are the ones up to the
race that is waiting.

**Consequence.** The engine is unchanged: `races/scoring.py` chooses which
races to hand it. Slice 1's rule that a boat with nothing recorded scores DNC
still holds, but only in a race that is being scored. Two slice 1 tests
assumed an empty race was scored and now record a result in it. The committee
can save a regatta race's codes in any order; the page explains the wait until
a time goes in, rather than refusing the save.

---

## 2026-09-23 - No user action should crash a page

**Context.** The project owner's rule, after the regatta crash above. Probing
every edit the committee can make found two more: moving a race's start time
to after finishes already saved (negative elapsed times, which the engine
refuses), and swapping two race numbers in the admin (Django saves the rows
one at a time, so for a moment two races share a number and the database's
unique rule fails).

**Decision.** Each is stopped where it enters, with a message that says what
to do:

- A race's start time must be earlier than every finish already saved for it
  (`Race.clean`).
- Renumbered and removed races are parked on spare numbers before the real
  numbers are saved (`RaceInlineFormSet`), so any renumbering that is valid
  once saved also saves.
- Removing an entry that has results explains why it is refused and what to do
  instead, in place of Django's "protected related objects" wording. This one
  never crashed; the message was just unhelpful.

Two backstops for anything not yet found: `score_series` catches input the
engine refuses, logs it, and the pages say the results cannot be calculated
rather than failing; and `templates/500.html` replaces Django's bare "Server
Error (500)" with a plain page in production.

**Consequence.** The backstops only hide a crash from the person using the
site. The logged error still needs looking at, so validation stays the first
line: each route found so far has its own check and a test that drives it the
way the committee would.

---

## 2026-09-23 - The test site is hosted on Render, deploying main

**Context.** The project owner wanted a hosted copy that updates itself, to
test changes without running the app locally.

**Decision.** Render, described in `render.yaml` so the setup lives in the
repository: a web service deploying `main` on every push, and a managed
PostgreSQL database. Two dependencies were approved for it: `gunicorn` to serve
the site, and `whitenoise` to serve its static files without a separate file
server. `build.sh` runs `migrate` on every deploy, so schema changes ship with
the code that needs them.

**Consequence.** Every merge to `main` goes live, so `main` is what testers
see. Testing a pull request before merging it would need Render's preview
environments, a paid feature when this was written. The first staff login is
created from two environment variables by `ensure_superuser`, because a free
Render service may have no shell to run `createsuperuser` in; it only ever
creates the account, so a password changed later in the admin stays changed.
Production settings are keyed off `DJANGO_DEBUG=0`, so development and the test
suite are unchanged. HSTS and Django's own HTTPS redirect are deliberately off:
Render redirects to HTTPS already, and HSTS is hard to undo on a test site.
(Reversed in slice 11 part 4, below: a service for paying clubs is HTTPS only.)

---

## 2026-09-24 - Slice 3: four roles, and members change nothing directly

**Context.** Slice 3 brings accounts. The plan asked for the role rules to be
written into the brief first; six questions were settled with the project
owner before any code.

**Decision.**
- Four roles: the public, members, race committee and administrator. Only the
  administrator (a superuser) manages accounts, approves them included; the
  committee is staff in a "Race committee" group granted the racing models and
  nothing about users, so it cannot give itself more access.
- Members sign themselves up with their email as the login, and the account is
  inactive until the administrator approves it. No email is needed for this,
  which matters because email arrives in slice 4.
- A boat has at most one owning account, set only by the committee.
  `owner_name` stays for boats with none.
- Every member action is a request the committee approves or rejects: boat
  registration, any change to a boat (details included, not only the base
  number), a claim to own a boat already on record, and series entry.

**Consequence.** Nothing a member types reaches a boat, an entry or a result
without a committee member's approval, and approvals go through the same
audited code as the admin, so slice 2's change history stays complete and
every change in it has a committee member's name on it. The cost is committee
workload, including approving harmless detail changes such as a boat's name;
that was chosen deliberately over letting members edit details directly.
Co-owners cannot act for a boat; moving from one owner to several later is a
small migration.

---

## 2026-09-24 - Slice 3: how the roles are enforced

**Decision.**
- The committee is staff *in the "Race committee" group*, checked by
  `races/roles.py`. Staff status alone no longer opens the committee pages:
  the group is what grants the racing parts of the admin, so without it a
  staff account would reach pages whose admin it cannot use.
- The login says an account is waiting for approval only when the password is
  right, so it never reveals which emails have signed up. It does this in the
  form rather than with Django's backend that lets inactive accounts log in,
  because that backend would also keep a *deactivated* person's existing
  session alive.
- A boat's owner is chosen in the admin from a plain list of active accounts,
  not Django's search box, which needs permission to browse accounts - a
  permission the committee deliberately does not have.
- Requests are read-only in the admin. Changing a request's status there would
  not apply it; only the Requests page does.
- Approving claims the request with a conditional update inside the same
  transaction, so a double click or two committee members cannot both apply
  it, and a failed approval leaves it pending. Everything is validated again
  at approval, in case the boat or series changed since the member asked.
- A member trying another member's boat or request gets a 404, not a 403, so
  the site does not confirm it exists.

**Consequence.** Any existing committee login that is staff but not a
superuser must be added to the Race committee group after this deploys, or it
loses the finish-entry and history pages. `docs/deploying.md` says how.

---

## 2026-09-24 - History labels keep their capitals from now on

**Context.** The change history labelled fields with Python's
`str.capitalize()`, which lowercases everything after the first letter, so rows
read "Nhc base number" and "Use rrs a5.3" while the rest of the site says
"NHC base number" and "Use RRS A5.3".

**Decision.** New rows use Django's `capfirst`, which changes only the first
letter. Rows already recorded are shown as stored; the project owner chose not
to translate the old spellings.

**Consequence.** History recorded before this change keeps the old spelling.

---

## 2026-09-24 - A user manual in manual/, built with MkDocs

**Context.** The project owner wanted a manual for the site's users, in
Markdown that could be published on a site such as Read the Docs.

**Decision.** MkDocs, approved as a docs-only dependency in
`requirements-docs.txt`, with its built-in "readthedocs" theme. The manual is
in `manual/`, apart from the developer documentation in `docs/`, and is
organised by role. Pages use plain CommonMark and tables only, so they read on
GitHub and would move to another tool unchanged. Screenshots are generated by
a script against throwaway sample data rather than taken by hand, so they can
all be refreshed when the screens change. The definition of done now includes
updating the manual.

**Consequence.** Refreshing screenshots needs Node.js with Playwright, a tool
outside the Python project; building or reading the manual does not.
`tests/test_manual.py` checks links, images and contents with only PyYAML, and
CI builds the manual strictly, so it cannot quietly break. Keeping it current
is now part of every user-facing change.

---

## 2026-09-24 - Slice 4: what gets emailed, and who decides when

**Context.** The plan's line was "emailing results after a race is
published", but nothing was ever "published": results are public the moment a
finish is saved. Slice 3 also deferred account emails to this slice.

**Decision.** Agreed with the project owner:
- A **Publish results** button, which emails the race's results. The public
  page keeps showing results before that, labelled provisional.
- After corrections, the committee sends a "results updated" email with a
  button, when they have finished correcting. The site never sends on its own,
  so a run of corrections cannot flood every owner's inbox.
- Emails also for account approval, request decisions, series entry, any
  change to a boat, and password reset. A change the owner asked for is
  reported once, in the "request approved" email, not again as "boat
  updated".
- Django's built-in SMTP email, no new dependency; the provider is chosen
  before deploying.

**Consequence.** Two new fields on Race (published and last sent), proposed
for approval. "Amended since sent" reuses the change history rather than
tracking changes a second time.

---

## 2026-09-24 - Slice 4: how email is sent

**Decision.**
- Every email goes through `races/notifications.send`, which sends once the
  database transaction commits, so a change that is rolled back emails
  nobody. A sending failure is logged and shown as a warning on the page; the
  change itself stands.
- Publishing records `results_sent_at` only once every email has gone. A
  failed send therefore leaves the race "published but not sent", and the
  finish-entry page offers to send again.
- Each owner gets their own message rather than one message to everyone, so
  owners never see each other's addresses.
- Emails are plain-text templates in `templates/emails/`, first line the
  subject, with autoescaping off so names like "Wind & Water" arrive as
  typed.
- A request's email names the boat as it was when the member asked, so an
  approved rename is reported as a change to the old name.

**Consequence.** Emails are sent while the page request is handled, not by a
background worker. For a club's series (tens of owners) that is a second or
two; a much larger fleet would want a queue. The tests make "after commit"
run immediately, as it does on the live site, except the rollback test, which
uses Django's real deferral because that is what it checks.

---

## 2026-09-24 - Slice 5: the results app reads, and never writes

**Context.** The plan asks for "another Django app" for racers to view
results. Two apps that both know how to score a series could drift apart.

**Decision.**
- `results/` has no models and no views that save. It shows what
  `races.scoring.score_series` computes and nothing else, so it cannot
  disagree with the committee's pages.
- The dependency runs one way: `results` imports from `races`, never the
  reverse, checked by a test.
- Each HTMX interaction uses the same URL as its full page, returning a
  fragment only when `request.htmx` is set, so every view works without
  JavaScript and every state has a link that can be shared.

**Consequence.** The boat page scores every series the boat is entered in,
once each, per request. For a club's handful of series that is cheap; it is
the same trade-off as "results are computed on request, never stored".

---

## 2026-09-24 - Slice 5: the new pages replace the old, and show no owners

**Decision.** Agreed with the project owner:
- The `results` app replaces today's public home and series pages rather than
  sitting beside them, and serves the same URLs (`/`, `/series/<pk>/`), so
  there is one public results page and no redirect.
- Public pages show boats by sail number, name, make and model, never the
  owner's name. A member finds their own boats through "My boats".
- No race-day auto-refresh for now.

---

## 2026-09-24 - Slice 5: how the results pages behave

**Decision.**
- The series page shows one race at a time, opening on the latest with
  results. Choosing a race, following a boat and "More detail" all swap the
  same part of the page (`#series-body`), so the choices it carries can never
  disagree with each other; the URL records them all.
- A view returns a fragment only when HTMX names that fragment as its target
  and it is not a history restore, so the back button always gets a whole
  page. Responses vary on `HX-Request` and `HX-Target`, so a cache never
  serves a fragment as a page.
- "All pages only read" is tested by running every page and fragment and
  checking every query is a SELECT, rather than by listing allowed imports.
- The home page's latest results cover at most five series, since showing
  one means scoring it.
- The boat page states the next handicap from the last scored race's
  `effective_next_tcf`, and names the next race only when one is scheduled.
  Before any race is scored it is the base number, as every series starts on
  base numbers.

**Consequence.** An older `/series/<pk>/#race-N` link opens on the latest race,
not race N, because the part after `#` never reaches the server. Emails link
with `?race=N` from now on; no emails had gone to real members yet.

---

## 2026-09-24 - Slice 6: race entry is a committee start sheet, and a gate on publishing

**Context.** The brief's user journey 3 has the committee enter boats per race,
and its owners told. Slice 1 left race entry out and noted that, if it came
back, it must say whether a boat entered in a race with no finish is DNC or
DNS.

**Decision.** Agreed with the project owner:
- Only the race committee records who is racing, on a start sheet per race.
  Members don't enter races, not even by request.
- A boat on the start sheet with nothing recorded is neither DNC nor DNS. It
  is "not recorded", and the race can't be published, or updated results
  sent, until the committee records a time or a code. Until then it is passed
  to the engine as DNC, as a missing finish is today, so nothing about
  scoring changes.
- Every race has a start sheet, and only boats on it can have a finish
  recorded. At first a start sheet was optional, with races without one
  working as before. The project owner dropped that option so there is one
  way of working. Races already sailed get their start sheet from a data
  migration: the boats that have a finish.
- Persons on board is recorded on the start sheet, shown to the committee
  only, and not used in scoring.
- Emails go to the owner when a boat is put on a start sheet, taken off
  one, or removed from a series. Putting a boat back on sends a second
  confirmation, and a boat added after the race still gets one. Removing a
  boat from a series sends only the series email, not one per race.
- The data model was approved by the project owner on 2026-09-24.
- Start sheet changes are not in the change history, because none of them can
  move a score.

**Consequence.** A new `RaceEntry` model and a data migration to fill it for races already sailed. The open question on DNC/DNS for race entrants is closed without a
rule change: the committee has to say what happened.

---

## 2026-09-24 - Slice 7: a hand-written stylesheet on design tokens

**Context.** The site still has the walking skeleton's deliberately plain
styling. The project owner asked for a clean, simple, modern look.

**Decision.** Agreed with the project owner:
- Neutral nautical colours (navy header, one sea-blue accent, white cards on
  light grey), light only, the device's own font, and the Django admin left
  with its standard look.
- One hand-written stylesheet whose colours all come from CSS custom
  properties (tokens) at its top. No CSS framework, web font, icon set or
  JavaScript, so nothing new to install, vendor or keep up to date, and
  nothing loaded from another site.
- Templates change only where layout needs it, and keep every class, id and
  HTMX attribute that behaviour, tests or the screenshot script rely on.
- Colour contrast is tested against WCAG AA, so a later change to the
  tokens (a club's own colours, say) can't quietly make text unreadable.

**Consequence.** A club wanting its own colours changes a few tokens. Every
manual screenshot changes, so the whole manual is regenerated in this slice.

---

## 2026-09-24 - Slice 8: other handicap systems, worked out by hand

**Context.** The project owner chose "support for other scoring systems" as
slice 8, meaning other handicap systems, not other points systems.

**Decision.** Agreed with the project owner:
- A series chooses one handicap system: NHC (the default, and every
  existing series), Portsmouth Yardstick or RYA YTC. RRS Appendix A scoring
  is shared by all three.
- No reference documents or worked examples exist in the repo for PY or YTC.
  The spec is written from the published rules, and its worked examples are
  worked by hand and checked by the project owner before they become
  fixtures. The engine is never used to produce them.

Proposed, and waiting for the project owner (see the spec's open
questions): the data model, the YTC formula and number format, whether
corrected times are rounded before ranking, and the default for new series.
The engine keeps the name `nhc` rather than being renamed.

Parked on 2026-09-24 at the project owner's request, with nothing built.

---

## 2026-09-24 - Slice 9: one race day page, finishes by tap

**Context.** Entering finishes means reading a watch and typing each time, on
a separate page from the start sheet. On the water, boats cross seconds
apart.

**Decision.** Agreed with the project owner:
- One race day page per race replaces the start sheet and finish-entry pages;
  the old addresses redirect to it.
- A **Finished** button stamps the site's local time, in whole seconds, on the
  race's own date from its start time. Every time can still be typed or
  corrected.
- Boats are shown as "still racing" (sail-number order, so nothing moves under
  a finger) and "finished" (in order across the line).
- **Undo** within two minutes of saving a finish, on an unpublished race, with
  no reason. This relaxes slice 2's "a saved finish can't be cleared" for
  that one case; both the finish and its removal stay in the history.
- The Finishing view refreshes every 5 seconds (HTMX polling, a 204 when
  nothing changed, paused while a form is open), for two devices at once.
- **The one JavaScript exception**, approved by the project owner:
  `static/js/race-clock.js`, a small hand-written script with no library,
  ticks the race clock in the site's time. The page works without it.

**Consequence.** One proposed field, `Finish.recorded_at`, for Undo (awaiting
approval). The change history can't provide it: its rows don't name the boat
except in text.

---

## 2026-09-25 - Slice 10: a final series is locked, and keeps a copy of its results

**Context.** The brief's user journey 5 has the committee produce final
series places, shown on screen and exportable as a file. Results are never
stored: every page replays the series (slice 1). A boat's base number is
shared by every series it sails in, so correcting it would change a season
that has already ended.

**Decision.** Agreed with the project owner:
- **Declaring a series final locks it.** Finishes, start sheets, races,
  entries, settings and publishing are all refused until the committee
  reopens it with a reason, which is recorded in the change history. Boats,
  including their base numbers, and the series' name stay editable.
- **A final series keeps a copy of the engine's results,** as JSON, and is
  scored from that copy rather than replayed. This bends slice 1's "nothing
  derived is stored" rule for final series only; reopening drops the copy.
  Boat names and sail numbers aren't copied.
- **Declaring emails every owner** their final place. Declaring again after
  reopening sends an "updated" email. Reopening sends nothing.
- **Anyone can download any series as one CSV,** final or provisional, using
  Python's csv module. It contains no owner names and no persons on board.

**Consequence.** Four proposed fields on `Series`, awaiting approval. Every
write path checks one function in `races/final.py`, tested path by path.

---

## 2026-09-25 - Slice 11: many clubs in one database, a subdomain each

**Context.** The project owner wants to offer Race Times to sailing clubs as a
hosted service. The site assumes one club throughout: global sail numbers,
a global committee group, and the superuser as the administrator.

**Decision.** Agreed with the project owner:
- **One database for every club, with the club on every row,** filtered in
  one place (`for_club`) and tested for isolation on every page. Not a
  schema per club (django-tenants: a new dependency, and PostgreSQL only),
  and not a separate site per club (cost and upgrades grow with every club).
- **A subdomain per club,** found from the request's host. A club's own
  domain comes later. A `SINGLE_CLUB` setting keeps the current test site,
  and the tests, working on an address with no subdomain.
- **One login, many clubs:** roles belong to a membership of a club, not to
  the account. Superuser now means the service's operator only.
- **The operator (the project owner) sets clubs up** and invites each
  club's first administrator. There's no self-serve sign-up or payments yet.
- **One transactional email provider over SMTP** for every club, with the
  club as the sender's name and reply-to address.
- **Sentry** (`sentry-sdk`, a new dependency, approved) for errors, and an
  external uptime check against `/health/`.
- **The UK GDPR essentials** in this slice: privacy notice and terms, a
  member's data download and account deletion, a club export, and deleting a
  club.
- **Production hosting is deferred** to a later slice.

**Answered by the project owner, 2026-09-25:**
- **Joining a club is what gets approved,** not the account.
- **A boat belongs to one club.**
- **The service is Race Times, at `racetimes.co.uk`.**
- **The first club is "Demo Club",** at `demo.racetimes.co.uk`, and the
  current test site's data becomes its data.
- **The legal review is deferred** and recorded as an open requirement
  (below).

- **The data model is approved:** `Club`, `ClubMembership`,
  `ClubInvitation`, `OperatorAction`, and a club on `Boat`, `Series`,
  `BoatRequest` and `ScoringChange`.

**Consequence.** The largest change since slice 1. It is built in five parts,
each merged on its own.

---

## 2026-09-25 - Slice 11 part 2: refuse, don't redirect, someone logged in without the role

**Context.** Since slice 3, a page for a role you don't have sent you to log
in. That's right for the public. But the login page sends anyone already
logged in straight back to where they came from, so a member opening a
committee page went round in a loop until the browser gave up. The unit
tests checked only the first redirect, so it was found in slice 11 part 2's
browser check, where more people now lack roles: at another club, or while
waiting to join.

**Decision.** The public is still sent to log in. Someone logged in without
the role gets a 403 page saying the page isn't available to them, with links
to their own page and the club's results. The admin keeps its own behaviour:
it sends everyone without access to its login, which refuses anyone already
logged in.

**Consequence.** The tests that expected a login redirect for a logged-in
member now expect 403. The role table in races/test_roles.py records it for
every page.

---

## 2026-09-25 - Slice 11 part 3: the operator's pages, and invitations

**Context.** Part 3 gives the operator proper pages to create clubs, invite
each club's first administrator and suspend a club, replacing the stopgap of
editing clubs and memberships in the Django admin.

**Decision.**
- **The operator's pages are at `/operator/`, on the service's own address
  only.** On a club's address they're a 404, even for the operator. The
  public is sent to the admin's login page, the one login on the service's
  own address; anyone else logged in gets a 403 (see part 2's decision).
- **Clubs and memberships leave the Django admin.** The operator's pages and
  each club's Members page do everything they did, and every operator action
  is logged, which admin edits wouldn't be. Correcting a club's name or
  contact email isn't offered yet; add it to the club's page if it's needed.
- **An invitation link is a `signing.dumps` of the invitation's id,** with
  its own salt and a 7-day `max_age`, not a password-reset style token: that
  needs an account, and the invitee may have none. It works once (the row's
  `accepted_at`) and only at its own club's address. The link is built for
  the club's address from `SERVICE_DOMAIN`, keeping the request's scheme and
  port.
- **Accepting proves the email.** Someone with no account makes one on the
  invitation page, active at once. Someone with an account logs in first, on
  the club's normal login page, so part 4's login throttling will cover it.
  Someone logged in as another account is asked to log out first, rather than
  being switched to a new account.
- **Subdomains:** lower-case letters, digits and hyphens, as the spec says,
  and also not starting or ending with a hyphen, which DNS doesn't allow.
- **A suspended club can't be sent invitations,** since nobody could open
  the link while its site is paused.
- **The front page's contact address** is a setting,
  `SERVICE_CONTACT_EMAIL`, defaulting to `hello@racetimes.co.uk`.

**Consequence.** The operator's pages aren't available on the Render test
site: `SINGLE_CLUB` makes every address there Demo Club's. They need real
subdomains, which come with production hosting.

---

## 2026-09-25 - Slice 11 part 4: the owner's answers on running in production

**Decision.** Agreed with the project owner, from the part 4 plan's questions:
- **HSTS preload stays off,** and its deploy-check warning (`security.W021`)
  is silenced with a comment. Preloading is hard to undo, and belongs with
  choosing hosting.
- **The client's address for throttling** is taken from `X-Forwarded-For`,
  `TRUSTED_PROXIES` places from the right-hand end: 0 in development, 1 on
  Render. The left-hand end can be forged, so it's never trusted.
- **A login lock can be used against an account's owner:** anyone who knows
  a member's email can lock their login for 15 minutes at a time. That's the
  usual trade-off, and it's accepted. A password reset doesn't clear the
  lock.
- **`sentry-sdk[django]` 2.70.0 is added** as a dependency, as the spec
  approved.

---

## 2026-09-25 - Slice 11 part 4: running it in production

**Decision.**
- **HTTPS redirect and HSTS are on** with `DJANGO_DEBUG=0`, reversing the
  slice 1 hosting note. HSTS starts at an hour (`SECURE_HSTS_SECONDS`) and
  covers subdomains, so every club's address; it's raised without a code
  change once hosting is settled. `/health/` is answered before the
  redirect and the host check, since hosts poll over plain HTTP from an
  internal address.
- **Every email comes from its club** at the service's one sending address:
  "<Club> via Race Times", Reply-To the club's contact email. One address
  means one domain for the provider to vouch for (SPF, DKIM, DMARC); sending
  "from" each club's own domain would need every club to set up DNS. The
  club is the one the email names (an invitation's), else the request's.
- **Failed-login counts are in Django's database cache.** The workers share
  the database and nothing else, and it needs no new dependency. The keys
  are hashed, so the table holds no email or IP addresses. Counting isn't
  exact under concurrent requests, which is fine for slowing guessing down.
- **The client's address** counts `TRUSTED_PROXIES` from the right of
  `X-Forwarded-For` (see the owner's answers above).
- **Logs name the club, and error reports and logs name nobody.** The club
  goes in a context variable, cleared on Django's request signals rather
  than by the middleware, since Django logs a response ("Not Found") after
  the middleware has returned it. Email-shaped text is redacted in log lines
  and, going a little beyond the plan, in Sentry reports too: an exception's
  message (an SMTP refusal, say) is sent whatever `send_default_pii` says.

**Why.** The slice 11 spec, part 4; the owner's answers above.

---

## 2026-09-25 - Slice 11 part 5: the owner's answers on data protection

**Decision.** Agreed with the project owner, from the part 5 plan's questions:
- **The privacy notice and terms** are at `/privacy/` and `/terms/` on every
  address, the service's and each club's, with the same text. The footer
  links to the one on the address you're on, so the test site (which has no
  service address) links to itself.
- **Deleting an account anonymises everywhere their login is kept as text:**
  change history, who decided a request or membership, who declared a
  series final, who sent an invitation, the operator log (its details
  included), and invitations sent to their address. Each becomes "a deleted
  account". Free-text reasons are left as typed; the notice says so.
- **One email confirms an account's deletion,** to the deleted address.
- **The operator can take a club's export,** including while the club is
  suspended, and each operator export and each club deletion is logged.
  `OperatorAction.Action` gains two choices for it (a choices-only
  migration), approved.
- **The notice's legal name and address are marked placeholders** until the
  legal review, which is already an open requirement.

---

## 2026-09-25 - Slice 11 part 5: how data protection was built

**Decision.**
- **Messages travel in the session,** not in their own cookie, so the site
  sets only the session and CSRF cookies, both essential: no cookie banner.
- **A person's own pages cross clubs.** The account page and the data
  download show every club the person belongs to, since it's all theirs.
  They're the one exception to "a page shows only its own club", tested on
  its own terms: someone at one club sees nothing of another, and a member
  of two sees only their own rows at each.
- **Deleting an account edits records that are otherwise never edited.** The
  change history and a final series are locked against changes, but removing
  a login from them changes no result, so the anonymising updates go around
  those rules on purpose (`races/account_deletion.py`).
- **Deleting a club deletes in order** (history, requests, series, then
  boats), in one transaction, because a boat in a series is protected from
  deletion. No model change.
- **No guard for the `SINGLE_CLUB` club:** the plan had one, but with
  `SINGLE_CLUB` set every address with no club shows that club, so the
  operator's pages, and the delete button, don't exist at all.
- **Spreadsheet formulas:** typed text starting with `=`, `+`, `-` or `@`
  gets a leading apostrophe in the club export and in the series CSV, which
  share the code (moved from `results/export.py` to `races/series_csv.py`).
- **Two intermittent test failures fixed:** a random CSRF token could contain
  a short name a test checked was absent, and a signed link includes the
  time to the second. Tests now fix the token and read links back.

**Why.** The slice 11 spec, part 5; the owner's answers above.

---

## 2026-09-25 - Slice 12: production hosting on Render, in Frankfurt

**Decision.** Agreed with the project owner:
- **Render, Frankfurt,** for production: the deploy set-up already exists,
  wildcard certificates are automatic, point-in-time recovery comes with
  paid databases, and data stays in the EU, which UK GDPR accepts. Heroku
  would also do the subdomains, but a database it can roll back starts at
  about $50 a month.
- **Postmark** sends every club's email.
- **Production deploys only when Deploy is pressed.** The test site keeps
  deploying on every merge to `main`, so it's always the first to get a
  change.
- **Off-site backups from the start:** a nightly, encrypted copy to
  S3-compatible storage (Backblaze B2's EU region recommended), using the
  storage's own command-line tool, so there's no new Python dependency.
- **Production starts empty.** The test site keeps its sample data, and
  stays in Oregon.
- **The domain's DNS is at Gandi.**

---

## 2026-09-26 - Slice 12: production's database replaced, in Frankfurt

**Decision.** The first production database was created in Oregon, though
`render.yaml` asked for Frankfurt and the web service is there: probably
created before the Blueprint's region applied. A Render database can't change
region, so `render.yaml` names a new one, `racetimes-production-db-fra`, in
Frankfurt, and the Oregon one is deleted by hand. Production was still empty,
so nothing was copied; the first deploy sets it up again.
`races/test_production.py` checks that every database production uses is in
Frankfurt, whatever it's called, and that the old name doesn't come back.

**Why.** Personal data stays in the EU, as agreed for slice 12, and the web
service and its database sit together rather than across the Atlantic.

---

## 2026-09-26 - Slice 13: the operator may decide who's waiting to join a club

**Decision.** An exception to slice 11's "clubs make their own membership
decisions", agreed with the project owner:
- the operator can approve (as member, race committee or club
  administrator) or turn down anyone **waiting** to join a club, from the
  club's operator page;
- nothing more: changing roles and removing people stay the club's;
- refused while the club is suspended;
- recorded on the membership as "the Race Times operator" (the club sees
  that, not a personal login), and in the operator log with the login;
- no email to the club's administrators; the person's email comes from the
  club as usual.

**Why.** A new club before its administrator has joined, a club whose only
administrator is away, and Demo Club in production would otherwise leave
people waiting with nobody able to let them in, short of changing the
database by hand.

---

## 2026-09-26 - Slice 14: optional capping and realignment, at full precision

**Decision.** Two optional steps from the fuller NHC method (HalSail, as
Medway Cruising Club publishes), each a setting on a series, off by default:
capping extreme results, and realigning finishers' new handicaps to their
base numbers. Agreed with the project owner where the spec and the code
differed:
- **No rounding between races,** unlike the spec's "round to 3 d.p.": the
  RYA reference says rounding is for display only, and it keeps "both off"
  identical to before. A long season may differ from MCC's published figures
  in the last decimal.
- **Club series only,** refused on a regatta.
- **In the existing "Scoring rules" section,** not a new heading.
- **Two new Series fields,** approved.

The steps live in `nhc/options.py`, apart from the RYA calculation in
`nhc/handicap.py`, which only calls them when asked. The MCC race is a
fixture; its base numbers are the spec's test values, not MCC's.

**Why.** So a club that scores with the fuller method gets the same handicaps
from Race Times as it publishes, without changing anything for anyone else.

---

## Open requirements

Things that must be done before a stated milestone, but aren't code.

- **Legal review before the first paying club** (slice 11, recorded
  2026-09-25).
  - The privacy notice and terms of service are drafts, marked "Draft" on
    the page, until reviewed.
  - Clubs will also need a data processing agreement: the club is the
    controller of its members' data, and Race Times is its processor.
  - The drafts have marked placeholders to fill in: the operator's legal
    name and postal address, and the terms' limits of liability. (The
    processors are named since slice 12: Render, Postmark, Backblaze and
    Sentry.)
  - None of this blocks building or testing slice 11. It blocks taking on a
    paying club.
  - Also listed, as the gate before the first paying club, in the slice 12
    spec (`docs/slices/12-production-hosting.md`) and in
    `docs/production.md` step 9. That includes signing each provider's
    data processing agreement.

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
  not addressed by the RYA spec at all. Slice 1 uses only the engine's four;
  see "Slice 1: only the engine's four statuses" above.
- **Elapsed time vs start/finish clock times.** Resolved 2026-09-23: the
  committee enters clock times and the app derives elapsed. See "Slice 1: the
  committee enters clock times" above.

---
