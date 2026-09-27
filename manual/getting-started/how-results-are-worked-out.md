# How results and handicaps are worked out

*For everyone: sailors, the race committee and the administrator.*

This page walks through exactly what Race Times does with a race. It starts
with the numbers you give it and ends with each boat's handicap for its next
race. Every step is simple arithmetic: adding, multiplying and dividing.

Race Times follows the RYA's rules for NHC (the National Handicap for
Cruisers) and the scoring rules in Appendix A of the Racing Rules of Sailing.
Nothing here is Race Times' own invention, apart from the optional steps
near the end, which a club has to switch on.

We'll use one real race all the way through. It's the RYA's own worked
example, so you can check every number against the RYA's published figures.

## What goes in

Race Times needs only three things:

- **Each boat's NHC base number.** The RYA publishes it, and the race
  committee enters it on the boat's page (see
  [Setting up boats](../committee/setting-up-boats.md)). It's the boat's
  handicap in the first race of every series.
- **The race's start time.**
- **Each boat's finish time**, or a code if it didn't finish: DNC (did not
  come to the start), DNS (did not start) or DNF (did not finish).

Everything else is worked out from these, every time a results page is
shown. No handicap is ever typed in by hand.

A handicap is a number close to 1, such as 0.964. **A higher handicap means
the boat is expected to be faster.** Its time is multiplied by a bigger
number, so it has to sail faster to beat slower boats.

### Our example race

Five boats are entered. The race starts at 18:30:00.

| Boat | Handicap for this race | Finish time |
|---|---|---|
| Boat 1 | 0.966 | 19:28:47 |
| Boat 2 | 0.819 | 19:46:50 |
| Boat 3 | 0.939 | 19:29:08 |
| Boat 4 | 0.964 | 19:27:28 |
| Boat 5 | 0.983 | DNC (didn't come) |

## Step 1: How long each boat took (elapsed time)

For each boat that finished:

> **Elapsed time = finish time − start time**

Race Times counts it in seconds.

| Boat | Finish time | Elapsed time | In seconds |
|---|---|---|---|
| Boat 4 | 19:27:28 | 57 min 28 s | 3448 |
| Boat 1 | 19:28:47 | 58 min 47 s | 3527 |
| Boat 3 | 19:29:08 | 59 min 08 s | 3548 |
| Boat 2 | 19:46:50 | 1 h 16 min 50 s | 4610 |

Boat 5 has no elapsed time, because it didn't race.

## Step 2: Corrected time, and the places

Each boat's elapsed time is multiplied by its handicap:

> **Corrected time = elapsed time × handicap**

The boat with the **lowest corrected time wins**, and the others follow in
order.

| Place | Boat | Elapsed (seconds) | × Handicap | = Corrected (seconds) | Shown as |
|---|---|---|---|---|---|
| 1 | Boat 4 | 3448 | × 0.964 | = 3323.87 | 0:55:24 |
| 2 | Boat 3 | 3548 | × 0.939 | = 3331.57 | 0:55:32 |
| 3 | Boat 1 | 3527 | × 0.966 | = 3407.08 | 0:56:47 |
| 4 | Boat 2 | 4610 | × 0.819 | = 3775.59 | 1:02:56 |
| DNC | Boat 5 | - | - | - | - |

Boat 1 crossed the line before Boat 3, but Boat 3 has the lower handicap, so
it's second on corrected time.

If two boats have exactly the same corrected time, they share the place.
Two boats tied for first are both 1st, and the next boat is 3rd.

## Step 3: Points

Race Times uses the Low Point System (RRS Appendix A):

- 1st scores 1 point, 2nd scores 2, and so on.
- A boat that didn't finish scores **one more than the number of boats
  entered in the series**. That covers DNC, DNS and DNF alike. With five
  boats entered, Boat 5 scores 6.
- Boats tied on a place share the points for the places they fill. Two boats
  tied for 1st fill 1st and 2nd, so each scores (1 + 2) ÷ 2 = 1.5.

| Boat | Place | Points |
|---|---|---|
| Boat 4 | 1 | 1 |
| Boat 3 | 2 | 2 |
| Boat 1 | 3 | 3 |
| Boat 2 | 4 | 4 |
| Boat 5 | DNC | 6 |

A series can use **RRS A5.3**, if its notice of race says so. Then a boat that
came to the start but didn't finish scores one more than the number of boats
that came to the start, instead. A DNC still scores one more than the
entries. See [A series' scoring rules](../committee/scoring-rules.md).

## Step 4: Each boat's handicap for its next race

This is the part NHC is known for. After every race, each boat that finished
gets a new handicap, nudged towards how well it actually sailed. A boat that
sailed better than its handicap expected goes up a little. A boat that
sailed worse goes down a little.

It takes four small steps: **4a** to **4d**.

### 4a. Work out the race's "par time"

The par time is one corrected time for the whole race, worked out from how
every finisher sailed. Think of it as the time a boat sailing exactly to its
handicap would have scored. (The RYA doesn't give it a name. We call it the
par time to make the steps easier to follow.)

Only boats that finished are used. Boat 5 plays no part.

1. For each finisher, divide 100 by its elapsed time in seconds. The RYA calls
   this the boat's **adjustment scale**.

   | Boat | 100 ÷ elapsed seconds | = Adjustment scale |
   |---|---|---|
   | Boat 4 | 100 ÷ 3448 | = 0.029002 |
   | Boat 3 | 100 ÷ 3548 | = 0.028185 |
   | Boat 1 | 100 ÷ 3527 | = 0.028353 |
   | Boat 2 | 100 ÷ 4610 | = 0.021692 |

2. Add up the finishers' handicaps:
   0.964 + 0.939 + 0.966 + 0.819 = **3.688**
3. Add up their adjustment scales:
   0.029002 + 0.028185 + 0.028353 + 0.021692 = **0.107232**
4. Divide the first total by the second: 3.688 ÷ 0.107232 = **34.3928**. The
   RYA doesn't name this; call it the **fleet ratio**.
5. Multiply by 100: 34.3928 × 100 = **3439.28 seconds** (57 min 19 s). That's
   the **par time**.

### 4b. Did each boat beat par?

Compare each boat's corrected time (from step 2) with the par time:

| Boat | Corrected time | Par time | Result |
|---|---|---|---|
| Boat 4 | 3323.87 | 3439.28 | Faster than par: **better** than its handicap |
| Boat 3 | 3331.57 | 3439.28 | Faster than par: **better** |
| Boat 1 | 3407.08 | 3439.28 | Faster than par: **better** |
| Boat 2 | 3775.59 | 3439.28 | Slower than par: **worse** than its handicap |

### 4c. The handicap each boat "achieved"

For each finisher, work out the handicap that would have put it exactly on
par. That's its **achieved handicap**:

> **Achieved handicap = par time ÷ elapsed time**

| Boat | Par time ÷ elapsed | = Achieved handicap | Handicap it raced on |
|---|---|---|---|
| Boat 4 | 3439.28 ÷ 3448 | = 0.9975 | 0.964 |
| Boat 3 | 3439.28 ÷ 3548 | = 0.9694 | 0.939 |
| Boat 1 | 3439.28 ÷ 3527 | = 0.9751 | 0.966 |
| Boat 2 | 3439.28 ÷ 4610 | = 0.7460 | 0.819 |

A boat that beat par has an achieved handicap *higher* than the one it raced
on, and a boat slower than par has a *lower* one.

The RYA's document gets the same number another way: fleet ratio × the
boat's adjustment scale. For Boat 4, that's 34.3928 × 0.029002 = 0.9975, the
same answer.

### 4d. Move part of the way towards the achieved handicap

A boat's handicap doesn't jump straight to what it achieved in one race.
That would be far too jumpy: a lucky wind shift could change a handicap
completely. Instead it moves **part of the way**:

- A boat that sailed **better** than its handicap moves **30%** of the way
  towards its achieved handicap.
- A boat that sailed **worse** moves only **15%** of the way.

Good results count for twice as much as bad ones: that's the RYA's rule.
A bad race is often down to bad luck, such as a hole in the wind or a
tangled sheet, so it's trusted less than a good one.

> **New handicap = old handicap + (achieved − old) × 30% or 15%**

| Boat | Old | Achieved | Difference | × Share | = Change | New handicap |
|---|---|---|---|---|---|---|
| Boat 4 | 0.964 | 0.9975 | +0.0335 | × 30% | +0.0100 | **0.974** |
| Boat 3 | 0.939 | 0.9694 | +0.0304 | × 30% | +0.0091 | **0.948** |
| Boat 1 | 0.966 | 0.9751 | +0.0091 | × 30% | +0.0027 | **0.969** |
| Boat 2 | 0.819 | 0.7460 | −0.0730 | × 15% | −0.0109 | **0.808** |
| Boat 5 | 0.983 | - | - | - | - | **0.983** (unchanged) |

These are exactly the RYA's published answers for this race.

**A boat that didn't finish keeps its handicap.** It isn't in any of the
totals above either, so being absent can't change anyone else's handicap.

### Then the next race

Each boat races the next race on its new handicap, and the same four steps
run again. Boat 4 sails race 2 on 0.974, Boat 5 still on 0.983, and so on.

## Numbers are never rounded along the way

Handicaps are shown to 3 decimal places, as the RYA publishes them, and times
to the nearest second. Behind the scenes, Race Times keeps every number
exact, and passes the exact handicap on to the next race. Boat 1's new
handicap is really 0.96873..., shown as 0.969. The RYA's rules say so,
because rounding at every race would add up to real errors over a season.

So if you redo the sums yourself from the rounded figures on the results
page, your answer can differ from Race Times' in the last decimal place.

## When nobody's handicap changes

- **Too few finishers.** A series can set **Minimum finishers**. If fewer
  boats finish a race than that number, nobody's handicap changes after it.
  It's off (0) unless the committee sets it. See
  [A series' scoring rules](../committee/scoring-rules.md).
- **Only one finisher.** The par time is then that boat's own corrected
  time, so its achieved handicap equals the one it raced on, and nothing
  moves.
- **Nobody finished.** Every handicap carries forward.

## The two optional steps

Some clubs add one or both of these steps. They're off unless the race
committee switches them on for a series, and the race's results say so when
they're used. With both off, the calculation is exactly the RYA's.

### Capping extreme results

This happens between steps 4b and 4c. It stops one freak result swinging a
handicap too far.

1. Work out the **average** of the finishers' corrected times. In our race:
   (3323.87 + 3331.57 + 3407.08 + 3775.59) ÷ 4 = 3459.53 seconds.
2. Work out how spread out the corrected times usually are. Statisticians
   call this the *standard deviation*. Here it's 214.03 seconds.
3. That gives a band: from 3459.53 − 214.03 = **3245.50** to 3459.53 + 214.03
   = **3673.55** seconds.
4. A boat whose corrected time is outside the band is treated, *for its
   handicap only*, as if it had finished right on the edge of the band.

Boat 2's corrected time, 3775.59, is above the band. So for its new handicap,
Race Times uses 3673.55 instead. That's the same as an elapsed time of
3673.55 ÷ 0.819 = 4485.4 seconds. Its achieved handicap becomes
3439.28 ÷ 4485.4 = 0.7668, and its new handicap 0.811 instead of 0.808.

Its place, corrected time and points don't change. The par time is still
worked out from the real times. Capping needs at least three finishers.

### Realigning to base handicaps

This happens after step 4d. It stops a whole fleet's handicaps drifting up
or down together over a season.

1. Add up the finishers' **base numbers**. In our race, say they're the same
   as the handicaps they raced on (as they would be in a series' first race):
   **3.688**.
2. Add up the finishers' **new handicaps** from step 4d, unrounded:
   0.9740 + 0.9481 + 0.9687 + 0.8081 = **3.6989**.
3. Divide the first by the second: 3.688 ÷ 3.6989 = **0.99704**.
4. Multiply every finisher's new handicap by that number. Boat 4 goes from
   0.974 to 0.974 × 0.99704 = 0.971.

Afterwards, the finishers' new handicaps add up to the same total as their
base numbers. Boats that didn't finish are left out, and keep their handicap.

## A regatta works slightly differently

A series set up as a **regatta** follows the RYA's regatta rules. There are
only a few races, so the handicaps need to find their level faster:

- **Every boat starts on its base number.**
- **Boats that didn't finish still count** in the par time. Race Times gives
  them a stand-in time:
  - DNC or DNS: the average corrected time of the top three finishers (or
    of all the finishers, if fewer than three finished).
  - DNF: the corrected time of the middle finisher. With an even number of
    finishers, it's the average of the middle two.

  Each stand-in corrected time is divided by the boat's handicap to give it
  an elapsed time. That's used only for the handicap sums; it never gives the
  boat a place or changes its points.
- **Handicaps move further:** 60% of the way for a boat that sailed better,
  and 50% for one that sailed worse. In the regatta's first race, every boat
  moves 60%.
- **Limits:** after every race, a boat's new handicap is kept within 10% of its
  base number. For a base number of 0.900, that's between 0.810 and 0.990.

The minimum finishers setting and the two optional steps are for club series
only.

## Across the whole series

- **Race by race, from the start.** Every time a results page is shown, Race
  Times replays the whole series from race 1. So if a finish time in race 2 is
  corrected, every handicap from race 3 onwards is worked out again too. Every
  place and point that depends on them is updated as well.
- **Series totals.** A boat's total is its points from every race, less its
  worst score or scores (the **discards** the series sets). The lowest total
  wins.
- **Ties in the series.** Boats on the same total are split by comparing their
  scores best to worst. If they're still level, the most recent race decides
  (RRS A8).
- **A new series starts afresh.** Every series starts each boat on its base
  number. Handicaps don't carry over from one series to the next.

## Checking the numbers yourself

On a series' results page, choose a race and press **More detail**. For each
boat, you'll see its finish time, elapsed time, the handicap it raced on, its
corrected time, points, and the handicap it takes into the next race. See
[Finding your results](finding-results.md).
