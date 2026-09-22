# NHC Calculation Library - Specification

*As of 2026-09-21*

Specification for implementing the RYA National Handicap for Cruisers (NHC) scoring and handicap-adjustment algorithms as a standalone calculation library, covering club series, regatta series, and end-of-series realignment.

## 1. Core definitions and terminology

| Term | Symbol | Meaning |
| --- | --- | --- |
| Time Correction Factor | TCF | A boat's current handicap number. Used as a multiplier on elapsed time. Lower = faster rating. |
| Base Number | BN | A boat's starting/reference TCF, published by the RYA (or assigned by the club) before any performance adjustment. |
| Elapsed Time | E | Time taken by a boat to complete the course, in seconds. |
| Corrected Time | C | E multiplied by TCF; used to rank the fleet. Lowest corrected time wins. |
| Adjustment Scale | AS | 100 / E for a boat that has a valid elapsed time. A weighting factor, not a handicap itself. |
| Achieved Handicap | TCFr | The TCF a boat would have needed to exactly tie for 1st in this race, given its actual elapsed time. |
| Next-race TCF | TCFn | The TCF to be used for a boat's next race, blending TCF and TCFr. |
| Over-performance | - | A race where TCFr > TCF (the boat sailed faster than its handicap predicted). |
| Under-performance | - | A race where TCFr < TCF (the boat sailed slower than its handicap predicted). |

All TCF/TCFr/TCFn values are dimensionless decimals (typically 0.6-1.1). All times are in whole seconds unless otherwise noted.

## 2. Race scoring formula

For every boat that starts and has a recorded elapsed time:

```latex
C = E \times TCF
```

Boats are ranked by ascending corrected time (lowest C = 1st place). A boat that did not take part receives no corrected time and no adjustment for that race (club series) or is handled per section 4 (regatta series).

Worked example (used as a test vector in section 8):

| Boat | E (sec) | TCF | C (sec) | Position |
| --- | --- | --- | --- | --- |
| Boat 4 | 3448 | 0.964 | 3323.87 | 1 |
| Boat 3 | 3548 | 0.939 | 3331.57 | 2 |
| Boat 1 | 3527 | 0.966 | 3407.08 | 3 |
| Boat 2 | 4610 | 0.819 | 3775.59 | 4 |
| Boat 5 | 0 (DNC) | 0.983 | - | DNC |

## 3. Club series handicap adjustment

Applies to a standard ongoing club series, race by race.

**Step 1 - Adjustment scale.** For every boat that finished (E > 0):

```latex
AS = \frac{100}{E}
```

**Step 2 - Achieved handicap (TCFr).** Computed only over boats that took part (E > 0):

```latex
TCFr = \left(\frac{\sum TCF}{\sum AS}\right) \times AS
```

where the sums run over every boat that started, and AS/TCF on the right are that individual boat's own values.

**Step 3 - Classify performance.**

- If TCFr > TCF: over-performance (boat sailed faster than its handicap predicted).
- If TCFr <= TCF: under-performance.

**Step 4 - Next-race TCF (TCFn).**

```latex
TCFn = \begin{cases} 0.7 \times TCF + 0.3 \times TCFr & \text{over-performance} \\ 0.85 \times TCF + 0.15 \times TCFr & \text{under-performance} \end{cases}
```

**Non-starters (E = 0):** no TCFr, no reclassification. TCFn = TCF (handicap carries forward unchanged), and the boat is excluded from the sums in Step 2 for every other boat's calculation.

**Practical note (unconfirmed in the official RYA text, seen in at least one third-party scoring package's documentation):** some club implementations require at least 3 finishers in a race before recalculating handicaps at all; with 1-2 finishers all handicaps carry forward unchanged. Flagged as an assumption to confirm - see section 9.

## 4. Regatta series handicap adjustment

Applies to a short, standalone regatta. All boats start on their Base Number. TCFr is computed exactly as in section 3, Step 2, but over ALL boats in the fleet (including back-calculated non-finishers below), not just literal finishers.

**Step 1 - Back-calculate elapsed time for non-finishers**, so every boat has a usable E for the TCFr sum:

- DNC or DNS: `E = (average corrected time of the top 3 finishers) / TCF`. If fewer than 3 boats finished, average whatever finished (2, or 1).
- DNF: `E = (corrected time of the median finisher) / TCF`. With an even number of finishers, median = average of the corrected times of the two middle-placed boats.

**Step 2 - AS and TCFr:** identical formulas to club series (section 3, Steps 1-2), using the real or back-calculated E for every boat.

**Step 3 - Next-race TCF.**

- **First race of the regatta (all boats, no over/under distinction):**

```latex
TCFn = TCF + 0.6 \times (TCFr - TCF)
```

- **Every subsequent race:**

```latex
TCFn = \begin{cases} TCF + 0.6 \times (TCFr - TCF) & \text{over-performance } (TCFr > TCF) \\ TCF + 0.5 \times (TCFr - TCF) & \text{under-performance } (TCFr \le TCF) \end{cases}
```

**Step 4 - Clamp to Base Number.** After Step 3, clamp every boat's TCFn to within +/-10% of its own Base Number (BN):

```latex
TCFn_{clamped} = \min\big(\max(TCFn,\ 0.9 \times BN),\ 1.1 \times BN\big)
```

The clamp applies at every race of the regatta, not just the first.

## 5. End-of-series realignment

Run once, after the final race of a club series, over every boat that took part in that series:

```latex
CN = \left(\frac{\sum BN}{\sum EH}\right) \times EH
```

where:

- `CN` = realigned club number - the TCF the boat starts the next series with.
- `BN` = the boat's Base Number.
- `EH` = the boat's ending handicap (its TCFn after the final race of the series just finished).
- Both sums run over every boat in the series being realigned.

This pulls the whole fleet's drifted handicaps back into alignment with their Base Numbers before the next series begins. It is not applied mid-series, and is a separate step from the regatta clamp in section 4.

## 6. Suggested data model

Language-agnostic shapes; adapt to idiomatic types (e.g. Python dataclasses).

```markdown
Boat
  id: string
  name: string
  base_number: float          # BN, published rating
  current_tcf: float          # TCF going into the next race

RaceStatus = "FINISHED" | "DNC" | "DNS" | "DNF"

RaceEntry
  boat_id: string
  status: RaceStatus
  elapsed_time_seconds: float | null   # required if FINISHED, else null
  tcf_used: float                      # TCF this boat raced under

RaceResult (per boat, computed)
  boat_id: string
  elapsed_time_used: float     # real E, or back-calculated for regattas
  corrected_time: float | null # null for non-finishers in club series
  position: int | "DNC"
  adjustment_scale: float
  achieved_handicap: float     # TCFr
  performance: "OVER" | "UNDER" | null
  next_tcf: float              # TCFn, pre-clamp
  next_tcf_clamped: float | null  # regatta only

SeriesType = "CLUB" | "REGATTA"

RaceInput
  series_type: SeriesType
  is_first_race_of_regatta: bool   # regatta only; ignored for club
  entries: RaceEntry[]

RealignmentInput
  boats: { boat_id: string, base_number: float, ending_handicap: float }[]

RealignmentResult
  boat_id: string
  realigned_tcf: float          # CN
```

Core functions to implement: `score_race(entries) -> RaceResult[]`, `compute_club_adjustment(entries) -> RaceResult[]`, `compute_regatta_adjustment(entries, is_first_race) -> RaceResult[]`, `realign_series(boats) -> RealignmentResult[]`.

## 7. Validation rules and edge cases

| Case | Handling |
| --- | --- |
| elapsed\_time <= 0 with status FINISHED | Reject as invalid input. |
| Fewer than 2 boats with a valid E in a club race | AS/TCFr sums degrade to trivial (single-boat) values; TCFn collapses toward TCF. Library should still compute but callers may want to flag this. |
| Zero finishers in a regatta race | Back-calculation for DNC/DNS/DNF has no source data (no top-3 average, no median). Return an explicit error rather than dividing by an empty set. |
| Exactly 1 or 2 finishers in a regatta (for the DNC/DNS top-3 average) | Average whatever finished (1 or 2 boats) rather than erroring. |
| Tied corrected times | Position/rank ties are a scoring-system (RRS Appendix A) concern, out of scope for the handicap-adjustment formulas themselves; expose corrected time and let the caller resolve ties. |
| TCF or Base Number <= 0 | Reject as invalid input - all formulas divide or multiply by these. |
| Rounding | Corrected time: round to the nearest whole second only for display/reporting; keep full floating-point precision through all TCF/TCFr/TCFn calculations, matching the RYA reference document's approach. |
| Boat with no Base Number (new to regatta) | Cannot apply the clamp in section 4, Step 4. Treat as a required field for regatta entries. |
| Points/scoring (RRS Appendix A, e.g. DNC penalties) | Out of scope for this library - it produces corrected times and handicaps only, not series points. |

## 8. Test vectors

Taken from the RYA's own published worked example - use these to unit-test `compute_club_adjustment`.

**Input:**

| Boat | E (sec) | TCF used |
| --- | --- | --- |
| Boat 4 | 3448 | 0.964 |
| Boat 3 | 3548 | 0.939 |
| Boat 1 | 3527 | 0.966 |
| Boat 2 | 4610 | 0.819 |
| Boat 5 | 0 (DNC) | 0.983 |

**Expected output:**

| Boat | Corrected time | AS | TCFr | Performance | TCFn |
| --- | --- | --- | --- | --- | --- |
| Boat 4 | 3323.87 | 0.02900232 | 0.997 | Over | 0.974 |
| Boat 3 | 3331.57 | 0.02818489 | 0.969 | Over | 0.948 |
| Boat 1 | 3407.08 | 0.02835271 | 0.975 | Over | 0.969 |
| Boat 2 | 3775.59 | 0.02169197 | 0.746 | Under | 0.808 |
| Boat 5 | - (DNC) | 0 | - | - | 0.983 (unchanged) |

A correct implementation should reproduce TCFn to 3 decimal places for boats 1-4, and carry Boat 5's TCF forward unchanged.

**Realignment test vector (section 5):**

| Boat | Ending handicap (EH) | Base Number (BN) | Expected realigned (CN) |
| --- | --- | --- | --- |
| Boat 1 | 0.966 | 0.821 | 0.906 |
| Boat 2 | 0.819 | 0.770 | 0.768 |
| Boat 3 | 0.939 | 0.890 | 0.881 |
| Boat 4 | 0.964 | 0.922 | 0.904 |
| Boat 5 | 0.983 | 0.977 | 0.922 |

## 9. Open questions and assumptions

- [ ] Confirm whether a minimum-finisher threshold (some third-party software requires 3+) should be built into this library, or left as an option the caller enables.
- [ ] Confirm tie-breaking behaviour for equal corrected times is genuinely out of scope, or whether the library should expose a hook for it.
- [ ] Confirm rounding convention for elapsed/corrected time (whole seconds vs sub-second) expected by the target club's timing setup.
- [ ] Confirm whether multihull-specific adjustments (referenced in RYA/MOCRA scheme updates) are needed for this deployment, or out of scope.
- [ ] Confirm the exact tie-break for the regatta DNC/DNS "average of top 3" when there are duplicate corrected times among the top 3.
- [ ] Source of truth: this spec follows the RYA's own "NHC Results Software Calculations" document. If the target club's existing scoring software (e.g. HalSail or similar) rounds or sequences steps differently, note that as a compatibility requirement before implementation.
