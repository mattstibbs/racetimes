"""Members' change requests (slice 3): registering, claiming or changing a boat,
and entering a series; and the committee's decision on one.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Value
from django.db.models.functions import Replace, Upper

from .models import YTC_NUMBER_FIELDS, Boat, BoatRequest, Series, SeriesEntry


class _BoatDetailsForm(forms.ModelForm):
    """A boat as the member wants it to be: for a registration or a change."""

    class Meta:
        model = BoatRequest
        fields = [*BoatRequest.PROPOSED_FIELDS, "member_note"]
        labels = {"member_note": "Note for the race committee (optional)"}
        help_texts = {
            "base_number": (
                "From your RYA NHC certificate. Needed to enter an NHC series. "
                "The race committee checks it."
            ),
            "py_number": (
                "Your Portsmouth Number. Needed to enter a Portsmouth Yardstick "
                "series. The race committee checks it."
            ),
            "ytc_number": (
                "From your RYA YTC certificate. Needed to enter an RYA YTC series "
                "on it. The race committee checks it."
            ),
            "ytc_number_non_spinnaker": (
                "The non-spinnaker (white sail) number on your RYA YTC "
                "certificate. The race committee checks it."
            ),
        }

    # The boat this request is about, if any; excluded from the sail-number check.
    boat = None

    def __init__(self, *args, club, **kwargs):
        # The club the boat is (or will be) registered with (slice 11).
        self.club = club
        super().__init__(*args, **kwargs)
        self.fields["sail_number"].required = True

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

    def clean(self):
        cleaned = super().clean()
        # Slice 24: no number is required on its own, but a boat needs one to
        # race on at all (slice 25 adds the two YTC numbers).
        names = ("base_number", "py_number", *YTC_NUMBER_FIELDS)
        if not self.errors and all(cleaned.get(name) is None for name in names):
            raise ValidationError(
                "Give a number for your boat to race on: its NHC base number, "
                "Portsmouth Number or YTC number."
            )
        return cleaned


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
    ytc_number_used = forms.ChoiceField(
        label="Number to race on (RYA YTC series only)",
        required=False,
        choices=[
            ("", "The boat's YTC number if she has one"),
            *SeriesEntry.NumberUsed.choices,
        ],
        help_text="A boat with both YTC numbers races on one of them for the whole series.",
    )
    member_note = forms.CharField(
        label="Note for the race committee (optional)", required=False, max_length=500
    )

    def __init__(self, *args, boat, **kwargs):
        super().__init__(*args, **kwargs)
        self.boat = boat
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

    def clean_series(self):
        # Slice 24: a request the committee could never approve is refused now,
        # with a way forward, rather than left waiting.
        series = self.cleaned_data["series"]
        if series.boats_lack(self.boat):
            raise ValidationError(
                f"{self.boat} has no {series.number_label}, which this "
                f"{series.get_handicap_system_display()} series needs. Ask for a "
                "change to your boat's details first, to add it."
            )
        return series

    def clean(self):
        cleaned = super().clean()
        series = cleaned.get("series")
        if series is None or series.handicap_system != Series.HandicapSystem.YTC:
            # The choice means nothing outside a YTC series.
            cleaned["ytc_number_used"] = SeriesEntry.NumberUsed.SPINNAKER
            return cleaned
        used = cleaned.get("ytc_number_used") or SeriesEntry.default_number_used(
            self.boat
        )
        field = {v: k for k, v in YTC_NUMBER_FIELDS.items()}[used]
        if getattr(self.boat, field) is None:
            label = self.boat._meta.get_field(field).verbose_name
            self.add_error(
                "ytc_number_used",
                f"{self.boat} has no {label}. Choose the number she has, or ask "
                "for a change to your boat's details first.",
            )
        cleaned["ytc_number_used"] = used
        return cleaned


class DecisionForm(forms.Form):
    """The committee's approve-or-reject on one request."""

    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    reason = forms.CharField(required=False, max_length=500)
    note = forms.CharField(required=False, max_length=500)
