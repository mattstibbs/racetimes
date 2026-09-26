# Slice 13: the operator approves people joining a club

**Status: complete (2026-09-26).**

## Goal
Today only a club's own administrators can approve someone asking to join it,
on the club's **Members** page. That leaves a gap:
- a new club whose administrator hasn't accepted their invitation yet;
- a club whose only administrator is away;
- Demo Club, which has no administrator in production.

In each case, people waiting to join sit there with nobody to let them in.
The only ways round it today are for the operator to invite themselves as the
club's administrator, or to change the database by hand in Render's Shell.

This slice gives the operator a **Waiting to join** list on each club's page
under `/operator/`, where they can approve or turn down each person, just as
a club administrator would. Everything else about membership stays with the
club.

## Why this needs a slice, not a quick change
Slice 11 set a principle: **clubs make their own membership decisions**, and
the operator runs the service without any role at a club. This slice makes
one deliberate exception, and it should be recorded as such in
`docs/decisions.md`:
- the operator can decide **waiting** requests, and nothing more (question
  2);
- every decision is visible to the club and logged in the operator log.

The privacy notice describes the club as controller and Race Times as
processor. The operator admitting someone to a club acts for the club, so the
notice and the club's data processing agreement should say the operator may
do this at the club's request (question 5).

## What's there already
- **One place decides a membership:** `races/membership_views._decide`
  approves, turns down, changes a role or removes. It takes care of:
  - the "last administrator" rule and the "not your own membership" rule;
  - recording who decided and when (`decided_by_name`, `decided_at`);
  - locking the row (`select_for_update`), so two people deciding at once
    can't both win.

  It reads the club from `request.club`, which is `None` on the service's own
  address, where the operator's pages are. So it needs the club passed in
  instead: a small refactor with no change of behaviour.
- **The person is emailed** by `notifications.membership_decided`. Its links
  ("My boats", the club's results) are built from the request's address,
  which would point at the *service's* address, not the club's, when the
  operator decides. They must be built with `clubs.club_address(request,
  club, ...)` instead, as invitations already do.
- **The email already comes from the club** ("<Club> via Race Times", with
  replies to the club's contact email), because the club is in the email's
  context (slice 11 part 4). Nothing to change there.
- **The operator's club page** (`/operator/clubs/<pk>/`) shows the club's
  status, administrators, invitations, data and the operator log. The new
  list goes there.
- **The operator log** records every operator action. `OperatorAction.Action`
  is a list of choices, so new kinds of entry need a small migration, with no
  table changes (as in slice 11 part 5).

## What gets built
1. **`_decide` takes the club** rather than reading `request.club`. The
   club administrator's view passes `request.club`, so behaviour there is
   unchanged; the existing tests prove it.
2. **The operator's club page gains "Waiting to join"**, above the
   administrators. For each person waiting:
   - name, email, and when they asked;
   - a role to approve them as (question 1);
   - **Approve** and **Don't approve** buttons.

   It uses the same layout as the club's Members page. It shows only people
   waiting at *that* club, and when nobody is waiting it says so.
3. **Deciding** (`POST /operator/clubs/<pk>/members/<membership pk>/`, for
   the operator only, on the service's own address):
   - it acts only on a membership of that club that is still waiting.
     Anything else (another club's membership, an approved or removed one,
     a stale page) changes nothing, as on the Members page;
   - it goes through `_decide`, so the same rules, locking and record
     apply. `decided_by_name` is the operator's login;
   - the person is emailed exactly as when a club administrator decides,
     from the club, with links to the **club's** address;
   - it's logged in the operator log, e.g. "Approved kim@example.com as
     member" (question 3 covers the log's new actions);
   - it's refused while the club is suspended, as invitations are
     (question 4);
   - the operator's page says what happened: "Kim Park: approved and
     emailed."
4. **The club can see it was the operator.**
   - An operator's decision is recorded on the membership as "the Race Times
     operator", not the operator's personal login, which means nothing to
     the club. The operator log keeps the login.
   - The club's data export already has a "decided by" column.
   - The Members page doesn't show who decided today (this spec first said
     it did), so it gains a small note on anyone the operator approved:
     "approved by the Race Times operator".
5. **Tests** (in `races/test_operator.py` and `races/test_isolation.py`):
   - the list shows exactly the club's waiting people, and none from
     another club;
   - approve and don't approve change the membership and send the email,
     with links on the club's address;
   - a membership from another club, or one no longer waiting, isn't
     changed;
   - only the operator can do it, and only on the service's address:
     - a club administrator, a committee member, a member and the public are
       refused;
     - at a club's address the page is a 404, like every operator page;
   - it's refused while the club is suspended;
   - the log entry is written;
   - the club administrator's existing Members page tests still pass
     unchanged after the refactor;
   - the new address joins the every-URL isolation test.
6. **Docs:**
   - `docs/operating.md`: a new section, "People waiting to join";
   - the manual's "Running your club: members and roles" page: one line
     saying the service's operator can also approve people waiting, for
     example before the club has an administrator;
   - `docs/decisions.md`: the exception to "clubs decide their own
     members", and why;
   - `docs/plan.md`.

   No new screenshots are needed in the manual, since the operator's pages
   aren't in it.

## Acceptance criteria
- The operator can approve or turn down anyone waiting to join a club, from
  that club's operator page, and the person is emailed with links to the
  club.
- The operator can't change an approved member's role or remove anyone
  (unless question 2 is answered otherwise).
- Every decision is recorded on the membership and in the operator log.
- Nobody else can reach the new page or action, and no other club's data
  appears on it.
- All existing tests pass unchanged.

## Out of scope
- The operator changing roles or removing members (see question 2).
- The operator approving members' boat and entry requests, which stay with
  each club's race committee.
- Bulk approval ("approve all").

## Questions for the project owner
1. **Which roles can the operator approve someone as?**
   - **Recommended: any of the three** (member, race committee, club
     administrator), defaulting to member. Approving someone as club
     administrator is how the operator would give a new club its first
     administrator when that person signed up themselves instead of
     accepting an invitation.
   - Or **member only**, keeping every role above member for the club to
     decide.
2. **Only people waiting, or more?** Recommended: **waiting requests
   only**, approve or don't approve. Changing roles and removing people stay
   the club's.
3. **How it's recorded:**
   - **The operator log** gains two kinds of entry, "Approved someone
     joining" and "Turned down someone joining". That's a choices-only
     migration, like slice 11 part 5's. **This changes the data model, so
     it needs your approval.**
   - **The club's Members page** shows "the Race Times operator" as who
     decided, rather than the operator's login. **Recommended.**
4. **Suspended clubs.** Recommended: **refused while suspended**, as
   invitations are. The person couldn't use the club's site anyway.
5. **Telling the club.** Should the club's administrators get an email when
   the operator approves someone? **Recommended: no.** The Members page
   already shows who decided, and the email to the person comes from the
   club. The privacy notice gains one sentence: the operator may admit
   people to a club at the club's request. That wording goes into the legal
   review.

**The owner's answers (2026-09-26):**
1. **Any of the three roles,** defaulting to member.
2. **Waiting requests only.**
3. **Yes to both:**
   - the two new operator log actions, a choices-only migration (approved);
   - "the Race Times operator" as who decided, as seen by the club.
4. **Refused while the club is suspended.**
5. **No email to the club's administrators.** The privacy notice gains one
   sentence saying the operator may admit people to a club at the club's
   request, for the legal review to check.

