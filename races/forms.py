from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from . import audit
from .models import Boat, Finish, Race, Series

REASON_HELP = "Required when correcting results already recorded."


class AuditedFormMixin:
    """Works out, while validating, what saving this form would record.

    ``_post_clean`` is where a ModelForm copies the cleaned values onto its
    instance, so straight after it the instance holds the new values and the
    database still holds the old ones. That is the moment to compare them. A
    correction without a reason becomes a validation error, so nothing is saved.
    """

    scoring_changes = ()

    def _post_clean(self):
        super()._post_clean()
        if self._errors:
            return
        self.scoring_changes = audit.changes_to_save(self.instance)
        if audit.needs_reason(self.scoring_changes) and not self.correction_reason():
            self.add_error(self.reason_error_field, audit.REASON_REQUIRED)

    reason_error_field = "reason"

    def correction_reason(self):
        return self.cleaned_data.get("reason", "")


class FinishForm(AuditedFormMixin, forms.ModelForm):
    """One boat's row on the finish-entry page."""

    reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Reason, if correcting"}),
    )

    class Meta:
        model = Finish
        fields = ["finish_time", "status"]
        widgets = {
            # step=1 makes browsers offer seconds, which finishes need.
            "finish_time": forms.TimeInput(
                format="%H:%M:%S", attrs={"type": "time", "step": "1"}
            ),
        }
        labels = {"finish_time": "Finish time", "status": "Result"}


class _AdminReasonForm(AuditedFormMixin, forms.ModelForm):
    reason = forms.CharField(
        label="Reason for change", required=False, max_length=500, help_text=REASON_HELP
    )


class SeriesAdminForm(_AdminReasonForm):
    class Meta:
        model = Series
        fields = "__all__"


class BoatAdminForm(_AdminReasonForm):
    class Meta:
        model = Boat
        fields = "__all__"


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
        self.removal_changes = []
        for form in self.forms:
            if self._should_delete_form(form) and form.instance.pk:
                self.removal_changes += audit.changes_to_delete(form.instance)
        if audit.needs_reason(self.removal_changes) and not self.data.get("reason", "").strip():
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
                for race, spare in zip(moving, spares):
                    Race.objects.filter(pk=race.pk).update(number=spare)
        return super().save_existing_objects(commit)

    def _spare_numbers(self, count):
        # Counting down from 32767, the largest small positive integer on
        # both SQLite and PostgreSQL, skipping any number in use now or about
        # to be.
        in_use = set(Race.objects.filter(series=self.instance).values_list("number", flat=True))
        in_use |= {form.cleaned_data.get("number") for form in self.forms if form.cleaned_data}
        return [n for n in range(32767, 0, -1) if n not in in_use][:count]
