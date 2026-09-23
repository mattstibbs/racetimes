import pytest


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    # pytest-django's admin_client creates a user with a password, and the real
    # hasher is deliberately slow. Tests do not need it to be secure.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
