"""Slice 19: the service's landing page, and Find my club.

The page is on the service's own address, which in tests is ``localhost`` with
SINGLE_CLUB unset. A club's address is ``<subdomain>.localhost``.
"""

import re

import pytest
from django.conf import settings

from races.models import Club
from races.service_views import MAX_MATCHES
from races.testing import make_club

pytestmark = pytest.mark.django_db

SERVICE = {"HTTP_HOST": "localhost"}
HTMX = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "club-matches"}


@pytest.fixture(autouse=True)
def service_address(settings):
    settings.SINGLE_CLUB = ""


def page(client, query=None, **headers):
    data = {} if query is None else {"club": query}
    return client.get("/", data, **SERVICE, **headers).content.decode()


# --- The landing page ------------------------------------------------------------------------


def test_the_landing_page_sells_race_times_and_says_how_to_get_it(client, settings):
    settings.SERVICE_CONTACT_EMAIL = "clubs@racetimes.example"
    html = page(client)
    assert "Race results and handicaps, sorted for your sailing club" in html
    assert "What your club gets" in html and "How it works" in html
    assert 'href="mailto:clubs@racetimes.example"' in html
    assert 'id="club-search"' in html
    # The photo is credited, with its licence.
    assert "Peter Trimming" in html and "creativecommons.org/licenses/by-sa/2.0" in html


def test_the_landing_page_loads_only_the_sites_own_files(client):
    html = page(client)
    files = re.findall(
        r'<(?:link|script|img|source)\b[^>]*?\b(?:href|src)="([^"]+)"', html
    )
    for srcset in re.findall(r'\bsrcset="([^"]+)"', html):
        files += [part.split()[0] for part in srcset.split(",")]
    assert "/static/img/landing/cowes-1600.webp" in files
    assert all(url.startswith(settings.STATIC_URL) for url in files), files


def test_the_bigger_logo_is_on_the_services_own_pages_only(client):
    assert "brand-service-home" in page(client)
    make_club("harbour", "Harbour Sailing Club")
    club_page = client.get("/", HTTP_HOST="harbour.localhost").content.decode()
    assert "brand-service-home" not in club_page


def test_a_clubs_address_still_shows_the_clubs_own_home_page(client):
    make_club("harbour", "Harbour Sailing Club")
    html = client.get("/", HTTP_HOST="harbour.localhost").content.decode()
    assert "Find my club" not in html
    assert "Harbour Sailing Club" in html and 'id="find-a-boat"' in html


# --- Find my club ----------------------------------------------------------------------------


@pytest.fixture
def clubs():
    return {
        "harbour": make_club("harbour", "Harbour Sailing Club"),
        "exesc": make_club("exesc", "Exe Sailing Club"),
        "gone": make_club(
            "gone", "Harbourside Yacht Club", status=Club.Status.SUSPENDED
        ),
    }


def matches(html):
    return re.findall(r'<li><a href="([^"]+)">([^<]+)</a>', html)


def test_nothing_is_listed_until_someone_searches(client, clubs):
    html = page(client)
    assert "Harbour Sailing Club" not in html and "Exe Sailing Club" not in html


def test_a_club_is_found_by_part_of_its_name_in_any_case(client, clubs):
    assert matches(page(client, "HARB")) == [
        ("http://harbour.localhost/", "Harbour Sailing Club")
    ]


def test_a_club_is_found_by_its_address(client, clubs):
    assert matches(page(client, "exesc")) == [
        ("http://exesc.localhost/", "Exe Sailing Club")
    ]


def test_a_suspended_club_isnt_listed(client, clubs):
    assert [name for _, name in matches(page(client, "harbour"))] == [
        "Harbour Sailing Club"
    ]


def test_a_search_needs_two_letters(client, clubs):
    html = page(client, "h")
    assert matches(html) == [] and "Type at least 2 letters" in html


def test_no_match_says_so_and_points_to_getting_race_times(client, clubs):
    html = page(client, "Solent")
    assert "No club called &ldquo;Solent&rdquo; uses Race Times yet" in html
    assert 'href="#get-race-times"' in html


def test_at_most_ten_are_listed_in_name_order(client):
    for n in range(MAX_MATCHES + 2):
        make_club(f"club{n:02d}", f"Club {n:02d} Sailing Club")
    html = page(client, "Sailing")
    names = [name for _, name in matches(html)]
    assert names == [f"Club {n:02d} Sailing Club" for n in range(MAX_MATCHES)]
    assert "Showing the first 10" in html


def test_over_htmx_only_the_matches_come_back(client, clubs):
    html = page(client, "exe", **HTMX)
    assert html.startswith('<div id="club-matches"') and "<html" not in html
    assert matches(html) == [("http://exesc.localhost/", "Exe Sailing Club")]


def test_without_htmx_the_whole_page_comes_back_with_the_matches(client, clubs):
    html = page(client, "exe")
    assert "<html" in html and "Exe Sailing Club" in html


def test_a_club_is_shown_by_name_and_address_only(client, settings):
    make_club("harbour", "Harbour Sailing Club", contact_email="sec@harbour.example")
    html = page(client, "harbour", **HTMX)
    assert "Harbour Sailing Club" in html and "harbour.localhost" in html
    assert "sec@harbour.example" not in html
