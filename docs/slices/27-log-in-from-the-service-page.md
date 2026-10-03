# Slice 27: logging in from racetimes.co.uk

**Status: ready to build (2026-10-03).** The project owner chose one shared
login (option B) and agreed the other recommendations; see "The project
owner's answers" at the end. Numbered 27 because slice 26 (more scoring codes)
is already planned.

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
  itself (`DEFAULT_FROM_EMAIL`, as `notifications.sender` already does with no
  club) rather than a club, so `races/test_email_sender.py` still holds.
- **Send the confirmation link again** (offered on the login page to someone
  whose email isn't confirmed yet) works here too: the email names, and links
  to, the club they signed up at.
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

### One login for every address *(the project owner's decision, 2026-10-03)*
Logging in anywhere on `racetimes.co.uk` logs you in at every club's address,
and logging out anywhere logs you out everywhere. This reverses slice 11's
"logging in is per club address" (recorded in `docs/decisions.md`).

- **The session cookie's domain** is `.racetimes.co.uk` in production only, set
  by a `SESSION_COOKIE_DOMAIN` environment variable in the production
  Blueprint. Locally (`localhost`) and on the Render test site (an onrender.com
  address, Demo Club only) it stays unset, since a browser won't share a cookie
  there.
- **The cookie is renamed** (`racetimes_session`), so old per-address cookies
  can't linger beside the new shared one and keep someone logged in after they
  log out. Everyone is logged out once when this is deployed. The privacy
  notice names the new cookie.
- **Roles are unchanged:** they still belong to a membership of one club, so
  being logged in at a club where you have no membership shows nothing more
  than the public sees (`races/test_roles.py`).
- **The CSRF cookie stays per address.** Only the session is shared.
- **Every `*.racetimes.co.uk` address must stay Race Times'.** Anything else on
  a subdomain would receive the login cookie; `docs/production.md` says so.

### Logging out
- **Log out** on any address logs out everywhere and goes to that address's
  front page.

## Data model
None. No migration.

## Security and privacy
- No new cookies: still only `sessionid` and `csrftoken` (`races/test_legal.py`).
- `next` after logging in on the service's address only ever goes to a page on
  the service's address.
- The service's address shows a person their own clubs only, as My account
  does today. Nothing about any club is shown to someone not logged in beyond
  what Find my club shows now.

## Tests
- Logging in on the service's address: right and wrong password, the
  throttle, an unconfirmed email, an inactive account, the operator.
- Your clubs: approved, waiting, suspended, none; the role shown; only the
  person's own clubs (an isolation test).
- The cookie's domain is in the production Blueprint and nowhere else
  (`races/test_production.py`), and the session cookie's name.
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
- "Remember me", social logins, two-factor authentication.
- A club on its own domain rather than a subdomain.

## The project owner's answers *(2026-10-03)*
1. **One login for every address (option B),** not a one-time hand-off. The
   owner accepted that a forgotten logout on a shared computer reaches every
   club the person belongs to, and that every `*.racetimes.co.uk` address must
   stay Race Times'.
2. **One approved club only: straight there** after logging in, to its My boats.
   Your clubs is still in the header.
3. **My account, Download my data and Delete my account** work on the
   service's address too.
4. **"Log in"** in the front page header, and **"Your clubs"** for the page
   after.
