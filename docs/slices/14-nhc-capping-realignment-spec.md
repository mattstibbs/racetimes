# Change spec: optional NHC extreme-result capping and base-handicap realignment

**App:** RaceTimes
**Type:** Vertical slice (model → scoring → UI → results → tests)
**Status:** Complete (2026-09-26). See "How it was built" at the end for the
owner's decisions where the spec and the code differed.

## 1. Why

RaceTimes calculates the next NHC handicaps with the core RYA NHC formula. Medway Cruising Club (MCC) publishes results using the full specification, which adds two steps:

1. **Capping extreme results.** Before the achieved handicap is worked out, a boat whose corrected time is more than one standard deviation from the mean has its elapsed time replaced by a threshold time.
2. **Realignment to base handicaps.** Every finisher's new handicap is multiplied by one common factor, so the finishers' handicaps keep the same total as their base handicaps.

With the same race data, the two apps produce different next handicaps. This change adds both steps as **independent, optional settings on each Series**. A series can then match MCC (or any club using the full method) and still keep the current behaviour as the default.

## 2. Before you start (for Claude Code)

This spec doesn't know RaceTimes' file layout. Before writing code:

- Find the **Series** model, and where series settings are created and edited (forms, views, templates, admin).
- Find the **next-handicap calculation**: the function that turns finishers' handicaps and elapsed times into new handicaps.
- Find where each **yacht's base handicap** is stored.
- Check how results are **stored and recalculated**. Are next handicaps persisted per race? Is there a "rescore" path?
- Follow the project's existing conventions for migrations, forms, tests and naming.

If anything here conflicts with how the code actually works, stop and ask. Don't guess.

## 3. Current algorithm (unchanged when both settings are off)

For the finishers in a race (boats with an elapsed time):

- `H` = the boat's handicap for this race
- `Te` = the boat's elapsed time in seconds

```
k  = ΣH / Σ(1/Te)                      # sums over all finishers
Ha = k / Te                            # achieved handicap
α  = 0.3 if Ha > H else 0.15
Hp = H + α × (Ha − H)
new handicap = round(Hp, 3)
```

Non-finishers (DNC, DNF, DNS etc.) keep their current handicap.

**Requirement:** with both new settings off, results must match the current output exactly. Check this with the regression test in §7.

## 4. New settings on Series

Add two boolean fields to Series:

| Field | Label in UI | Default | Help text |
|---|---|---|---|
| `nhc_cap_extremes` | Cap extreme results | `False` | Results more than one standard deviation from the fleet's mean corrected time are limited to the band edge before the handicap is adjusted (RYA NHC). |
| `nhc_realign_to_base` | Realign to base handicaps | `False` | After adjustment, the finishers' new handicaps are rescaled so their total matches the total of their base handicaps (RYA NHC). |

- The migration sets both fields to `False` for existing series.
- Both fields appear on the series create/edit form (and in admin, if the project uses it), grouped under a heading such as "NHC handicap options".
- The two settings are independent. Any combination is valid.

## 5. New algorithm

### Step A: extreme capping (only if `nhc_cap_extremes`)

```
CT      = Te × H for each finisher         # corrected time
μ       = mean(CT)
σ       = SAMPLE standard deviation of CT  # statistics.stdev, NOT pstdev
lower   = μ − σ
upper   = μ + σ

for each finisher:
    if   CT < lower: Te_used = lower / H
    elif CT > upper: Te_used = upper / H
    else:            Te_used = Te
```

- `k` is **still** calculated from the **real** elapsed times: `k = ΣH / Σ(1/Te)`.
- Then `Ha = k / Te_used`. The α choice and `Hp` are as before.
- **Guard:** if there are fewer than 3 finishers, skip capping (`Te_used = Te`).
- The capped time is used **only** inside this calculation. The displayed elapsed and corrected times and the race positions don't change.

### Step B: realignment (only if `nhc_realign_to_base`)

After every finisher's `Hp` has been calculated (with or without Step A):

```
factor = Σ(base handicap of each finisher) / Σ(Hp of each finisher)
Hp     = Hp × factor                    # for each finisher
```

- Both sums cover **finishers only**. Non-finishers aren't rescaled and don't count towards either sum.
- **Guard:** if any finisher has no base handicap recorded, skip realignment for that race and log a warning. Don't mix defaults.

### Step C: rounding

`new handicap = round(Hp, 3)`. Round **once, at the very end**, never between steps.

## 6. UI and output

- Series form: the two checkboxes from §4.
- Race results page: if either setting is on for the series, show a short note under the results, e.g. "Handicaps adjusted with: extreme-result capping, realignment to base handicaps."
- Optional, if it's easy: on the results page, mark boats whose result was capped (e.g. a † next to their next handicap with a footnote "result capped as extreme").

## 7. Tests (required)

Use this real race. It's a Medway Cruising Club race where the published results are known. The boat names here are made up (generated at random), so no real boat is named; the times, handicaps and results are the race's own.

| Boat | Elapsed | Elapsed (s) | Handicap | Base handicap (fixture) |
|---|---|---|---|---|
| Lanternledger | 2:22:07 | 8527 | 0.909 | 0.909 |
| Nettlesong | 2:28:57 | 8937 | 0.934 | 0.934 |
| Lanternfold | 2:45:32 | 9932 | 0.902 | 0.902 |
| Brindledene | 2:47:00 | 10020 | 0.930 | **0.935** |
| Fenstar | 3:11:17 | 11477 | 0.865 | 0.865 |
| Lanternmere | 2:56:08 | 10568 | 0.940 | 0.940 |
| Cobbledene | 3:13:09 | 11589 | 0.952 | 0.952 |
| Saltwake | 4:28:23 | 16103 | 0.860 | 0.860 |
| Wrenwake | DNC | — | 0.770 | 0.770 |
| Nettlemere | DNC | — | 0.934 | 0.934 |
| Gorsestar | DNC | — | 0.963 | 0.963 |

The base handicaps are a **test fixture**. MCC's real base numbers aren't known, but the finishers' base total must be about 7.297 to reproduce MCC's published figures. The fixture gets that total by setting Brindledene's base to 0.935 (sum = 7.297).

Useful intermediate values (with capping): μ = 9889.787 s, σ (sample) = 1894.688 s, k = 9597.275.

### Expected next handicaps

| Boat | Both off (current) | Capping only | Realign only | Both on (= MCC published) |
|---|---|---|---|---|
| Lanternledger | 0.974 | 0.964 | 0.966 | **0.955** |
| Nettlesong | 0.976 | 0.976 | 0.968 | **0.967** |
| Lanternfold | 0.921 | 0.921 | 0.913 | **0.913** |
| Brindledene | 0.938 | 0.938 | 0.930 | **0.930** |
| Fenstar | 0.861 | 0.861 | 0.853 | **0.853** |
| Lanternmere | 0.935 | 0.935 | 0.927 | **0.927** |
| Cobbledene | 0.933 | 0.933 | 0.926 | **0.925** |
| Saltwake | 0.820 | 0.836 | 0.813 | **0.828** |
| Wrenwake / Nettlemere / Gorsestar | unchanged | unchanged | unchanged | unchanged |

Realignment factor: about 0.99154 (realign only) and about 0.99082 (both on).

### Test cases

1. **Regression:** both off → "Both off" column. This must match current RaceTimes output.
2. **Capping only** → "Capping only" column. Lanternledger and Saltwake are the only capped boats.
3. **Realign only** → "Realign only" column.
4. **Both on** → "Both on" column, which equals MCC's published results.
5. **Non-finishers** keep their handicap in every mode and are left out of every sum.
6. **Fewer than 3 finishers** with capping on → same result as capping off.
7. **A finisher missing a base handicap** with realignment on → realignment skipped, warning logged, capping (if on) still applied.
8. **Sample SD guard:** a test that would fail if `pstdev` were used instead of `stdev`. Case 4 does this: population SD gives Lanternledger 0.950, not 0.955.
9. **Form/model:** the new fields exist, default to `False`, and save from the series form.

## 8. Out of scope

- Changing α values, or making them configurable.
- Changing how positions, corrected times or points are calculated.
- Automatically rescoring past races when a series setting is changed. If the app already has a rescore action, it should use the new settings, but don't add one in this slice.
- Handling base handicaps that change mid-season.

## 9. Definition of done

- [ ] Migration adds both fields with default `False`
- [ ] Series form and admin show and save the settings
- [ ] Scoring implements Steps A–C exactly as specified, rounding only at the end
- [ ] All tests in §7 pass, including the regression test
- [ ] Results page shows which options were applied
- [ ] Existing test suite still passes

## Reference

- HalSail FAQ, "What is the detailed mathematical explanation of NHC?": https://halsail.com/Help/pdfFaq?Faqitem=NhcMaths

## How it was built *(2026-09-26)*

**Checked first.** A prototype of Steps A to C reproduces every column of
the §7 table, the intermediate values (μ, σ, k) and the pstdev figure (0.950),
and today's engine already gives the "Both off" column exactly.

**Where the spec and the code differed, decided with the project owner:**
1. **Rounding.** The spec rounds each new handicap to 3 d.p. RaceTimes never
   rounds between races: it carries full precision and rounds only for
   display, as the RYA reference requires (`docs/reference`, §7; the
   precision note in `nhc/domain.py`). **Kept full precision.** The §7
   expected values all match at 3 d.p., and "both off matches current
   output" holds exactly. Over a long season, results may differ from MCC's
   in the last decimal, since MCC carries its rounded figures forward.
2. **Regattas.** Both settings are **club series only**, refused on a regatta
   (in the model and in the engine), like "Minimum finishers". A regatta
   uses the RYA's own regatta formulas and clamps to base numbers.
3. **Where the settings go.** In the existing **"Scoring rules"** section of
   a Series (the name kept), not a new "NHC handicap options" heading.
4. **The data model change** (two boolean fields) was approved.

**Also different from the spec, because of how RaceTimes works:**
- **Base handicaps** are each boat's RYA base number (`Boat.base_number`),
  which is required and must be above 0. A finisher with no base number (§5
  Step B's guard, §7 case 7) can only arise using the engine directly, so it
  is handled and tested there. The engine does no I/O, so it can't log; it
  leaves `realignment_factor` as None instead.
- **The admin is the series form.** There's no separate one.
- **The results page** is the public series page. The note sits under each
  race's results; the † appears with "More detail", where the next-handicap
  column is shown. The series header and the CSV download name the options
  too.
- **In the site, a series starts on base numbers**, so the MCC race (where
  one boat races on 0.930 with a base of 0.935) can't be set up exactly
  there. The MCC figures are proven in the engine's tests; the site's tests
  reproduce the "off" and "capping only" columns exactly, and compare
  realignment with the engine for the same boats.

**Where the code is:**
- `nhc/options.py` holds the two steps, each on its own.
- `nhc/handicap.py` calls them only when asked.
- `RaceResult` records what happened: `elapsed_seconds_used`, `capped` and
  `realignment_factor`.
- The fixture is `tests/fixtures/mcc_full_nhc_method.yaml`. Its boat names
  are made up at random, so that no real boat is named in the tests.
- The tests are `tests/test_nhc_options.py` (the engine) and
  `races/test_nhc_series_options.py` (the site).
- The manual page is "A series' scoring rules".

