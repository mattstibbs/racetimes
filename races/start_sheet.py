"""Race day's start sheet: which boats in the series are racing (slice 6).

Only a boat on the start sheet can have a finish recorded, and every boat on
it must have a time or a code before the race's results are published. A boat
left off stayed at home and scores DNC. None of this moves a score, so none of
it is in the change history; see docs/decisions.md.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef

from . import notifications
from .models import Finish, RaceEntry

HAS_RESULT = (
    "{boat} has a result recorded in this race, so it stays on the start sheet. "
    "If it did not race, correct its result to DNC on the finishes page."
)


def unrecorded(race):
    """The series entries on the start sheet with no time or code yet, by sail number."""
    has_finish = Finish.objects.filter(race=race, entry=OuterRef("entry"))
    return [
        race_entry.entry
        for race_entry in race.race_entries.select_related("entry__boat")
        .filter(~Exists(has_finish))
        .order_by("entry__boat__sail_number")
    ]


def save_row(race, entry, *, racing, persons_on_board, request):
    """Put a boat on the start sheet, update it, or take it off.

    Returns a short message saying what happened, for the row. Raises
    ValidationError if the boat cannot be taken off. The owner is emailed
    when the boat goes on or comes off, once the change is saved.
    """
    with transaction.atomic():
        race_entry = RaceEntry.objects.select_for_update().filter(race=race, entry=entry).first()
        if racing:
            if race_entry is None:
                race_entry = RaceEntry(race=race, entry=entry, persons_on_board=persons_on_board)
                race_entry.full_clean()
                race_entry.save()
                notifications.start_sheet_changed(race, entry, request, racing=True)
                return _emailed("Added to the start sheet.", entry)
            if race_entry.persons_on_board == persons_on_board:
                return "Saved; nothing changed."
            race_entry.persons_on_board = persons_on_board
            race_entry.full_clean()
            race_entry.save()
            return "Persons on board saved."
        if race_entry is None:
            return "Saved; nothing changed."
        if Finish.objects.filter(race=race, entry=entry).exists():
            raise ValidationError(HAS_RESULT.format(boat=entry.boat))
        race_entry.delete()
        notifications.start_sheet_changed(race, entry, request, racing=False)
        return _emailed("Taken off the start sheet.", entry)


def _emailed(done, entry):
    if notifications.has_owner_to_email(entry.boat):
        return f"{done} The owner has been emailed."
    return f"{done} No email: the boat has no owner account."
