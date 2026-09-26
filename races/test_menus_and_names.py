"""Slice 15: the menu's items and order for each role, and the renamed pages."""

import re

import pytest
from django.urls import reverse
from django.utils import timezone

from races import final
from races.scoring import engine_outcome
from races.testing import (
    enter,
    make_administrator,
    make_boat,
    make_committee,
    make_member,
    make_operator,
    make_series,
)

pytestmark = pytest.mark.django_db


def menu(client, url="/", **kwargs):
    html = client.get(url, **kwargs).content.decode()
    nav = re.search(
        r'<nav aria-label="(?:Site|Operator)">(.*?)</nav>', html, re.S
    ).group(1)
    return [
        re.sub(r"\s+", " ", item).strip()
        for item in re.findall(r">([^<>]+)</(?:a|button)>", nav)
    ]


def logged_in(client, user):
    client.force_login(user)
    return client


# --- Items 11 to 14: the menu ------------------------------------------------------------------


def test_the_public_menu(client):
    assert menu(client) == ["Club results", "Log in", "Sign up"]


def test_a_member_s_menu(client):
    assert menu(logged_in(client, make_member())) == [
        "Club results",
        "My boats",
        "My account",
        "Log out",
    ]


@pytest.mark.parametrize(
    "status, label", [(None, "Join this club"), ("WAITING", "Waiting to join")]
)
def test_someone_not_yet_a_member_has_join_where_my_boats_would_be(
    client, status, label
):
    user = make_member(club=None) if status is None else make_member(status=status)
    assert menu(logged_in(client, user)) == [
        "Club results",
        label,
        "My account",
        "Log out",
    ]


def test_the_race_committee_s_menu(client):
    assert menu(logged_in(client, make_committee())) == [
        "Club results",
        "Club setup",
        "Change requests",
        "My boats",
        "My account",
        "Log out",
    ]


def test_a_club_administrator_s_menu(client):
    assert menu(logged_in(client, make_administrator())) == [
        "Club results",
        "Club setup",
        "Club members",
        "Change requests",
        "My boats",
        "My account",
        "Log out",
    ]


def test_club_results_goes_to_the_club_s_results_home_page(client):
    html = client.get(reverse("races:login")).content.decode()
    assert f'<a href="{reverse("results:home")}">Club results</a>' in html


def test_the_operator_s_menu_is_unchanged(client, settings):
    settings.SINGLE_CLUB = ""
    client.force_login(make_operator())
    assert menu(client, reverse("races:operator_clubs"), HTTP_HOST="localhost") == [
        "Clubs",
        "Operator log",
        "Accounts (admin)",
        "Log out",
    ]


# --- Items 7 to 10: the renamed pages ----------------------------------------------------------


def page(client, name, *args):
    return client.get(reverse(name, args=args)).content.decode()


def test_club_members_page(client):
    html = page(logged_in(client, make_administrator()), "races:members")
    assert (
        "<title>Club members - Demo Club - Race Times</title>" in html
        and "<h1>Club members</h1>" in html
    )
    # The club's download is at the very bottom, after every section.
    download = html.index("Download everything the club holds (ZIP)")
    assert (
        download > html.rindex("</section>")
        and html.count("Download everything the club holds") == 1
    )


def test_my_account_page(client):
    html = page(logged_in(client, make_member()), "races:account")
    assert (
        "<title>My account - Race Times</title>" in html
        and "<h1>My account</h1>" in html
    )
    for heading in ["My club memberships", "My data", "Delete my account"]:
        assert f"<h2>{heading}</h2>" in html
    assert (
        "Your account" not in html
        and "Your clubs" not in html
        and "Your data" not in html
    )


def test_the_delete_account_page(client):
    html = page(logged_in(client, make_member()), "races:delete_account")
    assert "<h1>Delete my account</h1>" in html and "Back to my account</a>" in html


def test_the_privacy_notice_and_terms_name_my_account(client):
    for name in ["races:privacy", "races:terms"]:
        html = page(client, name)
        assert "your My account page" in html and "Account page" not in html.replace(
            "My account page", ""
        )


def test_change_requests_page(client):
    html = page(logged_in(client, make_committee()), "races:requests")
    assert (
        "<title>Change requests - Race Times</title>" in html
        and "<h1>Change requests from members</h1>" in html
    )


def test_the_admin_sends_requests_to_the_change_requests_page(client):
    client.force_login(make_committee())
    html = client.get(
        reverse("admin:races_boatrequest_changelist"), follow=True
    ).content.decode()
    assert "on the <a" in html and "Change requests page</a>" in html


def test_my_boats_links(client):
    member = make_member()
    boat = make_boat("GBR42", name="Kittiwake", owner=member)
    html = page(logged_in(client, member), "races:my_boats")
    enter = f'<a href="{reverse("races:enter_series", args=[boat.pk])}">Register to enter a series</a>'
    change = f'<a href="{reverse("races:change_boat", args=[boat.pk])}">Request a change to this boat\'s information</a>'
    assert enter in html and change in html
    # On their own lines, entering first.
    between = html[html.index(enter) + len(enter) : html.index(change)]
    assert "</p>" in between and "&middot;" not in between
    assert ">Register a new boat</a>" in html


def test_the_register_page_matches_its_link(client):
    html = page(logged_in(client, make_member()), "races:register_boat")
    assert "<h1>Register a new boat</h1>" in html


# --- The admin's series links (question 3) -----------------------------------------------------


def test_the_admin_s_series_links(client):
    client.force_login(make_committee())
    series = make_series()
    enter(series, make_boat())
    url = reverse("admin:races_series_change", args=[series.pk])
    html = client.get(url).content.decode()
    assert ">Series history</a> &middot; <a" in html and ">Finalise results</a>" in html
    series.final_results = final.dump(engine_outcome(series))
    series.declared_final_at = timezone.now()
    series.save()
    assert ">Reopen results</a>" in client.get(url).content.decode()
