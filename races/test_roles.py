"""The four roles, and the models slice 3 adds for members."""

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.db import IntegrityError
from django.urls import reverse

from races.models import BoatRequest, EntryRequest
from races.roles import is_club_administrator, is_committee, is_member
from races.testing import (
    default_club, join,
    make_administrator, make_boat, make_club, make_committee, make_member, make_operator, make_series,
)

pytestmark = pytest.mark.django_db


# --- Who counts as what (slice 11: roles belong to a club membership) -------------


def test_roles_come_from_an_approved_membership_of_this_club():
    club = default_club()
    member, committee, admin = make_member(), make_committee(), make_administrator()
    people = (AnonymousUser(), member, committee, admin)
    assert [is_member(u, club) for u in people] == [False, True, True, True]
    assert [is_committee(u, club) for u in people] == [False, False, True, True]
    assert [is_club_administrator(u, club) for u in people] == [False, False, False, True]


def test_a_role_at_one_club_is_nothing_at_another():
    harbour = make_club("harbour")
    committee = make_committee()
    assert not is_member(committee, harbour) and not is_committee(committee, harbour)
    join(committee, harbour)
    assert is_member(committee, harbour) and not is_committee(committee, harbour)


@pytest.mark.parametrize("status", ["WAITING", "REMOVED"])
def test_a_membership_not_approved_has_no_role(status):
    person = make_committee(status=status)
    assert not is_member(person, default_club()) and not is_committee(person, default_club())


def test_staff_superusers_and_the_old_group_mean_nothing_at_a_club():
    operator = make_operator()
    staff = make_member("staff@example.com", club=None, is_staff=True)
    staff.groups.add(Group.objects.get(name="Race committee"))
    for person in (operator, staff):
        assert not is_member(person, default_club()) and not is_committee(person, default_club())


def test_an_inactive_account_has_no_role():
    assert not is_member(make_member(is_active=False), default_club())
    assert not is_committee(make_committee(is_active=False), default_club())


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
        club=default_club(),
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
        BoatRequest.objects.create(club=default_club(), kind=BoatRequest.Kind.REGISTER, boat=make_boat(), requested_by=member)


def test_several_pending_registrations_are_allowed():
    member = make_member()
    for sail in ("GBR1", "GBR2"):
        BoatRequest.objects.create(club=default_club(), kind=BoatRequest.Kind.REGISTER, sail_number=sail, requested_by=member)
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

# Slice 11: roles at Demo Club, plus the operator (a superuser, with no role at
# any club) and a race committee member of another club. Neither of the last two
# may do anything here that the public can't, except see that they're not a member.
ROLES = ["public", "member", "committee", "administrator", "operator", "committee elsewhere"]
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
            "operator": make_operator,
            "committee elsewhere": lambda: make_committee("far@example.com", club=make_club("harbour")),
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
    everyone = [SEES] * 6
    # The public is sent to log in; anyone logged in without the role is
    # refused (sending them to log in looped, since they're logged in already).
    # The admin sends everyone without access to its own login first.
    committee = [TO_LOGIN, REFUSED, SEES, SEES, REFUSED, REFUSED]
    admin_committee = [TO_LOGIN, TO_LOGIN, SEES, SEES, TO_LOGIN, TO_LOGIN]
    return {
        "home": (reverse("results:home"), everyone),
        "results": (reverse("results:series", args=[series.pk]), everyone),
        "a boat's results": (reverse("results:boat", args=[boat.pk]), everyone),
        "download (CSV)": (reverse("results:series_csv", args=[series.pk]), everyone),
        # Anyone logged in gets My boats; someone not a member here is offered Join this club.
        "my boats": (reverse("races:my_boats"), [TO_LOGIN, SEES, SEES, SEES, SEES, SEES]),
        "register a boat": (reverse("races:register_boat"), [TO_LOGIN, SEES, SEES, SEES, REFUSED, REFUSED]),
        "requests": (reverse("races:requests"), committee),
        "start sheet": ((reverse("races:race_day", args=[race.pk]) + "?view=start"), committee),
        "finish entry": ((reverse("races:race_day", args=[race.pk]) + "?view=finish"), committee),
        "history": (reverse("races:series_history", args=[series.pk]), committee),
        "final results": (reverse("races:final", args=[series.pk]), committee),
        "members": (reverse("races:members"), [TO_LOGIN, REFUSED, REFUSED, SEES, REFUSED, REFUSED]),
        "admin: boats": (reverse("admin:races_boat_changelist"), admin_committee),
        "admin: a boat": (reverse("admin:races_boat_change", args=[boat.pk]), admin_committee),
        "admin: series": (reverse("admin:races_series_changelist"), admin_committee),
        "admin: requests": (reverse("admin:races_boatrequest_changelist"), admin_committee),
        # Accounts span clubs: the operator's alone, on the service's own address.
        "admin: accounts": (reverse("admin:auth_user_changelist"), [TO_LOGIN, TO_LOGIN, REFUSED, REFUSED, TO_LOGIN, TO_LOGIN]),
        "admin: groups": (reverse("admin:auth_group_changelist"), [TO_LOGIN, TO_LOGIN, REFUSED, REFUSED, TO_LOGIN, TO_LOGIN]),
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
    page = as_role("public").get(reverse("results:home")).content.decode()
    assert "Sign up" in page and "Log in" in page and "My boats" not in page


@pytest.mark.parametrize("role, sees_requests", [("member", False), ("committee", True)])
def test_the_header_offers_requests_only_to_the_committee(as_role, role, sees_requests):
    page = as_role(role).get(reverse("results:home")).content.decode()
    assert "My boats" in page and "Log out" in page
    assert (reverse("races:requests") in page) is sees_requests


# --- Accounts belong to the operator; a club's people are on its Members page -----
# Slice 11: accounts span clubs, so the Django admin for them is the operator's,
# on the service's own address. Approving people is on the Members page
# (races/test_memberships.py).


@pytest.mark.parametrize("role", ["committee", "administrator"])
def test_nobody_at_a_club_can_change_an_account(as_role, role):
    member = make_member("pat@example.com")
    client = as_role(role)
    response = client.post(reverse("admin:auth_user_change", args=[member.pk]), {"is_staff": "on"})
    assert response.status_code == 403
    member.refresh_from_db()
    assert not member.is_staff


def test_the_committee_sets_a_boats_owner_from_this_clubs_members(as_role):
    member = make_member("pat@example.com")
    waiting = make_member("new@example.com", status="WAITING")
    elsewhere = make_member("far@example.com", club=make_club("harbour"))
    boat = make_boat()
    page = as_role("committee").get(reverse("admin:races_boat_change", args=[boat.pk])).content.decode()
    assert f'value="{member.pk}"' in page
    assert f'value="{waiting.pk}"' not in page and f'value="{elsewhere.pk}"' not in page


def test_requests_are_read_only_in_the_admin(as_role):
    request = BoatRequest.objects.create(club=default_club(), kind="REGISTER", sail_number="GBR1", requested_by=make_member("p@example.com"))
    client = as_role("administrator")
    response = client.post(reverse("admin:races_boatrequest_change", args=[request.pk]), {"status": "APPROVED"})
    assert response.status_code == 403
    request.refresh_from_db()
    assert request.status == "PENDING"


# --- The club's administrators are told about people waiting to join ------------------


def test_the_admin_front_page_counts_people_waiting_to_join(as_role):
    make_member("new1@example.com", status="WAITING")
    make_member("new2@example.com", status="WAITING")
    make_member("gone@example.com", status="REMOVED")
    page = as_role("administrator").get(reverse("admin:index")).content.decode()
    assert "2 people are waiting to join the club." in page
    assert reverse("races:members") in page


def test_one_person_waiting_reads_in_the_singular(as_role):
    make_member("new@example.com", status="WAITING")
    assert "1 person is waiting to join the club." in as_role("administrator").get(reverse("admin:index")).content.decode()


def test_no_notice_when_nobody_is_waiting(as_role):
    page = as_role("administrator").get(reverse("admin:index")).content.decode()
    assert "waiting to join" not in page


def test_the_committee_is_not_told_about_people_joining(as_role):
    make_member("new@example.com", status="WAITING")
    page = as_role("committee").get(reverse("admin:index")).content.decode()
    assert "waiting to join" not in page


# --- Members' requests waiting for the committee -------------------------------


def front_page(as_role, role):
    return as_role(role).get(reverse("admin:index")).content.decode()


@pytest.fixture
def waiting_requests():
    member = make_member("pat@example.com")
    for sail in ("GBR1", "GBR2"):
        BoatRequest.objects.create(club=default_club(), kind="REGISTER", sail_number=sail, requested_by=member)
    EntryRequest.objects.create(series=make_series(), boat=make_boat(owner=member), requested_by=member)
    # Decided requests wait for nobody.
    BoatRequest.objects.create(club=default_club(), kind="REGISTER", sail_number="GBR3", requested_by=member,
                               status="REJECTED", committee_note="No")


@pytest.mark.parametrize("role", ["committee", "administrator"])
def test_the_committee_is_told_about_waiting_requests(as_role, waiting_requests, role):
    page = front_page(as_role, role)
    assert "2 boat requests and 1 entry request are waiting for the race committee." in page
    assert reverse("races:requests") in page


def test_one_request_reads_in_the_singular(as_role):
    BoatRequest.objects.create(club=default_club(), kind="REGISTER", sail_number="GBR1", requested_by=make_member("p@example.com"))
    assert "1 boat request is waiting for the race committee." in front_page(as_role, "committee")


def test_no_request_notice_when_none_are_pending(as_role):
    assert "waiting for the race committee" not in front_page(as_role, "committee")


def test_the_administrator_sees_requests_and_people_together(as_role, waiting_requests):
    make_member("new@example.com", status="WAITING")
    page = front_page(as_role, "administrator")
    assert "waiting for the race committee" in page
    assert "1 person is waiting to join the club." in page
