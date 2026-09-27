"""Slice 16: changing your own password from My account."""

import logging

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse

from races import throttle
from races.testing import PASSWORD, Clock, log_in, make_member, make_operator

# Every test here sends email, so emails go at once (see run_on_commit in conftest).
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("run_on_commit")]

NEW = "a-brand-new-passphrase"
URL = "/account/password/"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(throttle, "now", clock)
    return clock


@pytest.fixture
def pat(client):
    pat = make_member(
        "pat@example.com", first_name="Pat", last_name="Jones", password=PASSWORD
    )
    client.force_login(pat)
    return pat


def change(client, current=PASSWORD, new=NEW, again=None, **kwargs):
    return client.post(
        URL,
        {
            "old_password": current,
            "new_password1": new,
            "new_password2": new if again is None else again,
        },
        **kwargs,
    )


def password_works(user, password):
    return get_user_model().objects.get(pk=user.pk).check_password(password)


# --- Who can reach it --------------------------------------------------------------------------


def test_the_address_and_name():
    assert reverse("races:change_password") == URL


def test_the_public_is_sent_to_log_in(client):
    response = client.get(URL)
    assert response.status_code == 302 and response.url.startswith(
        reverse("races:login")
    )


def test_the_page(client, pat):
    html = client.get(URL).content.decode()
    assert (
        "<title>Change my password - Race Times</title>" in html
        and "<h1>Change my password</h1>" in html
    )
    for label in ["Current password", "New password", "New password again"]:
        assert f">{label}:</label>" in html
    assert (
        'autocomplete="current-password"' in html
        and 'autocomplete="new-password"' in html
    )
    assert (
        f'href="{reverse("races:password_reset")}">Forgotten your current password?</a>'
        in html
    )
    assert f'href="{reverse("races:account")}">Back to my account</a>' in html


def test_someone_not_yet_a_member_of_any_club_can_change_it(client):
    client.force_login(make_member("new@example.com", club=None, password=PASSWORD))
    assert client.get(URL).status_code == 200


def test_the_operator_can_change_theirs_on_the_service_s_address(client, settings):
    settings.SINGLE_CLUB = ""
    operator = make_operator()
    operator.set_password(PASSWORD)
    operator.save()
    client.force_login(operator)
    assert client.get(URL, HTTP_HOST="localhost").status_code == 200
    response = change(client, HTTP_HOST="localhost")
    assert response.status_code == 302 and password_works(operator, NEW)
    assert response.url == reverse("races:operator_clubs")  # My account is a club page
    # There's no reset page on the service's own address, so neither the page nor the email links to one.
    assert (
        "Forgotten your current password?"
        not in client.get(URL, HTTP_HOST="localhost").content.decode()
    )
    [message] = mail.outbox
    assert (
        "password-reset" not in message.body
        and "change your password again straight away" in message.body
    )


def test_my_account_links_to_it(client, pat):
    html = client.get(reverse("races:account")).content.decode()
    assert (
        "<h2>My password</h2>" in html
        and f'<a href="{URL}">Change my password</a>' in html
    )
    assert (
        html.index("My club memberships")
        < html.index("My password")
        < html.index("<h2>My data</h2>")
    )


# --- Changing it -------------------------------------------------------------------------------


def test_changing_it(client, pat):
    other_device = Client()
    other_device.force_login(pat)
    response = change(client)
    assert response.status_code == 302 and response.url == reverse("races:account")
    # Only the new password works now.
    assert password_works(pat, NEW) and not password_works(pat, PASSWORD)
    # This browser stays logged in and is told what happened; any other is logged out.
    page = client.get(response.url).content.decode()
    assert (
        "Your password has been changed. Any other devices logged in to your account have been logged out."
        in page
    )
    assert other_device.get(reverse("races:account")).status_code == 302


def test_the_new_password_logs_in(client, pat):
    change(client)
    client.logout()
    log_in(client, pat.email, NEW)
    assert client.get(reverse("races:account")).status_code == 200


def test_one_email_says_it_changed_and_never_what_to(client, pat):
    change(client)
    [message] = mail.outbox
    assert message.to == ["pat@example.com"]
    assert message.subject == "Your Race Times password was changed"
    assert "Hello Pat," in message.body and "pat@example.com" in message.body
    assert (
        "Any other devices logged in to your account have been logged out."
        in message.body
    )
    assert "http://testserver" + reverse("races:password_reset") in message.body
    assert NEW not in message.body and PASSWORD not in message.body
    assert message.from_email.startswith(
        "Demo Club via Race Times"
    )  # from the club, as every email is


def test_the_log_names_the_user_by_id(client, pat, caplog):
    with caplog.at_level(logging.INFO, logger="races.account_views"):
        change(client)
    assert f"user {pat.pk} changed their password" in caplog.text
    assert "pat@example.com" not in caplog.text and "Pat" not in caplog.text


# --- Refusals ----------------------------------------------------------------------------------


def test_a_wrong_current_password_changes_nothing(client, pat):
    response = change(client, current="not-it")
    assert (
        response.status_code == 200
        and "That isn&#x27;t your current password." in response.content.decode()
    )
    assert password_works(pat, PASSWORD) and not mail.outbox


@pytest.mark.parametrize(
    "new, again, error",
    [
        (NEW, "something-else-entirely", "The two password fields didn"),
        ("short", None, "This password is too short."),
        ("password123", None, "This password is too common."),
    ],
)
def test_a_new_password_that_breaks_the_rules_is_refused(
    client, pat, new, again, error
):
    response = change(client, new=new, again=again)
    assert response.status_code == 200 and error in response.content.decode()
    assert password_works(pat, PASSWORD) and not mail.outbox


def test_wrong_current_passwords_count_as_failed_logins(client, pat, clock):
    for _ in range(10):
        change(client, current="not-it")
    # Locked now: even the right password is refused, and nothing changes.
    response = change(client)
    assert (
        "Too many failed logins. Try again in 15 minutes." in response.content.decode()
    )
    assert password_works(pat, PASSWORD)
    # And the login page is locked for the account too.
    other = Client()
    assert "Too many failed logins" in log_in(other, pat.email).content.decode()
    clock.minutes_pass(15)
    assert change(client).status_code == 302 and password_works(pat, NEW)
