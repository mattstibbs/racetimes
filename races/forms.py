from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from . import audit
from .models import Boat, Finish, Series

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
