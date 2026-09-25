# Running Race Times in production

Production is `racetimes.co.uk`, with every club at `<subdomain>.racetimes.co.uk`.
It runs on Render in Frankfurt, beside the free test site (see
`docs/deploying.md`), and is described by the same `render.yaml`. This is the
runbook: setting it up once, deploying, backups and restoring, and what to do
when an alert fires. The operator's day-to-day work (clubs, invitations) is in
`docs/operating.md`.

Services' screens and prices change. Where a step here doesn't match what you
see, the service's own help has the current steps; the *what* and *why* here
still hold.

## What it's made of

| Part | Where | What for |
|---|---|---|
| `racetimes-production` | Render web service, Frankfurt | The site. Deploys only when **Deploy** is pressed. |
| `racetimes-production-db` | Render PostgreSQL 16, Frankfurt | The data. Render keeps point-in-time recovery for it. |
| `racetimes-backup` | Render cron job, nightly at 02:17 UTC | An encrypted copy of the database, off-site. |
| Gandi | DNS for `racetimes.co.uk` | Sends the domain and every subdomain to Render; email records. |
| Postmark | Email | Sends every club's email from `noreply@racetimes.co.uk`. |
| Backblaze B2 | Storage, EU | Holds the nightly copies, encrypted. |
| Sentry | Error reports, EU | Tells you when a page fails. |
| UptimeRobot | Uptime checks | Tells you when the site stops answering. |

**Rough monthly cost** (check each service's pricing page; these were right
when written): Render web service (Starter) about $7, database (Basic 256 MB)
about $6, and the cron job a few cents; Postmark from about $15 once past its
free trial allowance; Backblaze pennies; Sentry and UptimeRobot free at this
size. Render's point-in-time recovery window is 3 days on the Hobby workspace,
or 7 on Pro (about $25 a month more).

## Setting it up, once

Do these in order. Keep every password, key and passphrase in your password
manager as you go.

### 1. Create the services on Render
1. In Render, open the Blueprint for this repository and **sync** it. It
   lists what it will add: `racetimes-production`, `racetimes-production-db`
   and `racetimes-backup`, all in Frankfurt. Check the plans it shows; if Render
   has renamed a plan, change it in `render.yaml` (by pull request) and sync
   again.
2. Render asks for the values marked `sync: false`. Fill in what you have
   now and come back for the rest as later steps give them to you:
   - `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD`: the
     operator's login (a strong, new password);
   - `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`: step 3;
   - `SENTRY_DSN`: step 4;
   - the backup's six values: step 5.

   Nothing deploys to production by itself, so there's no rush.

### 2. The domain, at Gandi
1. On `racetimes-production` in Render, under **Settings → Custom Domains**,
   add three: `racetimes.co.uk`, `www.racetimes.co.uk` and
   `*.racetimes.co.uk`. Render shows the DNS record each one needs, including
   an `_acme-challenge` record, which lets it get the wildcard certificate.
2. In Gandi, open the domain's **DNS Records** (LiveDNS):
   - **Remove Gandi's default records** for `@`, `www` and `*` if there are
     any (new domains often point at Gandi's parking page).
   - Add what Render showed. Typically:
     - `@`: an `ALIAS` record to `racetimes-production.onrender.com` (Gandi
       supports ALIAS at the top of a domain), or the `A` record Render gives;
     - `www`: `CNAME` to `racetimes-production.onrender.com.`;
     - `*`: `CNAME` to `racetimes-production.onrender.com.`;
     - `_acme-challenge`: the `CNAME` Render gives.
   - If there are any `CAA` records, add ones allowing `letsencrypt.org` and
     `pki.goog`, which Render's certificates come from.
   - A short TTL (300 seconds) while setting up makes mistakes quick to fix.
3. Back in Render, **Verify** each domain. When all three say the certificate
   is issued, the addresses work over HTTPS.

### 3. Email, with Postmark
1. Create a Postmark account and a **Server** called "Race Times". Its default
   *transactional* stream is the right one.
2. Under **Sender Signatures → Domains**, add `racetimes.co.uk`. Postmark
   shows a **DKIM** record (TXT) and a **Return-Path** record (a CNAME, usually
   `pm-bounces` to `pm.mtasv.net`). Add both at Gandi, then **Verify** in
   Postmark.
3. Add a **DMARC** record at Gandi: TXT at `_dmarc`, value
   `v=DMARC1; p=none; rua=mailto:<your address>`. Once the weekly reports
   show only Postmark sending, change `p=none` to `p=quarantine`.
4. New Postmark accounts are reviewed before they can send to anyone outside
   your own domain. Ask for approval from the account page, saying it's a
   results service for sailing clubs sending transactional email only.
5. In Render, set both `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` to the
   server's **API token** (Postmark's SMTP uses it as both). `EMAIL_HOST`,
   `EMAIL_PORT` and `DEFAULT_FROM_EMAIL` are already set by `render.yaml`.

### 4. Error reports, with Sentry
Create a Sentry account, choosing the **EU** data region when asked (it can't
be changed later), and a project for Django. Copy its **DSN** into
`SENTRY_DSN` in Render. Reports carry no names, email addresses or form
contents (`races/logs.py`).

### 5. Off-site backups, with Backblaze B2
1. Create a Backblaze account, choosing the **EU Central** region (the region
   is fixed per account).
2. Create a **private** bucket, e.g. `racetimes-backups-` plus a few random
   letters.
3. Give it a **lifecycle rule** so old copies go: keep each file 30 days, then
   delete it (in B2's terms: hide after 30 days, delete 1 day after hiding).
4. Create an **application key** that can read and write only that bucket.
5. In Render, on `racetimes-backup`, set:

   | Variable | Value |
   |---|---|
   | `BACKUP_BUCKET` | the bucket's name |
   | `BACKUP_ENDPOINT_URL` | the bucket's S3 endpoint, with `https://`, e.g. `https://s3.eu-central-003.backblazeb2.com` |
   | `AWS_DEFAULT_REGION` | the region part of that endpoint, e.g. `eu-central-003` |
   | `AWS_ACCESS_KEY_ID` | the key's **keyID** |
   | `AWS_SECRET_ACCESS_KEY` | the key's **applicationKey** |
   | `BACKUP_PASSPHRASE` | a long passphrase from your password manager |

   **Keep the passphrase in your password manager.** The copies are encrypted
   with it, and without it they can't be read by anyone, you included.

### 6. Uptime checks and alerts
- In UptimeRobot, add two **HTTP(s) – Keyword** monitors, every 5 minutes,
  alerting you by email: `https://racetimes.co.uk/health/` and
  `https://demo.racetimes.co.uk/health/`, each looking for the word `ok`.
- In Render, under **Workspace Settings → Notifications**, have failed
  deploys and failed cron jobs emailed to you.

### 7. The first deploy
1. On `racetimes-production`, choose **Manual Deploy → Deploy latest commit**.
   The pre-deploy step (`release.sh`) creates the tables, the cache table,
   Demo Club (empty) and the operator's login. Its log is on the deploy's page.
2. Once it's live, **delete `DJANGO_SUPERUSER_PASSWORD`** (and the username)
   from the service's environment. The account stays; the password shouldn't
   sit in the dashboard.

### 8. Check it, and record the results
Run each check and fill in the table below. A failure is fixed before the
first club is invited.

1. **From your computer:** `python scripts/check_live.py`. It checks HTTPS and
   certificates on the service's address, Demo Club's and a made-up club
   address; HTTP and `www` redirects; the security headers; and `/health/`.
2. **In the service's Shell** (Render dashboard, `racetimes-production`,
   **Shell**):
   - `python manage.py check --deploy`: no issues, one silenced;
   - `python manage.py sendtestemail <your address>`: it arrives. In your mail
     program, show the original message: SPF, DKIM and DMARC all say `pass`;
   - `python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('Race Times production test')"`:
     it appears in Sentry within a minute. (That each report is tagged with the
     club is proved by the tests, `races/test_logs.py`.)
3. **Uptime:** pause the site (`racetimes-production` → **Suspend**) for ten
   minutes and check the alert arrives; resume it.
4. **Backup:** on `racetimes-backup`, **Trigger Run**. A file appears in the
   bucket, and the run's log says `Backed up racetimes-... (N bytes)`.
5. **Restore**, below, once, into a spare database.

| Date | Check | Result |
|---|---|---|
| | `check_live.py` | |
| | `check --deploy` | |
| | Test email: SPF, DKIM, DMARC | |
| | Sentry test message | |
| | Uptime alert | |
| | Nightly backup ran | |
| | Restore rehearsed; `series_summary` identical | |

### 9. The first club
**Before the first paying club: the legal review must be done.** That means:
- the privacy notice and terms reviewed, with their placeholders filled in
  (the operator's legal name and address, the limits of liability) and the
  "Draft" banners removed;
- a data processing agreement ready for clubs to sign;
- each provider's data processing agreement signed.

The full list is in `docs/slices/12-production-hosting.md`, and it's an
open requirement in `docs/decisions.md`. A trial with your own club, or one
that knows the pages are drafts, can go ahead before that.

Log in at `https://racetimes.co.uk/admin/login/` as the operator, then follow
`docs/operating.md`: create the club, invite its administrator.

## Deploying a change
1. Merge the pull request. The test site redeploys by itself.
2. Check the change on the test site.
3. On `racetimes-production`: **Manual Deploy → Deploy latest commit**.
   Database changes run first; if they fail, the deploy stops and the old
   version keeps running. Render then waits for `/health/` before switching.
4. Run `python scripts/check_live.py`.

**Rolling back:** on the service's **Events** page, choose an earlier deploy
and **Rollback**. That brings back the old code, not an old database: a
migration isn't undone. Race Times' migrations only add, so the old code
still runs against the newer database; if a migration ever removes or renames
something, its pull request says so and how to roll back.

## Backups and restoring
Two kinds, for different disasters:
- **Point-in-time recovery (Render):** any moment in the last 3 days (7 on
  Pro). For a mistake or a bad deploy. On `racetimes-production-db`,
  **Recovery → restore**, which makes a **new** database at that moment.
- **The nightly off-site copy (B2):** 30 days of copies, outside Render. For
  losing the Render account or region.

**To restore an off-site copy** (and to rehearse it, before launch and then
once a year):
1. Make a new, empty PostgreSQL 16 database. For a rehearsal, a free Render
   database will do; delete it afterwards.
2. Download the copy from the B2 bucket.
3. On your computer (it needs PostgreSQL 16's client tools and `gpg`):

   ```bash
   BACKUP_PASSPHRASE='...' backup/restore.sh racetimes-<date>.dump.gpg '<new database external URL>'
   ```
4. Compare it with production, using the same code:

   ```bash
   DATABASE_URL='<new database external URL>' .venv/bin/python manage.py series_summary > restored.txt
   ```
   and `python manage.py series_summary` in production's Shell. The lines
   should be identical.
5. For a real restore, point `racetimes-production` at the new database: in
   `render.yaml`, change `racetimes-production`'s `DATABASE_URL` to the new
   database by pull request, or set `DATABASE_URL` directly on the service
   and bring `render.yaml` in line afterwards. Then deploy.

## Raising HSTS
`SECURE_HSTS_SECONDS` starts at an hour, so a mistake with HTTPS can't lock
browsers out for long. After a month without problems, raise it to a year
(`31536000`) in `render.yaml` by pull request (a value set only in the
dashboard is overwritten at the next Blueprint sync), and deploy. Lowering it
again only takes effect as browsers' stored value runs out.

## When an alert fires
- **Uptime:** open `racetimes-production` in Render: **Events** shows a
  failed deploy or a restart; **Logs** shows errors, each line naming the
  club (`ERROR [demo] ...`). The database's page shows whether it's
  available.
- **Sentry:** the report names the page and the club. Fix it, test it, then
  deploy as above.
- **A failed backup:** the cron job's **Logs**. Usually an expired or deleted
  key, or a full bucket; the job stops at the first error, so nothing
  half-written is uploaded.
- **Email not arriving:** Postmark's **Activity** shows each message, and
  whether it bounced or was marked as spam.
