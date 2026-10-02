"""The admin's forms for setting up a series and its boats.

The boat and series forms are the race office's (``races/office_forms.py``),
with a reason box always shown.

Each works out, while validating, what saving it would record in the history
(``races/audit.py``), and requires a reason for a correction.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from . import audit, final
from .audit import AuditedFormMixin
from .models import YTC_NUMBER_FIELDS, Race, Series, SeriesEntry
from .office_forms import BoatForm, SeriesForm, reason_field


class SeriesAdminForm(SeriesForm):
    """The race office's series form (races/office_forms.py), with the admin's
    reason box always shown."""

    reason = reason_field()


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


class EntryInlineForm(AuditedInlineForm):
    """A series entry row: the boat, and under RYA YTC which number she races on.

    The choice may be left blank: a new entry then takes the boat's own default
    (slice 25), and outside a YTC series the choice means nothing, so it is
    always the default and never recorded.
    """

    # Set by the formset: the system the series form was submitted with.
    series_system = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "ytc_number_used" in self.fields:
            self.fields["ytc_number_used"].required = False

    def has_changed(self):
        # A choice left blank is not a change: it keeps what the row has.
        if not self.data.get(self.add_prefix("ytc_number_used")):
            return bool(set(self.changed_data) - {"ytc_number_used"})
        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        used = cleaned.get("ytc_number_used")
        boat = cleaned.get("boat")
        if self.series_system != Series.HandicapSystem.YTC:
            cleaned["ytc_number_used"] = SeriesEntry.NumberUsed.SPINNAKER
        elif not used:
            cleaned["ytc_number_used"] = (
                self.instance.ytc_number_used
                if self.instance.pk
                else SeriesEntry.default_number_used(boat)
                if boat
                else None
            )
        return cleaned


class AuditedInlineFormSet(BaseInlineFormSet):
    """Records rows removed from the series form, and requires a reason where due."""

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        if isinstance(form, EntryInlineForm):
            form.series_system = self.instance.handicap_system
        return form

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
        self._check_boats_have_the_number()
        if (
            audit.needs_reason(self.removal_changes)
            and not self.data.get("reason", "").strip()
        ):
            raise ValidationError(audit.REASON_REQUIRED)

    def _check_boats_have_the_number(self):
        """Entries need the series' number (slice 24).

        The entry's own check (``SeriesEntry.clean``) can't run on the "add a
        series" page, where the series isn't saved and so isn't on the entry
        yet. The formset knows it: its instance holds the system as submitted.
        """
        if self.model is not SeriesEntry:
            return
        for form in self.forms:
            boat = form.cleaned_data.get("boat") if form.is_valid() else None
            if boat is None or self._should_delete_form(form):
                continue
            if self.instance.boats_lack(boat):
                form.add_error("boat", self.instance.lacks_number_message(boat))
                continue
            # Under RYA YTC, the number the entry chose must be one she has
            # (slice 25); she may have the other but not this.
            used = form.cleaned_data.get("ytc_number_used")
            if self.instance.handicap_system == Series.HandicapSystem.YTC and used:
                field = {v: k for k, v in YTC_NUMBER_FIELDS.items()}[used]
                if getattr(boat, field) is None:
                    label = boat._meta.get_field(field).verbose_name
                    form.add_error(
                        "ytc_number_used",
                        f"{boat} has no {label}. Choose the number she has, or "
                        "give her this one first.",
                    )

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
