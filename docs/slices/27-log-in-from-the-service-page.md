# Slice 27: logging in from racetimes.co.uk

**Status: draft, waiting on the project owner's answers (2026-10-03).**
Nothing is built. Numbered 27 because slice 26 (more scoring codes) is
already planned. See "Questions for the project owner" at the end.

## Goal
Someone who lands on `racetimes.co.uk` can log in there, with the same email
and password they use at their club, and get to their club's site (or any of
their clubs') without logging in again.

## What's there now
- **The service's own address** (`racetimes.co.uk`) answers only its front
  page (slice 19: the landing page and **Find my club**), the operator's pages,
  the Django admin, the privacy notice and terms, and **Change password**
  (`SERVICE_PATHS` in `races/clubs.py`). Everything else, including
  `/accounts/login/`, is a 404 there.
- **Logging in happens on a club's address**, `<club>.racetimes.co.uk/accounts/login/`
  (`member_views.LoginView`, `account_forms.LoginForm`: email and password, the
  login throttle, and the "confirm your email" message). After logging in a
  member lands on **My boats**, a club page.
- **The operator** logs in on the service's address through the Django admin
  (`/admin/login/`, `AdminLoginForm`, the same throttle).
- **Login sessions are per address, on purpose.** Slice 11 decided: "Each
  club's site keeps its own login session, which is the browser's default for
  a subdomain. Being logged in at one club doesn't log you in at another. This
  is deliberate: it keeps the clubs apart." No `SESSION_COOKIE_DOMAIN` is set.
- **One account, many clubs.** A person's memberships (approved or waiting)
  are already listed on **My account** (`/account/`, `races/account_views.py`),
  with a link to each club's address. That page is the one place another
  club's name is shown (`OWN_DATA` in `races/test_isolation.py`).
- **Password reset** is on club addresses only; its email comes from the club
  ("<Club> via Race Times", `ClubPasswordResetForm`).
- **Signing up** is on a club's address, because signing up asks to join that
  club. That stays as it is.

## What gets built

### On the service's front page
- **Log in** in the page header, beside the existing links, and a line under
  **Find my club**: "Already have an account? Log in."
- When someone is logged in, the header says **Your clubs** and **Log out**
  instead.

### The login page on `racetimes.co.uk`
- `racetimes.co.uk/accounts/login/`: the same form as a club's (email and
  password), the same throttle, and the same "confirm your email" message. The
  page says it works for every club, and that new members sign up on their
  club's site, with a link to **Find my club**.
- **Forgotten your password?** works here too. The email comes from Race Times
  itself (sender "Race Times", Reply-To `SERVICE_CONTACT_EMAIL`) rather than a
  club, through the same `notifications.email_to` route as every other email,
  so `races/test_email_sender.py` still holds.
- **The operator** can log in here too, and lands on the operator's pages. The
  admin's own login stays.

### After logging in: Your clubs
- A logged-in person lands on **Your clubs** on the service's address: each club
  they belong to, with their role, and a **Go to <club>** button; a membership
  still waiting says so (and that the club's administrators decide); a
  suspended club is listed without the button. Someone with no memberships is
  told so, with **Find my club**.
- This is My account's list of clubs, so the page reuses it. **My account**,
  **Download my data** and **Delete my account** also work on the service's
  address (they already act across every club), linked from Your clubs.
- **One approved club only:** see question 2.

### Getting into the club without logging in again
The heart of the slice, and the main question (question 1). Two ways:

- **A. A one-time hand-off (recommended).** **Go to <club>** sends the person
  to the club's address with a signed, single-use link valid for a minute. The
  club's site checks it, logs them in there, and goes straight on to **My
  boats** (so the link never stays in the address bar). Each address still has
  its own session, as slice 11 decided: logging out of one club doesn't log
  you out of another, and nothing about one club's session is readable at
  another.
  - Signed with Django's signing (salt specific to this use), naming the
    person and the club; refused for another club, after a minute, or a
    second time (a used link is remembered in the database cache that the
    login throttle already uses).
  - Only for an active account, and only for a club the person has a
    membership of. A refused link goes to the club's normal login page, which
    says the link had expired.
  - Recorded in the logs by user id and club, never by name or email.
- **B. One login for every address.** Set the session cookie's domain to
  `.racetimes.co.uk`, so logging in anywhere logs you in everywhere. Much less
  code, but it reverses slice 11's decision, logs out everyone once when it's
  deployed, and logging out logs you out of every club. Local development
  (`localhost`) and the Render test site keep per-address sessions, because
  browsers won't share a cookie there.

### Logging out
- **Log out** on the service's address logs out of the service's address.
  Under A, each club's site keeps its own session (as now); under B, it logs
  out everywhere.

## Data model
None. No migration. (A's used links live in the existing database cache.)

## Security and privacy
- No new cookies: still only `sessionid` and `csrftoken` (`races/test_legal.py`).
- `next` after logging in on the service's address only ever goes to a page on
  the service's address; Go to <club> only to that club's address.
- The service's address shows a person their own clubs only, as My account
  does today. Nothing about any club is shown to someone not logged in beyond
  what Find my club shows now.
- Under A, the hand-off link is in a URL for a moment: one minute, single use,
  and the club's site redirects away from it at once.

## Tests
- Logging in on the service's address: right and wrong password, the
  throttle, an unconfirmed email, an inactive account, the operator.
- Your clubs: approved, waiting, suspended, none; the role shown; only the
  person's own clubs (an isolation test).
- Under A: a hand-off logs in at the right club only; refused when expired,
  reused, for another club, for a club with no membership, for an inactive
  account, or tampered with; the link doesn't survive in the address; a club's
  session is untouched by logging out of another address.
- Under B: the cookie's domain in production settings (`races/test_production.py`),
  and that local and test-site settings don't share.
- Forgotten password on the service's address: sent as Race Times, from the
  usual sender, and the link works.
- `races/test_isolation.py` and `races/test_roles.py` cover the new paths.

## User manual
- **Logging in** (getting started): logging in at racetimes.co.uk, Your clubs,
  going to a club, and that signing up is still on your club's site. New
  screenshots: the front page header, the login page, Your clubs.
- **Forgotten password** and **Changing your password**: mention the service's
  address.

## Out of scope
- Signing up on the service's address (you sign up by asking to join a club).
- Logging out of every club at once (under A).
- "Remember me", social logins, two-factor authentication.
- A club on its own domain rather than a subdomain.

## Questions for the project owner
1. **Getting into the club: A (hand-off, recommended) or B (one login
   everywhere)?** A keeps slice 11's "logging in is per club address"; B
   reverses it for simplicity.
2. **One approved club only: go straight there after logging in, or always
   show Your clubs?** Recommended: straight there, since most people belong to
   one club; Your clubs is still in the header.
3. **My account on the service's address:** open My account, Download my data
   and Delete my account there too (recommended, they already work across
   clubs), or only Your clubs and Change password?
4. **Wording:** "Log in" in the front page header, and "Your clubs" for the
   page after. Fine?
