"""The race committee's Change requests page: approving or rejecting what
members ask for (slice 3). Members make the requests in ``member_views``;
``approvals`` applies an approved one.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import approvals, notifications
from .models import Boat, BoatRequest, EntryRequest
from .request_forms import DecisionForm
from .roles import committee_required

REQUEST_MODELS = {"boat": BoatRequest, "entry": EntryRequest}


@committee_required
def requests_page(request):
    pending, decided = [], []
    for kind, model in REQUEST_MODELS.items():
        related = (
            ["requested_by", "boat", "series"]
            if model is EntryRequest
            else ["requested_by", "boat"]
        )
        for member_request in model.objects.for_club(request.club).select_related(
            *related
        ):
            (pending if member_request.is_pending else decided).append(
                _request_row(kind, member_request)
            )
    pending.sort(
        key=lambda row: row["request"].created_at
    )  # oldest first: first come, first served
    decided.sort(
        key=lambda row: row["request"].decided_at or row["request"].created_at,
        reverse=True,
    )
    return render(
        request, "races/requests.html", {"pending": pending, "decided": decided[:50]}
    )


@committee_required
@require_POST
def decide_request(request, kind, pk):
    model = REQUEST_MODELS.get(kind)
    if model is None:
        return HttpResponse(status=404)
    member_request = get_object_or_404(model.objects.for_club(request.club), pk=pk)
    form = DecisionForm(request.POST)
    error = message = ""
    # Worked out before deciding: once a change is applied, the boat already
    # matches it, and a claim changes who the previous owner was.
    details = approvals.proposed_values(member_request) if kind == "boat" else []
    previous_owner = (
        member_request.boat.owner if kind == "boat" and member_request.boat else None
    )
    boat_name = str(member_request.boat) if member_request.boat_id else None
    if form.is_valid():
        try:
            if form.cleaned_data["decision"] == "approve":
                message = approvals.approve(
                    member_request, request.user, form.cleaned_data["reason"]
                )
            else:
                message = approvals.reject(
                    member_request, request.user, form.cleaned_data["note"]
                )
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
        request,
        "races/_request_row.html",
        {"row": row, "error": error, "message": message},
    )


def _request_row(kind, member_request):
    return {
        "kind": kind,
        "request": member_request,
        "proposed": approvals.proposed_values(member_request) if kind == "boat" else [],
        # Worked out only while it can still matter, since it replays scores.
        "needs_reason": member_request.is_pending
        and approvals.needs_reason(member_request),
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
    if (
        approved_claim
        and previous_owner is not None
        and previous_owner != member_request.requested_by
    ):
        boat = Boat.objects.for_club(request.club).get(
            pk=member_request.boat_id
        )  # as it is now, new owner and all
        notifications.boat_updated(
            boat,
            [
                (
                    "Owner",
                    previous_owner.get_full_name() or previous_owner.get_username(),
                    boat.owner_display,
                )
            ],
            [previous_owner],
            request,
        )
