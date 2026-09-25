"""The history of changes to anything that feeds a score.

Everything that saves a score-affecting value - the finish-entry view and the
admin - asks this module what the save would record, requires a reason if any
of it is a correction, and records it in the same transaction as the save.
Changes are recorded explicitly rather than by model signals, because a signal
cannot see who made the change or why.

A change is a *correction* when it alters something that has already fed into a
result: a saved finish, a race that has finishes, or a series' settings,
entries or boats once the series has any finishes.
"""

from dataclasses import dataclass
from datetime import time

from django.utils import timezone
from django.utils.text import capfirst

from .models import Boat, Finish, Race, ScoringChange, Series, SeriesEntry

# The fields whose changes are recorded, per model. Everything else on these
# models is display only and moves no number. Adding a field here is all it
# takes to audit it.
AUDITED_FIELDS = {
    Finish: ["status", "finish_time"],
    # A race's date moves nothing: elapsed time is measured within the day.
    Race: ["number", "start_time"],
    Series: ["series_type", "discards", "minimum_finishers", "apply_a5_3"],
    SeriesEntry: [],  # only being added or removed matters (the A5.2 entry count)
    Boat: ["base_number"],
}

KINDS = {
    Finish: ScoringChange.Kind.FINISH,
    Race: ScoringChange.Kind.RACE,
    Series: ScoringChange.Kind.SERIES,
    SeriesEntry: ScoringChange.Kind.ENTRY,
    Boat: ScoringChange.Kind.BOAT,
}

# Creating a series or a boat moves no result on its own; its entries and races do.
_CREATION_NOT_AUDITED = (Series, Boat)

REASON_REQUIRED = "This changes results already recorded, so give a reason for the correction."


def changes_to_save(obj):
    """The unsaved ScoringChange rows that saving ``obj`` as it stands would record.

    Compares ``obj`` with its stored row, so call it after the form has
    updated the instance and before saving it. Empty if nothing audited changed.
    """
    fields = AUDITED_FIELDS[type(obj)]
    stored = type(obj)._default_manager.filter(pk=obj.pk).first() if obj.pk else None
    if stored is None:
        if isinstance(obj, _CREATION_NOT_AUDITED):
            return []
        changes = {_label(obj, name): ["", _display(obj, name)] for name in fields}
        return _rows(obj, ScoringChange.Action.ADDED, changes)

    changes = {
        _label(obj, name): [_display(stored, name), _display(obj, name)]
        for name in fields
        if getattr(stored, name) != getattr(obj, name)
    }
    if not changes:
        return []
    return _rows(obj, ScoringChange.Action.CHANGED, changes)


def changes_to_delete(obj):
    """The unsaved ScoringChange rows that deleting ``obj`` would record."""
    changes = {_label(obj, name): [_display(obj, name), ""] for name in AUDITED_FIELDS[type(obj)]}
    return _rows(obj, ScoringChange.Action.REMOVED, changes)


def needs_reason(changes):
    return any(change.is_correction for change in changes)


def record(changes, user, reason=""):
    """Save the rows. Call inside the transaction that saves the change itself."""
    now = timezone.now()
    for change in changes:
        change.timestamp = now
        change.user = user
        change.user_name = user.get_username()
        change.reason = reason
    ScoringChange.objects.bulk_create(changes)
    return changes


def series_has_finishes(series):
    return series.pk is not None and Finish.objects.filter(race__series=series).exists()


def _rows(obj, action, changes):
    def row(series, race, is_correction):
        return ScoringChange(
            club=_club_of(obj),
            kind=KINDS[type(obj)],
            action=action,
            description=_describe(obj),
            changes=changes,
            series=series,
            race=race,
            is_correction=is_correction,
        )

    if isinstance(obj, Finish):
        return [row(obj.race.series, obj.race, action != ScoringChange.Action.ADDED)]
    if isinstance(obj, Race):
        has_finishes = obj.pk is not None and obj.finishes.exists()
        return [row(obj.series, obj, action != ScoringChange.Action.ADDED and has_finishes)]
    if isinstance(obj, Series):
        return [row(obj, None, series_has_finishes(obj))]
    if isinstance(obj, SeriesEntry):
        return [row(obj.series, None, series_has_finishes(obj.series))]
    # A base number feeds every series the boat is in, so each series' history
    # gets its own row and is complete without looking anywhere else.
    series_list = list(Series.objects.filter(entries__boat=obj).distinct()) if obj.pk else []
    if not series_list:
        return [row(None, None, False)]
    return [row(series, None, series_has_finishes(series)) for series in series_list]


def _club_of(obj):
    """The club a changed row belongs to (slice 11)."""
    if isinstance(obj, Finish):
        return obj.race.series.club
    if isinstance(obj, (Race, SeriesEntry)):
        return obj.series.club
    return obj.club  # a Series or a Boat


def _describe(obj):
    if isinstance(obj, Finish):
        return f"{obj.entry.boat}, Race {obj.race.number}"
    if isinstance(obj, Race):
        return f"Race {obj.number}"
    if isinstance(obj, SeriesEntry):
        return str(obj.boat)
    return str(obj)


def _label(obj, name):
    # capfirst, not str.capitalize: only the first letter changes, so
    # "NHC base number" and "use RRS A5.3" keep their capitals.
    return capfirst(str(obj._meta.get_field(name).verbose_name))


def _display(obj, name):
    field = obj._meta.get_field(name)
    value = getattr(obj, name)
    if value is None:
        return ""
    if field.choices:
        return str(dict(field.flatchoices).get(value, value))
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return str(value)


# --- What a change did to the results --------------------------------------


@dataclass(frozen=True)
class Effect:
    places: list  # race numbers where any place or points moved
    handicaps: list  # race numbers where any boat sailed on a different handicap
    standings: bool


def compare(before, after):
    """Which results differ between two scorings of a series.

    Compares what a person sees - places, points and handicaps to 3 d.p. - so
    it never reports a change too small to show on the results page. Nothing
    here is stored; both scorings are replays.
    """
    before_races = {race_results.race.pk: race_results for race_results in before.races}
    places, handicaps = [], []
    for race_results in after.races:
        old = before_races.get(race_results.race.pk)
        if old is None:
            continue
        if _places(old) != _places(race_results):
            places.append(race_results.race.number)
        if _handicaps(old) != _handicaps(race_results):
            handicaps.append(race_results.race.number)
    return Effect(places, handicaps, _standings(before) != _standings(after))


def describe_effect(before, after):
    """``compare`` as a sentence or two for the person who made the change."""
    effect = compare(before, after)
    parts = []
    if effect.places:
        parts.append(f"Places changed in {race_list(effect.places)}.")
    if effect.handicaps:
        parts.append(f"Handicaps changed in {race_list(effect.handicaps)}.")
    if effect.standings:
        parts.append("Standings changed.")
    return " ".join(parts) or "No places, handicaps, or standings were affected by this change."


def _places(race_results):
    return {row.entry.pk: (row.result.position, row.result.points) for row in race_results.rows}


def _handicaps(race_results):
    return {row.entry.pk: round(row.result.tcf_used, 3) for row in race_results.rows}


def _standings(results):
    return {row.entry.pk: (row.position, row.total) for row in results.standings}


def race_list(numbers):
    """[3] -> "race 3"; [2, 4, 5, 6] -> "races 2, 4-6"."""
    numbers = sorted(numbers)
    if len(numbers) == 1:
        return f"race {numbers[0]}"
    runs = [[numbers[0], numbers[0]]]
    for number in numbers[1:]:
        if number == runs[-1][1] + 1:
            runs[-1][1] = number
        else:
            runs.append([number, number])
    return "races " + ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)
