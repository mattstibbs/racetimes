## Problem and users
This is a simple online race database and scoring system, which can be used by local Sailing Clubs who are running racing series and regattas. 

There are two main user groups for this app:

- Sailing Club Race Committee Members - who are running multiple series of yacht races. They need to be able to register yachts and their key stats (make, model, sail number, base handicap), record race entries, and track completion times for those races. They also need fully automatic scoring, handicap tracking and time adjustments, and full implementation of the NHC handicap rules including handicap adjustments after each race using the reference documentation specified.

- Sailing Club Members - who are entering their yachts into races, providing some details about their yacht, and want to receive details of their race results

## Outcomes (observable success measures)

This app will let the committee users: 

- manage a list of entrants (boats and skippers)
- create races as part of a race series
- record which yachts enter each race, and some details about them (e.g. persons on board, sail number, baseline handicap)
- record race completion times against each yacht that passed over the finish line
- automatically calculate final race positions based on adjusted times adjusted by the NHC handicap ratings system

It will also expose all of the race and yacht data via a very simple to use API.

## Domain
### Glossary
- **Boat**: a yacht registered with the club. Has make, model, sail number,
  and a base NHC handicap (TCF).
- **Series**: a set of races scored together (e.g. "Wednesday Evening Spring").
  Owns its scoring rules: discards, scoring system, handicap policy.
- **Race**: a single race within a series, on a date, with one or more starts.
- **Start**: a start time for one fleet within a race.
- **Entry**: a boat entered into a series (and therefore eligible for its races).
- **Finish**: the recorded outcome for an entry in a race — either a finish
  time or a scoring code (DNF, DNC, DNS, OCS, RET, DSQ).
- **Elapsed time**: finish time minus start time.
- **Corrected time**: elapsed time × the boat's TCF for that race.
- **Race handicap**: the TCF a boat sails a given race on. For race 1 this is
  the base handicap; thereafter it is derived by the NHC progressive rules.
- **Result**: position and points for an entry in a race, derived from
  corrected times and codes.
- **Series standing**: aggregate points after discards.

### Entities and relationships

### Invariants / business rules
- A boat's sail number is unique within the club.
- A finish is either a time or a code, never both.
- Handicaps are never edited directly; they are derived from base handicap
  plus race history. Correcting any finish triggers recalculation of all
  subsequent race handicaps and results in that series.
- Handicap progression scope is configurable per series: carries over / resets.
- Handicap adjustment for boats that don't finish is configurable per series: adjusted / not adjusted.


### Source of truth
- NHC calculation: docs/reference/RYA_nhc_calculation_spec.md. Where Claude's
  understanding conflicts with these documents, the documents win.
- Scoring: docs/reference/2025-2028-RRS-with-Changes-and-Corrections.pdf. Racing Rules of Sailing, Appendix A.

## User journeys (3–6 short narratives)
- User Journey 1: A race committee user creates a new race series called "Autumn 2026 Series", and sets handicap progression to be reset for that series. They also schedule 6 races within that series.
- User Journey 2: The race committee administrator adds boat records for every boat that has registered to enter the "Autumn 2026 Series" including their boat make, model, sail number, length over all, waterline length, NHC base handicap value, and boat owner name. The boat owner receives a confirmation that they have been entered into the series.
- User Journey 3: A race committee member creates entries into a specific race for boats that are racing that day. The boat owners receive a confirmation that they have been entered into the race.
- User Journey 4: A race committee member adds finish times or finish outcome codes for each entry in that race. The system automatically calculates adjusted elapsed times based on their handicap adjustments, and calculates final places and scoring for that race. 
- User Journey 5: At the end of a race series, the race committee adminstrator initiates the final scoring calculation for the entire series - this generates final places in the series based on scores accrued by the boats during the season. These results are displayed on screen as well as being exportable in a file.

## In scope (v1)
## Out of scope
## Open questions
