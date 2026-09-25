"""Slice 11 part 4: running as a service. The health check and the security settings.

Email from the club, Sentry, logs and throttling have their own sections
below as they're added.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml
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


# --- The Render Blueprint (slice 12) -----------------------------------------------------------

BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text())
SERVICES = {service["name"]: service for service in BLUEPRINT["services"]}
DATABASES = {database["name"]: database for database in BLUEPRINT["databases"]}


def env(service):
    return {var["key"]: var for var in service["envVars"]}


def test_production_deploys_only_when_asked_in_frankfurt_with_checks():
    production = SERVICES["racetimes-production"]
    assert production["autoDeploy"] is False and production["region"] == "frankfurt"
    assert production["preDeployCommand"] == "./release.sh" and production["healthCheckPath"] == "/health/"
    assert "migrate" not in production["buildCommand"]  # database changes wait for the pre-deploy step
    assert DATABASES["racetimes-production-db"]["region"] == "frankfurt"
    assert DATABASES["racetimes-production-db"]["plan"] != "free"


def test_production_is_every_club_at_its_own_address_with_no_secret_in_the_file():
    variables = env(SERVICES["racetimes-production"])
    assert variables["DJANGO_DEBUG"]["value"] == "0" and variables["TRUSTED_PROXIES"]["value"] == "1"
    assert "SINGLE_CLUB" not in variables and "SERVICE_DOMAIN" not in variables  # racetimes.co.uk by default
    for secret in ("EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "SENTRY_DSN", "DJANGO_SUPERUSER_PASSWORD"):
        assert variables[secret] == {"key": secret, "sync": False}
    assert variables["DJANGO_SECRET_KEY"] == {"key": "DJANGO_SECRET_KEY", "generateValue": True}
    for secret in ("AWS_SECRET_ACCESS_KEY", "BACKUP_PASSPHRASE"):
        assert env(SERVICES["racetimes-backup"])[secret] == {"key": secret, "sync": False}


def test_the_test_site_is_as_it_was():
    test_site = SERVICES["racetimes"]
    assert test_site["plan"] == "free" and test_site["buildCommand"] == "./build.sh"
    assert env(test_site)["SINGLE_CLUB"]["value"] == "demo" and "region" not in test_site
    assert "./release.sh" in (ROOT / "build.sh").read_text()


def test_the_release_step_migrates_and_makes_the_cache_table():
    release = (ROOT / "release.sh").read_text()
    assert "migrate --no-input" in release and "createcachetable" in release and "ensure_superuser" in release


def test_the_scripts_stop_at_the_first_failure_and_can_run():
    import os

    for script in ("build.sh", "release.sh", "backup/backup.sh", "backup/restore.sh"):
        path = ROOT / script
        assert os.access(path, os.X_OK), script
        assert "set -o errexit" in path.read_text() or "set -eu" in path.read_text(), script


def test_backups_are_encrypted_before_they_leave_and_never_logged():
    backup = (ROOT / "backup" / "backup.sh").read_text()
    assert backup.index("gpg") < backup.index("aws s3 cp")
    assert "--symmetric --cipher-algo AES256" in backup and 'echo "$BACKUP_PASSPHRASE' not in backup


# --- scripts/check_live.py (slice 12) ----------------------------------------------------------

sys.path.insert(0, str(ROOT / "scripts"))
import check_live  # noqa: E402


def test_the_live_checks_judge_answers_correctly():
    assert check_live.healthy(200, {}, "ok\n") and not check_live.healthy(503, {}, "error")
    assert not check_live.healthy(200, {}, "<html>")  # a page, not the health check
    to_apex = check_live.redirects_to("https://racetimes.co.uk/")
    assert to_apex(301, {"Location": "https://racetimes.co.uk/"}, "")
    assert not to_apex(302, {"Location": "https://racetimes.co.uk/"}, "")  # temporary isn't enough
    assert not to_apex(301, {"Location": "http://racetimes.co.uk/"}, "")
    good = {"Strict-Transport-Security": "max-age=3600; includeSubDomains", "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin"}
    assert check_live.secure_headers(200, good, "")
    assert not check_live.secure_headers(200, {**good, "Strict-Transport-Security": "max-age=3600"}, "")


def test_the_live_checks_cover_every_address_including_a_made_up_one():
    urls = [url for _, url, _ in check_live.checks("racetimes.co.uk", "demo")]
    assert "https://racetimes.co.uk/health/" in urls and "https://demo.racetimes.co.uk/health/" in urls
    assert "http://racetimes.co.uk/" in urls and "https://www.racetimes.co.uk/" in urls
    made_up = [u for u in urls if u.startswith("https://check-")]
    assert len(made_up) == 1 and made_up[0].endswith(".racetimes.co.uk/health/")


def test_the_live_check_uses_nothing_but_the_standard_library():
    source = (ROOT / "scripts" / "check_live.py").read_text()
    imports = {line.split()[1].split(".")[0] for line in source.splitlines() if line.startswith(("import ", "from "))}
    assert imports <= set(sys.stdlib_module_names), imports - set(sys.stdlib_module_names)
