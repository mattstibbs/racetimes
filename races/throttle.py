"""Slowing down password guessing (slice 11 part 4).

Two counts of failed logins are kept, in Django's cache (the database cache,
so every web worker shares them):

- one per account: the email as typed, normalised as the login form does;
- one per address: the client's IP address (``client_address``).

After ``LIMIT`` failures within ``WINDOW`` of the first, either count locks
for ``LOCK``. A locked login is refused before the password is checked, so
guessing gets nowhere even with the right password. A correct password clears
its account's count, not the address's, or one good login would let an
attacker keep guessing at other accounts from the same address.

It works the same whether or not the email has an account, so the message
reveals nothing. The owner agreed that someone can lock an account's owner
out this way for 15 minutes, and that a password reset doesn't lift the lock
(docs/decisions.md).

Keys are hashed, so the cache holds no email or IP addresses. Two failures at
the same instant can both read the same count; that loses a count, not a lock,
which is fine for slowing guessing down.
"""

import hashlib
import time
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

LIMIT = 10
WINDOW = 15 * 60  # seconds
LOCK = 15 * 60

LOCKED = "Too many failed logins. Try again in 15 minutes."

now = time.time  # the clock; tests fix it


def client_address(request):
    """The address of whoever sent the request.

    Behind the host's proxy, REMOTE_ADDR is the proxy's, the same for everyone,
    and the client's is in X-Forwarded-For. But anyone can send that header
    with made-up addresses in it; only the entries the trusted proxies added,
    at its right-hand end, can be believed. TRUSTED_PROXIES says how many
    there are: 0 with no proxy (development), 1 on Render.
    """
    trusted = settings.TRUSTED_PROXIES
    if trusted:
        forwarded = [a.strip() for a in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if a.strip()]
        if forwarded:
            return forwarded[-min(trusted, len(forwarded))]
    return request.META.get("REMOTE_ADDR", "")


def _key(kind, value):
    return f"login-failures:{kind}:{hashlib.sha256(value.encode()).hexdigest()}"


def _keys(request, username):
    keys = [_key("account", username)]
    if request is not None:
        keys.append(_key("address", client_address(request)))
    return keys


def _locked(key):
    record = cache.get(key)
    return bool(record and record["locked_until"] and now() < record["locked_until"])


def _failed(key):
    record = cache.get(key)
    if not record or now() - record["since"] >= WINDOW:
        record = {"failures": 0, "since": now(), "locked_until": None}
    record["failures"] += 1
    if record["failures"] >= LIMIT:
        record["locked_until"] = now() + LOCK
    # Kept a little longer than it matters; expired rows are cleared by the cache.
    cache.set(key, record, WINDOW + LOCK)


@contextmanager
def guard(request, username, password):
    """Wrap a login form's check of the password.

    Raises the "too many" error if the account or address is locked, counts a
    failed login ("invalid_login"), and clears the account's count when the
    check passes. With either field empty no password is checked, so there's
    nothing to guard (and nothing to clear).
    """
    if not username or not password:
        yield
        return
    keys = _keys(request, username)
    if any(_locked(key) for key in keys):
        raise ValidationError(LOCKED, code="throttled")
    try:
        yield
    except ValidationError as error:
        if getattr(error, "code", None) == "invalid_login":
            for key in keys:
                _failed(key)
        raise
    cache.delete(keys[0])
