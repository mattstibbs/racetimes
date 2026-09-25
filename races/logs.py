"""Logs and error reports that say which club, and name nobody (slice 11 part 4).

- Every log line says which club's address the request was for, e.g.
  ``WARNING [demo] django.request: Not Found: /series/99/``, or ``[-]`` outside
  a request or on the service's own address. ``ClubMiddleware`` sets it.
- Anything shaped like an email address is replaced with ``[email]``, in log
  lines (tracebacks included) and in error reports sent to Sentry. An SMTP
  error, for one, can quote the address it refused. Names can't be spotted
  like that, so new log calls follow the rule "ids, never names" (CLAUDE.md).

Settings load this module before Django is set up, so it imports nothing
from the app.
"""

import logging
import re
from contextvars import ContextVar

NO_CLUB = "-"

EMAIL_SHAPED = re.compile(r"[\w.%+'-]+@[\w-]+(\.[\w-]+)+")

club = ContextVar("club", default=NO_CLUB)


def redact(text):
    return EMAIL_SHAPED.sub("[email]", text)


def forget_club(**kwargs):
    """Connected to request_started and request_finished (races/apps.py).

    Not reset by the middleware itself, since Django logs a response (such as
    "Not Found") after the middleware has returned it.
    """
    club.set(NO_CLUB)


class ClubFilter(logging.Filter):
    """Gives every log record a ``club``, for the formatter to show."""

    def filter(self, record):
        record.club = club.get()
        return True


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


# --- Sentry ----------------------------------------------------------------------------------


def sentry_options():
    """How ``sentry_sdk.init`` is called when SENTRY_DSN is set (config/settings.py)."""
    return {
        "send_default_pii": False,  # no user, IP address or cookies
        "max_request_body_size": "never",  # no form contents
        "include_local_variables": False,  # a failing function's variables can hold names and emails
        "before_send": scrub_event,
        "before_breadcrumb": scrub_event,  # log messages recorded before the error
    }


def scrub_event(event, hint):
    """An error report (or a breadcrumb in one) with every email-shaped string redacted."""
    return _scrub(event)


def _scrub(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value
