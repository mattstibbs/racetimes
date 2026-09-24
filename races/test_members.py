"""Slice 3: members' accounts, and the requests they make.

Organised by acceptance criterion. Pages are driven the way a member would,
through the client, including trying other members' boats and requests by URL.
"""

from decimal import Decimal
from html import escape

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from races.forms import PENDING_APPROVAL
from races.models import Boat, BoatRequest, EntryRequest, SeriesEntry
from races.testing import enter, make_boat, make_member, make_series

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"


def sign_up(client, email="new@example.com", **fields):
    data = {"first_name": "Sam", "last_name": "Taylor", "email": email,
            "password1": PASSWORD, "password2": PASSWORD, **fields}
    return client.post(reverse("races:signup"), data)


def log_in(client, email, password=PASSWORD):
    return client.post(reverse("races:login"), {"username": email, "password": password})


@pytest.fixture
def member(client):
    user = make_member("pat@example.com")
    client.force_login(user)
    return user


def boat_form(**fields):
    data = {"sail_number": "GBR42", "name": "Kittiwake", "make": "Westerly", "model": "Centaur",
            "length_overall_m": "7.92", "waterline_length_m": "6.48", "base_number": "0.805",
            "member_note": ""}
    data.update(fields)
    return data


# --- Sign-up: nobody logs in until the administrator approves -----------------


def test_sign_up_creates_an_account_that_cannot_log_in_yet(client):
    response = sign_up(client, email="New@Example.com")
    assert "waiting for approval" in response.content.decode()
    user = get_user_model().objects.get()
    assert (user.username, user.email, user.is_active) == ("new@example.com", "new@example.com", False)
    assert user.get_full_name() == "Sam Taylor"


def test_a_waiting_member_is_told_why_they_cannot_log_in(client):
    sign_up(client)
    response = log_in(client, "new@example.com")
    assert escape(PENDING_APPROVAL) in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_a_wrong_password_does_not_reveal_a_waiting_account(client):
    sign_up(client)
    response = log_in(client, "new@example.com", "not-the-password")
    html = response.content.decode()
    assert escape(PENDING_APPROVAL) not in html
    assert "correct" in html  # Django's own "enter a correct username and password"


def test_an_approved_member_logs_in_with_their_email_in_any_case(client):
    sign_up(client)
    get_user_model().objects.update(is_active=True)
    response = log_in(client, "NEW@example.COM")
    assert response.status_code == 302
    assert response["Location"] == reverse("races:my_boats")


@pytest.mark.parametrize("email", ["pat@example.com", "PAT@example.com"])
def test_one_account_per_email(client, email):
    make_member("pat@example.com")
    response = sign_up(client, email=email)
    assert "already exists" in response.content.decode()
    assert get_user_model().objects.count() == 1


def test_names_are_required(client):
    response = sign_up(client, first_name="", last_name="")
    assert response.status_code == 200
    assert not get_user_model().objects.exists()


def test_a_weak_password_is_refused(client):
    response = sign_up(client, password1="password", password2="password")
    assert "too common" in response.content.decode()


# --- Requests change nothing until approved -----------------------------------


def test_registering_a_boat_is_a_request(client, member):
    response = client.post(reverse("races:register_boat"), boat_form())
    assert response.status_code == 302
    request = BoatRequest.objects.get()
    assert (request.kind, request.requested_by, request.status) == ("REGISTER", member, "PENDING")
    assert request.base_number == Decimal("0.805")
    assert not Boat.objects.exists()


def test_a_sail_number_on_record_offers_a_claim_instead(client, member):
    boat = make_boat("GBR 42", name="Kittiwake")
    response = client.post(reverse("races:register_boat"), boat_form(sail_number="gbr42"))
    html = response.content.decode()
    assert "already registered" in html
    assert reverse("races:claim_boat", args=[boat.pk]) in html
    assert not BoatRequest.objects.exists()


def test_claiming_a_boat_is_a_request(client, member):
    boat = make_boat()
    client.post(reverse("races:claim_boat", args=[boat.pk]), {"member_note": "Bought her in May"})
    request = BoatRequest.objects.get()
    assert (request.kind, request.boat, request.member_note) == ("CLAIM", boat, "Bought her in May")
    boat.refresh_from_db()
    assert boat.owner is None


def test_requesting_a_change_starts_from_the_boats_details(client, member):
    boat = make_boat("GBR42", base_number="0.805", owner=member, name="Kittiwake")
    page = client.get(reverse("races:change_boat", args=[boat.pk])).content.decode()
    assert 'value="Kittiwake"' in page and 'value="0.805"' in page

    client.post(reverse("races:change_boat", args=[boat.pk]), boat_form(base_number="0.812"))
    request = BoatRequest.objects.get()
    assert (request.kind, request.boat, request.base_number) == ("CHANGE", boat, Decimal("0.812"))
    boat.refresh_from_db()
    assert boat.base_number == Decimal("0.805")


def test_a_change_that_changes_nothing_is_refused(client, member):
    boat = make_boat("GBR42", base_number="0.805", owner=member, name="Kittiwake",
                     make="Westerly", model="Centaur",
                     length_overall_m=Decimal("7.92"), waterline_length_m=Decimal("6.48"))
    response = client.post(reverse("races:change_boat", args=[boat.pk]), boat_form())
    assert "Nothing has changed" in response.content.decode()
    assert not BoatRequest.objects.exists()


def test_a_change_cannot_take_another_boats_sail_number(client, member):
    make_boat("GBR99")
    boat = make_boat("GBR42", owner=member)
    response = client.post(reverse("races:change_boat", args=[boat.pk]), boat_form(sail_number="GBR99"))
    assert "already registered" in response.content.decode()


def test_one_request_at_a_time_per_boat(client, member):
    boat = make_boat("GBR42", owner=member)
    client.post(reverse("races:change_boat", args=[boat.pk]), boat_form(name="New name"))
    response = client.get(reverse("races:change_boat", args=[boat.pk]))
    assert response.status_code == 302
    assert BoatRequest.objects.count() == 1


def test_entering_a_series_is_a_request(client, member):
    boat = make_boat(owner=member)
    series = make_series()
    client.post(reverse("races:enter_series", args=[boat.pk]), {"series": series.pk, "member_note": ""})
    request = EntryRequest.objects.get()
    assert (request.series, request.boat, request.status) == (series, boat, "PENDING")
    assert not SeriesEntry.objects.exists()


def test_only_series_not_yet_entered_or_asked_for_are_offered(client, member):
    boat = make_boat(owner=member)
    entered, asked, open_ = make_series("Entered"), make_series("Asked"), make_series("Open")
    enter(entered, boat)
    EntryRequest.objects.create(series=asked, boat=boat, requested_by=member)
    page = client.get(reverse("races:enter_series", args=[boat.pk])).content.decode()
    assert "Open" in page and "Entered" not in page and "Asked" not in page


def test_a_member_can_withdraw_a_pending_request(client, member):
    request = BoatRequest.objects.create(kind="REGISTER", sail_number="GBR1", requested_by=member)
    client.post(reverse("races:withdraw_request", args=["boat", request.pk]))
    request.refresh_from_db()
    assert request.status == "WITHDRAWN"


def test_a_decided_request_cannot_be_withdrawn(client, member):
    request = BoatRequest.objects.create(kind="REGISTER", sail_number="GBR1", requested_by=member,
                                         status="REJECTED", committee_note="Not a club boat")
    client.post(reverse("races:withdraw_request", args=["boat", request.pk]))
    request.refresh_from_db()
    assert request.status == "REJECTED"


def test_my_boats_shows_boats_entries_and_requests(client, member):
    boat = make_boat("GBR42", owner=member, name="Kittiwake")
    enter(make_series("Autumn 2026"), boat)
    BoatRequest.objects.create(kind="REGISTER", sail_number="GBR7", name="Puffin",
                               requested_by=member, status="REJECTED", committee_note="Wrong base number")
    page = client.get(reverse("races:my_boats")).content.decode()
    for text in ["GBR42 Kittiwake", "Autumn 2026", "Rejected", "Wrong base number"]:
        assert text in page


def test_my_boats_links_to_each_boat_s_results(client, member):
    boat = make_boat("GBR42", owner=member, name="Kittiwake")
    series = make_series("Autumn 2026")
    enter(series, boat)
    page = client.get(reverse("races:my_boats")).content.decode()
    assert reverse("results:boat", args=[boat.pk]) in page
    # The series opens with the boat followed.
    assert f'{reverse("results:series", args=[series.pk])}?boat={boat.pk}"' in page


# --- A member sees and acts on only their own boats and requests --------------


@pytest.fixture
def someone_elses(member):
    other = make_member("other@example.com")
    boat = make_boat("GBR99", owner=other)
    request = BoatRequest.objects.create(kind="CHANGE", boat=boat, requested_by=other, name="x")
    return boat, request


def test_another_members_boat_cannot_be_changed_or_entered(client, someone_elses):
    boat, _ = someone_elses
    assert client.get(reverse("races:change_boat", args=[boat.pk])).status_code == 404
    assert client.get(reverse("races:enter_series", args=[boat.pk])).status_code == 404
    assert client.post(reverse("races:enter_series", args=[boat.pk]),
                       {"series": make_series().pk}).status_code == 404


def test_another_members_request_cannot_be_withdrawn(client, someone_elses):
    _, request = someone_elses
    response = client.post(reverse("races:withdraw_request", args=["boat", request.pk]))
    assert response.status_code == 404
    request.refresh_from_db()
    assert request.status == "PENDING"


def test_my_boats_shows_nothing_of_anyone_elses(client, someone_elses):
    page = client.get(reverse("races:my_boats")).content.decode()
    assert "GBR99" not in page


def test_member_pages_need_a_login(client):
    for name in ["races:my_boats", "races:register_boat"]:
        response = client.get(reverse(name))
        assert response.status_code == 302
        assert response["Location"].startswith(reverse("races:login"))
