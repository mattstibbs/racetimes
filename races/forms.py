import logging
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db.models import Q, Value
from django.db.models.functions import Replace, Upper
from django.forms.models import BaseInlineFormSet
from django.template.loader import render_to_string

from . import audit, final, notifications
from .models import Boat, BoatRequest, Club, Finish, Race, Series

logger = logging.getLogger(__name__)

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
        fields = "__all__"

    # A final series can still be renamed: a name moves no score (slice 10).
    UNLOCKED_FIELDS = {"name", "reason"}

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and set(self.changed_data) - self.UNLOCKED_FIELDS:
            try:
                final.check_series_open(self.instance.pk)
            except ValidationError as locked:
                raise ValidationError(locked.messages)
        return cleaned


class BoatAdminForm(_AdminReasonForm):
    class Meta:
        model = Boat
        fields = "__all__"

    def clean_sail_number(self):
        # The unique-in-club constraint can't be checked by the form itself,
        # because club isn't one of its fields, so it's checked here instead.
        sail_number = self.cleaned_data["sail_number"]
        existing = boat_with_sail_number(
            self.instance.club, sail_number, exclude=self.instance if self.instance.pk else None
        )
        if existing is not None:
            raise ValidationError("A boat with this sail number is already registered.")
        return sail_number


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
                    Race.objects.for_club(self.instance.club).filter(pk=race.pk).update(number=spare)
        return super().save_existing_objects(commit)

    def _spare_numbers(self, count):
        # Counting down from 32767, the largest small positive integer on
        # both SQLite and PostgreSQL, skipping any number in use now or about
        # to be.
        in_use = set(Race.objects.for_club(self.instance.club).filter(series=self.instance).values_list("number", flat=True))
        in_use |= {form.cleaned_data.get("number") for form in self.forms if form.cleaned_data}
        return [n for n in range(32767, 0, -1) if n not in in_use][:count]


# --- Accounts ----------------------------------------------------------------

UNCONFIRMED = (
    "Confirm your email address first: open the link we emailed you when you signed up. "
    "It lasts three days."
)


def _normalise_login(value):
    # Members log in with their email, stored lower-cased. Other usernames
    # (older committee accounts made in the admin) are left exactly as typed.
    value = value.strip()
    return value.lower() if "@" in value else value


class SignUpForm(UserCreationForm):
    """Anyone's own sign-up. The account is switched off until its email is confirmed (slice 11)."""

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
            raise ValidationError(
                "An account with this email address already exists. Log in, and use Join this club."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        user.is_active = False
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Everyone's login, by email. An account whose email isn't confirmed yet is told so."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean(self):
        if "username" in self.cleaned_data:
            self.cleaned_data["username"] = _normalise_login(self.cleaned_data["username"])
        try:
            return super().clean()
        except ValidationError:
            # Say "confirm your email" only to someone who knows the password,
            # so the form never reveals which emails have signed up. An
            # account switched off after it had logged in gets the usual
            # message instead.
            username = self.cleaned_data.get("username", "")
            password = self.cleaned_data.get("password", "")
            user = get_user_model().objects.filter(username=username).first()
            if user and not user.is_active and user.last_login is None and user.check_password(password):
                self.unconfirmed = True
                raise ValidationError(UNCONFIRMED, code="inactive")
            raise

    unconfirmed = False


class ClubPasswordResetForm(PasswordResetForm):
    """Django's password reset, but the email comes from the club (slice 11 part 4).

    Django builds and sends this one email itself, so it can't go through
    notifications.email_to; this gives it the same sender. Like Django's, a
    failure to send is logged and not shown, so the page never reveals whether
    the email address has an account.
    """

    reply_to = ()

    def save(self, *args, request=None, **kwargs):
        kwargs["from_email"], self.reply_to = notifications.sender(getattr(request, "club", None))
        return super().save(*args, request=request, **kwargs)

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email,
                  html_email_template_name=None):
        subject = "".join(render_to_string(subject_template_name, context).splitlines())
        body = render_to_string(email_template_name, context)
        message = EmailMessage(subject, body, from_email, [to_email], reply_to=self.reply_to)
        try:
            message.send()
        except Exception:
            logger.exception("Could not send a password reset email to user %s", context["user"].pk)


# --- The operator (slice 11 part 3) -------------------------------------------

# Names that belong to the service, never to a club.
RESERVED_SUBDOMAINS = ("www", "admin", "operator", "mail", "api", "static", "app")
SUBDOMAIN_RULE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class ClubForm(forms.ModelForm):
    """A new club: its name, its address and where replies to its emails go."""

    class Meta:
        model = Club
        fields = ["name", "subdomain", "contact_email"]
        labels = {"subdomain": "Address", "contact_email": "Contact email"}
        help_texts = {
            "subdomain": "The club's address, e.g. exesc for exesc.racetimes.co.uk. "
                         "Letters, digits and hyphens only. It can't be changed later.",
            "contact_email": "Replies to the club's emails go here.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact_email"].required = True

    def clean_subdomain(self):
        subdomain = self.cleaned_data["subdomain"].strip().lower()
        # A hyphen can't start or end an address: DNS doesn't allow it.
        if not SUBDOMAIN_RULE.match(subdomain):
            raise ValidationError(
                "Use only letters, digits and hyphens, not starting or ending with a hyphen."
            )
        if subdomain in RESERVED_SUBDOMAINS:
            raise ValidationError(f"{subdomain} is reserved for the service. Choose another.")
        return subdomain


class InvitationForm(forms.Form):
    email = forms.EmailField(label="Their email")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class InvitedSignUpForm(UserCreationForm):
    """An account for someone accepting an invitation. The invitation gives the email.

    Opening the emailed link proves the address, so the account is active
    straight away, with no separate confirmation.
    """

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["first_name", "last_name"]

    def __init__(self, *args, email, **kwargs):
        super().__init__(*args, **kwargs)
        self.email = email
        for name in ["first_name", "last_name"]:
            self.fields[name].required = True

    def _post_clean(self):
        # Set before the password checks, which compare it with the account's details.
        self.instance.username = self.instance.email = self.email
        super()._post_clean()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = True
        if commit:
            user.save()
        return user


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

    def __init__(self, *args, club, **kwargs):
        # The club the boat is (or will be) registered with (slice 11).
        self.club = club
        super().__init__(*args, **kwargs)
        for name in ["sail_number", "base_number"]:
            self.fields[name].required = True

    def clean_sail_number(self):
        sail_number = self.cleaned_data["sail_number"].strip()
        self.existing_boat = boat_with_sail_number(self.club, sail_number, exclude=self.boat)
        if self.existing_boat is not None:
            raise ValidationError(f"{self.existing_boat} is already registered with the club.")
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
        # Only the boat's own club's series (slice 11).
        self.fields["series"].queryset = Series.objects.for_club(boat.club).exclude(entries__boat=boat).exclude(
            entry_requests__boat=boat, entry_requests__status=BoatRequest.Status.PENDING
        )


class DecisionForm(forms.Form):
    """The committee's approve-or-reject on one request."""

    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")])
    reason = forms.CharField(required=False, max_length=500)
    note = forms.CharField(required=False, max_length=500)


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
