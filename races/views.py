from datetime import datetime, time

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import approvals, audit, notifications, publishing, race_day, start_sheet
from .forms import DecisionForm, FinishForm, StartSheetRowForm
from .models import NOT_ON_START_SHEET, Boat, BoatRequest, EntryRequest, Finish, Race, Series
from .roles import committee_required
from .scoring import score_series


def ping(request):
    """Example HTMX endpoint: returns an HTML fragment, not a full page."""
    return HttpResponse('pong (htmx)' if request.htmx else 'pong')


@committee_required
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


# --- The race day page (slice 9) -----------------------------------------------
# One page per race, with two views: the start sheet, and finishing. It
# replaces the slice 1 finish-entry page and the slice 6 start sheet page,
# whose addresses now redirect here.

VIEWS = ("start", "finish")


@committee_required
def race_day_page(request, pk):
    race = get_object_or_404(Race.objects.select_related("series"), pk=pk)
    view = request.GET.get("view")
    if view not in VIEWS:
        # Before anyone is racing there is nothing to finish, so open on the start sheet.
        view = "finish" if race.race_entries.exists() else "start"
    since = request.GET.get("since")
    if view == "finish" and since and request.htmx and since == race_day.version(race):
        # The page refreshes itself every few seconds; 204 tells HTMX nothing changed.
        return HttpResponse(status=204)
    return _render_race_day(request, race, view)


def _render_race_day(request, race, view, **extra):
    context = _race_day_context(race, view, **extra)
    target = request.htmx.target if request.htmx else None
    if target == "finish-panel" and view == "finish":
        return render(request, "races/_finish_panel.html", context)
    if target in ("race-day-body", "finish-panel"):
        return render(request, "races/_race_day_body.html", context)
    return render(request, "races/race_day.html", context)


def _race_day_url(race, view):
    return f"{reverse('races:race_day', args=[race.pk])}?view={view}"


@committee_required
def start_sheet_page(request, pk):
    """The slice 6 address: kept working for bookmarks."""
    return redirect(_race_day_url(get_object_or_404(Race, pk=pk), "start"))


@committee_required
def finish_entry(request, pk):
    """The slice 1 address: kept working for bookmarks and old links."""
    return redirect(_race_day_url(get_object_or_404(Race, pk=pk), "finish"))


def _race_day_context(race, view, **extra):
    at = race_day.now()
    context = {
        "race": race,
        "view": view,
        "start_url": _race_day_url(race, "start"),
        "finish_url": _race_day_url(race, "finish"),
        # For the race clock: the site's time now and the start, in epoch ms,
        # so the script can show the site's time whatever the device's clock says.
        "now_ms": int(at.timestamp() * 1000),
        "start_ms": int(race_day.start_moment(race).timestamp() * 1000),
        "now": at,
        "time_zone": settings.TIME_ZONE,
        # The race clock is shown only on the race's own date.
        "is_race_date": at.date() == race.date,
    }
    if view == "start":
        context.update(_start_sheet_context(race, extra.get("bound_form"), extra.get("bound_entry"),
                                            extra.get("refused", "")))
    else:
        context.update(_finishing_context(race, at, **extra))
    return context


def _finishing_context(race, at, bound_form=None, bound_entry=None, message="", error="", touched=None):
    """Still racing (sail-number order), finished (order across the line), not racing."""
    results = score_series(race.series)
    finishes = {finish.entry_id: finish for finish in race.finishes.select_related("race")}
    racing = {race_entry.entry_id: race_entry for race_entry in race.race_entries.all()}
    still_racing, finished, not_racing = [], [], []
    for entry in race.series.entries.select_related("boat"):
        if entry.pk not in racing:
            not_racing.append(entry)
            continue
        finish = finishes.get(entry.pk)
        bound = bound_entry is not None and entry.pk == bound_entry.pk
        row = {
            "entry": entry,
            "race_entry": racing[entry.pk],
            "finish": finish,
            "form": bound_form if bound else FinishForm(instance=finish, prefix=_prefix(entry)),
            "open": bound and bound_form is not None and bool(bound_form.errors),
            "touched": touched is not None and entry.pk == touched.pk,
        }
        if finish is None:
            still_racing.append(row)
        else:
            row["can_undo"] = race_day.can_undo(finish, race)
            finished.append(row)
    if bound_form is not None and bound_form.errors and bound_entry.pk not in racing:
        # A stale page or hand-made request for a boat that isn't racing: it has
        # no row to show the error in, so the panel shows it at the top.
        error = " ".join(message for messages_ in bound_form.errors.values() for message in messages_)
    # Across the line in time order; boats with a code after them, by sail number.
    # Two boats tapped within the same second share a time, so the one saved
    # first - tapped first - comes first. (The list starts in sail-number order,
    # and sort() keeps it for everything else that ties.)
    epoch = timezone.make_aware(datetime.min.replace(year=2000))
    finished.sort(key=lambda row: (
        row["finish"].finish_time is None,
        row["finish"].finish_time or time.min,
        row["finish"].recorded_at or epoch,
    ))
    for number, row in enumerate(r for r in finished if r["finish"].finish_time is not None):
        row["order"] = number + 1
    return {
        "still_racing": still_racing,
        "finished": finished,
        "not_racing": not_racing,
        "can_tap": race_day.can_tap(race, at),
        "note": results.note_for(race),
        "version": race_day.version(race),
        "panel_message": message,
        "panel_error": error,
        **_publishing_context(race),
    }


def _finish_or_page(request, race, **extra):
    """After a change on the Finishing view: the panel over HTMX, else back to the page."""
    if request.htmx:
        return render(request, "races/_finish_panel.html", _race_day_context(race, "finish", **extra))
    if extra.get("error"):
        messages.error(request, extra["error"])
    elif extra.get("message"):
        messages.success(request, extra["message"])
    return redirect(_race_day_url(race, "finish"))


@committee_required
@require_POST
def tap_finish(request, race_pk, entry_pk):
    """The Finished button: record this boat as finishing now."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=race_pk)
    entry = get_object_or_404(race.series.entries.select_related("boat"), pk=entry_pk)
    try:
        finish = race_day.tap(race, entry, request.user)
    except ValidationError as refused:
        return _finish_or_page(request, race, error=" ".join(refused.messages))
    return _finish_or_page(
        request, race, touched=entry, message=f"{entry.boat} {race_day.describe(finish)}."
    )


@committee_required
@require_POST
def undo_finish(request, race_pk, entry_pk):
    """Undo a finish saved in the last two minutes: the boat is racing again."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=race_pk)
    entry = get_object_or_404(race.series.entries.select_related("boat"), pk=entry_pk)
    try:
        race_day.undo(race, entry, request.user)
    except ValidationError as refused:
        return _finish_or_page(request, race, error=" ".join(refused.messages))
    return _finish_or_page(request, race, touched=entry, message=f"Undone: {entry.boat} is racing again.")


@committee_required
@require_POST
def save_finish(request, race_pk, entry_pk):
    """A typed finish time or code, from either list. Each row saves alone."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=race_pk)
    entry = get_object_or_404(race.series.entries.select_related("boat"), pk=entry_pk)
    if not request.htmx and not race.race_entries.filter(entry=entry).exists():
        # The page offers no form for a boat that is not racing, so this is a
        # stale page or a hand-made request. With HTMX, the row shows the
        # form's own error, which says the same.
        messages.error(request, NOT_ON_START_SHEET)
        return redirect(_race_day_url(race, "finish"))
    finish = Finish.objects.filter(race=race, entry=entry).first() or Finish(race=race, entry=entry)
    form = FinishForm(request.POST, instance=finish, prefix=_prefix(entry))
    if not form.is_valid():
        if request.htmx:
            return _finish_or_page(request, race, bound_form=form, bound_entry=entry)
        # Without HTMX, redisplay the whole page with this row's form open.
        return render(request, "races/race_day.html",
                      _race_day_context(race, "finish", bound_form=form, bound_entry=entry))
    before = score_series(race.series)
    # The finish and its history are saved together or not at all.
    with transaction.atomic():
        form.save()
        recorded = audit.record(form.scoring_changes, request.user, form.cleaned_data["reason"])
    message = f"{entry.boat}: {_saved_message(recorded, before, score_series(race.series))}"
    return _finish_or_page(request, race, touched=entry, message=message)


def _saved_message(recorded, before, after):
    if not recorded:
        return "Saved; nothing changed."
    first = "Corrected." if audit.needs_reason(recorded) else "Saved."
    return f"{first} {audit.describe_effect(before, after)}"


def _prefix(entry):
    # Every row is its own form on one page, so field ids need to be unique.
    return f"entry-{entry.pk}"


# --- The start sheet view ------------------------------------------------------


@committee_required
@require_POST
def save_start_sheet_row(request, race_pk, entry_pk):
    """Put one boat on the start sheet, change who is aboard, or take it off."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=race_pk)
    entry = get_object_or_404(race.series.entries.select_related("boat__owner"), pk=entry_pk)
    form = StartSheetRowForm(request.POST, prefix=_prefix(entry))
    message = refused = ""
    if form.is_valid():
        try:
            message = start_sheet.save_row(
                race,
                entry,
                racing=form.cleaned_data["racing"],
                persons_on_board=form.cleaned_data["persons_on_board"],
                request=request,
            )
        except ValidationError as error:
            # The row shows the boat as it really is, still on the sheet.
            refused = " ".join(error.messages)
            form = None
    failed = bool(refused) or (form is not None and form.errors)
    if not request.htmx:
        if not failed:
            messages.success(request, f"{entry.boat}: {message}")
            return redirect(_race_day_url(race, "start"))
        return render(request, "races/race_day.html", _race_day_context(
            race, "start", bound_form=form, bound_entry=entry, refused=refused))
    context = _start_sheet_context(race, form, entry, refused)
    row = next(row for row in context["rows"] if row["entry"].pk == entry.pk)
    return render(
        request,
        "races/_start_sheet_row.html",
        {**context, "row": row, "saved": not failed, "message": message, "update_count": True},
    )


def _start_sheet_context(race, bound_form=None, bound_entry=None, refused=""):
    racing = {race_entry.entry_id: race_entry for race_entry in race.race_entries.all()}
    recorded = set(race.finishes.values_list("entry_id", flat=True))
    rows = []
    for entry in race.series.entries.select_related("boat__owner"):
        race_entry = racing.get(entry.pk)
        this_row = bound_entry is not None and entry.pk == bound_entry.pk
        if this_row and bound_form is not None and bound_form.errors:
            form = bound_form
        else:
            form = StartSheetRowForm(
                initial={
                    "racing": race_entry is not None,
                    "persons_on_board": race_entry.persons_on_board if race_entry else None,
                },
                prefix=_prefix(entry),
            )
        rows.append({
            "entry": entry,
            "form": form,
            "racing": race_entry is not None,
            "has_result": entry.pk in recorded,
            "can_email": notifications.has_owner_to_email(entry.boat),
            "refused": refused if this_row else "",
        })
    return {"race": race, "rows": rows, "racing_count": len(racing), "entry_count": len(rows)}


# --- The committee's requests page -------------------------------------------

REQUEST_MODELS = {"boat": BoatRequest, "entry": EntryRequest}


@committee_required
def requests_page(request):
    pending, decided = [], []
    for kind, model in REQUEST_MODELS.items():
        related = ["requested_by", "boat", "series"] if model is EntryRequest else ["requested_by", "boat"]
        for member_request in model.objects.select_related(*related):
            (pending if member_request.is_pending else decided).append(_request_row(kind, member_request))
    pending.sort(key=lambda row: row["request"].created_at)  # oldest first: first come, first served
    decided.sort(key=lambda row: row["request"].decided_at or row["request"].created_at, reverse=True)
    return render(
        request, "races/requests.html", {"pending": pending, "decided": decided[:50]}
    )


@committee_required
@require_POST
def decide_request(request, kind, pk):
    model = REQUEST_MODELS.get(kind)
    if model is None:
        return HttpResponse(status=404)
    member_request = get_object_or_404(model, pk=pk)
    form = DecisionForm(request.POST)
    error = message = ""
    # Worked out before deciding: once a change is applied, the boat already
    # matches it, and a claim changes who the previous owner was.
    details = approvals.proposed_values(member_request) if kind == "boat" else []
    previous_owner = member_request.boat.owner if kind == "boat" and member_request.boat else None
    boat_name = str(member_request.boat) if member_request.boat_id else None
    if form.is_valid():
        try:
            if form.cleaned_data["decision"] == "approve":
                message = approvals.approve(member_request, request.user, form.cleaned_data["reason"])
            else:
                message = approvals.reject(member_request, request.user, form.cleaned_data["note"])
        except ValidationError as failure:
            error = " ".join(failure.messages)
    else:
        error = "Choose approve or reject."
    member_request.refresh_from_db()
    if not error:
        _email_decision(member_request, request, details, previous_owner, boat_name)
    if not request.htmx:
        if error:
            messages.error(request, error)
        else:
            messages.success(request, message)
        return redirect("races:requests")
    row = _request_row(kind, member_request)
    return render(
        request, "races/_request_row.html", {"row": row, "error": error, "message": message}
    )


def _request_row(kind, member_request):
    return {
        "kind": kind,
        "request": member_request,
        "proposed": approvals.proposed_values(member_request) if kind == "boat" else [],
        # Worked out only while it can still matter, since it replays scores.
        "needs_reason": member_request.is_pending and approvals.needs_reason(member_request),
    }


# --- Publishing results --------------------------------------------------------


@committee_required
@require_POST
def publish_results(request, pk):
    race = get_object_or_404(Race.objects.select_related("series"), pk=pk)
    missing = start_sheet.unrecorded(race)
    if missing:
        messages.error(request, UNRECORDED.format(boats=", ".join(str(entry.boat) for entry in missing)))
    elif score_series(race.series).for_race(race) is None:
        messages.error(request, "There are no results to publish yet: nothing is scored in this race.")
    else:
        updated = request.POST.get("send") == "updated"
        sent_before = race.results_sent_at
        count = (publishing.send_updated if updated else publishing.publish)(race, request)
        race.refresh_from_db()
        # If sending failed, results_sent_at has not moved, and notifications
        # has already said so on the page; claiming success here would contradict it.
        if race.results_sent_at != sent_before:
            first = "Updated results sent" if updated else "Results published and sent"
            messages.success(request, f"{first} to {_owners(count)}.")
    return redirect(_race_day_url(race, "finish"))


def _owners(count):
    return f"{count} boat owner{'s' if count != 1 else ''}"


UNRECORDED = (
    "Not sent: record a time or a code for every boat on the start sheet first. "
    "Still to record: {boats}."
)


def _publishing_context(race):
    race.refresh_from_db(fields=["published_at", "results_sent_at"])
    return {
        "race": race,
        "amended": publishing.amended_since_sent(race),
        "unrecorded": start_sheet.unrecorded(race),
    }


def _email_decision(member_request, request, details, previous_owner, boat_name):
    """The member hears the decision; a claim's previous owner hears they lost the boat.

    The member's own "request approved" email carries what changed, so they are
    not also sent "your boat was updated" or "your boat was entered".
    """
    notifications.request_decided(member_request, request, details, boat_name)
    approved_claim = (
        isinstance(member_request, BoatRequest)
        and member_request.kind == BoatRequest.Kind.CLAIM
        and member_request.status == BoatRequest.Status.APPROVED
    )
    if approved_claim and previous_owner is not None and previous_owner != member_request.requested_by:
        boat = Boat.objects.get(pk=member_request.boat_id)  # as it is now, new owner and all
        notifications.boat_updated(
            boat,
            [("Owner", previous_owner.get_full_name() or previous_owner.get_username(), boat.owner_display)],
            [previous_owner],
            request,
        )
