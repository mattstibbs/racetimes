from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q, Value
from django.db.models.functions import Replace, Upper
from django.forms.models import BaseInlineFormSet

from . import audit
from .models import Boat, BoatRequest, Finish, Race, Series

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


# --- Accounts ----------------------------------------------------------------

PENDING_APPROVAL = (
    "Your account is waiting for approval by the club's administrator. "
    "You can log in once it has been approved."
)


def _normalise_login(value):
    # Members log in with their email, stored lower-cased. Other usernames
    # (older committee accounts made in the admin) are left exactly as typed.
    value = value.strip()
    return value.lower() if "@" in value else value


class SignUpForm(UserCreationForm):
    """A member's own sign-up. The account starts switched off until approved."""

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["first_name", "last_name", "email"]:
            self.fields[name].required = True
        self.fields["email"].help_text = "You will log in with this."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        user.is_active = False
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Everyone's login, by email. A member still waiting for approval is told so."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean(self):
        if "username" in self.cleaned_data:
            self.cleaned_data["username"] = _normalise_login(self.cleaned_data["username"])
        try:
            return super().clean()
        except ValidationError:
            # Say "waiting for approval" only to someone who knows the
            # password, so the form never reveals which emails have signed up.
            username = self.cleaned_data.get("username", "")
            password = self.cleaned_data.get("password", "")
            user = get_user_model().objects.filter(username=username).first()
            if user and not user.is_active and user.check_password(password):
                raise ValidationError(PENDING_APPROVAL, code="inactive")
            raise


# --- Members' requests -------------------------------------------------------


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["sail_number", "base_number"]:
            self.fields[name].required = True

    def clean_sail_number(self):
        sail_number = self.cleaned_data["sail_number"].strip()
        others = Boat.objects.exclude(pk=self.boat.pk) if self.boat else Boat.objects.all()
        # The same comparison as the boat's unique constraint, so they agree.
        self.existing_boat = (
            others.annotate(normalised=Upper(Replace("sail_number", Value(" "), Value(""))))
            .filter(normalised=sail_number.replace(" ", "").upper())
            .first()
        )
        if self.existing_boat is not None:
            raise ValidationError(f"{self.existing_boat} is already registered with the club.")
        return sail_number


class BoatRegistrationForm(_BoatDetailsForm):
    pass


class BoatChangeForm(_BoatDetailsForm):
    """Starts from the boat's current details; the member edits what should change."""

    def __init__(self, *args, boat, **kwargs):
        self.boat = boat
        initial = {name: getattr(boat, name) for name in BoatRequest.PROPOSED_FIELDS}
        super().__init__(*args, initial=initial, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if not self.errors and all(
            cleaned.get(name) == getattr(self.boat, name) for name in BoatRequest.PROPOSED_FIELDS
        ):
            raise ValidationError("Nothing has changed. Edit the details that are wrong.")
        return cleaned


class EntryRequestForm(forms.Form):
    series = forms.ModelChoiceField(queryset=Series.objects.none(), empty_label=None)
    member_note = forms.CharField(
        label="Note for the race committee (optional)", required=False, max_length=500
    )

    def __init__(self, *args, boat, **kwargs):
        super().__init__(*args, **kwargs)
        # Series the boat is not in and has not already asked to join.
        self.fields["series"].queryset = Series.objects.exclude(entries__boat=boat).exclude(
            entry_requests__boat=boat, entry_requests__status=BoatRequest.Status.PENDING
        )


class DecisionForm(forms.Form):
    """The committee's approve-or-reject on one request."""

    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    reason = forms.CharField(required=False, max_length=500)
    note = forms.CharField(required=False, max_length=500)
