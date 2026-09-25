"""Slice 11 part 4: after 10 failed logins, an account or an address is locked for 15 minutes."""

import re

import pytest
from django.urls import reverse

from races import throttle
from races.test_members import PASSWORD, log_in
from races.testing import make_member

pytestmark = pytest.mark.django_db

LOCKED = "Too many failed logins. Try again in 15 minutes."
WRONG = "not-the-password"


class Clock:
    def __init__(self):
        self.time = 1_000_000.0

    def __call__(self):
        return self.time

    def minutes_pass(self, minutes):
        self.time += minutes * 60


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(throttle, "now", clock)
    return clock


@pytest.fixture
def pat():
    return make_member("pat@example.com", password=PASSWORD)


def fail(client, email="pat@example.com", times=1, **extra):
    for _ in range(times):
        response = client.post(reverse("races:login"), {"username": email, "password": WRONG}, **extra)
    return response


def logged_in(response):
    return response.status_code == 302


def test_the_ninth_failure_does_not_lock(client, pat):
    fail(client, times=9)
    assert logged_in(log_in(client, "pat@example.com"))


def test_the_tenth_failure_locks_even_the_right_password(client, pat):
    fail(client, times=9)
    response = fail(client)
    assert LOCKED not in response.content.decode()  # the tenth itself says the password was wrong
    response = log_in(client, "pat@example.com")
    assert not logged_in(response) and LOCKED in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_the_account_is_normalised_as_the_login_form_does(client, pat):
    fail(client, " PAT@Example.com ", times=10)
    assert LOCKED in log_in(client, "pat@example.com").content.decode()


def test_the_lock_ends_after_15_minutes(client, pat, clock):
    fail(client, times=10)
    clock.minutes_pass(14)
    assert not logged_in(log_in(client, "pat@example.com"))
    clock.minutes_pass(1)
    assert logged_in(log_in(client, "pat@example.com"))


def test_failures_count_for_15_minutes_from_the_first(client, pat, clock):
    fail(client, times=9)
    clock.minutes_pass(15)
    fail(client, times=9)  # a fresh count
    assert logged_in(log_in(client, "pat@example.com"))


def test_a_locked_attempt_does_not_extend_the_lock(client, pat, clock):
    fail(client, times=10)
    clock.minutes_pass(10)
    fail(client, times=5)
    clock.minutes_pass(5)
    assert logged_in(log_in(client, "pat@example.com"))


def test_one_account_locks_from_every_address(client, pat):
    for n in range(10):
        fail(client, REMOTE_ADDR=f"10.0.0.{n}")
    assert LOCKED in log_in(client, "pat@example.com").content.decode()


def test_one_address_locks_every_account(client, pat):
    for n in range(10):
        fail(client, f"guess{n}@example.com")
    assert LOCKED in log_in(client, "pat@example.com").content.decode()
    other = client.post(reverse("races:login"), {"username": "pat@example.com", "password": PASSWORD},
                        REMOTE_ADDR="10.9.9.9")
    assert logged_in(other)  # the account itself isn't locked


def test_a_correct_password_clears_the_accounts_count_not_the_addresss(client, pat):
    at_a, at_b = {"REMOTE_ADDR": "10.0.0.1"}, {"REMOTE_ADDR": "10.0.0.2"}
    fail(client, times=9, **at_a)
    assert logged_in(log_in_from(client, at_a))
    client.logout()
    fail(client, times=9, **at_b)
    assert logged_in(log_in_from(client, at_b))  # the account's count had started again
    client.logout()
    fail(client, "someone@example.com", **at_a)  # the address's tenth failure
    assert LOCKED in log_in_from(client, at_a).content.decode()


def log_in_from(client, address):
    return client.post(reverse("races:login"), {"username": "pat@example.com", "password": PASSWORD}, **address)


def test_it_reveals_nothing_about_who_has_an_account(client, pat):
    fail(client, "pat@example.com", times=10, REMOTE_ADDR="10.0.0.1")
    fail(client, "nobody@example.com", times=10, REMOTE_ADDR="10.0.0.2")
    known = log_in(client, "pat@example.com").content.decode()
    unknown = client.post(reverse("races:login"), {"username": "nobody@example.com", "password": PASSWORD},
                          REMOTE_ADDR="10.0.0.3").content.decode()
    assert LOCKED in known

    def comparable(page, email):
        # Every page has its own CSRF token.
        page = re.sub(r'"X-CSRFToken": "\w+"|name="csrfmiddlewaretoken" value="\w+"', "", page)
        return page.replace(email, "X")

    assert comparable(known, "pat@example.com") == comparable(unknown, "nobody@example.com")


def test_an_empty_password_neither_counts_nor_clears(client, pat):
    fail(client, times=9)
    client.post(reverse("races:login"), {"username": "pat@example.com", "password": ""})
    fail(client)
    assert LOCKED in log_in(client, "pat@example.com").content.decode()


def test_the_operators_admin_login_is_limited_too(client, settings):
    settings.SINGLE_CLUB = ""
    make_member("op@example.com", club=None, is_superuser=True, password=PASSWORD)  # the operator
    login = reverse("admin:login")
    for _ in range(10):
        client.post(login, {"username": "op@example.com", "password": WRONG}, HTTP_HOST="localhost")
    response = client.post(login, {"username": "op@example.com", "password": PASSWORD}, HTTP_HOST="localhost")
    assert response.status_code == 200 and LOCKED in response.content.decode()


# --- The client's address ----------------------------------------------------------------------


@pytest.mark.parametrize("trusted, forwarded, expected", [
    (0, "203.0.113.9", "10.0.0.1"),  # no proxy: the header is anyone's to invent
    (1, "203.0.113.9", "203.0.113.9"),
    (1, "1.2.3.4, 203.0.113.9", "203.0.113.9"),  # the client put 1.2.3.4 there itself
    (2, "1.2.3.4, 203.0.113.9, 10.1.1.1", "203.0.113.9"),
    (1, "", "10.0.0.1"),
])
def test_the_clients_address(rf, settings, trusted, forwarded, expected):
    settings.TRUSTED_PROXIES = trusted
    request = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR=forwarded)
    assert throttle.client_address(request) == expected


def test_a_made_up_forwarded_address_doesnt_escape_the_lock(client, pat, settings):
    settings.TRUSTED_PROXIES = 1
    for n in range(10):
        fail(client, f"guess{n}@example.com", HTTP_X_FORWARDED_FOR=f"1.1.1.{n}, 203.0.113.9")
    response = client.post(reverse("races:login"), {"username": "pat@example.com", "password": PASSWORD},
                           HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.9")
    assert LOCKED in response.content.decode()


def test_the_cache_holds_no_email_or_ip_address(client, pat):
    from django.db import connection

    fail(client, REMOTE_ADDR="10.0.0.1")
    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key FROM racetimes_cache")
        keys = " ".join(row[0] for row in cursor.fetchall())
    assert keys and "pat@" not in keys and "10.0.0.1" not in keys
