"""Slice 11 part 2: people and roles per club.

Sign-up and confirming an email are tested in races/test_members.py, and
every page as each role in races/test_roles.py. This file covers:
- the migration from site-wide roles;
- joining a club;
- the Members page and its emails;
- who gets club emails;
- the admin's door at a club.
"""

from datetime import timedelta
from html import escape

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone

from races import notifications
from races.membership_views import LAST_ADMINISTRATOR, OWN_MEMBERSHIP
from races.models import ClubMembership
from races.testing import (
    default_club, enter, join, make_administrator, make_boat, make_club, make_committee, make_member,
    make_operator, make_race, make_series, record,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def run_on_commit(monkeypatch):
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())


def membership_of(user, club=None):
    return ClubMembership.objects.get(user=user, club=club or default_club())


# --- Everyone keeps the access they had ------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_the_migration_turns_site_wide_roles_into_demo_club_memberships():
    executor = MigrationExecutor(connection)
    executor.migrate([("races", "0013_club_required")])
    old = executor.loader.project_state([("races", "0013_club_required")]).apps
    User = old.get_model(*settings.AUTH_USER_MODEL.split("."))
    OldGroup = old.get_model("auth", "Group")
    # Demo Club, as migration 0012 made it (a flush may have removed it).
    old.get_model("races", "Club").objects.get_or_create(subdomain="demo", defaults={"name": "Demo Club"})
    make = lambda name, **fields: User.objects.create(username=name, email=name, **fields)  # noqa: E731
    make("root@example.com", is_superuser=True, is_staff=True, is_active=True)
    officer = make("officer@example.com", is_staff=True, is_active=True)
    # get_or_create: a transactional test before this one may have flushed the
    # group that migration 0005 made.
    officer.groups.add(OldGroup.objects.get_or_create(name="Race committee")[0])
    make("staff-only@example.com", is_staff=True, is_active=True)
    make("pat@example.com", is_active=True)
    make("new@example.com", is_active=False)
    make("left@example.com", is_active=False, last_login=timezone.now())

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    got = {m.user.username: (m.role, m.status) for m in ClubMembership.objects.select_related("user")}
    assert got == {
        "root@example.com": ("ADMINISTRATOR", "APPROVED"),
        "officer@example.com": ("COMMITTEE", "APPROVED"),
        "staff-only@example.com": ("MEMBER", "APPROVED"),
        "pat@example.com": ("MEMBER", "APPROVED"),
        "new@example.com": ("MEMBER", "WAITING"),
        "left@example.com": ("MEMBER", "REMOVED"),
    }
    accounts = get_user_model().objects
    assert accounts.get(username="new@example.com").is_active  # can log in now, and wait to join
    assert not accounts.get(username="left@example.com").is_active
    assert accounts.get(username="root@example.com").is_superuser  # still the operator
    assert set(ClubMembership.objects.values_list("club__subdomain", flat=True)) == {"demo"}


# --- Joining a club -----------------------------------------------------------------------


def test_someone_logged_in_but_not_a_member_is_offered_to_join(client):
    client.force_login(make_member("far@example.com", club=make_club("harbour")))
    page = client.get(reverse("races:my_boats")).content.decode()
    assert "not a member of Demo Club yet" in page and "Join this club</button>" in page
    assert ">Join this club</a>" in client.get(reverse("results:home")).content.decode()


def test_joining_asks_the_clubs_administrators(client):
    person = make_member("far@example.com", club=make_club("harbour"))
    client.force_login(person)
    response = client.post(reverse("races:join_club"), follow=True)
    assert "Asked to join Demo Club" in response.content.decode()
    assert (membership_of(person).status, membership_of(person).role) == ("WAITING", "MEMBER")
    page = client.get(reverse("races:my_boats")).content.decode()
    assert "You've asked to join <strong>Demo Club</strong>" in page
    assert ">Waiting to join</a>" in client.get(reverse("results:home")).content.decode()


def test_someone_removed_can_ask_again(client):
    person = make_member("pat@example.com", status="REMOVED", role="COMMITTEE")
    client.force_login(person)
    assert "no longer a member of Demo Club" in client.get(reverse("races:my_boats")).content.decode()
    client.post(reverse("races:join_club"))
    assert (membership_of(person).status, membership_of(person).role) == ("WAITING", "MEMBER")


def test_joining_twice_changes_nothing(client):
    person = make_member("pat@example.com")
    client.force_login(person)
    client.post(reverse("races:join_club"))
    assert membership_of(person).status == "APPROVED"
    assert ClubMembership.objects.filter(user=person).count() == 1


def test_joining_needs_a_login(client):
    response = client.post(reverse("races:join_club"))
    assert response.status_code == 302 and "login" in response["Location"]


# --- The Members page --------------------------------------------------------------------


@pytest.fixture
def admin(client):
    user = make_administrator()
    client.force_login(user)
    return user


def decide(client, person, action, role=""):
    return client.post(reverse("races:decide_membership", args=[membership_of(person).pk]),
                       {"action": action, "role": role}, follow=True)


def test_the_members_page_lists_people_by_status(client, admin):
    make_member("waiting@example.com", first_name="Wendy", status="WAITING")
    make_member("pat@example.com", first_name="Pat")
    make_member("gone@example.com", first_name="Gary", status="REMOVED")
    make_member("far@example.com", first_name="Fiona", club=make_club("harbour"))
    page = client.get(reverse("races:members")).content.decode()
    waiting, rest = page.split('id="approved"')
    assert "Wendy" in waiting and "Pat" not in waiting
    assert "Pat" in rest and "Gary" in rest.split("No longer members")[1]
    assert "Fiona" not in page  # another club's


@pytest.mark.parametrize("role", ["MEMBER", "COMMITTEE", "ADMINISTRATOR"])
def test_approving_someone_with_a_role_emails_them(client, admin, role, run_on_commit):
    person = make_member("new@example.com", first_name="Nia", status="WAITING")
    page = decide(client, person, "approve", role).content.decode()
    assert "Nia Jones: approved and emailed." in page
    found = membership_of(person)
    assert (found.status, found.role, found.decided_by_name) == ("APPROVED", role, admin.username)
    [message] = mail.outbox
    assert message.to == ["new@example.com"] and message.subject == "Welcome to Demo Club on Race Times"


def test_not_approving_someone_emails_them(client, admin, run_on_commit):
    person = make_member("new@example.com", status="WAITING")
    decide(client, person, "reject")
    assert membership_of(person).status == "REMOVED"
    assert mail.outbox[0].subject == "Your request to join Demo Club"


def test_changing_a_role_emails_the_person(client, admin, run_on_commit):
    person = make_member("pat@example.com")
    decide(client, person, "role", "COMMITTEE")
    assert membership_of(person).role == "COMMITTEE"
    assert mail.outbox[0].subject == "Your role at Demo Club has changed"
    assert "You are now: Race committee" in mail.outbox[0].body


def test_removing_someone_takes_their_access_and_emails_them(client, admin, run_on_commit):
    person = make_committee()
    decide(client, person, "remove")
    assert membership_of(person).status == "REMOVED"
    assert mail.outbox[0].subject == "You are no longer a member of Demo Club on Race Times"
    client.force_login(person)
    assert client.get(reverse("races:requests")).status_code == 403


def test_nobody_can_change_their_own_membership(client, admin, run_on_commit):
    page = decide(client, admin, "role", "MEMBER").content.decode()
    assert escape(OWN_MEMBERSHIP) in page
    assert membership_of(admin).role == "ADMINISTRATOR" and not mail.outbox
    page = client.get(reverse("races:members")).content.decode()
    assert f'action="{reverse("races:decide_membership", args=[membership_of(admin).pk])}"' not in page


def test_the_club_keeps_at_least_one_administrator(client, run_on_commit):
    # Two administrators; one removes the other, then can't be left without one.
    first, second = make_administrator("a1@example.com"), make_administrator("a2@example.com")
    client.force_login(first)
    decide(client, second, "remove")
    assert membership_of(second).status == "REMOVED"
    # The rule is checked on its own too, in case a club ever has no administrator left to act.
    from races.membership_views import _decide
    from django.test import RequestFactory
    request = RequestFactory().post("/")
    request.user, request.club = second, default_club()
    with pytest.raises(Exception, match="at least one administrator"):
        _decide(request, membership_of(first), "role", "MEMBER")
    assert membership_of(first).role == "ADMINISTRATOR"


def test_a_stale_decision_changes_nothing(client, admin, run_on_commit):
    person = make_member("pat@example.com")
    decide(client, person, "approve")  # already approved
    decide(client, person, "role", "MEMBER")  # already a member
    assert not mail.outbox and membership_of(person).decided_by_name == ""


def test_only_administrators_open_the_members_page(client):
    client.force_login(make_committee())
    assert client.get(reverse("races:members")).status_code == 403


# --- Club emails go to approved members only ------------------------------------------


@pytest.mark.parametrize("status", ["WAITING", "REMOVED"])
def test_only_approved_members_get_a_clubs_results(client, status, run_on_commit):
    owner = make_member("pat@example.com", status=status)
    series = make_series()
    entry = enter(series, make_boat(owner=owner))
    race = make_race(series)
    record(race, entry, "19:00:00")
    assert not notifications.has_owner_to_email(entry.boat)
    assert list(notifications.series_owners(series)) == []


# --- The admin at a club ----------------------------------------------------------------


def test_the_operator_has_no_admin_at_a_club_without_a_membership(client):
    client.force_login(make_operator())
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302 and "/admin/login/" in response["Location"]
    assert client.get(response["Location"]).status_code == 403


def test_the_admin_login_at_a_club_is_the_sites_login(client):
    response = client.get(reverse("admin:login") + "?next=/admin/")
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("races:login")) and "next=/admin/" in response["Location"]


def test_the_club_administrator_manages_people_on_the_members_page_not_the_admin(client, admin):
    page = client.get(reverse("admin:index")).content.decode()
    assert "Users" not in page and "Groups" not in page and "Clubs" not in page


def test_the_old_group_and_staff_flag_open_nothing(client):
    person = make_member("staff@example.com", club=None, is_staff=True)
    person.groups.add(Group.objects.get(name="Race committee"))
    client.force_login(person)
    assert client.get(reverse("races:requests")).status_code == 403
    assert client.get(reverse("admin:index")).status_code == 302  # to the admin login, which refuses


def test_each_clubs_login_is_its_own():
    # No cookie domain: the browser keeps a separate login for each club's address.
    assert settings.SESSION_COOKIE_DOMAIN is None


def test_the_operator_gives_memberships_in_the_admin_on_the_services_address(client, settings):
    settings.SINGLE_CLUB = ""
    client.force_login(make_operator())
    person = make_member("first@example.com", club=None)
    response = client.post(reverse("admin:races_clubmembership_add"), {
        "user": person.pk, "club": default_club().pk, "role": "ADMINISTRATOR", "status": "APPROVED",
        "created_at_0": "2026-09-25", "created_at_1": "10:00:00", "decided_by_name": "", "decided_at_0": "",
        "decided_at_1": "",
    }, HTTP_HOST="localhost")
    assert response.status_code == 302
    assert membership_of(person).role == "ADMINISTRATOR"


def test_a_club_administrator_cant_give_memberships_in_the_admin(client, admin):
    assert client.get(reverse("admin:races_clubmembership_changelist")).status_code == 403
