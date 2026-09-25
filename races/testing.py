"""Builders for the app's tests. Not collected as tests itself.

Each takes only what a test cares about and defaults the rest, so a test reads
as the situation it sets up.
"""

from datetime import date, time
from decimal import Decimal

from races.models import Boat, Club, ClubMembership, Finish, Race, RaceEntry, Series, SeriesEntry


def default_club():
    """The first club, which the migrations create and tests see by default (slice 11)."""
    return Club.objects.get(subdomain="demo")


def make_club(subdomain, name=None, **fields):
    return Club.objects.create(subdomain=subdomain, name=name or subdomain.capitalize(), **fields)


def make_boat(sail_number="GBR1234", base_number="0.964", club=None, **fields):
    return Boat.objects.create(
        club=club or default_club(), sail_number=sail_number, base_number=Decimal(str(base_number)), **fields
    )


def make_series(name="Autumn 2026", club=None, **fields):
    return Series.objects.create(club=club or default_club(), name=name, **fields)


def enter(series, boat):
    return SeriesEntry.objects.create(series=series, boat=boat)


def make_race(series, number=1, start="18:00:00", on=date(2026, 9, 23)):
    return Race.objects.create(
        series=series, number=number, date=on, start_time=time.fromisoformat(start)
    )


def start(race, entry, persons_on_board=None):
    """Put a boat on a race's start sheet (if it is not on it already)."""
    race_entry, _ = RaceEntry.objects.get_or_create(race=race, entry=entry)
    if persons_on_board is not None:
        race_entry.persons_on_board = persons_on_board
        race_entry.save()
    return race_entry


def record(race, entry, finish_time=None, status=None):
    """Record a finish: a clock time like "19:02:17", or a status code.

    The boat goes on the start sheet first, as it must on the real site.
    """
    start(race, entry)
    if status is None:
        status = Finish.Status.FINISHED if finish_time else Finish.Status.DNC
    return Finish.objects.create(
        race=race,
        entry=entry,
        status=status,
        finish_time=time.fromisoformat(finish_time) if finish_time else None,
    )


_DEFAULT = object()


def make_member(email="member@example.com", first_name="Pat", last_name="Jones",
                club=_DEFAULT, role="MEMBER", status="APPROVED", **fields):
    """An active account, logged in by email, with an approved membership of Demo Club.

    Pass ``club`` for another club, or ``club=None`` for an account that
    belongs to no club. ``role`` and ``status`` are the membership's (slice 11).
    """
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        username=email, email=email, first_name=first_name, last_name=last_name, **fields
    )
    if club is _DEFAULT:
        club = default_club()
    if club is not None:
        ClubMembership.objects.create(user=user, club=club, role=role, status=status)
    return user


def join(user, club, role="MEMBER", status="APPROVED"):
    """Give an existing account a membership of another club."""
    from races.roles import forget_memberships

    forget_memberships(user)  # the user object may have looked up its memberships already
    return ClubMembership.objects.create(user=user, club=club, role=role, status=status)


def make_committee(email="officer@example.com", club=_DEFAULT, **fields):
    """A race committee member of Demo Club (or ``club``)."""
    return make_member(email, first_name="Race", last_name="Officer", club=club, role="COMMITTEE", **fields)


def make_administrator(email="admin@example.com", club=_DEFAULT, **fields):
    """A club administrator of Demo Club (or ``club``). Not the operator."""
    return make_member(email, first_name="Club", last_name="Admin", club=club, role="ADMINISTRATOR", **fields)


def make_operator(email="operator@example.com"):
    """The service's operator: a superuser with no club membership."""
    return make_member(email, first_name="Service", last_name="Operator", club=None,
                       is_staff=True, is_superuser=True)
