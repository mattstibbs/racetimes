"""The admin's forms for setting up a series and its boats.

The boat form is the race office's (``races/office_forms.py``), with a reason box
always shown.

Each works out, while validating, what saving it would record in the history
(``races/audit.py``), and requires a reason for a correction.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from . import audit, final
from .audit import AuditedFormMixin
from .models import Race, Series
from .office_forms import BoatForm, reason_field


class _AdminReasonForm(AuditedFormMixin, forms.ModelForm):
    reason = reason_field()

    # The club a new boat or series belongs to. The admin sets it from the
    # request (races/admin.py); a row's club is never a field anyone can edit.
    club = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.club is not None and self.instance.club_id is None:
            self.instance.club = self.club


class SeriesAdminForm(_AdminReasonForm):
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

    # A final series can still be renamed: a name moves no score (slice 10).
    UNLOCKED_FIELDS = {"name", "reason"}

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and set(self.changed_data) - self.UNLOCKED_FIELDS:
            try:
                final.check_series_open(self.instance.pk)
            except ValidationError as locked:
                raise ValidationError(locked.messages) from None
        return cleaned


class BoatAdminForm(BoatForm):
    """The race office's boat form (races/office_forms.py), with the admin's
    reason box always shown."""

    reason = reason_field()


class AuditedInlineForm(AuditedFormMixin, forms.ModelForm):
    """A race or entry row inside the series form. Its reason is the series form's box."""

    reason_error_field = None

    def correction_reason(self):
        # Every formset on the page is bound to the same POST, so the parent
        # form's unprefixed reason box is readable from here.
        return self.data.get("reason", "").strip()


class AuditedInlineFormSet(BaseInlineFormSet):
    """Records rows removed from the series form, and requires a reason where due."""

    def clean(self):
        super().clean()
        # Slice 10: a final series' races and entries can't change. Checked
        # against the database, not the form, which may have been open a while.
        if self.instance.pk and any(form.has_changed() for form in self.forms):
            final.check_series_open(self.instance.pk)
        self.removal_changes = []
        for form in self.forms:
            if self._should_delete_form(form) and form.instance.pk:
                self.removal_changes += audit.changes_to_delete(form.instance)
        if (
            audit.needs_reason(self.removal_changes)
            and not self.data.get("reason", "").strip()
        ):
            raise ValidationError(audit.REASON_REQUIRED)

    def changes_to_record(self):
        """Added and changed rows; valid only after the formset has been validated."""
        return [
            change
            for form in self.forms
            if not self._should_delete_form(form)
            for change in form.scoring_changes
        ]


class RaceInlineFormSet(AuditedInlineFormSet):
    """The series form's races, saved so that renumbering them cannot collide.

    Django saves the rows one at a time. Swapping races 1 and 2 would therefore
    give two races the same number for a moment, which the database's unique
    rule refuses, even though the numbers are unique once saving finishes.
    So every race that is renumbered or removed is first parked on a spare
    number. The admin saves inside a transaction, so nobody sees the parked
    numbers.
    """

    def save_existing_objects(self, commit=True):
        if commit:
            moving = [
                form.instance
                for form in self.initial_forms
                if self._should_delete_form(form) or "number" in form.changed_data
            ]
            if moving:
                spares = self._spare_numbers(len(moving))
                for race, spare in zip(moving, spares, strict=True):
                    Race.objects.for_club(self.instance.club).filter(pk=race.pk).update(
                        number=spare
                    )
        return super().save_existing_objects(commit)

    def _spare_numbers(self, count):
        # Counting down from 32767, the largest small positive integer on
        # both SQLite and PostgreSQL, skipping any number in use now or about
        # to be.
        in_use = set(
            Race.objects.for_club(self.instance.club)
            .filter(series=self.instance)
            .values_list("number", flat=True)
        )
        in_use |= {
            form.cleaned_data.get("number") for form in self.forms if form.cleaned_data
        }
        return [n for n in range(32767, 0, -1) if n not in in_use][:count]
