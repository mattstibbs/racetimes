"""The race office's forms for setting up boats, series and races (slice 18).

The Django admin uses the boat and series forms through thin subclasses
(``races/admin_forms.py``), so the rules live in one place whichever page a
boat or series is changed on. Each form works out, while validating, what saving it
would record in the history (``races/audit.py``), and requires a reason for a
correction.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from . import audit, final, notifications
from .audit import AuditedFormMixin
from .models import Boat, ClubMembership, Race, Series
from .request_forms import boat_with_sail_number
from .scoring import score_series

REASON_HELP = "Required when correcting results already recorded."


def reason_field():
    return forms.CharField(
        label="Reason for change", required=False, max_length=500, help_text=REASON_HELP
    )


class ReasonWhereItAppliesMixin(AuditedFormMixin):
    """Adds the reason box only when saving could be a correction (slice 18).

    Worked out each time the form is built, so a result recorded while the
    form was open adds the box on the next submit rather than losing the
    requirement. A form that declares ``reason`` itself (the admin's) always
    shows it.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "reason" not in self.fields and self.reason_applies():
            self.fields["reason"] = reason_field()
        if "reason" not in self.fields:
            # Without the box a correction can't happen, but say so at the
            # top of the form rather than fail if one somehow did.
            self.reason_error_field = None

    def reason_applies(self):
        raise NotImplementedError


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


class BoatForm(ReasonWhereItAppliesMixin, forms.ModelForm):
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

    def reason_applies(self):
        return boat_has_results(self.instance)

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


# --- Series ---------------------------------------------------------------------------


class SeriesForm(ReasonWhereItAppliesMixin, forms.ModelForm):
    """A series' name and scoring rules. The admin's subclass always shows the reason box."""

    club = None  # as for BoatForm

    class Meta:
        model = Series
        # Every editable field. Listed, not "__all__", so a new field is shown
        # only once someone decides it belongs here.
        fields = [
            "name",
            "series_type",
            "discards",
            "minimum_finishers",
            "apply_a5_3",
            "nhc_cap_extremes",
            "nhc_realign_to_base",
        ]

    SCORING_RULES = [
        "discards",
        "minimum_finishers",
        "apply_a5_3",
        # Slice 14: the optional extra NHC steps (nhc/options.py).
        "nhc_cap_extremes",
        "nhc_realign_to_base",
    ]

    # A final series can still be renamed: a name moves no score (slice 10).
    UNLOCKED_FIELDS = {"name", "reason"}

    def __init__(self, *args, club=None, **kwargs):
        super().__init__(*args, **kwargs)
        club = club or self.club
        if club is not None and self.instance.club_id is None:
            self.instance.club = club

    def reason_applies(self):
        return audit.series_has_finishes(self.instance)

    def groups(self):
        """The fields as the page shows them: the series, then its scoring rules."""
        rules = [self[name] for name in self.SCORING_RULES]
        rest = [field for field in self if field.name not in self.SCORING_RULES]
        return [
            (None, [f for f in rest if f.name != "reason"]),
            ("Scoring rules", rules),
        ]

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and set(self.changed_data) - self.UNLOCKED_FIELDS:
            try:
                final.check_series_open(self.instance.pk)
            except ValidationError as locked:
                raise ValidationError(locked.messages) from None
        return cleaned

    def save_audited(self, request):
        """Save the series and its history; after a correction, say what it moved.

        Call inside a transaction, once the form is valid.
        """
        series = self.instance
        before = (
            score_series(Series.objects.for_club(series.club).get(pk=series.pk))
            if series.pk
            else None
        )
        series.save()
        recorded = audit.record(
            self.scoring_changes, request.user, self.cleaned_data.get("reason", "")
        )
        if before is not None and audit.needs_reason(recorded):
            effect = audit.describe_effect(before, score_series(series))
            messages.info(request, f"Correction recorded. {effect}")
        return series


# --- Races ----------------------------------------------------------------------------


def next_race_number(series):
    """One more than the highest race number in the series, or 1."""
    numbers = series.races.values_list("number", flat=True)
    return max(numbers, default=0) + 1


class RaceForm(ReasonWhereItAppliesMixin, forms.ModelForm):
    """One race of a series: its number, date and start time."""

    class Meta:
        model = Race
        fields = ["number", "date", "start_time"]
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            # step=1 makes browsers offer seconds, which a start may need.
            "start_time": forms.TimeInput(
                format="%H:%M:%S", attrs={"type": "time", "step": "1"}
            ),
        }

    def __init__(self, *args, series, **kwargs):
        instance = kwargs.setdefault("instance", Race())
        if instance.series_id is None:
            instance.series = series
        if instance.pk is None:
            kwargs.setdefault("initial", {"number": next_race_number(series)})
        super().__init__(*args, **kwargs)

    def reason_applies(self):
        # Renumbering or re-timing a race is a correction once it has results.
        return self.instance.pk is not None and self.instance.finishes.exists()

    def clean_number(self):
        # The unique rule includes the series, which isn't a field here, so the
        # form can't check it itself. A clear refusal rather than a swap
        # feature: renumbering is rare (slice 18).
        number = self.cleaned_data["number"]
        taken = self.instance.series.races.filter(number=number).exclude(
            pk=self.instance.pk
        )
        if taken.exists():
            raise ValidationError(f"Race {number} already exists in this series.")
        return number

    def clean(self):
        cleaned = super().clean()
        try:
            final.check_series_open(self.instance.series_id)
        except ValidationError as locked:
            raise ValidationError(locked.messages) from None
        return cleaned
