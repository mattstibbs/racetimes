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

## Suspending and reactivating a club

On the club's page, **Suspend** pauses its site: everyone who opens it sees
"This club's site is paused". Nothing is deleted, and **Reactivate** brings
it back as it was. Use it, for example, while an unpaid invoice is chased, or
before deleting a club.

(A superuser can still open a suspended club's pages, to check them.)

## Exporting and deleting a club

Part 5 of slice 11: a club's administrator downloads the club's data, and the
operator deletes a suspended club after typing its address to confirm. Not
built yet.

## Clubs at a glance

**Clubs** lists every club, with its status, how many approved members and
series it has, and when a result was last recorded there: a quick way to see
which clubs are using the service.
