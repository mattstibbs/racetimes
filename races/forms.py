from django import forms

from .models import Finish


class FinishForm(forms.ModelForm):
    """One boat's row on the finish-entry page."""

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
