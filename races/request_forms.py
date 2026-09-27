"""Members' change requests (slice 3): registering, claiming or changing a boat,
and entering a series; and the committee's decision on one.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Value
from django.db.models.functions import Replace, Upper

from .models import Boat, BoatRequest, Series


class _BoatDetailsForm(forms.ModelForm):
    """A boat as the member wants it to be: for a registration or a change."""

    class Meta:
        model = BoatRequest
        fields = [*BoatRequest.PROPOSED_FIELDS, "member_note"]
        labels = {"member_note": "Note for the race committee (optional)"}
        help_texts = {
            "base_number": "From your RYA NHC certificate. The race committee checks it.",
        }

    # The boat this request is about, if any; excluded from the sail-number check.
    boat = None

    def __init__(self, *args, club, **kwargs):
        # The club the boat is (or will be) registered with (slice 11).
        self.club = club
        super().__init__(*args, **kwargs)
        for name in ["sail_number", "base_number"]:
            self.fields[name].required = True

    def clean_sail_number(self):
        sail_number = self.cleaned_data["sail_number"].strip()
        self.existing_boat = boat_with_sail_number(
            self.club, sail_number, exclude=self.boat
        )
        if self.existing_boat is not None:
            raise ValidationError(
                f"{self.existing_boat} is already registered with the club."
            )
        return sail_number


def boat_with_sail_number(club, sail_number, exclude=None):
    """The club's boat with this sail number, ignoring case and spaces, or None.

    The same comparison as the boat's unique constraint, so the two agree. Only
    within the club: two clubs can each have a GBR 42 (slice 11).
    """
    boats = Boat.objects.for_club(club)
    if exclude is not None:
        boats = boats.exclude(pk=exclude.pk)
    return (
        boats.annotate(normalised=Upper(Replace("sail_number", Value(" "), Value(""))))
        .filter(normalised=sail_number.replace(" ", "").upper())
        .first()
    )


class BoatRegistrationForm(_BoatDetailsForm):
    pass


class BoatChangeForm(_BoatDetailsForm):
    """Starts from the boat's current details; the member edits what should change."""

    def __init__(self, *args, boat, **kwargs):
        self.boat = boat
        initial = {name: getattr(boat, name) for name in BoatRequest.PROPOSED_FIELDS}
        super().__init__(*args, initial=initial, club=boat.club, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if not self.errors and all(
            cleaned.get(name) == getattr(self.boat, name)
            for name in BoatRequest.PROPOSED_FIELDS
        ):
            raise ValidationError(
                "Nothing has changed. Edit the details that are wrong."
            )
        return cleaned


class EntryRequestForm(forms.Form):
    series = forms.ModelChoiceField(queryset=Series.objects.none(), empty_label=None)
    member_note = forms.CharField(
        label="Note for the race committee (optional)", required=False, max_length=500
    )

    def __init__(self, *args, boat, **kwargs):
        super().__init__(*args, **kwargs)
        # Series the boat is not in and has not already asked to join.
        # Only the boat's own club's series (slice 11).
        self.fields["series"].queryset = (
            Series.objects.for_club(boat.club)
            .exclude(entries__boat=boat)
            .exclude(
                entry_requests__boat=boat,
                entry_requests__status=BoatRequest.Status.PENDING,
            )
        )


class DecisionForm(forms.Form):
    """The committee's approve-or-reject on one request."""

    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    reason = forms.CharField(required=False, max_length=500)
    note = forms.CharField(required=False, max_length=500)
