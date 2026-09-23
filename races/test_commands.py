"""The ensure_superuser command, run on every deploy."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db

STRONG = "correct-horse-battery-staple"


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "officer")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", STRONG)


def test_creates_the_superuser(credentials):
    call_command("ensure_superuser")
    user = get_user_model().objects.get(username="officer")
    assert user.is_superuser and user.is_staff
    assert user.check_password(STRONG)


def test_leaves_an_existing_user_alone(credentials, monkeypatch):
    call_command("ensure_superuser")
    user = get_user_model().objects.get(username="officer")
    user.set_password("changed-later-in-the-admin")
    user.save()

    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "something-else-entirely")
    call_command("ensure_superuser")
    user.refresh_from_db()
    assert user.check_password("changed-later-in-the-admin")
    assert get_user_model().objects.count() == 1


def test_does_nothing_without_the_variables(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    call_command("ensure_superuser")
    assert not get_user_model().objects.exists()


def test_refuses_a_weak_password(credentials, monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "password")
    with pytest.raises(CommandError, match="too common"):
        call_command("ensure_superuser")
    assert not get_user_model().objects.exists()
