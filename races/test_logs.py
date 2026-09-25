"""Slice 11 part 4: log lines name the club and no email addresses, and error reports keep personal data out.

Log output is captured from the console handler the settings configure, so
these check the lines exactly as the host would collect them. Sentry is
tested with a transport that keeps its reports in memory; nothing is sent.
"""

import io
import logging
from smtplib import SMTPRecipientsRefused

import pytest
import sentry_sdk
from django.test import Client
from django.urls import reverse
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.transport import Transport

from races import logs
from races.testing import make_club, make_member, make_series

pytestmark = pytest.mark.django_db


@pytest.fixture
def log_output():
    """What the console handler writes, as a function returning it so far."""
    [handler] = [h for h in logging.getLogger().handlers if isinstance(h.formatter, logs.RedactingFormatter)]
    stream = io.StringIO()
    old = handler.setStream(stream)
    yield stream.getvalue
    handler.setStream(old)


def test_a_log_line_names_the_club(client, log_output):
    make_club("harbour")
    client.get("/series/999999/", HTTP_HOST="harbour.localhost")
    assert "WARNING [harbour] django.request: Not Found: /series/999999/\n" in log_output()


def test_on_the_single_club_address_it_names_that_club(client, log_output):
    client.get("/series/999999/")
    assert "WARNING [demo] django.request: Not Found: /series/999999/\n" in log_output()


def test_the_services_own_address_and_outside_a_request_are_dashes(client, settings, log_output):
    settings.SINGLE_CLUB = ""
    make_club("harbour")
    client.get("/series/1/", HTTP_HOST="harbour.localhost")
    client.get("/operator/nothing-here/", HTTP_HOST="localhost")
    logging.getLogger("races").warning("Outside any request")
    lines = log_output().splitlines()
    assert "WARNING [-] django.request: Not Found: /operator/nothing-here/" in lines
    assert lines[-1] == "WARNING [-] races: Outside any request"  # not the last request's club


def test_email_addresses_are_redacted_even_in_tracebacks(log_output):
    try:
        raise SMTPRecipientsRefused({"ann.o'neil+racing@example.co.uk": (550, b"No such user")})
    except SMTPRecipientsRefused:
        logging.getLogger("races.notifications").exception("Could not send %d email(s)", 1)
    output = log_output()
    assert "Traceback" in output and "[email]" in output
    assert "example.co.uk" not in output and "neil" not in output


# --- Sentry ----------------------------------------------------------------------------------


class Kept(Transport):
    """Keeps each report instead of sending it."""

    reports = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.reports.append(event)


@pytest.fixture
def sentry():
    Kept.reports = []
    sentry_sdk.init(dsn="https://key@sentry.invalid/1", transport=Kept, integrations=[DjangoIntegration()],
                    default_integrations=False, **logs.sentry_options())
    yield Kept.reports
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # no DSN: sends nothing


def test_an_error_is_reported_with_the_club_and_nobody_in_it(sentry, monkeypatch):
    series = make_series()
    secret = "-".join(["only", "in", "a", "variable"])  # built, so the source code shown doesn't contain it

    def fails(series):
        password = secret  # a local variable, which must not be sent
        raise RuntimeError(f"Scoring failed for pat@example.com ({len(password)})")

    monkeypatch.setattr("results.views.score_series", fails)
    client = Client(raise_request_exception=False)
    client.force_login(make_member("pat@example.com"))
    response = client.get(reverse("results:series", args=[series.pk]), HTTP_HOST="demo.localhost",
                          HTTP_COOKIE="sessionid=abc")
    assert response.status_code == 500
    [report] = [r for r in sentry if r.get("exception")]
    assert report["tags"]["club"] == "demo"
    assert report["transaction"] == "/series/{pk}/"  # the page
    text = repr(report)
    assert "pat@example.com" not in text and "[email]" in text
    assert secret not in text and "sessionid" not in text
    assert not any("vars" in frame for frame in report["exception"]["values"][0]["stacktrace"]["frames"])
    assert "user" not in report or "email" not in report["user"]
