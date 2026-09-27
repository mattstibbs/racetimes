"""Every site stays out of search engines: /robots.txt, and a noindex header."""

import pytest
from django.urls import reverse

from races.models import Club
from races.robots import NOINDEX
from races.testing import enter, make_boat, make_club, make_series

pytestmark = pytest.mark.django_db


@pytest.fixture
def service_address(settings):
    # The service's own address names no club (see races/clubs.py).
    settings.SINGLE_CLUB = ""
    return "localhost"


def test_robots_txt_asks_every_crawler_to_stay_away(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert response.content.decode() == "User-agent: *\nDisallow: /\n"
    assert response["X-Robots-Tag"] == NOINDEX


def test_robots_txt_answers_on_the_service_s_own_address(client, service_address):
    response = client.get("/robots.txt", HTTP_HOST=service_address)
    assert response.status_code == 200
    assert "Disallow: /" in response.content.decode()


@pytest.mark.parametrize("state", ["no such club", "suspended"])
def test_robots_txt_answers_where_the_club_s_pages_dont(client, state):
    # Without it, a crawler would read the 404 or 503 as "try again later".
    if state == "suspended":
        make_club("harbour", status=Club.Status.SUSPENDED)
    host = "nosuch.localhost" if state == "no such club" else "harbour.localhost"
    assert client.get("/", HTTP_HOST=host).status_code in (404, 503)
    response = client.get("/robots.txt", HTTP_HOST=host)
    assert response.status_code == 200
    assert "Disallow: /" in response.content.decode()


def test_every_kind_of_response_says_noindex(client, service_address):
    series = make_series()
    enter(series, make_boat("GBR1", name="Kittiwake"))
    demo = {"HTTP_HOST": "demo.localhost"}
    responses = {
        "home page": client.get("/", **demo),
        "series page": client.get(reverse("results:series", args=[series.pk]), **demo),
        "CSV download": client.get(
            reverse("results:series_csv", args=[series.pk]), **demo
        ),
        "login page": client.get(reverse("races:login"), **demo),
        "a page that needs a login": client.get(reverse("races:requests"), **demo),
        "a page not found": client.get("/no/such/page/", **demo),
        "the service's front page": client.get("/", HTTP_HOST=service_address),
    }
    assert {name: r["X-Robots-Tag"] for name, r in responses.items()} == dict.fromkeys(
        responses, NOINDEX
    )
