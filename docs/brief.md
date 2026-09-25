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


### Roles and permissions
Agreed with the project owner on 2026-09-24, before slice 3. Changed in slice
11 (2026-09-25), when Race Times became a service for many clubs: roles now
belong to a person's membership of a club, not to their account.

| Can… | Public | Member | Race committee | Club administrator |
|---|:-:|:-:|:-:|:-:|
| See the club's results and standings | ✓ | ✓ | ✓ | ✓ |
| Sign up, or ask to join the club | ✓ | | | |
| Request a boat registration, a change to their own boat, ownership of a boat already on record, or a series entry; see and withdraw their own requests | | ✓ | ✓ | ✓ |
| Approve or reject those requests; set up boats, series and races; enter finishes; see the change history | | | ✓ | ✓ |
| Approve people joining the club; set each person's role; remove people | | | | ✓ |

Each column is a role *at one club*. The same person can be a member at one
club and on the race committee at another, and a role at one club gives
nothing at another. The **operator** (the project owner, a superuser) runs
the service: creating and suspending clubs, and managing accounts. The
operator has no role at any club unless given a membership like anyone else.

- **Accounts are people, not boats.** A person signs up with their email
  address, which is also their login, and can log in once they've confirmed
  it. It's joining a club that waits for approval, by that club's
  administrators (slice 11; before that, the administrator approved the
  account itself).
- **A boat has at most one owning account.** Only the race committee sets or
  changes it. A boat with no owning account (a visitor, say) shows its typed
  owner name.
- **Members change nothing directly.** Every registration, change to a boat,
  claim of ownership and series entry is a request that the race committee
  approves or rejects, so nothing a member types reaches a boat or a result
  without a committee member's say-so.
- **The race committee cannot manage people**, including giving themselves
  more access. That is the club administrators' alone. No administrator can
  change their own membership, and a club always keeps at least one
  administrator.
- A forgotten password is reset by email (slice 4).

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
