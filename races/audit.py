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

from .models import (
    NUMBER_FIELDS,
    YTC_NUMBER_FIELDS,
    Boat,
    Finish,
    Race,
    ScoringChange,
    Series,
    SeriesEntry,
)

# The fields whose changes are recorded, per model. Everything else on these
# models is display only and moves no number. Adding a field here is all it
# takes to audit it.
AUDITED_FIELDS = {
    Finish: ["status", "finish_time", "scoring_penalty"],
    # A race's date moves nothing: elapsed time is measured within the day.
    Race: ["number", "start_time"],
    Series: [
        "handicap_system",
        "series_type",
        "discards",
        "discard_threshold",
        "minimum_finishers",
        "apply_a5_3",
        "nhc_cap_extremes",
        "nhc_realign_to_base",
    ],
    # Being added or removed matters (the A5.2 entry count). So does, in a YTC
    # series only (slice 25), which of her two numbers the boat races on; see
    # fields_for.
    SeriesEntry: ["ytc_number_used"],
    Boat: ["base_number", "py_number", "ytc_number", "ytc_number_non_spinnaker"],
}


def fields_for(obj):
    """The audited fields that mean something for this row.

    An entry's choice of number means nothing outside a YTC series (slice 25),
    so it is not recorded there.
    """
    fields = AUDITED_FIELDS[type(obj)]
    if isinstance(obj, SeriesEntry) and not _series_is_ytc(obj):
        return [name for name in fields if name != "ytc_number_used"]
    return fields


def _series_is_ytc(entry):
    try:
        return entry.series.handicap_system == Series.HandicapSystem.YTC
    except Series.DoesNotExist:  # an entry whose series is not set yet
        return False


KINDS = {
    Finish: ScoringChange.Kind.FINISH,
    Race: ScoringChange.Kind.RACE,
    Series: ScoringChange.Kind.SERIES,
    SeriesEntry: ScoringChange.Kind.ENTRY,
    Boat: ScoringChange.Kind.BOAT,
}

# Creating a series or a boat moves no result on its own; its entries and races do.
_CREATION_NOT_AUDITED = (Series, Boat)

REASON_REQUIRED = (
    "This changes results already recorded, so give a reason for the correction."
)


def changes_to_save(obj):
    """The unsaved ScoringChange rows that saving ``obj`` as it stands would record.

    Compares ``obj`` with its stored row, so call it after the form has
    updated the instance and before saving it. Empty if nothing audited changed.
    """
    fields = fields_for(obj)
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
    changes = {_label(obj, name): [_display(obj, name), ""] for name in fields_for(obj)}
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
    def row(series, race, is_correction, these=None):
        return ScoringChange(
            club=_club_of(obj),
            kind=KINDS[type(obj)],
            action=action,
            description=_describe(obj),
            changes=changes if these is None else these,
            series=series,
            race=race,
            is_correction=is_correction,
        )

    if isinstance(obj, Finish):
        return [row(obj.race.series, obj.race, action != ScoringChange.Action.ADDED)]
    if isinstance(obj, Race):
        has_finishes = obj.pk is not None and obj.finishes.exists()
        return [
            row(obj.series, obj, action != ScoringChange.Action.ADDED and has_finishes)
        ]
    if isinstance(obj, Series):
        return [row(obj, None, series_has_finishes(obj))]
    if isinstance(obj, SeriesEntry):
        return [row(obj.series, None, series_has_finishes(obj.series))]
    # A boat's numbers each feed only the series scored on them (slice 24): the
    # NHC base number the NHC series, the Portsmouth Number the Portsmouth ones.
    # Each series' history gets a row of the changes that touched it, so it is
    # complete without looking anywhere else. A change that touched no series
    # at all (a boat in none, or only in series that don't use that number) is
    # kept in one row for the club, so it is still recorded.
    # A YTC number (slice 25) feeds a series only through the entries that chose
    # it, so a change to one the boat is not entered on touches no series.
    series_list = (
        list(Series.objects.filter(entries__boat=obj).distinct()) if obj.pk else []
    )
    system_of_label = {_label(obj, field): s for field, s in NUMBER_FIELDS.items()}
    ytc_label = {_label(obj, field): used for field, used in YTC_NUMBER_FIELDS.items()}
    chose = {}  # series pk -> the YTC choices its entries for this boat made
    if obj.pk:
        for series_id, used in SeriesEntry.objects.filter(
            boat=obj, series__handicap_system=Series.HandicapSystem.YTC
        ).values_list("series_id", "ytc_number_used"):
            chose.setdefault(series_id, set()).add(used)

    def touches(label, series):
        if label in ytc_label:
            return ytc_label[label] in chose.get(series.pk, ())
        return system_of_label.get(label, series.handicap_system) == (
            series.handicap_system
        )

    rows, covered = [], set()
    for series in series_list:
        mine = {
            label: change for label, change in changes.items() if touches(label, series)
        }
        if mine:
            rows.append(row(series, None, series_has_finishes(series), mine))
            covered |= set(mine)
    rest = {label: change for label, change in changes.items() if label not in covered}
    if rest:
        rows.append(row(None, None, False, rest))
    return rows


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


# --- Forms that save audited fields ----------------------------------------------------


class AuditedFormMixin:
    """Works out, while validating, what saving this form would record.

    ``_post_clean`` is where a ModelForm copies the cleaned values onto its
    instance, so straight after it the instance holds the new values and the
    database still holds the old ones. That is the moment to compare them. A
    correction without a reason becomes a validation error, so nothing is saved.
    """

    scoring_changes = ()
    # Where a missing reason's error is shown; None puts it at the top of the form.
    reason_error_field = "reason"

    def _post_clean(self):
        super()._post_clean()
        if self._errors:
            return
        self.scoring_changes = changes_to_save(self.instance)
        if needs_reason(self.scoring_changes) and not self.correction_reason():
            self.add_error(self.reason_error_field, REASON_REQUIRED)

    def correction_reason(self):
        return self.cleaned_data.get("reason", "")


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
    fixed = after.series.is_fixed_number
    places, handicaps = [], []
    for race_results in after.races:
        old = before_races.get(race_results.race.pk)
        if old is None:
            continue
        if _places(old) != _places(race_results):
            places.append(race_results.race.number)
        # No handicap can move in a fixed-number series (slice 24), so none is
        # ever reported as having moved.
        if not fixed and _handicaps(old) != _handicaps(race_results):
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
    nothing = (
        "No places or standings were affected by this change."
        if after.series.is_fixed_number
        else "No places, handicaps, or standings were affected by this change."
    )
    return " ".join(parts) or nothing


def _places(race_results):
    return {
        row.entry.pk: (row.result.position, row.result.points)
        for row in race_results.rows
    }


def _handicaps(race_results):
    return {row.entry.pk: round(row.raced_on, 3) for row in race_results.rows}


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
