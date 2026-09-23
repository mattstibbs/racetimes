from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
    return render(request, "races/series_results.html", {"results": score_series(series)})


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
    if saved:
        form.save()
        if not request.htmx:
            return redirect("races:finish_entry", race.pk)
        form = FinishForm(instance=finish, prefix=_prefix(entry))
    elif not request.htmx:
        # Without HTMX, redisplay the whole page with this row's errors.
        return render(request, "races/finish_entry.html", _finish_entry_context(race, form, entry))

    scored = score_series(race.series).for_race(race).for_entry(entry)
    return render(
        request,
        "races/_finish_row.html",
        {"race": race, "row": _row(entry, form, scored), "saved": saved},
    )


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
