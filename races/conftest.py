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
