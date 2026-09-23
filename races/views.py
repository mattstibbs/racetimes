from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import audit
from .forms import FinishForm
from .models import Finish, Race, Series
from .scoring import score_series


def home(request):
    return render(request, "home.html", {"series_list": Series.objects.all()})


def ping(request):
    """Example HTMX endpoint: returns an HTML fragment, not a full page."""
    return HttpResponse('pong (htmx)' if request.htmx else 'pong')


def series_results(request, pk):
    series = get_object_or_404(Series, pk=pk)
    results = score_series(series)
    # The public sees that a result was corrected, and when, but not who or why.
    corrections = series.scoring_changes.filter(is_correction=True)
    amended = dict(
        corrections.exclude(race=None).order_by().values_list("race").annotate(Max("timestamp"))
    )
    return render(
        request,
        "races/series_results.html",
        {
            "results": results,
            "races": [(r, amended.get(r.race.pk)) for r in results.races],
            # Any correction can move the standings, so the latest of them all.
            "standings_amended": corrections.aggregate(Max("timestamp"))["timestamp__max"],
        },
    )


@staff_member_required
def series_history(request, pk):
    series = get_object_or_404(Series, pk=pk)
    changes = series.scoring_changes.select_related("race")
    race = None
    if request.GET.get("race", "").isdigit():
        race = get_object_or_404(series.races, pk=request.GET["race"])
        changes = changes.filter(race=race)
    return render(
        request,
        "races/series_history.html",
        {"series": series, "race": race, "changes": changes},
    )


@staff_member_required
def finish_entry(request, pk):
    race = get_object_or_404(Race.objects.select_related("series"), pk=pk)
    return render(request, "races/finish_entry.html", _finish_entry_context(race))


@staff_member_required
@require_POST
def save_finish(request, race_pk, entry_pk):
    """Save one boat's row. Each row saves alone, so one bad time loses nothing else."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=race_pk)
    entry = get_object_or_404(race.series.entries.select_related("boat"), pk=entry_pk)
    finish = Finish.objects.filter(race=race, entry=entry).first() or Finish(race=race, entry=entry)
    form = FinishForm(request.POST, instance=finish, prefix=_prefix(entry))

    saved = form.is_valid()
    message = ""
    if saved:
        before = score_series(race.series)
        # The finish and its history are saved together or not at all.
        with transaction.atomic():
            form.save()
            recorded = audit.record(
                form.scoring_changes, request.user, form.cleaned_data["reason"]
            )
        if not request.htmx:
            return redirect("races:finish_entry", race.pk)
        message = _saved_message(recorded, before, score_series(race.series))
        form = FinishForm(instance=finish, prefix=_prefix(entry))
    elif not request.htmx:
        # Without HTMX, redisplay the whole page with this row's errors.
        return render(request, "races/finish_entry.html", _finish_entry_context(race, form, entry))

    scored = score_series(race.series).for_race(race).for_entry(entry)
    return render(
        request,
        "races/_finish_row.html",
        {"race": race, "row": _row(entry, form, scored), "saved": saved, "message": message},
    )


def _saved_message(recorded, before, after):
    if not recorded:
        return "Saved; nothing changed."
    first = "Corrected." if audit.needs_reason(recorded) else "Saved."
    return f"{first} {audit.describe_effect(before, after)}"


def _prefix(entry):
    # Every row is its own form on one page, so field ids need to be unique.
    return f"entry-{entry.pk}"


def _row(entry, form, scored):
    return {"entry": entry, "form": form, "scored": scored}


def _finish_entry_context(race, bound_form=None, bound_entry=None):
    results = score_series(race.series)
    race_results = results.for_race(race) if results.races else None
    rows = []
    # Sail-number order rather than finishing order, so a row stays put while
    # the committee works down the sheet.
    for entry in race.series.entries.select_related("boat"):
        scored = race_results.for_entry(entry)
        if bound_entry is not None and entry.pk == bound_entry.pk:
            form = bound_form
        else:
            form = FinishForm(instance=scored.finish, prefix=_prefix(entry))
        rows.append(_row(entry, form, scored))
    return {"race": race, "rows": rows}
