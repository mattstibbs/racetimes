"""Slice 27: logging in from the service's own address, racetimes.co.uk.

The same login as a club's, a Your clubs page after it, and a person's own
account pages, all on the service's address (``localhost`` in tests, with
SINGLE_CLUB off). The shared session cookie itself is a production setting,
pinned in races/test_production.py: the test client is one browser for every
address already, so these tests check what each address does with a login.
"""

from urllib.parse import urlparse

import pytest
from django.core import mail
from django.urls import reverse

from races import throttle
from races.models import Club
from races.testing import (
    PASSWORD,
    Clock,
    join,
    make_club,
    make_member,
    make_operator,
)

pytestmark = pytest.mark.django_db

SERVICE = {"HTTP_HOST": "localhost"}
DEMO = {"HTTP_HOST": "demo.localhost"}


@pytest.fixture(autouse=True)
def service_address(settings):
    """``localhost`` is the service's own address, with no club."""
    settings.SINGLE_CLUB = ""


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(throttle, "now", clock)
    return clock


@pytest.fixture
def harbour():
    return make_club("harbour", "Harbour Sailing Club")


def log_in(client, email="pat@example.com", password=PASSWORD, **data):
    return client.post(
        reverse("races:login"),
        {"username": email, "password": password, **data},
        **SERVICE,
    )


def page(client, name, **extra):
    return client.get(reverse(name), **SERVICE, **extra).content.decode()


# --- The front page and the login page --------------------------------------------------


def test_the_front_page_offers_log_in(client):
    html = page(client, "results:home")
    assert f'href="{reverse("races:login")}">Log in</a>' in html
    assert "Already have an account?" in html


def test_the_front_page_knows_who_is_logged_in(client):
    client.force_login(make_member("pat@example.com"))
    html = page(client, "results:home")
    assert f'href="{reverse("races:your_clubs")}">Your clubs</a>' in html
    assert "You're logged in." in html
    assert ">Log in</a>" not in html


def test_the_login_page_is_on_the_services_address(client):
    response = client.get(reverse("races:login"), **SERVICE)
    html = response.content.decode()
    assert response.status_code == 200
    assert "one login works at every club you belong to" in html
    assert reverse("races:password_reset") in html
    # Signing up asks to join a club, so it's on a club's site, not here.
    assert reverse("races:signup") not in html and "Find your club" in html


def test_signing_up_is_still_only_on_a_clubs_address(client):
    assert client.get(reverse("races:signup"), **SERVICE).status_code == 404
    assert client.get(reverse("races:signup"), **DEMO).status_code == 200


# --- Where logging in goes ---------------------------------------------------------------


def test_someone_approved_at_one_club_goes_straight_to_its_my_boats(client):
    make_member("pat@example.com", password=PASSWORD)
    response = log_in(client)
    assert response.status_code == 302
    assert response["Location"] == "http://demo.localhost/my/boats/"


def test_someone_at_several_clubs_goes_to_your_clubs(client, harbour):
    join(make_member("pat@example.com", password=PASSWORD), harbour)
    assert log_in(client)["Location"] == reverse("races:your_clubs")


@pytest.mark.parametrize(
    "setup",
    ["waiting", "no club", "suspended club", "removed"],
)
def test_anyone_else_goes_to_your_clubs(client, setup):
    if setup == "waiting":
        make_member("pat@example.com", password=PASSWORD, status="WAITING")
    elif setup == "no club":
        make_member("pat@example.com", password=PASSWORD, club=None)
    elif setup == "removed":
        make_member("pat@example.com", password=PASSWORD, status="REMOVED")
    else:
        make_member("pat@example.com", password=PASSWORD)
        Club.objects.update(status=Club.Status.SUSPENDED)
    assert log_in(client)["Location"] == reverse("races:your_clubs")


def test_the_operator_goes_to_the_operators_pages(client):
    operator = make_operator()
    operator.set_password(PASSWORD)
    operator.save()
    response = log_in(client, "operator@example.com")
    assert response["Location"] == reverse("races:operator_clubs")


def test_a_safe_next_is_followed_and_another_sites_is_not(client):
    make_member("pat@example.com", password=PASSWORD)
    assert log_in(client, next="/account/")["Location"] == "/account/"
    client.logout()
    response = log_in(client, next="https://evil.example/")
    assert response["Location"] == "http://demo.localhost/my/boats/"


def test_someone_already_logged_in_is_sent_on(client):
    client.force_login(make_member("pat@example.com"))
    response = client.get(reverse("races:login"), **SERVICE)
    assert response["Location"] == "http://demo.localhost/my/boats/"


def test_logging_in_at_a_club_still_goes_to_its_my_boats(client):
    make_member("pat@example.com", password=PASSWORD)
    response = client.post(
        reverse("races:login"),
        {"username": "pat@example.com", "password": PASSWORD},
        **DEMO,
    )
    assert response["Location"] == reverse("races:my_boats")


# --- The same login's rules ---------------------------------------------------------------


def test_a_wrong_password_is_refused(client):
    make_member("pat@example.com", password=PASSWORD)
    response = log_in(client, password="not-it")
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_the_login_throttle_applies_here_too(client):
    make_member("pat@example.com", password=PASSWORD)
    for _ in range(throttle.LIMIT):
        log_in(client, password="not-it")
    response = log_in(client)
    assert throttle.LOCKED in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_an_unconfirmed_account_can_have_its_link_sent_again_from_its_club(
    client, run_on_commit
):
    pat = make_member("pat@example.com", password=PASSWORD, status="WAITING")
    pat.is_active = False
    pat.save()
    html = log_in(client).content.decode()
    assert "Send the confirmation link again" in html
    with run_on_commit():
        client.post(
            reverse("races:resend_confirmation"),
            {"email": "pat@example.com"},
            **SERVICE,
        )
    [message] = mail.outbox
    # It names, and links to, the club they signed up at, as the first one did.
    assert "Demo Club" in message.body
    link = next(
        line for line in message.body.splitlines() if "/accounts/confirm/" in line
    )
    assert urlparse(link.strip()).netloc == "demo.localhost"


# --- Your clubs ------------------------------------------------------------------------------


def test_your_clubs_lists_each_club_with_the_role_and_a_way_in(client, harbour):
    pat = make_member("pat@example.com")
    join(pat, harbour, role="COMMITTEE")
    client.force_login(pat)
    html = page(client, "races:your_clubs")
    assert "Demo Club" in html and "Harbour Sailing Club" in html
    assert "Race committee." in html and "Member." in html
    assert 'href="http://demo.localhost/my/boats/">Go to Demo Club</a>' in html
    assert (
        'href="http://harbour.localhost/my/boats/">Go to Harbour Sailing Club</a>'
        in html
    )


def test_your_clubs_says_when_joining_is_waiting(client):
    client.force_login(make_member("pat@example.com", status="WAITING"))
    assert "Waiting for the club's administrators" in page(client, "races:your_clubs")


def test_a_suspended_club_is_listed_without_a_way_in(client):
    client.force_login(make_member("pat@example.com"))
    Club.objects.update(status=Club.Status.SUSPENDED)
    html = page(client, "races:your_clubs")
    assert "paused at the moment" in html and "Go to Demo Club" not in html


def test_someone_with_no_clubs_is_pointed_to_find_my_club(client):
    client.force_login(make_member("pat@example.com", club=None))
    html = page(client, "races:your_clubs")
    assert "You haven't joined a club yet." in html and "/#find-my-club" in html


def test_your_clubs_shows_only_your_own_clubs(client, harbour):
    make_member("sam@example.com", club=harbour)
    client.force_login(make_member("pat@example.com"))
    html = page(client, "races:your_clubs")
    assert "Harbour" not in html


def test_a_removed_membership_isnt_listed(client):
    client.force_login(make_member("pat@example.com", status="REMOVED"))
    assert "Demo Club" not in page(client, "races:your_clubs")


def test_your_clubs_needs_logging_in(client):
    response = client.get(reverse("races:your_clubs"), **SERVICE)
    assert response["Location"].startswith(reverse("races:login"))


def test_at_a_club_your_clubs_is_my_account(client):
    client.force_login(make_member("pat@example.com"))
    response = client.get(reverse("races:your_clubs"), **DEMO)
    assert response["Location"] == reverse("races:account")


# --- A person's own account, and logging out, on the service's address -----------------


@pytest.mark.parametrize(
    "name", ["races:account", "races:download_my_data", "races:delete_account"]
)
def test_my_account_pages_work_here(client, name):
    client.force_login(make_member("pat@example.com"))
    assert client.get(reverse(name), **SERVICE).status_code == 200


def test_changing_a_password_here_goes_back_to_my_account(client):
    client.force_login(make_member("pat@example.com", password=PASSWORD))
    new = "a-brand-new-sailing-password"
    response = client.post(
        reverse("races:change_password"),
        {"old_password": PASSWORD, "new_password1": new, "new_password2": new},
        **SERVICE,
    )
    assert response["Location"] == reverse("races:account")


def test_logging_out_here_logs_out(client):
    client.force_login(make_member("pat@example.com"))
    response = client.post(reverse("races:logout"), **SERVICE)
    assert response["Location"] == reverse("results:home")
    assert "_auth_user_id" not in client.session


def test_the_header_offers_your_clubs_and_log_out(client):
    client.force_login(make_member("pat@example.com"))
    html = page(client, "races:account")
    assert ">Your clubs</a>" in html and ">My account</a>" in html
    assert ">Log out</button>" in html


def test_a_forgotten_password_works_here_and_comes_from_race_times(
    client, settings, run_on_commit
):
    settings.DEFAULT_FROM_EMAIL = "Race Times <noreply@racetimes.example>"
    make_member("pat@example.com", password=PASSWORD)
    with run_on_commit():
        response = client.post(
            reverse("races:password_reset"),
            {"email": "pat@example.com"},
            follow=True,
            **SERVICE,
        )
    assert "Check your email" in response.content.decode()
    [message] = mail.outbox
    assert message.from_email == "Race Times <noreply@racetimes.example>"
    link = next(
        line
        for line in message.body.splitlines()
        if "/accounts/password-reset/" in line
    ).strip()
    assert urlparse(link).netloc == "localhost"
    assert client.get(link, follow=True, **SERVICE).status_code == 200


def test_club_pages_are_still_not_on_the_services_address(client):
    client.force_login(make_member("pat@example.com"))
    assert client.get(reverse("races:my_boats"), **SERVICE).status_code == 404
