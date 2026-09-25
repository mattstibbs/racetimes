import pytest


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
    from races.testing import default_club, join

    user = django_user_model.objects.create_superuser("admin", "admin@example.com", "password")
    join(user, default_club(), role="ADMINISTRATOR")
    return user
