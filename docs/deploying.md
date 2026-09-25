# Deploying the test site to Render

The repository describes its own hosting in `render.yaml` (a Render
"Blueprint"): one web service and one PostgreSQL database. Once it is set up,
every push to `main` - in practice, every merged pull request - redeploys the
site within a few minutes. Database migrations apply as part of each deploy.

## One-time setup

1. Create an account at [render.com](https://render.com) and connect your
   GitHub account when asked, giving Render access to the `racetimes`
   repository.
2. In the Render dashboard choose **New > Blueprint**, pick the `racetimes`
   repository, and leave the branch as `main`.
3. Render reads `render.yaml` and lists what it will create: a web service
   called `racetimes` and a database called `racetimes-db`. It asks for two
   values:
   - `DJANGO_SUPERUSER_USERNAME` - the staff login you want, e.g. `matt`.
   - `DJANGO_SUPERUSER_PASSWORD` - its password. It must pass Django's usual
     rules (not too short, not too common); if it does not, the first deploy
     fails and its log says why.
4. Apply the Blueprint. The first deploy takes a few minutes. Its log is under
   the `racetimes` service, **Events** / **Logs**.
5. The site's address is shown at the top of the service page, something like
   `https://racetimes-xxxx.onrender.com`. Log in at `/admin/` with the
   username and password from step 3, and set up boats and a series.

Render's dashboard changes from time to time; if a label above does not match,
the same steps are in Render's own guide to deploying Django.

## Clubs (slice 11)

Race Times now holds clubs: each club's data is kept apart, and each club has
its own address, `<subdomain>.<SERVICE_DOMAIN>`. The migrations put all the
existing data into the first club, **Demo Club** (subdomain `demo`, from
`FIRST_CLUB_NAME` and `FIRST_CLUB_SUBDOMAIN`).

- **The test site** on Render can't have subdomains: its address is fixed,
  e.g. `racetimes-xxxx.onrender.com`. `render.yaml` sets `SINGLE_CLUB=demo`,
  so that address shows Demo Club, exactly as the site did before. Without it,
  the address would show the service's own front page.
- **Locally**, open `http://demo.localhost:8000/`: every current browser
  sends `*.localhost` to your own machine with no setup.
  `http://127.0.0.1:8000/` shows Demo Club too, if you set `SINGLE_CLUB=demo`.
- **More clubs:** as the operator, add a club in the admin under **Clubs**,
  on the service's own address. Part 3 of slice 11 will add proper operator
  pages, including inviting a club's first administrator. Until then, give
  that person a membership in the admin by hand.
- **Production hosting** needs a wildcard DNS record and certificate for
  `*.racetimes.co.uk`. That's a later slice.

## Day to day

- **What's waiting.** At a club, the admin's front page lists what is
  waiting for you. For the race committee, that's members' boat and entry
  requests (linking to the Requests page); for club administrators, it's also
  people waiting to join (linking to the Members page).
- **People and roles** (slice 11). Anyone signs up at a club's address and
  confirms their email; a club administrator then approves them on the
  club's **Members** page, choosing their role (member, race committee or
  club administrator). Roles are per club. The Django admin no longer
  approves accounts, and staff status and the old "Race committee" group
  mean nothing.
- **The operator.** The superuser that `build.sh` creates is the service's
  operator. It has no role at a club unless it has a membership there. The
  migration gave the existing superuser Demo Club's administrator membership,
  so on the test site it still runs Demo Club. On the service's own address,
  `/admin/` is the operator's: clubs and accounts.

- **To update the site,** merge a pull request into `main`. Render builds and
  deploys it; if the build fails, the previous version stays live.
- **To see why something failed,** open the service's **Logs** in Render.
  Errors are printed there, including any page that failed to load.
- **The staff login** is created on the first deploy only. Change its password
  in the admin as usual; later deploys never touch an existing account.
- **The data** on the hosted site is separate from your laptop's. Nothing is
  copied either way.

## Sending email

The site emails results, account approvals, request decisions, boat changes
and password resets (slice 4). Until email is set up, it prints them to the
service's **Logs** instead of sending them, so nothing breaks, but nobody
receives anything.

To send real email, choose a provider and set these on the `racetimes`
service, under **Environment**:

| Variable | What it is |
|---|---|
| `EMAIL_HOST` | The provider's SMTP server, e.g. `smtp.example.com`. Setting this is what switches sending on. |
| `EMAIL_PORT` | Usually `587`. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | The login the provider gives you for SMTP. |
| `EMAIL_USE_TLS` | `1` (the default) for port 587. |
| `DEFAULT_FROM_EMAIL` | Who the emails come from, e.g. `Race Times <results@yourclub.org>`. It must be an address or domain the provider lets you send from. |

Before choosing, check two things:

- **Whether Render lets your plan send over SMTP.** Some hosts block outgoing
  SMTP on free plans to stop spam. If yours does, choose a provider that
  offers SMTP on a port Render allows, or ask to have an HTTP-API email
  library added (a new dependency).
- **The provider's free allowance.** A club series emails every owner after
  each race, so 30 boats and 20 races is about 600 emails a season, plus
  updates and account emails.

After saving the variables, Render redeploys. To test, use **Forgotten your
password?** on the login page with your own account's email address.

## Things to know about the free plans

Free tiers change, so check Render's pricing page. When this was written:

- A free web service goes to sleep after a while with no visitors, so the
  first page after that can take up to a minute to load.
- A free database is deleted after a set period unless upgraded. For a test
  site that may be fine; for anything you want to keep, use a paid database
  plan.

## What the deploy runs

`build.sh`, on every deploy: install the requirements, `collectstatic`,
`migrate`, then `ensure_superuser`. The site then runs under `gunicorn`.

The settings switch to production behaviour when `DJANGO_DEBUG` is `0`, which
`render.yaml` sets: static files are served by WhiteNoise, cookies are
HTTPS-only, and the site refuses to start without a `DJANGO_SECRET_KEY`
(Render generates one). Render also provides `RENDER_EXTERNAL_HOSTNAME`, which
the settings use to allow the site's own address.
