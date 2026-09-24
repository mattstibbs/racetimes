"""The results app reads and never writes, and races never depends on it."""

import ast
from pathlib import Path

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from races.testing import enter, make_boat, make_member, make_race, make_series, record

ROOT = Path(__file__).resolve().parent.parent


def imported_modules(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_races_never_imports_results():
    for path in (ROOT / "races").rglob("*.py"):
        for module in imported_modules(path):
            assert module.split(".")[0] != "results", f"{path} imports {module}"


def test_results_has_no_models_or_migrations():
    assert list(apps.get_app_config("results").get_models()) == []
    assert not (ROOT / "results" / "migrations").exists()


@pytest.fixture
def urls(db):
    member = make_member()
    boat = make_boat("GBR42", name="Kittiwake", owner=member)
    series = make_series()
    race = make_race(series)
    record(race, enter(series, boat), "19:00:00")
    series_url = reverse("results:series", args=[series.pk])
    return member, [
        (reverse("results:home"), {}, None),
        (reverse("results:home"), {"q": "gbr"}, "boat-matches"),
        (series_url, {}, None),
        (series_url, {"race": 1, "boat": boat.pk, "detail": 1}, "series-body"),
        (reverse("results:boat", args=[boat.pk]), {}, None),
    ]


def test_every_page_refuses_to_be_posted_to(client, urls):
    _, pages = urls
    for url, params, _ in pages:
        assert client.post(url, params).status_code == 405


@pytest.mark.parametrize("logged_in", [False, True])
def test_every_page_only_reads_the_database(client, urls, logged_in):
    member, pages = urls
    if logged_in:
        client.force_login(member)
    for url, params, target in pages:
        for headers in [{}, {"HX-Request": "true", "HX-Target": target}] if target else [{}]:
            with CaptureQueriesContext(connection) as queries:
                assert client.get(url, params, headers=headers).status_code == 200
            writes = [q["sql"] for q in queries if not q["sql"].lstrip().upper().startswith("SELECT")]
            assert writes == [], url
