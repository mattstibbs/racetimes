# Slice 28: signing up from racetimes.co.uk, starting with your club

**Status: draft, waiting on the project owner's answers (2026-10-03).**
Nothing is built. Builds on slice 27 (logging in from racetimes.co.uk, one
login for every club). See "Questions for the project owner" at the end.

## Goal
Someone new who arrives at `racetimes.co.uk` can sign up from there. Because
an account always starts by asking to join a club, the first step is "find
the club you want to join"; the second is their details.

## What's there now
- **Signing up is only on a club's address** (`<club>.racetimes.co.uk/accounts/signup/`,
  `member_views.signup`): name, email, password. It creates the account and a
  waiting membership of that club, and emails a link to confirm the email
  address. Once confirmed, the club's administrators approve them joining.
- **The sign-up page doesn't name the club.** It says "the club's
  administrator approves you joining" without saying which club.
- **Find my club** on the service's front page (slice 19) searches active clubs
  by name or address over HTMX; each match links to the club's results. "No
  club called ... uses Race Times yet" points to **Get Race Times for your
  club**.
- **After slice 27**, the service's header has **Log in**, and its login page
  says "No account yet? Find your club and sign up there."

## The journey

```
racetimes.co.uk ── Sign up ──▶ Step 1: Find your club ──▶ Step 2: Your details ──▶ Check your email
                                (racetimes.co.uk/signup/)   (<club>.racetimes.co.uk/   (as now)
                                                             accounts/signup/)
```

### Ways in
- **Sign up** in the service's header, beside **Log in**.
- The service's login page: "No account yet? **Sign up**" (replacing "Find
  your club and sign up there").
- The front page's hero: a **Sign up** link beside **Find my club** (question 3).

### Step 1: find the club you want to join (`racetimes.co.uk/signup/`)
- Heading "Sign up", a step marker "Step 1 of 2: find your club", and one line:
  "Your account starts with the club you sail at. You can join other clubs
  later with the same account."
- The same search as Find my club (`service_views.find_clubs`: active clubs,
  name or address, at most ten), answered over HTMX as you type and as a
  plain form without JavaScript.
- Each match: the club's name and address, and a **Sign up at <Club>** button.
- No match: "No club called ... uses Race Times yet. Check the name with your
  club, or tell them about Race Times", linking to **Get Race Times for your
  club** on the front page.
- "Already have an account? **Log in**."

### Step 2: your details (the club's own sign-up page)
- **Sign up at <Club>** goes to that club's sign-up page,
  `<club>.racetimes.co.uk/accounts/signup/`, the form that exists now.
- The page now names the club: "Sign up to **Harbour Sailing Club**", and
  "Harbour Sailing Club's administrators approve you joining." (On a club's
  site this helps everyone, however they arrived.)
- Arriving from step 1, it shows "Step 2 of 2: your details" and a "Not your
  club? **Choose another**" link back to step 1. Arriving any other way, it
  looks as it does now, apart from naming the club.
- Submitting is unchanged: the account, a waiting membership, and the
  confirmation email, which already names the club.

### Someone already logged in
- **Sign up** isn't shown to them. Instead, **Your clubs** (slice 27) gets
  "**Join another club**", which is step 1 with "Join <Club>" buttons. Choosing
  a club goes to its site, where they're already logged in (slice 27) and its
  existing **Join this club** asks to join. (Question 2.)

## What doesn't change
- An account still can't exist without asking to join a club, and joining
  still needs the club's administrators to approve.
- The email confirmation, the waiting page and the administrators' decision.
- Find my club on the front page, whose matches still go to each club's
  results (question 3).

## Data model
None. No migration.

## Security and privacy
- Step 1 shows only what Find my club already shows: active clubs' names and
  addresses. Suspended clubs aren't listed.
- The "came from step 1" marker is a plain query parameter (`?from=find`)
  that only changes wording; it carries nothing about the person.
- The form, terms and privacy wording, throttles and confirmation are the
  existing ones.

## Tests
- Step 1: the page and its search, with and without HTMX; only active clubs;
  "no club" wording; the button links to that club's sign-up page with the
  marker; on a club's address it isn't there (404).
- Step 2: names the club; shows the step and **Choose another** only with
  the marker; signing up still creates a waiting membership of that club.
- The header: **Sign up** for the public on the service's address, not when
  logged in; the login page's link.
- Logged in: Join another club lists clubs and links to each club's site.
- `races/test_isolation.py` and `races/test_roles.py` cover the new path.

## User manual
- **Joining a club** (getting started): signing up from racetimes.co.uk,
  step by step, with screenshots of step 1 (with a search) and step 2;
  signing up from your club's site still works as before.

## Out of scope
- Signing up without choosing a club.
- Asking to join several clubs at once.
- Inviting yourself to a club that isn't on Race Times (that stays the
  **Get Race Times for your club** email).

## Questions for the project owner
1. **Step 2 on the club's own sign-up page (recommended), or on
   racetimes.co.uk?** The club's page reuses the existing form, shows the
   club's name in the header so people can see they picked the right one,
   and sends the confirmation from that club, as now. Keeping it on
   racetimes.co.uk would keep people on one site but means a second sign-up
   form that has to carry the chosen club.
2. **Logged in: "Join another club" on Your clubs, using the same search
   (recommended)?**
3. **The front page:** add a **Sign up** link in the hero beside **Find my
   club** (recommended), and leave Find my club's matches going to each
   club's results? Or should each match there also offer **Sign up**?
4. **Wording:** "Sign up", "Step 1 of 2: find your club", "Sign up at
   <Club>", "Step 2 of 2: your details", "Not your club? Choose another".
   Fine?
