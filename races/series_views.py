"""The race committee's pages for a whole series: its history of changes, and
declaring its results final (slice 10).
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import final, notifications
from .models import ScoringChange, Series
from .roles import committee_required
from .scoring import score_series


@committee_required
def series_history(request, pk):
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
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


# --- Final results (slice 10) ----------------------------------------------------------


@committee_required
def final_page(request, pk):
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
    return render(request, "races/final.html", _final_context(series))


def _final_context(series, reopen_error=""):
    results = score_series(series)
    return {
        "series": series,
        "results": results,
        "blockers": [] if series.is_final else final.blockers(series, results),
        "not_sailed": final.not_sailed(results),
        "history": series.scoring_changes.filter(kind=ScoringChange.Kind.FINAL),
        "reopen_error": reopen_error,
    }


@committee_required
@require_POST
def declare_final(request, pk):
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
    try:
        count = final.declare(series, request.user, request)
    except ValidationError as refused:
        for message in refused.messages:
            messages.error(request, message)
    else:
        messages.success(
            request,
            f"{series} is final. Final standings sent to {notifications.boat_owners(count)}.",
        )
    return redirect("races:final", series.pk)


@committee_required
@require_POST
def reopen_series(request, pk):
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
    try:
        final.reopen(series, request.user, request.POST.get("reason", ""))
    except ValidationError as refused:
        return render(
            request,
            "races/final.html",
            _final_context(series, " ".join(refused.messages)),
        )
    messages.success(
        request,
        f"{series} is reopened. Declare it final again when the corrections are done.",
    )
    return redirect("races:final", series.pk)


@committee_required
@require_POST
def send_final(request, pk):
    """Send the final standings again, after a sending failure."""
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
    if not series.is_final:
        messages.error(request, final.NOT_FINAL)
    else:
        count = final.send(series, request, updated=False)
        series.refresh_from_db()
        if series.final_results_sent_at is not None:
            messages.success(
                request, f"Final standings sent to {notifications.boat_owners(count)}."
            )
    return redirect("races:final", series.pk)
