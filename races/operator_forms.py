"""The operator's forms (slice 11 part 3): a new club, and inviting its administrator."""

import re

from django import forms
from django.core.exceptions import ValidationError

from .models import Club

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
            raise ValidationError(
                f"{subdomain} is reserved for the service. Choose another."
            )
        return subdomain


class InvitationForm(forms.Form):
    email = forms.EmailField(label="Their email")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
