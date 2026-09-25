# Slice 11: Race Times as a service for many clubs

**Status: planned, and ready to build. Every open question is answered, and
the data model was approved by the project owner on 2026-09-25.**

## Goal
Race Times today is one club's website. It assumes a single club throughout:
- every sail number is unique across the whole site;
- the race committee is one global permission group;
- the administrator is Django's superuser;
- every email comes from one sender.

The project owner wants to offer it to sailing clubs as a hosted service
(software as a service). Each club gets its own site, at its own address,
with its own members, committee and results. The owner runs one service for
all of them.

This slice turns the single-club site into that multi-club service. It makes
it safe, supportable and ready to put in front of a paying club. Choosing and
setting up the production host is deliberately left to a later slice (see
"Deferred"). Everything here works the same wherever the site runs.

## The shape of it *(agreed with the project owner)*

| Decision | Choice |
|---|---|
| Keeping clubs apart | **One database, the club on every row.** One site and one database serve every club. Each club's data carries its club, and every page, form, email and download sees only the current club's rows. |
| Addresses | **A subdomain per club**, e.g. `exesc.<product domain>`, found from the web address of each request. A club's own domain comes later. |
| Accounts | **One login, many clubs.** A person has one account, and joins each club separately. Each club approves them and gives them their own role. |
| Onboarding | **The operator sets clubs up.** The project owner creates each club and invites its first administrator. There's no self-serve sign-up and no payments code; the operator invoices clubs outside the site. |
| Email | **One transactional email provider over SMTP**, using the SMTP settings the site already has, so there's no new dependency. Emails come from the service's domain, show the club's name as the sender, and send replies to the club. |
| Monitoring | **Sentry for errors, plus external uptime checks.** Adds one dependency, `sentry-sdk`, which the project owner approved. |
| Data protection | **The UK GDPR essentials:** privacy notice and terms, a member's own data download, deleting an account, a club's data export, and deleting a club. |
| Hosting | **Deferred** to a later slice. This slice keeps the code independent of any particular host. |

Why these choices, in short:
- **One database** is the cheapest to run and upgrade: one deploy for every
  club. It needs no new dependency, and SQLite still works for development.
  Its one real risk is a bug showing one club another's data. Club isolation
  is therefore enforced in one place in the code, and tested on every page
  (see "Isolation").
- **Subdomains** let the site tell clubs apart without changing any page's
  address, so every existing link and test keeps its shape.

## Roles *(the brief's roles table changes; for the project owner to confirm)*

Roles now belong to **a person in a club**, not to the account. The same
person can be a member at one club and on the committee at another.

| Role | Where | Can |
|---|---|---|
| Public | any club's site | See that club's results and standings. Ask to join. |
| Member | one club | Everything a member can do today, at that club. |
| Race committee | one club | Everything the committee can do today, at that club only. |
| Club administrator | one club | Everything the administrator does today, at that club only: approve people joining, make people committee or administrators. |
| **Operator** (new) | the whole service | Create, suspend and delete clubs; invite a club's first administrator. Sees no club's pages unless also a member there. Changes no results. |

- **Joining a club is what gets approved, not the account.** Today, a new
  account can't log in until the administrator approves it (slice 3). Under
  this slice:
  - Anyone can create an account, and log in once they've confirmed their
    email address.
  - Asking to join a club is a request that the club's administrators approve
    or reject.
  - Until it's approved, the person sees "waiting for approval at <club>" and
    has no member access there.

  This keeps slice 3's protection, since nobody reaches a club without that
  club's say-so, while letting one account span clubs. *(For the project
  owner to confirm: open question 1.)*
- **Django's `is_staff`, `is_superuser` and the "Race committee" group stop
  meaning anything for clubs.**
  - `races/roles.py` answers "is this person committee here?" from the club
    membership.
  - Superuser now means the operator only.
  - `committee_required` and `member_required` keep their names, and check
    the current club.

## What changes, by part

The slice is built and merged in **five parts**, in this order. Each part
leaves the site working, and each gets its own pull request. Only part 1
touches every page; the rest are additions.

### Part 1: clubs, and keeping them apart
- **A `Club`:**
  - its name;
  - its subdomain (a short name, e.g. `exesc`);
  - a contact email, where replies to its emails go;
  - a status: active or suspended;
  - when it was created.
- **Every row belongs to a club.**
  - `Boat` and `Series` gain a club.
  - Everything else follows from those: races, entries, finishes, start sheets
    and requests about a boat or series.
  - Two tables need a club of their own:
    - `BoatRequest`, because a registration has no boat yet;
    - `ScoringChange`, because a boat's change may be in no series.
- **Sail numbers are unique within a club,** not across the service. The
  existing constraint gains the club.
- **A boat belongs to one club.** A boat that races at two clubs is
  registered at each. Its handicap and history are each club's own business.
  This keeps clubs fully apart, at the cost of typing a boat twice. *(My
  recommendation; open question 2.)*
- **The current club comes from the address.** A small piece of middleware
  reads the request's host, finds the club whose subdomain matches, and
  attaches it to the request as `request.club`.
  - An unknown subdomain gets a plain "There's no club at this address"
    page.
  - A suspended club shows "This club's site is paused" to everyone except
    the operator.
  - The service's own address (no subdomain) shows the service's front page
    (part 3).
- **One place does the filtering.** Each club-owned model gets a manager
  method, `for_club(club)`. Every view, form, admin page, email and download
  asks for rows through it, or through a row already found that way.
  - A test walks every URL pattern and checks each page, as each role, for
    another club's data (see "Isolation").
  - A second test fails if any view in `races/` or `results/` queries a
    club-owned model directly, without `for_club`. It reads the source the
    same way `results/test_read_only.py` does today.
- **The Django admin, used by the committee to set things up, is scoped
  too.**
  - A custom admin site lets a person in only as committee or administrator
    of the current club.
  - Each model admin lists and edits only that club's rows.
  - Every choice list shows only that club's boats and series, for example a
    series' entries.
  - Accounts and groups disappear from the club admin. People are managed on
    the club's own Members page (part 2).
- **Existing data moves into a first club.** A data migration creates a club
  from two environment variables, `FIRST_CLUB_NAME` and
  `FIRST_CLUB_SUBDOMAIN`, with sensible defaults, and gives it every
  existing row. Every series, race and result scores exactly as before. This
  is tested the way slice 6's start sheet migration was.
- **Working without subdomains.** The current test site on Render has one
  fixed address and can't have subdomains, and neither can the test client.
  - A setting, `SINGLE_CLUB`, names the subdomain of a club to use whenever
    the address has no club in it.
  - The test site then keeps working, unchanged, until hosting is chosen.
  - Tests use a default club the same way, and can set the host to test
    several clubs.
  - In development, `exesc.localhost:8000` works in every current browser
    with no setup.
- **Every page shows which club it belongs to.** The header shows the
  club's name, with "Race Times" in smaller type.

### Part 2: people and roles per club
- **A `ClubMembership`** links a person to a club, with:
  - their role: member, committee or administrator;
  - a status: waiting, approved or removed;
  - who approved it, and when.
- **Signing up** confirms the person's email address with a link, using
  Django's own signed tokens, as the password reset already does.
  - Signing up at a club's address also asks to join that club.
  - A person who already has an account uses **Join this club** instead, and
    signs up nowhere.
- **The club administrator's Members page** (new, club administrators only):
  - approve or reject people waiting to join;
  - change a member's role;
  - remove someone from the club.

  It replaces the approval and "make someone committee" steps in today's
  Django admin, which are no longer available to clubs. Each decision emails
  the person, and those emails go through the existing
  `races/notifications.send`.
- **Nobody can manage themselves.** An administrator can't change or remove
  their own membership, and a club always keeps at least one administrator.
  Both are tested.
- **Logging in is per club address.** Each club's site keeps its own login
  session, which is the browser's default for a subdomain. Being logged in
  at one club doesn't log you in at another. This is deliberate: it keeps the
  clubs apart.
- **Existing people move over.** A data migration gives each existing
  account a membership of the first club:
  - staff in the "Race committee" group become committee;
  - the superuser becomes the club's administrator and the operator;
  - every other active account becomes a member;
  - accounts still waiting for approval get a waiting membership.

  The "Race committee" group and staff flags are then no longer read by
  anything.
- **The roles tests** (`races/test_roles.py`) run every page as each of five
  roles at a club, the operator included, and again as a committee member of
  a different club, who must see nothing more than the public.

### Part 3: the operator
- **The operator's pages** live on the service's own address, at
  `/operator/`, and only the operator can open them. They offer:
  - a list of clubs, with their status, how many members and series each
    has, and when each last had a result recorded;
  - **create a club**: its name, subdomain and contact email;
  - **invite a club administrator**: an emailed link, valid for 7 days,
    that creates their account if needed and makes them the club's
    administrator;
  - **suspend or reactivate a club**;
  - **delete a club** (part 5).
- **Subdomains are checked** for letters, digits and hyphens only. A short
  list of reserved names is refused: `www`, `admin`, `operator`, `mail`,
  `api`, `static`, `app`.
- **The service's front page** (on the service's own address) says what
  Race Times is, and gives a contact address for clubs that want it. It
  doesn't list clubs: a club tells its own members its address.
- **The operator changes no club data.** The operator can see a club's
  pages only by being given a membership like anyone else. Every operator
  action is recorded in an operator log (who, what, when).

### Part 4: running it in production
- **Email.**
  - Every email is sent from one address on the service's domain, set by
    `DEFAULT_FROM_EMAIL` as today. The display name is "<Club name> via Race
    Times", and the reply-to address is the club's contact email.
  - One provider sends for every club, set up through the existing `EMAIL_*`
    settings.
  - `docs/deploying.md` gains a checklist for choosing and verifying the
    provider:
    - the domain records the provider needs (SPF, DKIM and DMARC), so club
      emails aren't marked as spam;
    - the allowance needed: roughly 600 emails per club per season,
      according to the slice 4 note, times the number of clubs.
  - The provider itself is chosen with hosting.
- **Errors.**
  - `sentry-sdk` (the approved dependency) reports unhandled errors, tagged
    with the club's subdomain and the page. It's switched on only when a
    `SENTRY_DSN` environment variable is set, so development and tests send
    nothing.
  - Personal data is not sent: `send_default_pii` is off, and request bodies
    are not sent.
- **Health.**
  - `/health/` answers on every address. It returns "ok" when the database
    answers and an error otherwise, and reports no other detail.
  - It's what the host and the external uptime check (e.g. UptimeRobot)
    poll.
- **Security settings for production:**
  - HTTPS only (`SECURE_SSL_REDIRECT`);
  - HSTS, starting at one hour and raised once hosting is settled;
  - secure cookies, as today;
  - `X-Frame-Options: DENY`;
  - a strict referrer policy.

  `manage.py check --deploy` passes with production settings, and CI runs it
  as a new job.
- **Hosts:** `ALLOWED_HOSTS` accepts the service's domain and every
  subdomain of it, from a `SERVICE_DOMAIN` environment variable. The CSRF
  trusted origins follow it, to cover every club address.
- **Logs:**
  - Each log line of a request includes the club's subdomain, so a problem
    can be traced to a club.
  - Log lines carry no email addresses or names.
- **Throttling logins:** repeated failed logins for one account, or from one
  address, are slowed down. It uses Django's cache in the database, with no
  new dependency: after 10 failures in 15 minutes, logins are refused for 15
  minutes, with a message saying so. This matters more now that anyone can
  create an account.

### Part 5: data protection (UK GDPR essentials)
- **Pages.**
  - A **privacy notice** and **terms of service**, at `racetimes.co.uk`,
    linked from every page's footer.
  - Their text is a draft, marked "Draft" on the page until it has been
    reviewed. The review is an open requirement before the first paying
    club (open question 5).
  - Each club is the "controller" of its members' data and the service is
    its "processor". The notice explains that.
- **Cookies:** only the essential ones, the login session and the CSRF
  token, so there's no cookie banner. A test checks no page sets any other
  cookie.
- **A member's own data:** **Download my data** on the account page gives a
  JSON file with:
  - the account;
  - their memberships;
  - the boats they own at each club;
  - their requests;
  - the change history entries they made.
- **Deleting an account:**
  - The person deletes their own account, after confirming with their
    password.
  - Their memberships and requests go.
  - Their boats stay with the club, as the club's records, with no owner.
  - Change history entries they made keep the change but say "a deleted
    account" instead of their name. The results record stays complete
    without naming them.
  - A club's last administrator can't delete their account until they've
    handed that role on.
- **A club's data export:**
  - The club administrator downloads everything the club holds as a ZIP of
    CSV files: boats, series and their results, members (name, email, role),
    requests and the change history.
  - Built with Python's own `zipfile` and `csv`.
- **Deleting a club:**
  - The operator deletes a club only after typing its subdomain to confirm.
  - Everything belonging to it goes: boats, series, races, finishes,
    requests, history and memberships.
  - People's accounts stay, since they may belong to other clubs.
  - It's refused while the club is active: suspend it first. That gives a
    pause in which to take the export.
- **Retention:** nothing is deleted automatically. The notice says data is
  kept while the club uses the service, and deleted when it leaves.

## Data model *(approved by the project owner, 2026-09-25)*

| Change | Why |
|---|---|
| New `Club`: `name`, `subdomain` (unique), `contact_email`, `status` (active/suspended), `created_at` | The tenant. |
| New `ClubMembership`: `user`, `club`, `role` (member/committee/administrator), `status` (waiting/approved/removed), `decided_by_name`, `decided_at`, `created_at`; unique per user and club | Roles per club, replacing the group and staff flags for clubs. |
| New `ClubInvitation`: `club`, `email`, `role`, `invited_by_name`, `created_at`, `accepted_at` | The operator's invitation of a first administrator, and a record of it. The link itself is a signed token, so it isn't stored. |
| New `OperatorAction`: `who`, `action`, `club_subdomain`, `detail`, `timestamp` | The operator log. It keeps the club's subdomain as text so the log survives the club being deleted. |
| `Boat.club`, `Series.club`, `BoatRequest.club`, `ScoringChange.club` (foreign keys, required once filled) | Every row belongs to a club. |
| The sail number constraint gains `club` | Unique within a club. |
| Data migrations: the first club, every existing row into it, and memberships from today's roles | Nothing existing is lost or rescored. |

The migrations use nothing database-specific. Each schema migration is
paired with its data migration, and a nullable field is made required only
once it has been filled, so each migration can run on a live database.

## Isolation *(the acceptance criterion that matters most)*
- **Two clubs with overlapping data.** The test fixture builds two clubs
  with the same sail numbers, series names and people. One person is a
  member of both, with different roles.
- **Every page, as every role, at each club.** Every URL pattern is
  requested at each club: pages, HTMX fragments, CSV downloads and admin
  pages. The response must contain none of the other club's names, sail
  numbers or email addresses.
- **Object addresses:** every URL with an object id (a series, race, boat or
  request) is tried with another club's id, and must give a 404.
- **Every write path** (the same list as slice 10's lock) is tried against
  another club's rows, and must write nothing.
- **Emails:** every email sent for one club goes only to that club's
  people, and names only that club.
- **The CSV download, the club export and a member's data download** contain
  only rows they should.
- **The source check** fails if a club-owned model is queried in
  `races/`/`results/` without `for_club`.

## Acceptance criteria
- **Parts 1 to 5**, each as described above, each with tests. Every
  existing test still passes, moved onto a default club where needed, with no
  change to what it asserts.
- **The isolation tests above pass**, including against PostgreSQL 16, run
  by hand.
- **The data migrations** move an existing single-club database, a copy of
  the manual's sample data, into the first club. Every series then scores
  exactly as before, and every person keeps their access.
- **`manage.py check --deploy`** passes with production settings, in CI.
- **With `SINGLE_CLUB` set,** the current test site works as it does today.
- **The manual:**
  - gains an administrator page, "Running your club: members and roles";
  - gains a member page, "Joining a club, and your data";
  - `docs/` gains an operator guide, `docs/operating.md`: creating a club,
    inviting its administrator, suspending, exporting and deleting;
  - existing pages are updated wherever accounts, approvals or the admin are
    mentioned, and their screenshots are regenerated.

## Deferred (later slices)
- **Production hosting.** This covers:
  - choosing the host and region;
  - paid plans;
  - the service's domain and its wildcard certificate;
  - backups and point-in-time recovery;
  - choosing the email provider;
  - moving the current test site's data over.

  This slice leaves the code ready for any of them.
- **A club's own domain**, e.g. `results.exesc.org.uk`.
- **Self-serve club sign-up and card payments** (Stripe), and pricing.
- **Club branding:** logo and colours. The design tokens (slice 7) make
  colours a small change later.
- **Time zones per club.** Every club uses Europe/London, as today.
- **A boat shared across clubs,** with one handicap history.
- **The brief's public API.**

## Out of scope
- Any change to scoring, the `nhc` engine, or how results are calculated.
- Single sign-on (Google, Microsoft) and two-factor authentication.
- Moving other clubs' data in from other software.

## Open questions *(all answered by the project owner on 2026-09-25)*
1. **Joining a club is approved, not the account.** Anyone can create an
   account, and a club's administrators approve them joining. **Yes.**
2. **A boat belongs to one club.** A boat that races at two clubs is typed
   in at each, with separate handicap histories. **Yes, for now.**
3. **The product's name and domain.** **Race Times, at `racetimes.co.uk`.**
   - The service's front page, privacy notice and terms are at
     `racetimes.co.uk`.
   - Clubs are at `<subdomain>.racetimes.co.uk`.
   - Emails come from an address at `racetimes.co.uk`.
   - `SERVICE_DOMAIN` defaults to `racetimes.co.uk` in production, and to
     `localhost` in development.
4. **The first club.** **"Demo Club", at `demo.racetimes.co.uk`.** The data
   migration's defaults are `FIRST_CLUB_NAME="Demo Club"` and
   `FIRST_CLUB_SUBDOMAIN="demo"`, and the current test site's data becomes
   Demo Club's.
5. **Legal text.** **Deferred, and recorded as an open requirement.**
   - The privacy notice and terms are built as drafts, clearly marked
     "Draft" on the page.
   - Having them reviewed, and providing clubs with a data processing
     agreement, must happen before the first paying club signs up. It's
     listed under "Open requirements" in `docs/decisions.md`.
6. **Approve the data model** above. **Approved.**
