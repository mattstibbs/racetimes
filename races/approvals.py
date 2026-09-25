"""Applying and rejecting members' requests.

Approving a request makes its change through the same audit code the admin
uses, so it is recorded in the change history under the committee member's
name, and a correction needs a reason exactly as it does in the admin. Nothing
here trusts that the world is as it was when the member asked: everything is
validated again at the moment of approval.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import capfirst

from . import audit, final
from .models import Boat, BoatRequest, EntryRequest, Request, Series, SeriesEntry
from .scoring import score_series

ALREADY_DECIDED = "This request has already been decided."
NOTE_REQUIRED = "Say why, so the member knows. The note is shown to them."


@dataclass(frozen=True)
class Proposed:
    """One field of a boat request, as it is now and as the member wants it."""

    label: str
    current: str
    proposed: str

    @property
    def changed(self):
        return self.current != self.proposed


def proposed_values(request):
    """Each proposed field of a registration or change, old against new."""
    if request.kind == BoatRequest.Kind.CLAIM:
        return []
    rows = []
    for name in BoatRequest.PROPOSED_FIELDS:
        label = capfirst(BoatRequest._meta.get_field(name).verbose_name)
        current = _text(getattr(request.boat, name)) if request.boat else ""
        rows.append(Proposed(label, current, _text(getattr(request, name))))
    return rows


def needs_reason(request):
    """Whether approving this request would be a correction to recorded results."""
    return audit.needs_reason(_audited_changes(request))


def approve(request, user, reason=""):
    """Apply the request, record it, and return a message for the committee."""
    reason = reason.strip()
    with transaction.atomic():
        if isinstance(request, EntryRequest):
            # Slice 10: a final series takes no new entries. Checked first, so
            # the committee is told that rather than asked for a reason.
            final.check_series_open(request.series_id)
        _claim_decision(request, user, Request.Status.APPROVED)
        changes = _audited_changes(request)
        if audit.needs_reason(changes) and not reason:
            raise ValidationError(audit.REASON_REQUIRED)
        before = _scorings_before(request)
        message = _apply(request)
        audit.record(changes, user, reason)
    effects = [
        f"{series}: {audit.describe_effect(scored, score_series(series))}"
        for series, scored in before
    ]
    return " ".join([message, *effects])


def reject(request, user, note):
    note = note.strip()
    if not note:
        raise ValidationError(NOTE_REQUIRED)
    with transaction.atomic():
        _claim_decision(request, user, Request.Status.REJECTED, note)
    return "Rejected. The member can see your note."


def withdraw(request):
    """The member takes back a request the committee has not decided yet."""
    updated = type(request).objects.filter(pk=request.pk, status=Request.Status.PENDING).update(
        status=Request.Status.WITHDRAWN
    )
    if not updated:
        raise ValidationError(ALREADY_DECIDED)


def _claim_decision(request, user, status, note=""):
    # A conditional update, so a double click or two committee members deciding
    # at once cannot both succeed: the second finds the request no longer
    # pending. It runs inside the approval's transaction, so a failed approval
    # leaves the request pending.
    updated = type(request).objects.filter(pk=request.pk, status=Request.Status.PENDING).update(
        status=status,
        decided_by=user,
        decided_by_name=user.get_username(),
        decided_at=timezone.now(),
        committee_note=note,
    )
    if not updated:
        raise ValidationError(ALREADY_DECIDED)


def _audited_changes(request):
    """The change-history rows approving would record, before anything is saved."""
    if isinstance(request, EntryRequest):
        return audit.changes_to_save(SeriesEntry(series=request.series, boat=request.boat))
    if request.kind == BoatRequest.Kind.CHANGE:
        return audit.changes_to_save(_changed_boat(request))
    # A new boat moves no result until it is entered, and a new owner none at all.
    return []


def _scorings_before(request):
    """Each series whose results approving could move, scored as it stands now."""
    if isinstance(request, EntryRequest):
        series_list = [request.series]
    elif request.kind == BoatRequest.Kind.CHANGE:
        series_list = list(Series.objects.filter(entries__boat=request.boat).distinct())
    else:
        series_list = []
    return [(series, score_series(series)) for series in series_list if audit.series_has_finishes(series)]


def _apply(request):
    if isinstance(request, EntryRequest):
        entry = SeriesEntry(series=request.series, boat=request.boat)
        entry.full_clean()
        entry.save()
        return f"{request.boat} is entered in {request.series}."
    if request.kind == BoatRequest.Kind.REGISTER:
        boat = Boat(owner=request.requested_by, **_proposed(request))
        boat.full_clean()
        boat.save()
        return f"{boat} is registered to {boat.owner_display}."
    if request.kind == BoatRequest.Kind.CHANGE:
        boat = _changed_boat(request)
        boat.full_clean()
        boat.save()
        return f"{boat} is updated."
    boat = request.boat
    boat.owner = request.requested_by
    boat.save()
    return f"{boat} is now owned by {boat.owner_display}."


def _changed_boat(request):
    boat = Boat.objects.get(pk=request.boat_id)
    for name, value in _proposed(request).items():
        setattr(boat, name, value)
    return boat


def _proposed(request):
    return {name: getattr(request, name) for name in BoatRequest.PROPOSED_FIELDS}


def _text(value):
    return "" if value is None else str(value)
