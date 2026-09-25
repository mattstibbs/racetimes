"""Slice 11 part 4: every email comes from its club.

From is "<Club name> via Race Times" at the service's one sending address, and
replies go to the club's contact email. The club's name here has a comma,
quotes and an accent, the characters a hand-built address gets wrong; each
check reads the From header back as a mail program would.
"""

import email
import email.policy
import re
from pathlib import Path

import pytest
from django.core import mail
from django.urls import reverse

from races import notifications
from races.models import ClubMembership
from races.test_members import sign_up
from races.testing import (
    default_club, enter, make_administrator, make_boat, make_committee, make_member, make_operator, make_race,
    make_series, record,
)

pytestmark = pytest.mark.django_db

NAME = 'Côte, "Bay" & Harbour SC'
SENDING_ADDRESS = "noreply@racetimes.example"


@pytest.fixture(autouse=True)
def tricky_club(settings, monkeypatch):
    settings.DEFAULT_FROM_EMAIL = f"Race Times <{SENDING_ADDRESS}>"
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())
    club = default_club()
    club.name, club.contact_email = NAME, "secretary@bay.example"
    club.save()
    return club


def sender_of(message):
    """The From header's name and address, and the Reply-To, as a mail program reads them."""
    parsed = email.message_from_bytes(message.message().as_bytes(), policy=email.policy.default)
    [address] = parsed["From"].addresses
    return address.display_name, address.addr_spec, parsed["Reply-To"]


def from_the_club(message):
    return sender_of(message) == (f"{NAME} via Race Times", SENDING_ADDRESS, "secretary@bay.example")


def test_publishing_results(client):
    client.force_login(make_committee())
    series = make_series()
    entry = enter(series, make_boat(owner=make_member("pat@example.com")))
    race = make_race(series, 1)
    record(race, entry, "19:10:00")
    client.post(reverse("races:publish_results", args=[race.pk]))
    [message] = mail.outbox
    assert from_the_club(message)


def test_confirming_a_new_account(client):
    sign_up(client)
    [message] = mail.outbox
    assert message.subject.startswith("Confirm") and from_the_club(message)


def test_a_membership_decision(client):
    client.force_login(make_administrator())
    waiting = make_member("wait@example.com", status=ClubMembership.Status.WAITING)
    membership = waiting.memberships.get()
    client.post(reverse("races:decide_membership", args=[membership.pk]), {"action": "approve", "role": "MEMBER"})
    [message] = mail.outbox
    assert message.to == ["wait@example.com"] and from_the_club(message)


def test_a_password_reset(client):
    pat = make_member("pat@example.com")
    pat.set_password("a-password-at-sign-up")
    pat.save()
    client.post(reverse("races:password_reset"), {"email": "pat@example.com"})
    [message] = mail.outbox
    assert message.subject == "Reset your Race Times password" and from_the_club(message)


def test_an_invitation_sent_from_the_service_comes_from_the_club(client, settings):
    settings.SINGLE_CLUB = ""
    client.force_login(make_operator())
    client.post(reverse("races:operator_invite", args=[default_club().pk]), {"email": "ann@example.com"},
                HTTP_HOST="localhost")
    [message] = mail.outbox
    assert from_the_club(message)


def test_with_no_contact_email_there_is_no_reply_to(client, tricky_club):
    tricky_club.contact_email = ""
    tricky_club.save()
    sign_up(client)
    [message] = mail.outbox
    assert sender_of(message) == (f"{NAME} via Race Times", SENDING_ADDRESS, None)


def test_the_service_itself_sends_as_before(rf, settings):
    request = rf.get("/")
    request.club = None
    message = notifications.email(make_member(), "confirm_email", request, confirm_url="x")
    assert message.from_email == settings.DEFAULT_FROM_EMAIL and message.reply_to == []


def test_every_email_is_built_where_it_gets_the_club():
    # Only notifications.email_to and the password reset form build emails,
    # so no email can leave without the club's sender.
    builders = {}
    for path in Path(__file__).parent.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        found = re.findall(r"(?<!def )\b(EmailMessage|EmailMultiAlternatives|send_mail|mail_admins)\(", path.read_text())
        if found:
            builders[path.name] = found
    assert builders == {"notifications.py": ["EmailMessage"], "forms.py": ["EmailMessage"]}
