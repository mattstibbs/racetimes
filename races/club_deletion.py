"""Deleting a club and everything it holds (slice 11 part 5).

Only the operator does it, and only once the club is suspended (the pause in
which to take its export). People's accounts stay: they may belong to other
clubs.

Deleting the ``Club`` row alone doesn't work: a boat can't be deleted while a
series entry still uses it (``SeriesEntry.boat`` is PROTECT, so a boat with
results is never lost by accident). So the club's rows are deleted in order,
series before boats, in one transaction: all of it goes, or none of it.
"""

from django.db import transaction

from .models import Boat, BoatRequest, EntryRequest, ScoringChange, Series

REFUSED_ACTIVE = "Suspend the club before deleting it."


def delete_club(club):
    """Delete the club and everything it holds. Returns what went, for the operator log."""
    if club.is_active:
        raise ValueError(REFUSED_ACTIVE)
    with transaction.atomic():
        gone = {
            "boats": Boat.objects.for_club(club).count(),
            "series": Series.objects.for_club(club).count(),
            "memberships": club.memberships.count(),
        }
        ScoringChange.objects.for_club(club).delete()
        EntryRequest.objects.for_club(club).delete()
        BoatRequest.objects.for_club(club).delete()
        # A series takes its races, entries, start sheets and finishes with it.
        Series.objects.for_club(club).delete()
        Boat.objects.for_club(club).delete()
        club.delete()  # and its memberships and invitations
    return gone
