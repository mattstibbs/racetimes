"""A person's own data, as one JSON file (slice 11 part 5).

Everything held about them, at every club: it's all theirs, so the file isn't
limited to the club whose address they downloaded it from. It leaves out
other people's details, such as who approved them (someone else's login).

The account page offers it as **Download my data** (``races/account_views.py``).
"""

from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

from .models import Boat, BoatRequest, ClubMembership, EntryRequest, ScoringChange

# Never in the file: ids mean nothing outside the database, and the "decided
# by" fields name other people.
LEFT_OUT = {"id", "request_ptr", "club", "owner", "user", "user_name", "requested_by", "decided_by", "decided_by_name"}


def my_data(user):
    return {
        "downloaded_at": _value(timezone.now()),
        "account": {
            "login": user.get_username(),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined": _value(user.date_joined),
            "last_login": _value(user.last_login),
        },
        "memberships": [
            {"club": m.club.name, **_fields(m)}
            for m in ClubMembership.objects.filter(user=user).select_related("club").order_by("club__name")
        ],
        "boats": [
            {"club": boat.club.name, **_fields(boat)}
            for boat in Boat.objects.filter(owner=user).select_related("club").order_by("club__name", "sail_number")
        ],
        "boat_requests": [
            {"club": r.club.name, **_fields(r)}
            for r in BoatRequest.objects.filter(requested_by=user).select_related("club", "boat")
        ],
        "entry_requests": [
            {"club": r.series.club.name, **_fields(r)}
            for r in EntryRequest.objects.filter(requested_by=user).select_related("series__club", "boat")
        ],
        "changes_made": [
            {"club": change.club.name, **_fields(change)}
            for change in ScoringChange.objects.filter(user=user).select_related("club", "series", "race")
        ],
    }


def _fields(obj):
    """Every field of a row but those LEFT_OUT, with related rows by name and choices by label."""
    row = {}
    for field in obj._meta.concrete_fields:
        if field.name in LEFT_OUT:
            continue
        if field.is_relation:
            related = getattr(obj, field.name)
            row[field.name] = str(related) if related is not None else None
        elif field.choices:
            row[field.name] = getattr(obj, f"get_{field.name}_display")()
        else:
            row[field.name] = _value(getattr(obj, field.attname))
    return row


def _value(value):
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat() if timezone.is_aware(value) else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):  # a time of day
        return value.isoformat()
    return value
