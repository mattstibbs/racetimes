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
