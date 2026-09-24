# Slice 4: Notifications

## Goal
The site emails people when something that concerns them happens: race
results once the committee publishes them (and again, if the committee
chooses, after corrections), changes to their boats and entries, decisions on
their requests and accounts, and password resets. Nothing is emailed that the
person could not already see on the site.

## Scope

### Publishing results
Today a race's results are public the moment a finish is saved. That does not
change: the public page keeps showing them, but a race is labelled
**provisional** until the committee publishes it.

- The finish-entry page gets a **Publish results** button. Publishing marks
  the race published and emails its results to the owners of every boat
  entered in the series.
- If a published race's results change afterwards (a corrected finish, a
  changed start time, a late entry, a series setting or a base number that
  moves the scores), the race shows **"Amended since results were sent"** and
  a **Send updated results** button. Nothing is sent until the committee
  presses it; the committee decides when correcting is finished. *(Agreed with
  the project owner: the committee sends updates, never the site on its own.)*
- The public page says "Published" with the date once published, explains
  what "provisional" means, and warns "Amended since published" while an
  update is waiting to be sent. *(Added at the project owner's request.)*
- "Amended since results were sent" is worked out from the change history
  (slice 2): any correction recorded for the race, or for its whole series,
  since the results were last sent. Nothing extra is stored for it.

### The emails

| Email | Sent to | When |
|---|---|---|
| **Race results** | Owners of boats entered in the series | The committee publishes a race |
| **Race results updated** | The same | The committee presses **Send updated results** |
| **Your account is approved** | The member | The administrator approves their account |
| **Your request was approved / rejected** | The member who asked | The committee decides a request. Includes the committee's note, and for an approved change, each detail old and new |
| **Your boat has been entered in a series** | The boat's owner | The boat is entered in a series, whether by the committee in the admin or by approving a request |
| **Your boat information has been updated** | The boat's owner | The boat's details change in any way, with each change old and new |
| **Reset your password** | The member | They ask for it from the login page |

- **No duplicates.** When a change comes from the owner's own approved
  request, the "request approved" email carries the details, and the "boat
  updated" or "entered" email is not also sent. *(Agreed with the project
  owner.)*
- **Only owners with accounts.** A boat with no owning account (a visitor, say)
  gets no email.
- Emails are **plain text**, in the club's voice, with a link back to the
  relevant page on the site.
- Emails are sent **after the change is saved** (Django's `on_commit`), so a
  change that fails and is rolled back never emails anyone.
- A failure to send never loses the change and never crashes a page: the
  change is kept, the page says the emails could not be sent, and the error is
  logged. Publishing can then be retried.

### Password reset
Django's own password reset, linked from the login page: the member enters
their email and gets a link valid for a limited time. Only active accounts can
reset; the page does not reveal whether an email has an account. The login
page's "ask the administrator" note is replaced.

### Sending email
Django's built-in email, configured by environment variables, so no new
dependency: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL`. With no
`EMAIL_HOST` set, emails are printed to the console instead of sent, which is
what development uses; the tests use Django's in-memory outbox. Which
provider to send through, and whether the host allows outgoing SMTP, is
decided before deploying. *(Agreed with the project owner.)*

### Data model (proposed, awaiting approval)
- **Race**, two new fields:
  - `published_at`: when the committee published the results. Empty means
    provisional.
  - `results_sent_at`: when results (first or updated) were last emailed.
- Nothing else. "Amended since sent" comes from the change history, and
  password reset uses Django's own signed links, which store nothing.

## Acceptance criteria
- A race is provisional until published; the public page says so.
- Publishing emails the race's results to every owner of a boat entered in
  the series, and to nobody else.
- After a published race's results change, the committee sees that it was
  amended since the results were sent, and can send updated results. Nothing
  is sent automatically.
- Each email in the table is sent when, and only when, its event happens;
  tested per email, including the "no duplicates" rule.
- A change that is rolled back sends nothing; a sending failure keeps the
  change and says so on the page.
- A member can reset their password by email, and the page does not reveal
  whether an email address has an account.
- The user manual covers publishing results, the emails members receive, and
  resetting a password.
- Migrations use nothing specific to SQLite or PostgreSQL.

## Out of scope
- Choosing an email provider and configuring it on Render (a deployment step,
  recorded in `docs/deploying.md` once chosen).
- Letting members choose which emails they receive, or unsubscribing.
- HTML emails.
- Race-level entry and its confirmation (the brief's user journey 3):
  entries are per series.
- Emailing the committee about new requests: the admin front page already
  lists them.
