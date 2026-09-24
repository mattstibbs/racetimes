"""The race day page (slice 9): tapping Finished, Undo, and what changed.

Finishes tapped here are ordinary Finish rows, saved through the same audit
code as typed ones, so scoring, the history and publishing see no difference.
See docs/slices/09-race-day-page.md.
"""

import hashlib
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import audit
from .models import Finish, RaceEntry, ScoringChange

UNDO_WINDOW = timedelta(minutes=2)
UNDO_NOTE = "Undone on the race day page within two minutes of saving."

NOT_RACE_DAY = "Finished can only be tapped on the race's own day, from its start time."
ALREADY_FINISHED = "{boat} already has a result: {result}. Nothing was changed."
UNDO_GONE = (
    "Undo is only possible for two minutes after a finish is saved, before the "
    "results are published. Correct it instead, with a reason."
)


def now():
    """The site's local time. A function, so tests can fix the clock."""
    return timezone.localtime()


def can_tap(race, at=None):
    """Whether Finished is offered: on the race's own date, from its start time."""
    at = at or now()
    return at.date() == race.date and at.time() >= race.start_time


def start_moment(race):
    """The race's start as an aware datetime in the site's time zone."""
    return timezone.make_aware(datetime.combine(race.date, race.start_time))


def describe(finish):
    if finish.status == Finish.Status.FINISHED:
        return f"finished at {finish.finish_time:%H:%M:%S}"
    return finish.status


def tap(race, entry, user):
    """Record ``entry`` as finishing now. Returns the Finish.

    Raises ValidationError, changing nothing, if it isn't race day, the boat
    isn't on the start sheet, it already has a result, or the time fails the
    usual checks (after the start, whole seconds).
    """
    at = now()
    if not can_tap(race, at):
        raise ValidationError(NOT_RACE_DAY)
    existing = Finish.objects.filter(race=race, entry=entry).first()
    if existing is not None:
        raise ValidationError(ALREADY_FINISHED.format(boat=entry.boat, result=describe(existing)))
    finish = Finish(
        race=race,
        entry=entry,
        status=Finish.Status.FINISHED,
        finish_time=at.time().replace(microsecond=0),
    )
    finish.full_clean()
    changes = audit.changes_to_save(finish)
    try:
        with transaction.atomic():
            finish.save()
            audit.record(changes, user)
    except IntegrityError:
        # Another device saved this boat's finish in the same instant.
        existing = Finish.objects.get(race=race, entry=entry)
        raise ValidationError(ALREADY_FINISHED.format(boat=entry.boat, result=describe(existing)))
    return finish


def can_undo(finish, race, at=None):
    """Undo: within two minutes of saving, and only before the race is published."""
    if finish.recorded_at is None or race.published_at is not None:
        return False
    return (at or timezone.now()) - finish.recorded_at <= UNDO_WINDOW


def undo(race, entry, user):
    """Delete a finish saved in the last two minutes; the boat is racing again.

    The removal is recorded in the history like any other, marked as an undo
    rather than a correction, so it needs no reason.
    """
    with transaction.atomic():
        finish = Finish.objects.select_for_update().filter(race=race, entry=entry).first()
        if finish is None or not can_undo(finish, race):
            raise ValidationError(UNDO_GONE)
        changes = audit.changes_to_delete(finish)
        for change in changes:
            change.is_correction = False
        finish.delete()
        audit.record(changes, user, UNDO_NOTE)


def version(race):
    """A short fingerprint of everything the Finishing view shows.

    The page sends it back when it refreshes itself. If nothing has changed,
    the site answers 204 and HTMX leaves the page alone. Undo buttons that
    have just run out count as a change, so they disappear on the next
    refresh.
    """
    race.refresh_from_db(fields=["published_at", "results_sent_at"])
    at = timezone.now()
    finishes = sorted(
        (f.entry_id, f.status, str(f.finish_time), can_undo(f, race, at))
        for f in Finish.objects.filter(race=race)
    )
    racing = sorted(RaceEntry.objects.filter(race=race).values_list("entry_id", flat=True))
    latest_change = (
        ScoringChange.objects.filter(series=race.series).order_by("-pk").values_list("pk", flat=True).first()
    )
    parts = [finishes, racing, str(race.published_at), str(race.results_sent_at), latest_change]
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:12]
