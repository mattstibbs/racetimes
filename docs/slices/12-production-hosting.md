# Slice 12: production hosting

**Status: planning. The questions at the end need the project owner's answers
before building starts.**

## Goal
Slice 11 made Race Times a service for many clubs, and kept the code
independent of any host. This slice puts it live at `racetimes.co.uk`, ready
for a first club:
- every club at `<subdomain>.racetimes.co.uk`, over HTTPS;
- a database with backups that have been restored at least once;
- email that reaches inboxes;
- errors and downtime noticed quickly.

Most of this slice is setting up accounts and services, which only the
project owner can do: signing up, paying, and changing DNS. The code's part
is small: the deploy configuration, a few settings, and one redirect. The
rest is written instructions (runbooks) and checks that prove each piece
works, so every step can be followed and repeated.

## What's there already
- **The code is ready for production** (slice 11 part 4): HTTPS only with
  HSTS, `/health/`, Sentry when `SENTRY_DSN` is set, logs that name the club
  and no one else, and a failed-login lock. The club comes from the host
  name, under `SERVICE_DOMAIN`, which defaults to `racetimes.co.uk` when
  `DJANGO_DEBUG=0`.
- **The test site** runs on Render's free plan from `render.yaml`:
  - one web service and one database;
  - `SINGLE_CLUB=demo`, since its `onrender.com` address can't have club
    subdomains;
  - `build.sh` runs `migrate` during the build.
- **It names no region, so it runs in Render's default, Oregon (US).** Any
  personal data on it today is held in the US.
- **Email** is SMTP through the `EMAIL_*` settings. Every club's email is
  sent from `DEFAULT_FROM_EMAIL` under the club's name (slice 11 part 4).
  `docs/deploying.md` has the provider checklist: SPF, DKIM, DMARC and the
  allowance.
- **What hosting must provide** (from the spec for slice 11):
  - a wildcard DNS record and certificate for `*.racetimes.co.uk`;
  - backups and point-in-time recovery;
  - an email provider;
  - moving the test site's data over.

## The choices *(for the project owner; recommendations marked)*

### Where it runs
Checked on 2026-09-25; plans and prices change, so re-check at sign-up.

| | Render, Frankfurt **(recommended)** | Fly.io, London | DigitalOcean App Platform |
|---|---|---|---|
| **Data held in** | Germany (EU) | UK | Region to check (London for databases; the app region to confirm) |
| **Wildcard domain and certificate** | Yes, automatic, renewed by Render | Yes, $1/month | Yes, with a DNS verification record |
| **Managed PostgreSQL** | Yes, with point-in-time recovery on paid plans: 3 days on the Hobby workspace, 7 on Pro | Yes (Managed Postgres, available in London) | Yes |
| **Work to move** | Least: `render.yaml` already describes the site | A `Dockerfile` and `fly.toml`, and new tools to learn | An app spec, and new tools to learn |

**Recommendation: Render, in Frankfurt.**
- The deploy set-up already exists, and you already use Render.
- Frankfurt keeps personal data in the EU, which UK GDPR allows without
  extra paperwork: the UK recognises the EU's data protection as adequate.
- Render renews the wildcard certificate by itself.
- The one thing it lacks is a UK region. If the clubs, or their data
  processing agreement, will need data held in the UK, Fly.io London is the
  choice instead.

### Email
One provider sends for every club, over SMTP, so there's no new dependency.
The options, all with SPF, DKIM and DMARC support:
- **Postmark:** the simplest set-up and strong inbox delivery. It's a US
  company, so check its terms for transfers from the UK.
- **Amazon SES, London region:** the cheapest, with data in the UK. But the
  set-up is more involved: AWS access keys, and a request to leave the
  "sandbox" before it sends to anyone.
- **Brevo:** an EU company, with a free daily allowance.

**Recommendation: Postmark,** for the least set-up and the best chance that
results emails land in inboxes rather than spam. About 600 emails per club
per season (slice 4's estimate) fits a small plan.

### Two sites: test and production
- **The test site stays as it is:** free, with sample data, on
  `onrender.com`, and it still redeploys on every merge to `main`. New work
  is checked there first.
- **Production is new:** its own web service and database on paid plans, at
  `racetimes.co.uk`, with no `SINGLE_CLUB`.
- **Recommendation: production deploys only when you press Deploy** in
  Render. Auto-deploy is off, and a merge to `main` reaches the test site
  first, so nothing reaches clubs by accident.

## What gets built

1. **`render.yaml` gains production** (if Render is chosen):
   - a second web service, `racetimes-production`, and database,
     `racetimes-production-db`, both in `frankfurt` on paid plans;
   - auto-deploy off;
   - environment:
     - `DJANGO_DEBUG=0` and `TRUSTED_PROXIES=1`;
     - `SECURE_HSTS_SECONDS`, starting at an hour;
     - `SERVICE_DOMAIN` is left at its default, `racetimes.co.uk`;
     - `SENTRY_DSN`, the `EMAIL_*` settings and `DEFAULT_FROM_EMAIL` are
       entered in the dashboard (`sync: false`), so no secret is in the
       repository;
   - the test site is unchanged, and still free.
2. **Database changes run before the new version starts,** not during the
   build.
   - Production uses Render's pre-deploy step for `migrate` and
     `createcachetable`.
   - If a migration fails, the deploy stops and the old version keeps
     running.
   - `build.sh` keeps doing it for the free test site, which has no
     pre-deploy step.
3. **`www.racetimes.co.uk` redirects to `racetimes.co.uk`.** Today it would
   show "no club here", since `www` is a reserved name, never a club's.
   Tested.
4. **The operator's first login:**
   - `ensure_superuser` makes it on the first deploy, as on the test site,
     from two dashboard settings;
   - the runbook says to remove them afterwards.
5. **Checks before launch**, run against the live site, so each piece is
   proved rather than assumed:
   - `manage.py check --deploy` passes in the production environment;
   - `/health/` answers on `racetimes.co.uk` and on a club's subdomain, over
     HTTPS, with a valid certificate;
   - plain HTTP redirects to HTTPS, and the HSTS header is there;
   - a test email (Django's own `sendtestemail`) arrives, with SPF, DKIM and
     DMARC all "pass" in its headers;
   - a deliberate test error reaches Sentry, tagged with the club;
   - the uptime monitor alerts when `/health/` fails.
6. **Backups, and a restore that has been done:**
   - Render's point-in-time recovery covers mistakes and corruption (see
     question 4 for off-site copies);
   - the runbook has the restore steps, and they're rehearsed once before
     launch: restore to a new database, point a copy of the site at it,
     and check that a series scores as before.
7. **The runbook, `docs/production.md`**, which `docs/deploying.md` links
   to:
   - one-time set-up, in order:
     1. DNS for the apex, `www` and `*`, and certificate verification;
     2. the email provider's domain records;
     3. Sentry and the uptime monitor;
     4. the operator's first login;
     5. the first club;
   - deploying, and rolling back;
   - restoring from backup;
   - raising HSTS once settled;
   - the monthly costs;
   - what to do when an alert fires.
8. **The privacy notice names the processors**: the host and its region, the
   email provider, and Sentry. This fills one of its placeholders. The
   operator's legal name and address stay for the legal review.

## Acceptance criteria
- `racetimes.co.uk` and `demo.racetimes.co.uk` answer over HTTPS with valid
  certificates, and any other club subdomain gets a certificate
  automatically.
- A merge to `main` updates the test site and not production. Production
  updates when deployed on purpose, and a failed migration leaves the old
  version running.
- Every check in "Checks before launch" passes, and is recorded in
  `docs/production.md` with the date.
- A restore from backup has been done once, and the restored copy scores
  the same.
- The test suite and CI are unchanged apart from the new redirect's tests.
  The code still runs on any host.

## Out of scope
- A club's own domain (e.g. `results.exesc.org.uk`), self-serve sign-up and
  payments, and club branding. These are still later slices.
- Scaling beyond one web service. It's enough for many clubs; the runbook
  says how to add a second when needed.
- The legal review, which is already an open requirement.

## Questions for the project owner
1. **Host and region.** Render in Frankfurt (recommended), or Fly.io in
   London if data must stay in the UK?
2. **Email provider.** Postmark (recommended), Amazon SES in London, or
   Brevo?
3. **Deploying production.** Only when you press Deploy (recommended), or
   automatically on every merge to `main`, like the test site?
4. **Off-site backups.** Render's point-in-time recovery lives in the same
   Render account. A nightly copy to separate storage (e.g. Backblaze B2 or
   Amazon S3) also protects against losing the account or the region. It
   would run as a Render cron job, using the storage provider's own
   command-line tool, not a Python dependency. **Recommendation:** yes,
   once, before the first paying club. Now, or later?
5. **The test site's data.** Does it hold a real club's results that should
   move to production, or is it sample data, so that production starts
   empty with a fresh Demo Club?
6. **The domain.** Is `racetimes.co.uk` registered, and where is its DNS
   managed? The wildcard needs records you add there.
7. **The test site's region.** It's in Oregon (US) today, by default. Move it
   to Frankfurt too? That means making a new database and copying the data,
   because a Render database can't change region.
