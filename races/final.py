"""Declaring a series final, reopening it, and the copy of its results (slice 10).

A final series is locked: every write path that could move its results calls
``check_open`` first and is refused. It is also scored from a copy of the
engine's output saved when it was declared, rather than replayed, so a later
correction to a boat's base number (which every series the boat sails in
shares) can't change a finished season. That copy is the one place derived
results are stored; see docs/decisions.md.
"""

from dataclasses import fields, is_dataclass
from enum import Enum

import nhc
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import notifications, publishing, start_sheet
from .models import ScoringChange, Series

LOCKED = "This series is final. Reopen it to make changes."
NOTHING_SCORED = "Nothing is scored in this series yet, so there are no final standings to declare."
REOPEN_NEEDS_REASON = "Give a reason for reopening the series."
ALREADY_FINAL = "This series is already final."
NOT_FINAL = "This series isn't final."


def check_open(series):
    """Refuse any change to a final series. Every write path calls this first."""
    if series.is_final:
        raise ValidationError(LOCKED)


def check_series_open(series_pk):
    """As check_open, reading the series fresh: a page may have been open a while."""
    check_open(Series.objects.get(pk=series_pk))


def blockers(series, results):
    """What stops the series being declared final, as sentences naming races and boats."""
    if results.error:
        return [results.error]
    if not results.races:
        return [NOTHING_SCORED]
    problems = []
    for race_results in results.races:
        race = race_results.race
        missing = start_sheet.unrecorded(race)
        if missing:
            boats = ", ".join(str(entry.boat) for entry in missing)
            problems.append(f"Race {race.number}: nothing recorded yet for {boats}.")
        elif race.published_at is None:
            problems.append(f"Race {race.number} has results but isn't published yet.")
        elif publishing.amended_since_sent(race):
            problems.append(
                f"Race {race.number} has been corrected since its results were sent: send the updated results first."
            )
    return problems


def not_sailed(results):
    """Races left out of the final standings because nothing was recorded in them."""
    return [race for race, _ in results.unscored]


def declare(series, user, request):
    """Declare the series final: lock it, save the copy, record it, email the owners.

    Returns how many owners are emailed. Raises ValidationError, changing
    nothing, if it's already final or something still blocks it.
    """
    from .scoring import engine_outcome, score_series

    with transaction.atomic():
        series = Series.objects.select_for_update().get(pk=series.pk)
        if series.is_final:
            raise ValidationError(ALREADY_FINAL)
        results = score_series(series)
        problems = blockers(series, results)
        if problems:
            raise ValidationError(problems)
        again = series.scoring_changes.filter(kind=ScoringChange.Kind.FINAL).exists()
        series.declared_final_at = timezone.now()
        series.declared_final_by_name = user.get_username()
        series.final_results = dump(engine_outcome(series))
        series.final_results_sent_at = None
        series.save(update_fields=[
            "declared_final_at", "declared_final_by_name", "final_results", "final_results_sent_at",
        ])
        _history(series, user, "Declared final", {"Final": ["No", "Yes"]})
    return send(series, request, updated=again)


def reopen(series, user, reason):
    """Unlock a final series and drop its copy; it is scored live again. Emails nobody."""
    reason = reason.strip()
    if not reason:
        raise ValidationError(REOPEN_NEEDS_REASON)
    with transaction.atomic():
        series = Series.objects.select_for_update().get(pk=series.pk)
        if not series.is_final:
            raise ValidationError(NOT_FINAL)
        series.declared_final_at = None
        series.declared_final_by_name = ""
        series.final_results = None
        series.final_results_sent_at = None
        series.save(update_fields=[
            "declared_final_at", "declared_final_by_name", "final_results", "final_results_sent_at",
        ])
        _history(series, user, "Reopened", {"Final": ["Yes", "No"]}, reason)


def send(series, request, *, updated):
    """Email the final standings to every owner in the series. Returns how many.

    Only once every email has gone is the series marked sent; a failure leaves
    it unsent, so the committee is offered Send again.
    """
    sent_at = timezone.now()

    def mark_sent():
        Series.objects.filter(pk=series.pk).update(final_results_sent_at=sent_at)

    return notifications.final_standings(series, request, updated=updated, on_sent=mark_sent)


def _history(series, user, description, changes, reason=""):
    # Its own kind, so it neither marks races "amended since sent" nor moves
    # the standings' "Last updated" date: declaring and reopening move no score.
    ScoringChange.objects.create(
        club=series.club,
        series=series,
        user=user,
        user_name=user.get_username(),
        kind=ScoringChange.Kind.FINAL,
        action=ScoringChange.Action.CHANGED,
        description=f"{series}: {description.lower()}",
        changes=changes,
        reason=reason,
    )


# --- The copy of the engine's results ----------------------------------------------


def dump(value):
    """The engine's output as plain JSON: dataclasses to dicts, enums to their values.

    Floats go through JSON unchanged (Python writes the shortest repr that reads
    back as the same float), so the copy scores exactly as the replay did.
    """
    if is_dataclass(value):
        return {field.name: dump(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [dump(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def load(data):
    """Rebuild the engine's SeriesOutcome from ``dump``'s output."""
    return nhc.SeriesOutcome(
        races=tuple(
            nhc.RaceOutcome(race_id=race["race_id"], results=tuple(_result(r) for r in race["results"]))
            for race in data["races"]
        ),
        starting_handicaps=tuple((boat_id, tcf) for boat_id, tcf in data["starting_handicaps"]),
        standings=tuple(
            nhc.BoatStanding(
                boat_id=standing["boat_id"],
                position=standing["position"],
                total=standing["total"],
                scores=tuple(nhc.RaceScore(**score) for score in standing["scores"]),
            )
            for standing in data["standings"]
        ),
    )


def _result(data):
    data = dict(data)
    data["status"] = nhc.RaceStatus(data["status"])
    if data.get("performance") is not None:
        data["performance"] = nhc.Performance(data["performance"])
    return nhc.RaceResult(**data)
