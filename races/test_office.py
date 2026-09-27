"""Slice 18: the race office's pages - the front page (with Coming up), the boats
list, deleting a boat, and a series' page.

Who may open each page is in races/test_roles.py, and that no other club's
data shows is in races/test_isolation.py. The boat form's rules are in
races/test_office_forms.py.
"""

from datetime import date, datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from races import race_day
from races.models import Boat, BoatRequest
from races.testing import (
    enter,
    make_administrator,
    make_boat,
    make_member,
    make_race,
    make_series,
)

pytestmark = pytest.mark.django_db


def page(client, name, *args, query="", **headers):
    return client.get(reverse(name, args=args) + query, **headers).content.decode()


# --- The race office's front page ----------------------------------------------------------


def test_nothing_waiting_says_so(committee_client):
    assert "Nothing waiting." in page(committee_client, "races:office")


def test_waiting_requests_link_to_the_change_requests_page(committee_client):
    BoatRequest.objects.create(
        club=make_boat().club,
        kind="CLAIM",
        boat=Boat.objects.get(),
        requested_by=make_member(),
    )
    html = page(committee_client, "races:office")
    assert "1 boat request is waiting for the race committee." in html
    assert reverse("races:requests") in html and "Nothing waiting." not in html


def test_people_joining_are_shown_to_administrators_only(client, committee_client):
    make_member("new@example.com", status="WAITING")
    assert "waiting to join" not in page(committee_client, "races:office")
    client.force_login(make_administrator())
    html = page(client, "races:office")
    assert "1 person is waiting to join the club." in html
    assert reverse("races:members") in html


def test_series_are_listed_open_first_then_final(committee_client):
    older = make_series("Spring")
    make_series("Summer")
    finished = make_series("Winter")
    finished.declared_final_at = "2026-01-01T12:00:00Z"
    finished.save()
    enter(older, make_boat())
    make_race(older, 1)
    make_race(older, 2)
    html = page(committee_client, "races:office")
    assert html.index("Summer") < html.index("Spring") < html.index("Winter")
    # Spring's row: two races, one boat entered.
    row = html[html.index("Spring") :].split("</tr>")[0]
    assert '<td class="num">2</td>' in row and '<td class="num">1</td>' in row


def test_each_series_links_to_its_race_office_page(committee_client):
    series = make_series()
    html = page(committee_client, "races:office")
    assert reverse("races:office_series", args=[series.pk]) in html
    assert reverse("races:office_new_series") in html


def test_the_boats_link_counts_the_clubs_boats(committee_client):
    make_boat("GBR1")
    make_boat("GBR2")
    html = page(committee_client, "races:office")
    assert reverse("races:office_boats") in html and "(2)" in html


# --- The boats list ------------------------------------------------------------------------


@pytest.fixture
def fleet():
    pat = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    return [
        make_boat("GBR 77", name="Puffin", make="Sigma", model="33", owner=pat),
        make_boat("GBR42", name="Kittiwake", owner_name="M. Visitor"),
        make_boat("IRL5", name="Tern"),
    ]


def test_every_boat_is_listed_by_sail_number(committee_client, fleet):
    html = page(committee_client, "races:office_boats")
    assert html.index("GBR 77") < html.index("GBR42") < html.index("IRL5")
    for shown in ("Puffin", "Sigma", "33", "0.964", "Pat Jones", "M. Visitor"):
        assert shown in html
    assert reverse("races:office_boat", args=[fleet[0].pk]) in html


@pytest.mark.parametrize(
    "query, found",
    [
        ("gbr77", "Puffin"),  # ignoring case and spaces
        ("kitti", "Kittiwake"),  # the boat's name
        ("jones", "Puffin"),  # a member owner's name
        ("visitor", "Kittiwake"),  # a typed owner's name
    ],
)
def test_search_by_sail_number_name_or_owner(committee_client, fleet, query, found):
    html = page(committee_client, "races:office_boats", query=f"?q={query}")
    assert found in html
    others = {"Puffin", "Kittiwake", "Tern"} - {found}
    assert not any(f">{name}<" in html for name in others)


def test_search_over_htmx_answers_with_just_the_table(committee_client, fleet):
    html = page(
        committee_client,
        "races:office_boats",
        query="?q=tern",
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="boat-table",
    )
    assert html.startswith('<div id="boat-table"') and "<html" not in html
    assert "Tern" in html and "Puffin" not in html


def test_search_without_htmx_is_the_whole_page(committee_client, fleet):
    html = page(committee_client, "races:office_boats", query="?q=tern")
    assert "<html" in html and 'value="tern"' in html


def test_a_search_that_matches_nothing_says_so(committee_client, fleet):
    html = page(committee_client, "races:office_boats", query="?q=zzz")
    assert "No boats match" in html


# --- Deleting a boat -----------------------------------------------------------------------


def test_a_boat_never_entered_can_be_deleted_after_confirming(committee_client):
    boat = make_boat("GBR5", name="Tern")
    html = page(committee_client, "races:office_boat", boat.pk)
    delete_url = reverse("races:office_delete_boat", args=[boat.pk])
    assert delete_url in html
    confirm = page(committee_client, "races:office_delete_boat", boat.pk)
    assert "Delete Tern (GBR5)?" in confirm
    assert Boat.objects.filter(pk=boat.pk).exists()  # opening the page deletes nothing
    response = committee_client.post(delete_url, follow=True)
    assert not Boat.objects.filter(pk=boat.pk).exists()
    assert "Tern (GBR5) deleted." in response.content.decode()


def test_the_confirmation_says_members_requests_go_too(committee_client):
    boat = make_boat("GBR5")
    BoatRequest.objects.create(
        club=boat.club, kind="CLAIM", boat=boat, requested_by=make_member()
    )
    confirm = page(committee_client, "races:office_delete_boat", boat.pk)
    assert "1 request from members about this boat goes with it." in confirm


def test_a_boat_entered_in_a_series_cant_be_deleted(committee_client):
    boat = make_boat("GBR5")
    enter(make_series(), boat)
    html = page(committee_client, "races:office_boat", boat.pk)
    assert reverse("races:office_delete_boat", args=[boat.pk]) not in html
    assert "can't be deleted" in html
    for method in (committee_client.get, committee_client.post):
        response = method(reverse("races:office_delete_boat", args=[boat.pk]))
        assert response["Location"] == reverse("races:office_boat", args=[boat.pk])
    assert Boat.objects.filter(pk=boat.pk).exists()


# --- Coming up -----------------------------------------------------------------------------


@pytest.fixture
def on_23_september(monkeypatch):
    noon = timezone.make_aware(datetime(2026, 9, 23, 12, 0))
    monkeypatch.setattr(race_day, "now", lambda: noon)


def test_coming_up_lists_the_next_races_from_today(committee_client, on_23_september):
    autumn = make_series("Autumn")
    yesterday = make_race(autumn, 1, on=date(2026, 9, 22))
    today = make_race(autumn, 2, on=date(2026, 9, 23))
    later = [
        make_race(autumn, n, on=date(2026, 9, 23) + timedelta(weeks=n - 2))
        for n in (3, 4, 5, 6)
    ]
    too_late = make_race(autumn, 7, on=date(2026, 12, 1))
    closed = make_series("Summer")
    closed.declared_final_at = timezone.now()
    closed.save()
    finished = make_race(closed, 1, on=date(2026, 9, 24))
    html = page(committee_client, "races:office")
    section = html[html.index("Coming up") : html.index('id="series"')]
    links = [reverse("races:race_day", args=[race.pk]) for race in [today, *later]]
    assert all(link in section for link in links)
    assert [section.index(link) for link in links] == sorted(
        section.index(link) for link in links
    )
    for race in (yesterday, too_late, finished):
        assert reverse("races:race_day", args=[race.pk]) not in section
    assert section.count("Today") == 1 and "Autumn, Race 2" in section


def test_nothing_coming_up_says_so(committee_client, on_23_september):
    make_race(make_series(), 1, on=date(2026, 9, 1))
    assert "No races from today onwards" in page(committee_client, "races:office")


# --- A series' page ------------------------------------------------------------------------


def test_a_series_page_shows_its_races_and_entries(committee_client):
    series = make_series("Autumn")
    race = make_race(series, 1)
    entry = enter(series, make_boat("GBR5", name="Tern"))
    html = page(committee_client, "races:office_series", series.pk)
    for url in (
        reverse("races:race_day", args=[race.pk]),
        reverse("races:office_race", args=[race.pk]),
        reverse("races:office_remove_race", args=[race.pk]),
        reverse("races:office_new_race", args=[series.pk]),
        reverse("races:office_enter_boats", args=[series.pk]),
        reverse("races:office_remove_entry", args=[entry.pk]),
        reverse("races:office_series_settings", args=[series.pk]),
        reverse("races:office_delete_series", args=[series.pk]),
        reverse("results:series", args=[series.pk]),
        reverse("races:series_history", args=[series.pk]),
        reverse("races:final", args=[series.pk]),
    ):
        assert url in html, url
    assert "Tern (GBR5)" in html


def test_a_final_series_page_offers_no_changes(client, committee, season):
    series = season["series"]
    client.post(reverse("races:declare_final", args=[series.pk]))
    html = page(client, "races:office_series", series.pk)
    assert "This series' results are final." in html
    for name, pk in (
        ("races:office_race", season["races"][0].pk),
        ("races:office_remove_race", season["races"][0].pk),
        ("races:office_new_race", series.pk),
        ("races:office_enter_boats", series.pk),
        ("races:office_delete_series", series.pk),
    ):
        assert reverse(name, args=[pk]) not in html, name
    # Its name can still change.
    assert "Change the name" in html


def test_an_entry_with_results_offers_no_remove(committee_client, season):
    html = page(committee_client, "races:office_series", season["series"].pk)
    entry = season["entries"][0]
    assert reverse("races:office_remove_entry", args=[entry.pk]) not in html


def test_the_public_series_page_links_the_committee_to_set_it_up(
    client, committee_client
):
    series = make_series()
    url = reverse("races:office_series", args=[series.pk])
    assert url in page(committee_client, "results:series", series.pk)
    client.logout()
    assert url not in page(client, "results:series", series.pk)
