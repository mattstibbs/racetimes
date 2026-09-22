## Slice 0 - the scoring engine as a pure Python package. 
No Django, no database. Plain functions that take a series' race history (boats, base handicaps, starts, finishes) and return race handicaps, corrected times, results and standings. Build it test-first against your worked examples. This is where Claude Code shines: give it the reference docs and the fixtures, tell it the tests are the spec, and let it iterate until they pass. You review the logic, not the plumbing.

## Slice 1: walking skeleton. 
A Django app with Boat, Series, Race and Finish models, admin-style forms for the race committee to enter finish times, and a results page that calls the engine. Django with HTMX would suit this well; it's server-rendered and form-heavy, with no real need for a JavaScript framework.

## Slice 2: corrections and audit. 
Editing a finish and seeing everything downstream recalculate, with a history of what changed and who changed it. Race committees will need this on day one of real use, so it's worth doing early.

## Slice 3: member self-service. 
Accounts for members, boat registration requests, and series entry. This is where auth and permissions appear, so write the role rules into the brief before starting it.

## Slice 4: notifications. 
Emailing results after a race is published.

## Slice 5: results webapp.
Another Django app (in the same project) with an HTMX page that allows a racer to easily view race results.