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

## Day to day

- **What's waiting.** The admin's front page lists what is waiting for you:
  members' boat and entry requests for the race committee (linking to the
  Requests page), and, for the administrator, new accounts.
- **Accounts.** Members sign up on the site and wait for approval. As the
  administrator, the admin's front page tells you how many are waiting; follow
  its "Review and approve" link (or filter **Users** by "Waiting for
  approval"), tick them, and choose "Approve selected accounts".
- **Making someone race committee.** In the admin, open their account, tick
  "Staff status", and add them to the **Race committee** group. Staff status
  alone is not enough: the committee pages check the group, which is what
  gives access to the racing parts of the admin and nothing about accounts.

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
