# Slice 3: Member self-service

## Goal
Club members have accounts. A member can register a boat, ask for changes to
it, and ask to enter it in a series, and can see where each request stands.
The race committee approves or rejects every request, so the checks that
slices 1 and 2 put around anything that feeds a score still hold. Only the
administrator manages accounts.

The role rules are in `docs/brief.md` under "Roles and permissions".

## Scope

### Roles, in terms of Django accounts
- **Member**: an active account with no staff access.
- **Race committee**: an active account with staff access, in a new
  **Race committee** permission group. The group grants the racing models
  (boats, series, entries, races, finishes, requests) and nothing to do with
  users or groups, so the committee cannot manage accounts. A data migration
  creates the group. *(Today a staff account that is not a superuser sees an
  empty admin, because Django grants admin access model by model; this group
  fixes that.)*
- **Administrator**: a superuser. Approves accounts, adds people to the Race
  committee group, and resets passwords, all in the admin.

### Data model (proposed, awaiting approval)
- **User**: Django's built-in account, unchanged. At sign-up the email address
  (lower-cased) is stored as both the username and the email, and must be
  unique ignoring case. First and last name are required. `is_active` starts
  off.
- **Boat**, one new field: `owner`, an optional link to one account. If the
  account is deleted the link is cleared, and the boat and its results stay.
  Only the committee sets it. `owner_name` stays for boats with no owner; where
  a boat has an owner, the owner's full name is shown instead.
- **BoatRequest** (new), one table for all three kinds of boat request:
  - `kind`: register, change or claim.
  - `boat`: empty for a registration; the boat concerned for a change or a
    claim.
  - The proposed values: `sail_number`, `name`, `make`, `model`,
    `length_overall_m`, `waterline_length_m`, `base_number`. A registration
    fills them all in; a change fills in the whole boat as the member wants it
    to be, starting from its current values; a claim leaves them empty.
  - `member_note`, optional, for example "new RYA certificate attached to my
    email".
  - `requested_by`, the member's account. Their requests are deleted with it.
  - `status`: pending, approved, rejected or withdrawn.
  - `decided_by` (kept as a name too, like the change history, so it survives
    the account), `decided_at`, and `committee_note`, which is required when
    rejecting and shown to the member.
  - `created_at`.
  - Rules: at most one pending request per boat; a registration's sail number
    must not already belong to a boat (the form offers a claim instead).
- **EntryRequest** (new): `series`, `boat`, `requested_by`, `member_note`,
  `status`, `decided_by`/`decided_at`/`committee_note` as above, and
  `created_at`. At most one pending request per boat per series, and none for
  a boat already entered. Deleted with its series or boat.

Approving a request makes the change through the same code as the admin does,
so it is recorded in the change history under the committee member's name.
Where it is a correction (a base number change for a boat entered in a series
with results, or a late entry into one), the committee gives the reason, as
slice 2 requires.

### Screens
- **Sign up** (public): name, email and password. Afterwards: "Your account is
  waiting for approval."
- **Log in / log out**: one login page for everyone. An account still waiting
  for approval is told so, rather than "wrong password".
- **My boats** (member): their boats with each boat's series entries, their
  requests with status and any committee note, and links to:
  - **Register a boat.** If the sail number is already on record, it offers to
    ask for ownership of that boat instead.
  - **Request a change** to one of their boats: the boat's current details,
    pre-filled, to edit.
  - **Enter a series** with one of their boats: any series it isn't in yet.
  - **Withdraw** a pending request.
- **Requests** (race committee): every pending request, oldest first. Each
  shows who asked, what they asked for, and for a change the old and new value
  of each field. Approve (with a reason box, required where the change is a
  correction) or reject (note required). HTMX, row by row, as on the
  finish-entry page. Decided requests are listed below, newest first.
- **Admin** (administrator): a filter for accounts waiting for approval and an
  "Approve selected accounts" action. Adding someone to the Race committee is
  ticking "staff" and choosing the group, as Django already allows.
- The header shows the right links for whoever is logged in: My boats,
  Requests, Admin, Log out.

## Acceptance criteria
- Someone can sign up and cannot log in until the administrator approves the
  account; they are told why.
- A member can register a boat, request a change, claim a boat on record and
  request a series entry, and see each request's status and committee note.
  None of these changes a boat, an entry or a result until approved.
- The committee can approve or reject each kind of request. Approving applies
  exactly what was requested, records it in the change history under the
  committee member's name, and asks for a reason where it is a correction.
- A member sees and acts on only their own boats and requests. Tested by
  trying another member's boat and request directly by URL.
- The committee cannot see or change accounts or groups in the admin; the
  administrator can. Tested as each role against each page.
- Every page is tested as each of the four roles: public, member, committee,
  administrator.
- Migrations use nothing specific to SQLite or PostgreSQL.

## Out of scope
- Email of any kind: verification, approval notices, password reset (slice 4).
- Co-owners and crew accounts; several owners per boat.
- Race-level entry, and "persons on board".
- Members withdrawing from a series once entered (they ask the committee).
- The API from the brief.
- Members editing their own name or email (the administrator can, in the
  admin).
