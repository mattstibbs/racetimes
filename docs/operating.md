# Operating Race Times

For the service's operator: the person who runs Race Times for every club
(slice 11). This is developer documentation, not part of the user manual,
which is for clubs' own people.

The operator is a superuser (the account `build.sh` creates, see
`docs/deploying.md`). The operator's powers are on the **service's own
address**, `racetimes.co.uk` (`localhost:8000` in development), never on a
club's. At a club, the operator is nobody unless given a membership there
like anyone else, and the operator's pages change no club's data.

Everything done on the operator's pages is recorded in the **operator log**:
who, what, when, and for which club. It keeps the club's address as text, so
it still reads the same after a club is deleted.

## Logging in

Open `/operator/` on the service's own address. It sends you to the admin's
login page (the one login on the service's own address); after logging in you
land on **Clubs**. The header links to Clubs, the operator log and the Django
admin, where accounts are managed.

The operator's pages need an address with no club in it. On a site with
`SINGLE_CLUB` set, like the Render test site, every address is that club's,
so there are no operator's pages there: set clubs up locally, or once
production hosting (with subdomains) exists.

## Creating a club

**Clubs → Create a club.** Give:

- **its name**, as the club wants it shown at the top of every page;
- **its address** (subdomain): `exesc` makes `exesc.racetimes.co.uk`. Letters,
  digits and hyphens only, not starting or ending with a hyphen, stored in
  lower case. `www`, `admin`, `operator`, `mail`, `api`, `static` and `app`
  are reserved for the service. It can't be changed later;
- **its contact email**, where replies to the club's emails will go.

The club's site works at once, empty. Tell the club its address.

## Inviting the club's administrator

On the club's page, under **Invite an administrator**, enter the person's email
and press **Email the invitation**. They get an email with a link to the
club's own address, which lasts **7 days** and works once:

- with no Race Times account yet, they make one there (the invitation proves
  the email address, so there's no separate confirmation);
- with an account already, from another club, they log in and press
  **Accept**.

Either way they become the club's administrator (an approved membership), and
from then on the club manages its own people on its **Members** page. The
club's page lists every invitation and whether it was accepted. If a link
expires, send another; nothing needs cancelling. A suspended club can't be
sent invitations.

## People waiting to join

Normally a club's own administrators approve people joining, on the club's
**Members** page. When they can't (a new club before its administrator has
accepted the invitation, one whose only administrator is away, or Demo Club),
the club's page here has **Waiting to join**:
- choose a role (member, race committee or club administrator) and press
  **Approve**, or press **Don't approve**;
- the person is emailed from the club, with links to the club's address,
  exactly as when the club decides;
- the club sees "Approved by the Race Times operator" on its Members page,
  and in its data export, not your login;
- each decision is in the operator log, with your login.

Only people **waiting** can be decided here. Changing someone's role or
removing them stays with the club. Nothing can be decided while the club is
suspended. This is a deliberate exception to "clubs decide their own
members" (`docs/decisions.md`), so use it at the club's request.

## Suspending and reactivating a club

On the club's page, **Suspend** pauses its site: everyone who opens it sees
"This club's site is paused". Nothing is deleted, and **Reactivate** brings
it back as it was. Use it, for example, while an unpaid invoice is chased, or
before deleting a club.

(A superuser can still open a suspended club's pages, to check them.)

## Exporting and deleting a club

When a club leaves Race Times:

1. **Suspend it** (above), so its members see the site is paused.
2. **Download its data.** On the club's page, under "The club's data",
   **Download everything <club> holds (ZIP)** gives the same ZIP the club's
   administrators get from their Members page: boats, members, series,
   entries, races, start sheets, finishes, each series' results, requests and
   the change history, as CSV files. It works while the club is suspended,
   which is the point: its administrators can't reach its site then. Send it
   to the club. Each download is recorded in the operator log.
3. **Delete it.** Once the club is suspended, **Delete <club>...** on its page
   asks you to type the club's address (its subdomain) to confirm. Everything
   the club holds goes, in one step: boats, series, races, finishes,
   requests, history, memberships and invitations. People's accounts stay,
   since they may belong to other clubs. The operator log records it, with
   counts of what went, and keeps the club's subdomain as text so the log
   still reads after the club has gone.

An active club can't be deleted. With `SINGLE_CLUB` set (the test site),
there are no operator pages at all, so the club it shows can't be deleted
from the site.

People delete their own accounts, from **Account** at any club; the
operator's own account can't be deleted that way. See the manual's "Joining a
club, and your data".

## Clubs at a glance

**Clubs** lists every club, with its status, how many approved members and
series it has, and when a result was last recorded there: a quick way to see
which clubs are using the service.
