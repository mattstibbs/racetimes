"""The emails the site sends (slice 4), and how they are sent.

Every email goes through ``send``, which waits for the surrounding database
transaction to commit, so a change that fails and is rolled back never emails
anyone. If sending then fails, the change stands: the error is logged and the
person who made the change is told on the page, so nothing is silently lost
and no page crashes.

Each recipient gets their own message, addressed to them, rather than one
message to everyone: owners should not see each other's email addresses.

Templates are in templates/emails/. Their first line is the subject.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from .models import BoatRequest, EntryRequest
from .scoring import score_series

logger = logging.getLogger(__name__)

SEND_FAILED = (
    "Saved, but the emails about it could not be sent. The error has been logged; "
    "tell the club's administrator."
)


def send(emails, request=None, on_sent=None):
    """Send these emails once the current transaction commits.

    ``on_sent`` runs only if every email went, which is how publishing records
    that results were sent: a failure leaves them unsent, to be sent again.
    """
    emails = [email for email in emails if email.to]

    def deliver():
        try:
            if emails:
                with get_connection() as connection:
                    connection.send_messages(emails)
        except Exception:
            logger.exception("Could not send %d email(s)", len(emails))
            if request is not None:
                messages.warning(request, SEND_FAILED)
            return
        if on_sent is not None:
            on_sent()

    transaction.on_commit(deliver)


def email(user, template, request, **context):
    """One email to one person, from templates/emails/<template>.txt."""
    text = render_to_string(
        f"emails/{template}.txt",
        {"user": user, "site_url": request.build_absolute_uri("/").rstrip("/"), **context},
    )
    subject, _, body = text.strip().partition("\n")
    return EmailMessage(subject.strip(), body.strip() + "\n", to=[user.email] if user.email else [])


def _link(request, name, *args):
    return request.build_absolute_uri(reverse(name, args=args))


# --- Race results --------------------------------------------------------------


def series_owners(series):
    """Active members who own a boat entered in the series."""
    return get_user_model().objects.filter(
        boats__series_entries__series=series, is_active=True
    ).exclude(email="").distinct()


def race_results(race, request, *, updated, on_sent=None):
    """Email a race's results to every owner in its series. Returns how many."""
    results = score_series(race.series)
    owners = list(series_owners(race.series))
    context = {
        "race": race,
        "race_results": results.for_race(race),
        "note": results.note_for(race),
        "standings": results.standings,
        "updated": updated,
        "results_url": _link(request, "results:series", race.series.pk) + f"?race={race.number}",
    }
    send([email(owner, "race_results", request, **context) for owner in owners], request, on_sent)
    return len(owners)


def final_standings(series, request, *, updated, on_sent=None):
    """Email a final series' standings to every owner in it, each with their own place (slice 10)."""
    results = score_series(series)
    place = {}
    for row in results.standings:
        if row.entry.boat.owner_id is not None:
            place.setdefault(row.entry.boat.owner_id, []).append(row)
    owners = list(series_owners(series))
    context = {
        "series": series,
        "standings": results.standings,
        "updated": updated,
        "results_url": _link(request, "results:series", series.pk),
    }
    send(
        [email(owner, "final_standings", request, own_rows=place.get(owner.pk, []), **context) for owner in owners],
        request,
        on_sent,
    )
    return len(owners)


# --- Members: accounts, requests, boats and entries ------------------------------


def account_approved(users, request):
    send(
        [email(user, "account_approved", request, login_url=_link(request, "races:login")) for user in users],
        request,
    )


def request_decided(member_request, request, details=(), boat_name=None):
    """Tell the member what the committee decided, and for an approval what changed.

    ``details`` are the approvals.Proposed rows worked out before the change
    was applied, since afterwards the boat already matches them.
    """
    # The boat as it was named when the member asked, not after a change renamed it.
    boat_name = boat_name or str(member_request.boat)
    if isinstance(member_request, EntryRequest):
        what = f"to enter {boat_name} in {member_request.series}"
    elif member_request.kind == BoatRequest.Kind.REGISTER:
        what = f"to register {member_request.sail_number} {member_request.name}".strip()
    elif member_request.kind == BoatRequest.Kind.CHANGE:
        what = f"to change the details of {boat_name}"
    else:
        what = f"to be recorded as the owner of {boat_name}"
    # For a change, only what moves; for a registration, everything registered.
    is_change = getattr(member_request, "kind", None) == BoatRequest.Kind.CHANGE
    changed = [row for row in details if row.changed] if is_change else list(details)
    send(
        [
            email(
                member_request.requested_by,
                "request_decided",
                request,
                member_request=member_request,
                what=what,
                approved=member_request.status == member_request.Status.APPROVED,
                details=changed,
                boats_url=_link(request, "races:my_boats"),
            )
        ],
        request,
    )


def entered_in_series(entries, request):
    """Tell each owner their boat was entered, when the committee did it directly."""
    send(
        [
            email(
                entry.boat.owner,
                "entered_in_series",
                request,
                entry=entry,
                results_url=_link(request, "results:series", entry.series.pk),
            )
            for entry in entries
            if entry.boat.owner is not None and entry.boat.owner.is_active
        ],
        request,
    )


def removed_from_series(entries, request):
    """Tell each owner their boat is no longer entered in a series.

    Called after the entries are deleted, so each email is written from the
    entry as it was held in memory: its boat and series still exist. Their
    start sheet rows went with them, and that sends no race emails as well.
    """
    _to_owners(entries, "removed_from_series", request, lambda entry: {
        "boat": entry.boat,
        "series": entry.series,
        "results_url": _link(request, "results:series", entry.series.pk),
    })


def _to_owners(entries, template, request, context):
    """One email per series entry, to its boat's owner if they have an active account."""
    send(
        [
            email(entry.boat.owner, template, request, **context(entry))
            for entry in entries
            if has_owner_to_email(entry.boat)
        ],
        request,
    )


def has_owner_to_email(boat):
    """Whether the site can email this boat's owner at all."""
    return boat.owner is not None and boat.owner.is_active and bool(boat.owner.email)


# --- Race day: the start sheet ----------------------------------------------------


def start_sheet_changed(race, entry, request, *, racing):
    """Tell the owner their boat was put on, or taken off, a race's start sheet."""
    _to_owners([entry], "entered_in_race" if racing else "removed_from_race", request, lambda entry: {
        "boat": entry.boat,
        "race": race,
        "results_url": _link(request, "results:series", race.series.pk) + f"?race={race.number}",
    })


def boat_updated(boat, changes, owners, request):
    """Tell the owner(s) what changed about their boat.

    ``changes`` is a list of (label, old, new). ``owners`` is normally just the
    boat's owner, but when ownership itself changes the previous owner is told
    as well.
    """
    if not changes:
        return
    send(
        [
            email(owner, "boat_updated", request, boat=boat, changes=changes,
                  boats_url=_link(request, "races:my_boats"))
            for owner in owners
            if owner is not None and owner.is_active
        ],
        request,
    )
