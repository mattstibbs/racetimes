"""The race day page's forms: one boat's finish, and one boat's start sheet row."""

from django import forms

from .audit import AuditedFormMixin
from .models import Finish


class FinishForm(AuditedFormMixin, forms.ModelForm):
    """One boat's time or code, on the race day page's Finishing view."""

    reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Reason, if correcting"}),
    )

    class Meta:
        model = Finish
        fields = ["finish_time", "status", "scoring_penalty"]
        widgets = {
            # step=1 makes browsers offer seconds, which finishes need.
            "finish_time": forms.TimeInput(
                format="%H:%M:%S", attrs={"type": "time", "step": "1"}
            ),
        }
        labels = {
            "finish_time": "Finish time",
            "status": "Result",
            "scoring_penalty": "Scoring penalty",
        }


class StartSheetRowForm(forms.Form):
    """One boat's row on a race's start sheet: racing or not, and who is aboard."""

    racing = forms.BooleanField(required=False, label="Racing")
    persons_on_board = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=99,
        label="Persons on board",
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "size": 3}),
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("racing"):
            # Unticking a boat takes it off, whatever is still in the box.
            cleaned["persons_on_board"] = None
            self.errors.pop("persons_on_board", None)
        return cleaned
