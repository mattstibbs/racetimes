"""pytest fixtures for the races app's tests.

The autouse ones apply to every test here; the rest are shared by several test
modules, which ask for them by name. Plain helpers are in ``races/testing.py``.
"""

from contextlib import nullcontext
from datetime import date

import pytest

from races import notifications
from races.models import Finish
from races.testing import (
    build_club_data,
    default_club,
    enter,
    join,
    make_boat,
    make_club,
    make_committee,
    make_member,
    make_race,
    make_series,
    publish,
    record,
)


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    # pytest-django's admin_client creates a user with a password, and the real
    # hasher is deliberately slow. Tests do not need it to be secure.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def single_club(settings):
    # Slice 11: the test client's address ("testserver") names no club, so
    # every test sees the first club, as the test site on Render does.
    # Tests of several clubs set the host instead (races/test_isolation.py).
    settings.SINGLE_CLUB = "demo"


@pytest.fixture(autouse=True)
def plain_csrf_tokens(monkeypatch):
    """CSRF tokens without letters that could spell a name.

    Every page carries a random 64-letter token, and a test checking that a
    name like "Pat" is *not* on the page would fail whenever the token
    happened to contain it: about 1 run in 2,000 for a three-letter name. The
    token still works; it's just the same each time.
    """
    monkeypatch.setattr("django.middleware.csrf._get_new_csrf_string", lambda: "0" * 32)


@pytest.fixture
def admin_user(django_user_model):
    """pytest-django's superuser, plus Demo Club's administrator membership.

    That's what the migration gives the site's existing superuser (slice 11),
    so tests that use admin_client for the admin still reach Demo Club's.
    """
    user = django_user_model.objects.create_superuser(
        "admin", "admin@example.com", "password"
    )
    join(user, default_club(), role="ADMINISTRATOR")
    return user


# --- Fixtures shared by several test modules ------------------------------------------


@pytest.fixture
def run_on_commit(monkeypatch):
    """Send emails at once: they wait for the transaction to commit, which a test never does.

    Returns a do-nothing context manager, so ``with run_on_commit():`` also reads well.
    """
    monkeypatch.setattr(
        notifications.transaction, "on_commit", lambda func, *a, **kw: func()
    )
    return nullcontext


@pytest.fixture
def committee(client):
    user = make_committee()
    client.force_login(user)
    return user


@pytest.fixture
def committee_client(client):
    """The test client, logged in as Demo Club's race committee."""
    client.force_login(make_committee())
    return client


@pytest.fixture
def staff_user(django_user_model):
    # The superuser is Demo Club's administrator, as the slice 11 migration makes it.
    user = django_user_model.objects.create_user(
        "officer", is_staff=True, is_superuser=True
    )
    join(user, default_club(), role="ADMINISTRATOR")
    return user


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def season():
    """Three owned boats; races 1 and 2 sailed and published; race 3 never sailed."""
    series = make_series("Autumn 2026", discards=0)
    owners = [
        make_member(f"{name}@example.com", first_name=name.capitalize())
        for name in ("pat", "sam", "jo")
    ]
    entries = [
        enter(series, make_boat(sail, name=name, base_number=base, owner=owner))
        for (sail, name, base), owner in zip(
            [
                ("GBR42", "Kittiwake", "0.805"),
                ("GBR77", "Puffin", "0.842"),
                ("GBR7", "Tern", "0.900"),
            ],
            owners,
            strict=True,
        )
    ]
    race_1, race_2 = make_race(series, 1), make_race(series, 2, on=date(2026, 9, 30))
    race_3 = make_race(series, 3, on=date(2026, 10, 7))
    for race, times in [
        (race_1, ["19:05:31", "19:07:02", "19:02:10"]),
        (race_2, ["19:01:00", "19:06:30", None]),
    ]:
        for entry, time in zip(entries, times, strict=True):
            record(race, entry, time) if time else record(
                race, entry, status=Finish.Status.DNF
            )
    publish(race_1, race_2)
    return {
        "series": series,
        "entries": entries,
        "races": [race_1, race_2, race_3],
        "owners": owners,
    }


@pytest.fixture
def clubs():
    harbour = make_club(
        "harbour", "Harbour Sailing Club", contact_email="sec@harbour.example"
    )
    shared = make_member("shared@example.com", first_name="Sam")
    demo = build_club_data(
        default_club(),
        "Arctic",
        ["Avocet", "Auk", "Albatross"],
        "Autumn Series",
        make_member("ann@example.com", first_name="Ann"),
        shared,
    )
    join(shared, harbour)  # a member of both clubs (slice 11 part 2)
    harbour_data = build_club_data(
        harbour,
        "Black",
        ["Bittern", "Brant", "Booby"],
        "Harbour Winter",
        make_member("bea@example.com", first_name="Bea", club=harbour),
        shared,
    )
    return {"demo": demo, "harbour": harbour_data, "shared": shared}
