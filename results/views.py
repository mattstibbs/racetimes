"""The public results pages: home, a series, and a boat.

Every view is GET-only and every HTMX interaction goes to the same URL as its
full page. When ``request.htmx`` names one of the page's parts as its target,
the view renders just that part; otherwise it renders the whole page, which
shows the same thing. So every state has a link that can be shared, and the
pages work with JavaScript off.
"""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from django.db.models import F, Max, Q, Value
from django.db.models.functions import Replace, Upper
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_safe

from races.models import Boat, ScoringChange, Series
from races.publishing import amended_since_sent
from races.roles import is_member
from races.scoring import score_series

from . import export

# The home page shows the latest race of this many series, most recent first.
LATEST_SERIES = 5
# A search shows at most this many boats; typing more narrows it down.
MAX_MATCHES = 20


def _render(request, template, fragments, context):
    """The whole page, or just the part an HTMX request targets.

    ``fragments`` maps an element id on the page to the template that renders
    that element. A history restore (the back button, when HTMX has not kept
    the page) asks for the whole page, so it gets it.
    """
    htmx = request.htmx
    if htmx and not htmx.history_restore_request and htmx.target in fragments:
        template = fragments[htmx.target]
    response = render(request, template, context)
    # The same URL answers with a fragment or a whole page, so caches must
    # tell them apart.
    patch_vary_headers(response, ["HX-Request", "HX-Target"])
    return response


# --- Home ----------------------------------------------------------------------


@require_safe
def home(request):
    query = request.GET.get("q", "").strip()
    context = {
        "query": query,
        "searched": "q" in request.GET,
        "matches": search_boats(request.club, query) if query else None,
        "max_matches": MAX_MATCHES,
    }
    if not (request.htmx and request.htmx.target == "boat-matches"):
        context.update(
            latest=latest_results(request.club),
            series_list=Series.objects.for_club(request.club).annotate(latest=Max("races__date")).order_by(
                F("latest").desc(nulls_last=True), "name"
            ),
            my_boats=request.user.boats.filter(club=request.club) if is_member(request.user) else None,
        )
    return _render(request, "results/home.html", {"boat-matches": "results/_boat_matches.html"}, context)


def search_boats(club, query):
    """Boats whose sail number or name contains the query.

    Sail numbers match ignoring case and spaces, as the database already
    treats them, so "gbr1234" finds "GBR 1234". At most MAX_MATCHES + 1 are
    returned, so the page can say there are more.
    """
    squashed = query.replace(" ", "").upper()
    return list(
        Boat.objects.for_club(club).annotate(squashed=Upper(Replace("sail_number", Value(" "), Value(""))))
        .filter(Q(squashed__contains=squashed) | Q(name__icontains=query))
        .order_by("sail_number")[: MAX_MATCHES + 1]
    )


def latest_results(club):
    """Each series' most recent scored race, newest first, with its top three."""
    recent = (
        Series.objects.for_club(club).annotate(sailed=Max("races__date", filter=Q(races__finishes__isnull=False)))
        .filter(sailed__isnull=False)
        .order_by("-sailed", "name")[:LATEST_SERIES]
    )
    latest = []
    for series in recent:
        results = score_series(series)
        if results.races:
            race_results = results.races[-1]
            latest.append({"race": race_results.race, "podium": race_results.rows[:3]})
    return latest


# --- Series --------------------------------------------------------------------


@require_safe
def series(request, pk):
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
    results = score_series(series)
    races = list(series.races.order_by("number"))
    boats = sorted((entry.boat for entry in series.entries.select_related("boat")),
                   key=lambda boat: boat.sail_number)

    race = _chosen_race(request, races, results)
    followed = _chosen_boat(request, boats)
    detail = request.GET.get("detail") == "1"

    def link(**changes):
        """This page's URL with the given choices changed and the others kept."""
        choices = {"race": race.number if race else None,
                   "boat": followed.pk if followed else None,
                   "detail": 1 if detail else None} | changes
        return "?" + urlencode({k: v for k, v in choices.items() if v is not None})

    context = {
        "series": series,
        "results": results,
        "boats": boats,
        "followed": followed,
        "detail": detail,
        "race_links": [{"race": r, "url": link(race=r.number), "current": r == race} for r in races],
        "detail_url": link(detail=None if detail else 1),
        "section": _race_section(race, results) if race else None,
        # Any correction can move the standings, so the latest of them all.
        "standings_amended": series.scoring_changes.filter(is_correction=True)
        .exclude(kind=ScoringChange.Kind.FINAL)
        .aggregate(Max("timestamp"))["timestamp__max"],
    }
    # Choosing a race, following a boat and showing more detail all swap the
    # whole of #series-body, so the choices in it can never disagree.
    return _render(request, "results/series.html", {"series-body": "results/_series_body.html"}, context)


def _chosen_race(request, races, results):
    """The race asked for by number, else the latest with results, else the first."""
    number = request.GET.get("race", "")
    if number:
        chosen = next((r for r in races if str(r.number) == number), None)
        if chosen is None:
            raise Http404("No such race in this series.")
        return chosen
    if results.races:
        return results.races[-1].race
    return races[0] if races else None


def _chosen_boat(request, boats):
    """The boat being followed, which must be entered in the series."""
    pk = request.GET.get("boat", "")
    if not pk:
        return None
    chosen = next((b for b in boats if str(b.pk) == pk), None)
    if chosen is None:
        raise Http404("That boat is not entered in this series.")
    return chosen


def _race_section(race, results):
    # The public sees that a result was corrected, and when, but not who or why.
    corrections = race.scoring_changes.filter(is_correction=True)
    return {
        "race": race,
        "results": results.for_race(race),
        "note": results.note_for(race),
        "amended_on": corrections.aggregate(Max("timestamp"))["timestamp__max"],
        # Corrected since the owners were emailed: the version they have is out
        # of date until the committee sends the update.
        "changed_since_sent": race.published_at is not None and amended_since_sent(race),
    }


# --- Boat ----------------------------------------------------------------------


@dataclass
class RaceLine:
    """One race of a series, as the boat page shows it."""

    race: object
    row: object = None  # the boat's BoatRaceResult, if the race is scored
    points_discarded: bool = False
    note: str = ""  # why the race has no results, if it has none


@require_safe
def series_csv(request, pk):
    """The series' standings and every race's results as one CSV file, for anyone."""
    series = get_object_or_404(Series.objects.for_club(request.club), pk=pk)
    response = HttpResponse(
        export.series_csv(series, score_series(series)), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{export.filename(series)}"'
    return response


@require_safe
def boat(request, pk):
    boat = get_object_or_404(Boat.objects.for_club(request.club), pk=pk)
    entries = list(boat.series_entries.select_related("series"))
    histories = [_history(entry) for entry in entries]
    # Newest series first. A series with no races yet goes at the top, as it
    # is the one about to start.
    histories.sort(key=lambda h: (h["last_date"] is None, h["last_date"] or date.min), reverse=True)
    return _render(request, "results/boat.html", {}, {"boat": boat, "histories": histories})


def _history(entry):
    series = entry.series
    results = score_series(series)
    races = list(series.races.order_by("number"))
    standing = next((row for row in results.standings if row.entry.pk == entry.pk), None)
    discarded = {cell.race.pk: cell.discarded for cell in standing.scores} if standing else {}

    lines = []
    for race in races:
        race_results = results.for_race(race)
        if race_results is None:
            lines.append(RaceLine(race=race, note=results.note_for(race)))
        else:
            lines.append(RaceLine(race=race, row=race_results.for_entry(entry),
                                  points_discarded=discarded.get(race.pk, False)))
    return {
        "series": series,
        "error": results.error,
        "standing": standing,
        "fleet": len(results.standings),
        "lines": lines,
        "has_provisional": any(line.row and not line.race.published_at for line in lines),
        "has_not_recorded": any(line.row and line.row.not_recorded for line in lines),
        "next": _next_handicap(entry, results, races),
        "last_date": races[-1].date if races else None,
    }


def _next_handicap(entry, results, races):
    """What the boat sails on next: {"race": the next race or None, "tcf": ...}.

    After the last scored race it is that race's next handicap, which every
    later race starts from. Before any race is scored, a series starts on base
    numbers. None if the series cannot be scored.
    """
    if results.error:
        return None
    if not results.races:
        return {"race": races[0] if races else None, "tcf": entry.boat.base_number, "base": True}
    last = results.races[-1]
    later = [race for race in races if race.number > last.race.number]
    return {
        "race": later[0] if later else None,
        "after": last.race,
        "tcf": last.for_entry(entry).result.effective_next_tcf,
        "base": False,
    }
