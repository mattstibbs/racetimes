"""The race office's forms for setting up boats (slice 18).

The Django admin uses the same forms through thin subclasses
(``races/admin_forms.py``), so the rules live in one place whichever page a
boat is changed on. Each form works out, while validating, what saving it
would record in the history (``races/audit.py``), and requires a reason for a
correction.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from . import audit, notifications
from .audit import AuditedFormMixin
from .models import Boat, ClubMembership, Series
from .request_forms import boat_with_sail_number
from .scoring import score_series

REASON_HELP = "Required when correcting results already recorded."


def reason_field():
    return forms.CharField(
        label="Reason for change", required=False, max_length=500, help_text=REASON_HELP
    )


class OwnerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        # Name and email, as the Club members page shows people: two members
        # can share a name.
        name = user.get_full_name()
        return f"{name} ({user.email})" if name else user.get_username()


def owner_choices(club):
    """Only this club's approved members can own its boats (slice 11)."""
    return (
        get_user_model()
        .objects.filter(
            is_active=True,
            memberships__club=club,
            memberships__status=ClubMembership.Status.APPROVED,
        )
        .order_by("first_name", "last_name")
    )


def series_of(boat):
    """The series a boat is entered in."""
    if boat.pk is None:
        return []
    return list(
        Series.objects.for_club(boat.club).filter(entries__boat=boat).distinct()
    )


def boat_has_results(boat):
    """Whether a change to this boat's base number would be a correction."""
    return any(audit.series_has_finishes(series) for series in series_of(boat))


def boat_changes(before, after):
    """(label, old, new) for every field that differs between two versions of a boat."""
    changes = []
    for field in Boat._meta.concrete_fields:
        if field.primary_key:
            continue
        name = field.attname
        if getattr(before, name) == getattr(after, name):
            continue
        if field.name == "owner":
            old, new = before.owner_display or "", after.owner_display or ""
        else:
            old, new = getattr(before, field.name), getattr(after, field.name)
        label = field.verbose_name[:1].upper() + field.verbose_name[1:]
        changes.append(
            (label, "" if old is None else str(old), "" if new is None else str(new))
        )
    return changes


class BoatForm(AuditedFormMixin, forms.ModelForm):
    """A boat, as the race committee sets it up.

    The reason box appears only when the boat has results in some series, the
    one case where changing its base number is a correction (slice 18). The
    admin's subclass always shows it.
    """

    owner = OwnerChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        help_text="A member of the club, who then sees the boat under My boats.",
    )

    # The club a new boat belongs to: passed in by the race office, set on the
    # class by the admin (races/admin.py). A row's club is never a field
    # anyone can edit.
    club = None

    class Meta:
        model = Boat
        fields = [
            "sail_number",
            "name",
            "make",
            "model",
            "owner_name",
            "owner",
            "length_overall_m",
            "waterline_length_m",
            "base_number",
        ]
        help_texts = {"owner_name": "For a boat whose owner has no account here."}

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        club = club or self.club
        if club is not None and self.instance.club_id is None:
            self.instance.club = club
        if self.instance.club_id is not None:
            self.fields["owner"].queryset = owner_choices(self.instance.club)
        if "reason" not in self.fields and boat_has_results(self.instance):
            self.fields["reason"] = reason_field()
        if "reason" not in self.fields:
            # Without the box a correction can't happen, but say so at the
            # top of the form rather than fail if one somehow did.
            self.reason_error_field = None

    def clean_sail_number(self):
        # The unique-in-club constraint can't be checked by the form itself,
        # because club isn't one of its fields, so it's checked here instead.
        sail_number = self.cleaned_data["sail_number"]
        existing = boat_with_sail_number(
            self.instance.club,
            sail_number,
            exclude=self.instance if self.instance.pk else None,
        )
        if existing is not None:
            raise ValidationError("A boat with this sail number is already registered.")
        return sail_number

    def save_audited(self, request):
        """Save the boat, record its history, email its owner, and say what moved.

        Call inside a transaction, once the form is valid, so the boat and its
        history rows are saved together or not at all.
        """
        boat = self.instance
        stored = (
            Boat.objects.for_club(boat.club).select_related("owner").get(pk=boat.pk)
            if boat.pk
            else None
        )
        series_list = series_of(boat)
        before = {series.pk: score_series(series) for series in series_list}
        boat.save()
        if stored is not None:
            # The owner hears about any change the committee makes to their
            # boat; if the owner itself changed, the previous owner hears too.
            owners = [boat.owner]
            if stored.owner_id != boat.owner_id:
                owners.append(stored.owner)
            notifications.boat_updated(
                boat, boat_changes(stored, boat), owners, request
            )
        recorded = audit.record(
            self.scoring_changes, request.user, self.cleaned_data.get("reason", "")
        )
        if audit.needs_reason(recorded):
            for series in series_list:
                effect = audit.describe_effect(before[series.pk], score_series(series))
                messages.info(request, f"{series}: {effect}")
        return boat
