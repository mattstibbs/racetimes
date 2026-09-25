"""Slice 11 part 5: the privacy notice and terms, the footer, and essential cookies only."""

import pytest
from django.urls import reverse

from races.test_isolation import DEMO, clubs, log_in, urls_for  # noqa: F401 (clubs is a fixture)
from races.test_members import PASSWORD
from races.testing import make_member

pytestmark = pytest.mark.django_db

ESSENTIAL = {"sessionid", "csrftoken"}


@pytest.mark.parametrize("page, heading", [("races:privacy", "Privacy notice"), ("races:terms", "Terms of service")])
@pytest.mark.parametrize("host", ["demo.localhost", "localhost"])
def test_the_notice_and_terms_are_on_every_address_marked_draft(client, settings, page, heading, host):
    settings.SINGLE_CLUB = ""
    settings.SERVICE_CONTACT_EMAIL = "hello@racetimes.example"
    response = client.get(reverse(page), HTTP_HOST=host)
    html = response.content.decode()
    assert response.status_code == 200 and f"<h1>{heading}</h1>" in html
    assert "<strong>Draft.</strong>" in html and "hello@racetimes.example" in html


def test_the_notice_names_the_club_as_controller_and_lists_the_cookies(client):
    html = client.get(reverse("races:privacy")).content.decode()
    assert "<strong>controller</strong>" in html and "<strong>processor</strong>" in html
    assert "<strong>sessionid</strong>" in html and "<strong>csrftoken</strong>" in html


@pytest.mark.parametrize("role", ["public", "member", "committee", "administrator", "operator"])
def test_every_page_links_to_both_in_its_footer(client, clubs, role):
    log_in(client, role, clubs)
    footer = f'<a href="{reverse("races:privacy")}">Privacy notice</a> <a href="{reverse("races:terms")}">Terms</a>'
    missing = []
    for name, args in urls_for(clubs["demo"]).items():
        response = client.get(reverse(name, args=args), HTTP_HOST=DEMO)
        if response.status_code == 200 and response["Content-Type"].startswith("text/html") and not name.endswith("csv"):
            if "<html" in response.content.decode() and footer not in response.content.decode():
                missing.append(name)
    assert missing == []


def test_sign_up_says_what_you_agree_to(client):
    html = client.get(reverse("races:signup")).content.decode()
    assert "By signing up you agree to the" in html and reverse("races:terms") in html


def cookies_set(response):
    return set(response.cookies.keys())


@pytest.mark.parametrize("role", ["public", "member", "committee", "administrator", "operator"])
def test_no_page_sets_a_cookie_but_the_essential_two(client, clubs, role):
    log_in(client, role, clubs)
    seen = set()
    for name, args in urls_for(clubs["demo"]).items():
        seen |= cookies_set(client.get(reverse(name, args=args), HTTP_HOST=DEMO))
    assert seen <= ESSENTIAL, seen - ESSENTIAL


def test_logging_in_and_a_saved_message_use_only_the_essential_two(client):
    make_member("pat@example.com", password=PASSWORD)
    response = client.post(reverse("races:login"), {"username": "pat@example.com", "password": PASSWORD})
    seen = cookies_set(response)
    # Registering a boat says so on the next page: the message travels in the session.
    response = client.post(reverse("races:register_boat"), {"sail_number": "GBR5", "name": "Tern",
                                                            "base_number": "0.900"})
    seen |= cookies_set(response)
    page = client.get(response["Location"])
    seen |= cookies_set(page)
    assert '<ul class="messages">' in page.content.decode()
    assert seen <= ESSENTIAL, seen
