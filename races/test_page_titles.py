"""The title band: every page's heading sits in it, under the header."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from races.testing import (
    boat_form,
    make_boat,
    make_club,
    make_committee,
    make_member,
    make_operator,
    make_series,
)

TEMPLATES = Path(settings.BASE_DIR) / "templates"
BAND = '<div class="page-title"><div class="wrap">'

# Whole pages only: a partial (_name.html) is a piece of one, and base.html is
# what they all extend. The error page stands alone, with the band copied in,
# and the admin's index is Django's.
PAGES = sorted(
    path
    for path in TEMPLATES.rglob("*.html")
    if not path.name.startswith("_")
    and path.name not in ("base.html", "500.html")
    and "admin" not in path.parts
)


def band(html):
    """What the title band holds, or None if the page has no band."""
    found = re.search(
        r'<div class="page-title"><div class="wrap">(.*?)</div></div>', html, re.S
    )
    return found.group(1) if found else None


# --- Every template puts its heading in the band --------------------------------------


@pytest.mark.parametrize(
    "path", PAGES, ids=[str(p.relative_to(TEMPLATES)) for p in PAGES]
)
def test_a_pages_heading_is_in_the_heading_block(path):
    # A new page can't forget the band, or leave its heading in the content.
    source = path.read_text()
    assert '{% extends "base.html" %}' in source
    if "{% block page_header %}{% endblock %}" in source:
        # The service's front page: its heading is in the photo hero instead.
        assert "{% block hero %}" in source
        return
    heading = re.search(r"{% block heading %}(.*?){% endblock %}", source, re.S)
    assert heading and "<h1" in heading.group(1)
    assert "<h1" not in source.replace(heading.group(0), "")


def test_partials_have_no_page_heading():
    # A fragment swapped in over HTMX must never bring a second title with it.
    partials = list(TEMPLATES.rglob("_*.html"))
    assert partials
    assert not [p.name for p in partials if "<h1" in p.read_text()]


# --- Rendered: one heading, in the band, above everything else -----------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role, url_name, title",
    [
        (None, "races:login", "Log in"),
        (None, "races:privacy", "Privacy notice"),
        ("member", "races:my_boats", "My boats"),
        ("committee", "races:office", "Race office"),
        ("committee", "races:requests", "Change requests from members"),
    ],
)
def test_the_heading_is_in_the_band_before_the_content(client, role, url_name, title):
    if role == "member":
        client.force_login(make_member())
    elif role == "committee":
        client.force_login(make_committee())
    html = client.get(reverse(url_name)).content.decode()
    assert html.count("<h1") == 1
    assert f"<h1>{title}</h1>" in band(html)
    assert html.index("</header>") < html.index(BAND) < html.index("<main")


@pytest.mark.django_db
def test_a_way_back_sits_above_the_heading_in_the_band(client):
    client.force_login(make_committee())
    held = band(client.get(reverse("races:office_boats")).content.decode())
    back = f'<a href="{reverse("races:office")}">Race office</a>'
    assert back in held and held.index(back) < held.index("<h1>Boats</h1>")


@pytest.mark.django_db
def test_a_series_page_keeps_its_description_out_of_the_band(client):
    series = make_series(name="Autumn 2026")
    html = client.get(reverse("results:series", args=[series.pk])).content.decode()
    assert band(html).strip() == "<h1>Autumn 2026</h1>"


@pytest.mark.django_db
def test_a_message_shows_under_the_band(client):
    client.force_login(make_committee())
    boat = make_boat(name="Kittiwake")
    response = client.post(
        reverse("races:office_boat", args=[boat.pk]),
        boat_form(boat, name="Kittiwake II"),
        follow=True,
    )
    html = response.content.decode()
    assert '<ul class="messages">' in html
    assert html.index(BAND) < html.index("<main") < html.index('<ul class="messages">')


@pytest.mark.django_db
def test_the_services_front_page_has_no_band(client, settings):
    settings.SINGLE_CLUB = ""
    html = client.get("/", HTTP_HOST="localhost").content.decode()
    assert band(html) is None
    assert html.count("<h1") == 1  # the hero's


@pytest.mark.django_db
def test_the_operators_pages_have_the_band(client, settings):
    settings.SINGLE_CLUB = ""
    client.force_login(make_operator())
    html = client.get(
        reverse("races:operator_clubs"), HTTP_HOST="localhost"
    ).content.decode()
    assert "<h1>Clubs</h1>" in band(html)


def test_the_error_page_copies_the_band():
    html = render_to_string("500.html")
    assert '<div class="page-title"><h1>Something went wrong</h1></div>' in html
    assert html.index('class="page-title"') < html.index("<main")


# --- The results home page: the club's name, then "Race results" ---------------------


@pytest.mark.django_db
def test_the_home_page_is_titled_with_the_clubs_name(client):
    html = client.get("/").content.decode()
    held = band(html)
    assert "<h1>Demo Club</h1>" in held
    assert '<p class="page-subtitle">Race results</p>' in held
    assert held.index("<h1>") < held.index("Race results")
    assert "<title>Race results - Demo Club - Race Times</title>" in html
    assert "<h1>Results</h1>" not in html


@pytest.mark.django_db
def test_each_clubs_home_page_names_that_club(client):
    make_club("harbour", "Harbour Sailing Club")
    html = client.get("/", HTTP_HOST="harbour.localhost").content.decode()
    assert "<h1>Harbour Sailing Club</h1>" in band(html)
    assert "<title>Race results - Harbour Sailing Club - Race Times</title>" in html
    assert "Demo Club" not in html


@pytest.mark.django_db
def test_a_search_over_htmx_brings_no_title(client):
    make_boat(name="Kittiwake")
    response = client.get(
        "/?q=kitti", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="boat-matches"
    )
    html = response.content.decode()
    assert "Kittiwake" in html and "<h1" not in html and band(html) is None
