from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import approvals, audit, notifications, publishing, start_sheet
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


@committee_required
def finish_entry(request, pk):
    race = get_object_or_404(Race.objects.select_related("series"), pk=pk)
    return render(request, "races/finish_entry.html", _finish_entry_context(race))


@committee_required
@require_POST
def save_finish(request, race_pk, entry_pk):
    """Save one boat's row. Each row saves alone, so one bad time loses nothing else."""
    race = get_object_or_404(Race.objects.select_related("series"), pk=race_pk)
    entry = get_object_or_404(race.series.entries.select_related("boat"), pk=entry_pk)
    if not request.htmx and not race.race_entries.filter(entry=entry).exists():
        # The page offers no row for a boat that is not racing, so this is a
        # stale page or a hand-made request. With HTMX, the row shows the
        # form's own error, which says the same.
        messages.error(request, NOT_ON_START_SHEET)
        return redirect("races:finish_entry", race.pk)
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

    results = score_series(race.series)
    return render(
        request,
        "races/_finish_row.html",
        {
            "race": race,
            "row": _row(
                entry,
                form,
                results.for_race(race),
                _saved_finish(race, entry),
                race.race_entries.filter(entry=entry).first(),
            ),
            "saved": saved,
            "message": message,
            # Saving a row can change whether the race is scored at all, so the
            # page's note is sent back too, and HTMX swaps it in by id.
            "note": results.note_for(race),
            "update_note": True,
            **_publishing_context(race),
        },
    )


def _saved_message(recorded, before, after):
    if not recorded:
        return "Saved; nothing changed."
    first = "Corrected." if audit.needs_reason(recorded) else "Saved."
    return f"{first} {audit.describe_effect(before, after)}"


def _prefix(entry):
    # Every row is its own form on one page, so field ids need to be unique.
    return f"entry-{entry.pk}"


def _saved_finish(race, entry):
    return Finish.objects.select_related("race").filter(race=race, entry=entry).first()


def _row(entry, form, race_results, finish, race_entry):
    """One row of the finish-entry page.

    ``result`` is the engine's view of this boat in this race, or None when the
    race is not scored yet; ``finish`` is what is saved, whether scored or not;
    ``race_entry`` is its start sheet row, which holds persons on board.
    """
    result = race_results.for_entry(entry).result if race_results else None
    return {"entry": entry, "form": form, "finish": finish, "result": result, "race_entry": race_entry}


def _finish_entry_context(race, bound_form=None, bound_entry=None):
    results = score_series(race.series)
    race_results = results.for_race(race)
    finishes = {finish.entry_id: finish for finish in race.finishes.select_related("race")}
    racing = {race_entry.entry_id: race_entry for race_entry in race.race_entries.all()}
    rows, not_racing = [], []
    # Sail-number order rather than finishing order, so a row stays put while
    # the committee works down the sheet. Only boats on the start sheet get a
    # row to fill in; the rest stayed at home and score DNC.
    for entry in race.series.entries.select_related("boat"):
        if entry.pk not in racing:
            not_racing.append(entry)
            continue
        finish = finishes.get(entry.pk)
        if bound_entry is not None and entry.pk == bound_entry.pk:
            form = bound_form
        else:
            form = FinishForm(instance=finish, prefix=_prefix(entry))
        rows.append(_row(entry, form, race_results, finish, racing[entry.pk]))
    return {
        "race": race,
        "rows": rows,
        "not_racing": not_racing,
        "note": results.note_for(race),
        **_publishing_context(race),
    }


# --- The start sheet ---------------------------------------------------------


@committee_required
def start_sheet_page(request, pk):
    race = get_object_or_404(Race.objects.select_related("series"), pk=pk)
    return render(request, "races/start_sheet.html", _start_sheet_context(race))


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
            return redirect("races:start_sheet", race.pk)
        return render(
            request, "races/start_sheet.html", _start_sheet_context(race, form, entry, refused)
        )
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
    return redirect("races:finish_entry", race.pk)


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
