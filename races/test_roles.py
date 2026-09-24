"""The four roles, and the models slice 3 adds for members."""

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.db import IntegrityError
from django.urls import reverse

from races.models import BoatRequest, EntryRequest
from races.roles import COMMITTEE_GROUP, is_committee, is_member
from races.testing import (
    make_administrator, make_boat, make_committee, make_member, make_series,
)

pytestmark = pytest.mark.django_db


# --- Who counts as what -----------------------------------------------------


def test_roles():
    member, committee, admin = make_member(), make_committee(), make_administrator()
    assert [is_member(u) for u in (AnonymousUser(), member, committee, admin)] == [
        False, True, True, True,
    ]
    assert [is_committee(u) for u in (AnonymousUser(), member, committee, admin)] == [
        False, False, True, True,
    ]


def test_staff_alone_is_not_the_committee():
    """Staff access only counts with the group, or as the administrator."""
    assert not is_committee(make_member(is_staff=True))


def test_an_inactive_account_has_no_role():
    assert not is_member(make_member(is_active=False))
    assert not is_committee(make_committee(is_active=False))


def test_the_committee_group_grants_racing_and_nothing_about_people():
    codenames = set(
        Group.objects.get(name=COMMITTEE_GROUP).permissions.values_list("codename", flat=True)
    )
    for model in ["boat", "series", "seriesentry", "race", "finish"]:
        assert {f"{a}_{model}" for a in ("add", "change", "delete", "view")} <= codenames
    # Requests are decided on the Requests page; history is never edited.
    for model in ["boatrequest", "entryrequest", "scoringchange"]:
        assert f"view_{model}" in codenames
        assert f"change_{model}" not in codenames
    assert not any(c.endswith(("_user", "_group", "_permission")) for c in codenames)


# --- Boats and requests -----------------------------------------------------


def test_owner_shown_is_the_member_if_linked_else_the_typed_name():
    boat = make_boat(owner_name="A. Visitor")
    assert boat.owner_display == "A. Visitor"
    boat.owner = make_member(first_name="Pat", last_name="Jones")
    assert boat.owner_display == "Pat Jones"


def test_deleting_the_owner_keeps_the_boat():
    member = make_member()
    boat = make_boat(owner=member)
    member.delete()
    boat.refresh_from_db()
    assert boat.owner is None


def request_for(boat, member, **fields):
    return BoatRequest.objects.create(
        kind=BoatRequest.Kind.CHANGE, boat=boat, requested_by=member, **fields
    )


def test_one_pending_request_per_boat():
    member, boat = make_member(), make_boat()
    request_for(boat, member)
    with pytest.raises(IntegrityError):
        request_for(boat, member)


def test_a_decided_request_does_not_block_a_new_one():
    member, boat = make_member(), make_boat()
    request_for(boat, member, status=BoatRequest.Status.REJECTED)
    request_for(boat, member)
    assert BoatRequest.objects.count() == 2


def test_a_registration_has_no_boat_and_the_others_do():
    member = make_member()
    with pytest.raises(IntegrityError):
        BoatRequest.objects.create(kind=BoatRequest.Kind.REGISTER, boat=make_boat(), requested_by=member)


def test_several_pending_registrations_are_allowed():
    member = make_member()
    for sail in ("GBR1", "GBR2"):
        BoatRequest.objects.create(kind=BoatRequest.Kind.REGISTER, sail_number=sail, requested_by=member)
    assert BoatRequest.objects.count() == 2


def test_one_pending_entry_request_per_boat_per_series():
    member, boat, series = make_member(), make_boat(), make_series()
    EntryRequest.objects.create(series=series, boat=boat, requested_by=member)
    EntryRequest.objects.create(series=make_series("Other"), boat=boat, requested_by=member)
    with pytest.raises(IntegrityError):
        EntryRequest.objects.create(series=series, boat=boat, requested_by=member)


def test_a_members_requests_go_with_their_account():
    member, boat = make_member(), make_boat()
    request_for(boat, member)
    EntryRequest.objects.create(series=make_series(), boat=boat, requested_by=member)
    member.delete()
    assert not BoatRequest.objects.exists() and not EntryRequest.objects.exists()


# --- Every page, as each of the four roles -----------------------------------

ROLES = ["public", "member", "committee", "administrator"]
SEES = 200
TO_LOGIN = "login"
REFUSED = 403


@pytest.fixture
def as_role(client):
    def log_in(role):
        user = {
            "public": lambda: None,
            "member": make_member,
            "committee": make_committee,
            "administrator": make_administrator,
        }[role]()
        if user is not None:
            client.force_login(user)
        return client
    return log_in


@pytest.fixture
def pages():
    from races.testing import enter, make_race
    series = make_series()
    race = make_race(series)
    boat = make_boat()
    enter(series, boat)
    return {
        "home": (reverse("races:home"), [SEES] * 4),
        "results": (reverse("races:series_results", args=[series.pk]), [SEES] * 4),
        "my boats": (reverse("races:my_boats"), [TO_LOGIN, SEES, SEES, SEES]),
        "register a boat": (reverse("races:register_boat"), [TO_LOGIN, SEES, SEES, SEES]),
        "requests": (reverse("races:requests"), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "finish entry": (reverse("races:finish_entry", args=[race.pk]), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "history": (reverse("races:series_history", args=[series.pk]), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "admin: boats": (reverse("admin:races_boat_changelist"), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "admin: a boat": (reverse("admin:races_boat_change", args=[boat.pk]), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "admin: series": (reverse("admin:races_series_changelist"), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "admin: requests": (reverse("admin:races_boatrequest_changelist"), [TO_LOGIN, TO_LOGIN, SEES, SEES]),
        "admin: accounts": (reverse("admin:auth_user_changelist"), [TO_LOGIN, TO_LOGIN, REFUSED, SEES]),
        "admin: groups": (reverse("admin:auth_group_changelist"), [TO_LOGIN, TO_LOGIN, REFUSED, SEES]),
    }


@pytest.mark.parametrize("role", ROLES)
def test_every_page_as_each_role(as_role, pages, role):
    client = as_role(role)
    outcomes = {}
    for name, (url, expected) in pages.items():
        response = client.get(url)
        if response.status_code == 302 and "login" in response["Location"]:
            outcomes[name] = TO_LOGIN
        else:
            outcomes[name] = response.status_code
    assert outcomes == {name: expected[ROLES.index(role)] for name, (_, expected) in pages.items()}


def test_the_header_offers_log_in_and_sign_up_to_the_public(as_role):
    page = as_role("public").get(reverse("races:home")).content.decode()
    assert "Sign up" in page and "Log in" in page and "My boats" not in page


@pytest.mark.parametrize("role, sees_requests", [("member", False), ("committee", True)])
def test_the_header_offers_requests_only_to_the_committee(as_role, role, sees_requests):
    page = as_role(role).get(reverse("races:home")).content.decode()
    assert "My boats" in page and "Log out" in page
    assert (reverse("races:requests") in page) is sees_requests


# --- The administrator manages accounts; the committee cannot ----------------


def test_the_administrator_approves_waiting_accounts(as_role):
    waiting = [make_member(f"new{n}@example.com", is_active=False) for n in range(2)]
    client = as_role("administrator")
    client.post(reverse("admin:auth_user_changelist"), {
        "action": "approve_accounts", "_selected_action": [u.pk for u in waiting],
    })
    for user in waiting:
        user.refresh_from_db()
        assert user.is_active


def test_the_committee_cannot_change_an_account(as_role):
    member = make_member("pat@example.com")
    client = as_role("committee")
    response = client.post(reverse("admin:auth_user_change", args=[member.pk]), {"is_staff": "on"})
    assert response.status_code == 403
    member.refresh_from_db()
    assert not member.is_staff


def test_the_committee_sets_a_boats_owner_from_active_accounts(as_role):
    active, waiting = make_member("pat@example.com"), make_member("new@example.com", is_active=False)
    boat = make_boat()
    page = as_role("committee").get(reverse("admin:races_boat_change", args=[boat.pk])).content.decode()
    assert f'value="{active.pk}"' in page
    assert f'value="{waiting.pk}"' not in page


def test_requests_are_read_only_in_the_admin(as_role):
    request = BoatRequest.objects.create(kind="REGISTER", sail_number="GBR1", requested_by=make_member("p@example.com"))
    client = as_role("administrator")
    response = client.post(reverse("admin:races_boatrequest_change", args=[request.pk]), {"status": "APPROVED"})
    assert response.status_code == 403
    request.refresh_from_db()
    assert request.status == "PENDING"


# --- The administrator is told about new sign-ups ------------------------------


def test_the_admin_front_page_counts_accounts_waiting_for_approval(as_role):
    make_member("new1@example.com", is_active=False)
    make_member("new2@example.com", is_active=False)
    page = as_role("administrator").get(reverse("admin:index")).content.decode()
    assert "2 new accounts are waiting for approval" in page
    assert f'{reverse("admin:auth_user_changelist")}?approval=waiting' in page


def test_no_notice_when_nobody_is_waiting(as_role):
    page = as_role("administrator").get(reverse("admin:index")).content.decode()
    assert "waiting for approval" not in page


def test_an_account_switched_off_later_is_not_a_new_sign_up(as_role):
    from django.utils import timezone
    make_member("left@example.com", is_active=False, last_login=timezone.now())
    make_member("new@example.com", is_active=False)
    page = as_role("administrator").get(reverse("admin:index")).content.decode()
    assert "1 new account is waiting for approval" in page


def test_the_committee_is_not_told_about_sign_ups(as_role):
    make_member("new@example.com", is_active=False)
    page = as_role("committee").get(reverse("admin:index")).content.decode()
    assert "waiting for approval" not in page


def test_the_waiting_filter_lists_only_new_sign_ups(as_role):
    from django.utils import timezone
    make_member("left@example.com", is_active=False, last_login=timezone.now())
    make_member("new@example.com", is_active=False)
    make_member("active@example.com")
    page = as_role("administrator").get(
        reverse("admin:auth_user_changelist") + "?approval=waiting"
    ).content.decode()
    assert "new@example.com" in page
    assert "left@example.com" not in page and "active@example.com" not in page
