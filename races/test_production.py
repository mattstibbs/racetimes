"""Slice 11 part 4: running as a service. The health check and the security settings.

Email from the club, Sentry, logs and throttling have their own sections
below as they're added.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from django.db import connection
from django.urls import reverse

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent


# --- /health/ ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["demo.localhost", "localhost", "nowhere.localhost", "10.0.0.7", "not-allowed.example"])
def test_health_answers_ok_on_any_address(client, host):
    response = client.get("/health/", HTTP_HOST=host)
    assert response.status_code == 200 and response.content == b"ok"
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert not response.cookies


def test_health_answers_over_plain_http_with_the_https_redirect_on(client, settings):
    settings.SECURE_SSL_REDIRECT = True
    assert client.get("/health/").status_code == 200
    assert client.get(reverse("results:home")).status_code == 301  # everything else goes to HTTPS


def test_health_says_error_when_the_database_fails(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("the database is down")
    monkeypatch.setattr(connection, "cursor", broken)
    response = client.get("/health/")
    assert response.status_code == 503 and response.content == b"error"


# --- Security settings -------------------------------------------------------------------


def production_settings(code):
    """Run Python with the production settings loaded, and return what it prints."""
    env = {"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "test-only-" + "x" * 50,
           "DJANGO_SETTINGS_MODULE": "config.settings", "PATH": ""}
    result = subprocess.run(
        [sys.executable, "-c", f"import django; django.setup(); from django.conf import settings; {code}"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def test_production_is_https_only_for_every_club_address():
    got = production_settings(
        "print(settings.SECURE_SSL_REDIRECT, settings.SECURE_HSTS_SECONDS, "
        "settings.SECURE_HSTS_INCLUDE_SUBDOMAINS, settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)"
    )
    assert got == "True 3600 True True True"


def test_production_accepts_every_club_address():
    got = production_settings("print(settings.ALLOWED_HOSTS, settings.CSRF_TRUSTED_ORIGINS)")
    assert "'racetimes.co.uk', '.racetimes.co.uk'" in got
    assert "'https://racetimes.co.uk', 'https://*.racetimes.co.uk'" in got


def test_frames_and_referrers_are_set_explicitly(client):
    response = client.get(reverse("results:home"))
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"


def test_the_production_settings_pass_the_deploy_check():
    env = {"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "test-only-" + "x" * 50, "PATH": ""}
    result = subprocess.run([sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
