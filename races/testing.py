"""Builders for the app's tests. Not collected as tests itself.

Each takes only what a test cares about and defaults the rest, so a test reads
as the situation it sets up.
"""

from datetime import date, time
from decimal import Decimal

from races.models import Boat, Finish, Race, Series, SeriesEntry


def make_boat(sail_number="GBR1234", base_number="0.964", **fields):
    return Boat.objects.create(
        sail_number=sail_number, base_number=Decimal(str(base_number)), **fields
    )


def make_series(name="Autumn 2026", **fields):
    return Series.objects.create(name=name, **fields)


def enter(series, boat):
    return SeriesEntry.objects.create(series=series, boat=boat)


def make_race(series, number=1, start="18:00:00", on=date(2026, 9, 23)):
    return Race.objects.create(
        series=series, number=number, date=on, start_time=time.fromisoformat(start)
    )


def record(race, entry, finish_time=None, status=None):
    """Record a finish: a clock time like "19:02:17", or a status code."""
    if status is None:
        status = Finish.Status.FINISHED if finish_time else Finish.Status.DNC
    return Finish.objects.create(
        race=race,
        entry=entry,
        status=status,
        finish_time=time.fromisoformat(finish_time) if finish_time else None,
    )
