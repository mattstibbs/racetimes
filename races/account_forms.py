"""Accounts: signing up, logging in, and changing or deleting your own account.

Every form that checks a password does it inside the login throttle
(``races/throttle.py``), so none can be used to guess one.
"""

import logging

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db.models import Q
from django.template.loader import render_to_string

from . import notifications, throttle

logger = logging.getLogger(__name__)


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
        if User.objects.filter(
            Q(username__iexact=email) | Q(email__iexact=email)
        ).exists():
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


class LoginForm(AuthenticationForm):
    """Everyone's login, by email. An account whose email isn't confirmed yet is told so."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean(self):
        if "username" in self.cleaned_data:
            self.cleaned_data["username"] = _normalise_login(
                self.cleaned_data["username"]
            )
        username, password = (
            self.cleaned_data.get("username"),
            self.cleaned_data.get("password"),
        )
        with throttle.guard(self.request, username, password):
            return self._check_password()

    def _check_password(self):
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
            if (
                user
                and not user.is_active
                and user.last_login is None
                and user.check_password(password)
            ):
                self.unconfirmed = True
                raise ValidationError(UNCONFIRMED, code="inactive") from None
            raise

    unconfirmed = False


class DeleteAccountForm(forms.Form):
    """Deleting your own account needs your password (slice 11 part 5).

    The check is limited like a login (races/throttle.py), so this form can't
    be used to guess a password either.
    """

    password = forms.CharField(
        label="Your password", strip=False, widget=forms.PasswordInput
    )

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def clean_password(self):
        password = self.cleaned_data["password"]
        user = self.request.user
        with throttle.guard(self.request, user.get_username(), password):
            if not user.check_password(password):
                raise ValidationError("That isn't your password.", code="invalid_login")
        return password


class ChangePasswordForm(PasswordChangeForm):
    """Changing your own password, from My account (slice 16).

    Django's form, with the site's labels. The current password is checked
    inside the login throttle (races/throttle.py), as for deleting an account,
    so someone at an unattended, logged-in computer can't use this form to
    guess the password.
    """

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_incorrect": "That isn't your current password.",
    }

    def __init__(self, *args, request, **kwargs):
        super().__init__(request.user, *args, **kwargs)
        self.request = request
        self.fields["old_password"].label = "Current password"
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "New password again"

    def clean_old_password(self):
        password = self.cleaned_data["old_password"]
        with throttle.guard(self.request, self.user.get_username(), password):
            if not self.user.check_password(password):
                # "invalid_login" is the code the throttle counts as a failed login.
                raise ValidationError(
                    self.error_messages["password_incorrect"], code="invalid_login"
                )
        return password


class AdminLoginForm(AdminAuthenticationForm):
    """The admin's login on the service's own address, the operator's, with the same limit on guessing."""

    def clean(self):
        with throttle.guard(
            self.request,
            self.cleaned_data.get("username"),
            self.cleaned_data.get("password"),
        ):
            return super().clean()


class ClubPasswordResetForm(PasswordResetForm):
    """Django's password reset, but the email comes from the club (slice 11 part 4).

    Django builds and sends this one email itself, so it can't go through
    notifications.email_to; this gives it the same sender. Like Django's, a
    failure to send is logged and not shown, so the page never reveals whether
    the email address has an account.
    """

    reply_to = ()

    def save(self, *args, request=None, **kwargs):
        kwargs["from_email"], self.reply_to = notifications.sender(
            getattr(request, "club", None)
        )
        return super().save(*args, request=request, **kwargs)

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = "".join(render_to_string(subject_template_name, context).splitlines())
        body = render_to_string(email_template_name, context)
        message = EmailMessage(
            subject, body, from_email, [to_email], reply_to=self.reply_to
        )
        try:
            message.send()
        except Exception:
            logger.exception(
                "Could not send a password reset email to user %s", context["user"].pk
            )
