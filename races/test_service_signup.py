"""Slice 28: signing up from the service's own address, racetimes.co.uk.

Step 1 (find your club) is on the service's address; step 2 is the club's own
sign-up page, which names the club. ``localhost`` is the service, with
SINGLE_CLUB off; ``demo.localhost`` and ``harbour.localhost`` are clubs.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from races.models import Club, ClubMembership
from races.testing import PASSWORD, make_club, make_member

pytestmark = pytest.mark.django_db

SERVICE = {"HTTP_HOST": "localhost"}
DEMO = {"HTTP_HOST": "demo.localhost"}
HARBOUR = {"HTTP_HOST": "harbour.localhost"}


@pytest.fixture(autouse=True)
def service_address(settings):
    settings.SINGLE_CLUB = ""


@pytest.fixture
def harbour():
    return make_club("harbour", "Harbour Sailing Club")


def find(client, query=None, **extra):
    data = {} if query is None else {"club": query}
    return client.get(reverse("races:service_signup"), data, **SERVICE, **extra)


# --- Step 1 ------------------------------------------------------------------------------


def test_step_1_is_a_page_with_a_search(client):
    response = find(client)
    html = response.content.decode()
    assert response.status_code == 200
    assert "Step 1 of 2: find your club" in html
    assert "You can join other clubs later with the same account." in html
    assert "Already have an account?" in html


def test_step_1_lists_matches_with_a_button_to_the_clubs_signup_page(client, harbour):
    html = find(client, "harbour").content.decode()
    assert "Harbour Sailing Club" in html
    assert "Sign up at Harbour Sailing Club" in html
    assert "http://harbour.localhost/accounts/signup/?from=find" in html


def test_step_1_matches_by_address_too(client, harbour):
    assert "Harbour Sailing Club" in find(client, "harbo").content.decode()


def test_step_1_lists_only_active_clubs(client, harbour):
    Club.objects.filter(pk=harbour.pk).update(status=Club.Status.SUSPENDED)
    html = find(client, "harbour").content.decode()
    assert "Harbour Sailing Club" not in html
    assert "uses Race Times yet" in html
    assert "Get Race Times for your club" in html


def test_step_1_asks_for_more_letters(client):
    assert "Type at least 2 letters" in find(client, "h").content.decode()


def test_step_1_over_htmx_is_just_the_matches(client, harbour):
    response = find(
        client, "harbour", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="signup-matches"
    )
    html = response.content.decode()
    assert "Sign up at Harbour Sailing Club" in html
    assert "<h1>" not in html
    assert "HX-Target" in response["Vary"]


def test_step_1_is_not_on_a_clubs_address(client):
    assert client.get(reverse("races:service_signup"), **DEMO).status_code == 404


def test_step_1_names_no_people_or_other_clubs_data(client, harbour):
    make_member("pat@example.com", club=harbour)
    html = find(client, "harbour").content.decode()
    assert "pat@example.com" not in html


# --- The ways in -------------------------------------------------------------------------


def test_the_header_offers_sign_up_to_the_public(client):
    html = client.get(reverse("races:login"), **SERVICE).content.decode()
    assert f'href="{reverse("races:service_signup")}">Sign up</a>' in html


def test_the_front_page_hero_offers_sign_up(client):
    html = client.get("/", **SERVICE).content.decode()
    assert 'class="button secondary" href="/signup/">Sign up</a>' in html


def test_the_header_does_not_offer_sign_up_when_logged_in(client):
    client.force_login(make_member("pat@example.com"))
    html = client.get(reverse("races:your_clubs"), **SERVICE).content.decode()
    assert f'href="{reverse("races:service_signup")}">Sign up</a>' not in html


# --- Step 2 ------------------------------------------------------------------------------


def test_the_clubs_signup_page_names_the_club(client, harbour):
    html = client.get(reverse("races:signup"), **HARBOUR).content.decode()
    assert "Sign up to Harbour Sailing Club" in html
    assert "Harbour Sailing Club's administrators approve you joining" in html
    assert "Step 2 of 2" not in html and "Choose another" not in html


def test_arriving_from_step_1_shows_the_step_and_a_way_back(client, harbour):
    url = reverse("races:signup") + "?from=find"
    html = client.get(url, **HARBOUR).content.decode()
    assert "Step 2 of 2: your details" in html
    assert "Not your club?" in html
    assert 'href="http://localhost/signup/">Choose another</a>' in html


def test_signing_up_from_step_1_asks_to_join_that_club(
    client, harbour, mailoutbox, django_capture_on_commit_callbacks
):
    url = reverse("races:signup") + "?from=find"
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url,
            {
                "first_name": "Pat",
                "last_name": "Jones",
                "email": "pat@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            **HARBOUR,
        )
    assert response.status_code == 200
    user = get_user_model().objects.get(email="pat@example.com")
    membership = ClubMembership.objects.get(user=user)
    assert membership.club == harbour
    assert membership.status == ClubMembership.Status.WAITING
    assert (
        len(mailoutbox) == 1
        and "Harbour Sailing Club" in mailoutbox[0].subject + mailoutbox[0].body
    )


# --- Someone already logged in -----------------------------------------------------------


def test_your_clubs_offers_join_another_club(client):
    client.force_login(make_member("pat@example.com"))
    html = client.get(reverse("races:your_clubs"), **SERVICE).content.decode()
    assert "Join another club" in html
    assert f'href="{reverse("races:service_signup")}"' in html


def test_logged_in_step_1_offers_join_buttons_to_the_clubs_site(client, harbour):
    client.force_login(make_member("pat@example.com"))
    html = find(client, "harbour").content.decode()
    assert "Join another club" in html
    assert "Join Harbour Sailing Club" in html
    assert f"http://harbour.localhost{reverse('races:my_boats')}" in html
    assert "Step 1 of 2" not in html


def test_logged_in_step_1_goes_to_clubs_you_already_belong_to(client):
    client.force_login(make_member("pat@example.com"))
    html = find(client, "demo").content.decode()
    assert "Go to Demo Club" in html and "Join Demo Club" not in html
