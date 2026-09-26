"""Slice 11 part 3: the operator's pages, invitations, and the service's front page.

The operator's pages are on the service's own address, which in tests is
``localhost`` with SINGLE_CLUB unset. A club's address is ``<subdomain>.localhost``.
Who may open which page is in races/test_roles.py.
"""

import re
import time
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.urls import reverse
from django.utils import timezone

from races import notifications
from races.invitations import invitation_from, token_for
from races.models import Club, ClubInvitation, ClubMembership, OperatorAction
from races.testing import (
    default_club, enter, make_administrator, make_boat, make_club, make_member, make_operator, make_race,
    make_series, record,
)

pytestmark = pytest.mark.django_db

SERVICE = {"HTTP_HOST": "localhost"}


def at(subdomain):
    return {"HTTP_HOST": f"{subdomain}.localhost"}


@pytest.fixture(autouse=True)
def service_address(settings):
    settings.SINGLE_CLUB = ""


@pytest.fixture
def run_on_commit(monkeypatch):
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())


@pytest.fixture
def operator(client):
    person = make_operator()
    client.force_login(person)
    return person


# --- The service's front page -------------------------------------------------------------


def test_the_front_page_says_what_race_times_is_and_how_to_get_it(client, settings):
    settings.SERVICE_CONTACT_EMAIL = "clubs@racetimes.example"
    make_club("harbour", "Harbour Sailing Club")
    page = client.get("/", **SERVICE).content.decode()
    assert "Race Times" in page and "handicaps" in page
    assert 'href="mailto:clubs@racetimes.example"' in page
    # It doesn't list clubs: a club tells its own members its address.
    assert "Demo Club" not in page and "Harbour Sailing Club" not in page


def test_the_header_offers_the_operator_their_pages(client, operator):
    page = client.get("/", **SERVICE).content.decode()
    assert reverse("races:operator_clubs") in page and reverse("admin:logout") in page


# --- The list of clubs -------------------------------------------------------------------------


def test_the_clubs_page_counts_members_and_series_and_shows_the_last_result(client, operator):
    harbour = make_club("harbour", "Harbour Sailing Club")
    make_member("pat@example.com")
    make_member("wendy@example.com", status="WAITING")  # not a member yet
    series = make_series()
    make_series("Spring")
    entry = enter(series, make_boat())
    finish = record(make_race(series), entry, "19:00:00")
    finish.recorded_at = timezone.make_aware(timezone.datetime(2026, 9, 20, 19, 0))
    finish.save()
    page = client.get(reverse("races:operator_clubs"), **SERVICE).content.decode()
    rows = {name: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row)) for name, row in (
        ("demo", page.split("Demo Club</a>")[1].split("</tr>")[0]),
        ("harbour", page.split("Harbour Sailing Club</a>")[1].split("</tr>")[0]),
    )}
    assert rows["demo"].split() == ["demo", "Active", "1", "2", "20", "Sep", "2026"]
    assert rows["harbour"].split() == ["harbour", "Active", "0", "0", "None", "yet"]
    assert reverse("races:operator_club", args=[harbour.pk]) in page


# --- Creating a club -----------------------------------------------------------------------------


def create(client, **fields):
    data = {"name": "Exe Sailing Club", "subdomain": "exesc", "contact_email": "sec@exesc.example", **fields}
    return client.post(reverse("races:operator_create_club"), data, **SERVICE)


def test_the_operator_creates_a_club_and_it_is_logged(client, operator):
    response = create(client, subdomain="ExeSC")
    club = Club.objects.get(subdomain="exesc")  # stored lower-case
    assert response["Location"] == reverse("races:operator_club", args=[club.pk])
    assert (club.name, club.contact_email, club.status) == ("Exe Sailing Club", "sec@exesc.example", "ACTIVE")
    [action] = OperatorAction.objects.all()
    assert (action.who, action.action, action.club_subdomain) == ("operator@example.com", "CREATED", "exesc")
    # The new club's site works at once, empty.
    assert "Exe Sailing Club" in client.get("/", **at("exesc")).content.decode()


@pytest.mark.parametrize("subdomain", ["exe sc", "exe_sc", "exe.sc", "-exesc", "exesc-", "exé", ""])
def test_a_subdomain_is_letters_digits_and_hyphens(client, operator, subdomain):
    response = create(client, subdomain=subdomain)
    assert response.status_code == 200 and not Club.objects.filter(name="Exe Sailing Club").exists()


@pytest.mark.parametrize("subdomain", ["www", "admin", "operator", "mail", "api", "static", "app", "WWW"])
def test_reserved_subdomains_are_refused(client, operator, subdomain):
    response = create(client, subdomain=subdomain)
    assert "is reserved for the service" in response.content.decode()
    assert not Club.objects.filter(name="Exe Sailing Club").exists()


def test_a_subdomain_in_use_is_refused(client, operator):
    response = create(client, subdomain="Demo")
    assert "already exists" in response.content.decode()
    assert Club.objects.count() == 1 and not OperatorAction.objects.exists()


def test_a_club_needs_a_contact_email(client, operator):
    assert create(client, contact_email="").status_code == 200
    assert not Club.objects.filter(subdomain="exesc").exists()


# --- Suspending and reactivating -----------------------------------------------------------------


def set_status(client, club, status):
    return client.post(reverse("races:operator_club_status", args=[club.pk]), {"status": status}, **SERVICE)


def test_suspending_a_club_pauses_its_site_and_reactivating_brings_it_back(client, operator):
    harbour = make_club("harbour", "Harbour Sailing Club")
    set_status(client, harbour, "SUSPENDED")
    harbour.refresh_from_db()
    assert harbour.status == "SUSPENDED"
    client.logout()
    assert client.get("/", **at("harbour")).status_code == 503
    client.force_login(operator)
    set_status(client, harbour, "ACTIVE")
    client.logout()
    assert client.get("/", **at("harbour")).status_code == 200
    assert list(OperatorAction.objects.values_list("action", flat=True)) == ["REACTIVATED", "SUSPENDED"]


def test_setting_the_status_a_club_already_has_logs_nothing(client, operator):
    set_status(client, default_club(), "ACTIVE")
    set_status(client, default_club(), "NONSENSE")
    assert not OperatorAction.objects.exists() and default_club().status == "ACTIVE"


def test_the_operator_changes_no_club_data(client, operator):
    # The operator's pages touch only clubs, invitations and the log; at a club,
    # the operator is nobody without a membership (races/test_roles.py).
    series = make_series()
    assert client.get(reverse("races:final", args=[series.pk]), **at("demo")).status_code == 403


# --- Inviting a club's administrator ---------------------------------------------------------------


def invite(client, club, email="Ann@Example.com"):
    return client.post(reverse("races:operator_invite", args=[club.pk]), {"email": email}, **SERVICE)


def link_in(message):
    return re.search(r"https?://\S+", message.body).group(0)


def test_inviting_emails_a_link_to_the_clubs_address_and_is_logged(client, operator, run_on_commit):
    harbour = make_club("harbour", "Harbour Sailing Club")
    response = invite(client, harbour)
    assert response["Location"] == reverse("races:operator_club", args=[harbour.pk])
    invitation = ClubInvitation.objects.get()
    assert (invitation.club, invitation.email, invitation.role, invitation.invited_by_name) == (
        harbour, "ann@example.com", "ADMINISTRATOR", "operator@example.com")
    [message] = mail.outbox
    assert message.to == ["ann@example.com"]
    assert message.subject == "You're invited to run Harbour Sailing Club on Race Times"
    assert "within 7 days" in message.body
    # The link's token is signed with the time, to the second, so it's checked by
    # reading it back rather than by making another and comparing.
    prefix = "http://harbour.localhost" + reverse("races:accept_invitation", args=["TOKEN"]).split("TOKEN")[0]
    link = link_in(message)
    assert link.startswith(prefix) and invitation_from(link[len(prefix):].rstrip("/"), harbour) == invitation
    [action] = OperatorAction.objects.all()
    assert (action.action, action.club_subdomain, action.detail) == (
        "INVITED", "harbour", "ann@example.com as club administrator")
    page = client.get(reverse("races:operator_club", args=[harbour.pk]), **SERVICE).content.decode()
    assert "ann@example.com" in page and "Not yet" in page


def test_the_link_keeps_the_port(client, operator, run_on_commit):
    invite(client, default_club())
    client.post(reverse("races:operator_invite", args=[default_club().pk]), {"email": "b@example.com"},
                HTTP_HOST="localhost:8000")
    assert link_in(mail.outbox[1]).startswith("http://demo.localhost:8000/invitation/")


def test_a_bad_email_is_refused(client, operator, run_on_commit):
    response = invite(client, default_club(), email="not an email")
    assert response.status_code == 400 and not ClubInvitation.objects.exists() and not mail.outbox


def test_nobody_is_invited_to_a_suspended_club(client, operator, run_on_commit):
    harbour = make_club("harbour", status="SUSPENDED")
    invite(client, harbour)
    assert not ClubInvitation.objects.exists() and not mail.outbox and not OperatorAction.objects.exists()


# --- Accepting an invitation ---------------------------------------------------------------


@pytest.fixture
def harbour():
    return make_club("harbour", "Harbour Sailing Club")


def invitation_to(club, email="ann@example.com", role="ADMINISTRATOR"):
    invitation = ClubInvitation.objects.create(club=club, email=email, role=role, invited_by_name="operator@example.com")
    return invitation, reverse("races:accept_invitation", args=[token_for(invitation)])


NEW_ACCOUNT = {"first_name": "Ann", "last_name": "Lee", "password1": "a-long-Passphrase-9", "password2": "a-long-Passphrase-9"}


def test_someone_new_makes_an_account_and_becomes_the_clubs_administrator(client, harbour):
    invitation, url = invitation_to(harbour)
    page = client.get(url, **at("harbour")).content.decode()
    assert "Join Harbour Sailing Club as its club administrator" in page and "ann@example.com" in page
    response = client.post(url, NEW_ACCOUNT, **at("harbour"))
    assert response["Location"] == reverse("races:members")
    ann = get_user_model().objects.get(username="ann@example.com")
    assert ann.is_active and ann.email == "ann@example.com" and ann.get_full_name() == "Ann Lee"
    membership = ann.memberships.get()
    assert (membership.club, membership.role, membership.status, membership.decided_by_name) == (
        harbour, "ADMINISTRATOR", "APPROVED", "operator@example.com")
    invitation.refresh_from_db()
    assert invitation.accepted_at is not None
    # Logged in, and running the club.
    assert client.get(reverse("races:members"), **at("harbour")).status_code == 200


def test_a_new_accounts_password_is_checked(client, harbour):
    _, url = invitation_to(harbour)
    response = client.post(url, {**NEW_ACCOUNT, "password1": "ann", "password2": "ann"}, **at("harbour"))
    assert response.status_code == 200 and not get_user_model().objects.exists()


def test_the_link_works_once(client, harbour):
    _, url = invitation_to(harbour)
    client.post(url, NEW_ACCOUNT, **at("harbour"))
    client.logout()
    response = client.get(url, **at("harbour"))
    assert response.status_code == 400 and "doesn't work" in response.content.decode()


def test_the_link_lasts_seven_days(client, harbour, monkeypatch):
    invitation = ClubInvitation.objects.create(club=harbour, email="ann@example.com")
    real = time.time
    with monkeypatch.context() as m:
        m.setattr(signing.time, "time", lambda: real() - timedelta(days=7, minutes=1).total_seconds())
        old = reverse("races:accept_invitation", args=[token_for(invitation)])
        m.setattr(signing.time, "time", lambda: real() - timedelta(days=6, hours=23).total_seconds())
        recent = reverse("races:accept_invitation", args=[token_for(invitation)])
    assert client.get(old, **at("harbour")).status_code == 400
    assert client.get(recent, **at("harbour")).status_code == 200


def test_a_tampered_link_doesnt_work(client, harbour):
    _, url = invitation_to(harbour)
    assert client.get(url[:-3] + "xyz/", **at("harbour")).status_code == 400
    forged = reverse("races:accept_invitation", args=[signing.dumps(1, salt="something else")])
    assert client.get(forged, **at("harbour")).status_code == 400


def test_the_link_works_only_at_its_own_club(client, harbour):
    _, url = invitation_to(harbour)
    assert client.get(url, **at("demo")).status_code == 400


def test_someone_with_an_account_logs_in_first(client, harbour):
    make_member("ann@example.com", first_name="Ann")  # a member of Demo Club
    _, url = invitation_to(harbour)
    page = client.get(url, **at("harbour")).content.decode()
    assert "You already have a Race Times account" in page
    assert f"{reverse('races:login')}?next=" in page
    client.post(url, NEW_ACCOUNT, **at("harbour"))  # no account is made
    assert get_user_model().objects.count() == 1 and not ClubInvitation.objects.get().accepted_at


def test_an_older_account_is_found_by_its_email(client, harbour):
    get_user_model().objects.create_user(username="jsmith", email="ann@example.com")
    _, url = invitation_to(harbour)
    assert "You already have a Race Times account" in client.get(url, **at("harbour")).content.decode()


def test_someone_with_an_account_accepts_once_logged_in(client, harbour):
    ann = make_member("ann@example.com")
    ClubMembership.objects.create(user=ann, club=harbour)  # already asked to join: waiting
    _, url = invitation_to(harbour)
    client.force_login(ann)
    assert "Accept" in client.get(url, **at("harbour")).content.decode()
    assert client.post(url, **at("harbour"))["Location"] == reverse("races:members")
    membership = ann.memberships.get(club=harbour)
    assert (membership.role, membership.status) == ("ADMINISTRATOR", "APPROVED")
    # Nothing changes at the club they already belonged to.
    assert ann.memberships.get(club=default_club()).role == "MEMBER"


def test_someone_else_logged_in_cant_accept(client, harbour):
    _, url = invitation_to(harbour)
    other = make_member("bob@example.com", club=harbour)
    client.force_login(other)
    page = client.get(url, **at("harbour")).content.decode()
    assert "You're logged in as bob@example.com" in page
    client.post(url, NEW_ACCOUNT, **at("harbour"))
    assert other.memberships.get().role == "MEMBER"
    assert not get_user_model().objects.filter(username="ann@example.com").exists()


def test_invitations_arent_listed_for_the_club(client, harbour):
    # A club's administrators see people on the Members page; invitations are the operator's.
    invitation_to(harbour)
    client.force_login(make_administrator(club=harbour))
    assert "ann@example.com" not in client.get(reverse("races:members"), **at("harbour")).content.decode()


# --- The operator log ------------------------------------------------------------------------


def test_the_log_survives_the_club_and_the_account(client, operator):
    create(client, subdomain="exesc")
    OperatorAction.objects.create(who="old@example.com", action="SUSPENDED", club_subdomain="gone")
    page = client.get(reverse("races:operator_log"), **SERVICE).content.decode()
    assert "Created a club" in page and "exesc" in page
    assert "old@example.com" in page and "gone" in page
    assert "Suspended a club" in client.get(reverse("races:operator_clubs"), **SERVICE).content.decode()


# --- People waiting to join (slice 13) ----------------------------------------------------------


def waiting_at(club, email="kim@example.com", first_name="Kim"):
    person = make_member(email, first_name=first_name, last_name="Park", club=club, status="WAITING")
    return person.memberships.get(club=club)


def decide_joining(client, membership, action, role="MEMBER", host=SERVICE):
    url = reverse("races:operator_decide_joining", args=[membership.club.pk, membership.pk])
    return client.post(url, {"action": action, "role": role}, **host)


def test_the_club_page_lists_only_that_clubs_people_waiting(client, operator):
    demo, harbour = default_club(), make_club("harbour", "Harbour Sailing Club")
    waiting_at(demo)
    waiting_at(harbour, "bea@example.com", "Bea")
    make_member("sam@example.com", first_name="Sam", club=demo)  # already a member
    page = client.get(reverse("races:operator_club", args=[demo.pk]), **SERVICE).content.decode()
    waiting = page.split('id="waiting"')[1].split('id="administrators"')[0]
    assert "Waiting to join (1)" in page and "Kim Park" in waiting and "kim@example.com" in waiting
    assert "Bea" not in waiting and "Sam" not in waiting


@pytest.mark.parametrize("role", ["MEMBER", "COMMITTEE", "ADMINISTRATOR"])
def test_approving_someone_waiting_as_any_role(client, operator, run_on_commit, role):
    membership = waiting_at(default_club())
    response = decide_joining(client, membership, "approve", role)
    assert response["Location"].endswith(reverse("races:operator_club", args=[default_club().pk]) + "#waiting")
    membership.refresh_from_db()
    assert (membership.status, membership.role) == ("APPROVED", role)
    assert membership.decided_by_name == "the Race Times operator" and membership.decided_at is not None
    [action] = OperatorAction.objects.all()
    assert (action.action, action.club_subdomain, action.who) == ("APPROVED_JOIN", "demo", "operator@example.com")
    assert action.detail.startswith("kim@example.com as ")


def test_the_person_is_emailed_from_the_club_with_links_to_the_club(client, operator, run_on_commit):
    decide_joining(client, waiting_at(default_club()), "approve")
    [message] = mail.outbox
    assert message.to == ["kim@example.com"] and message.subject == "Welcome to Demo Club on Race Times"
    assert "Demo Club via Race Times" in message.from_email
    assert "http://demo.localhost/my/boats/" in message.body
    assert "http://localhost/my" not in message.body  # not the service's own address


def test_turning_someone_down(client, operator, run_on_commit):
    membership = waiting_at(default_club())
    page = client.get(reverse("races:operator_club", args=[default_club().pk]), **SERVICE)
    assert "Don&#x27;t approve" in page.content.decode() or "Don't approve" in page.content.decode()
    decide_joining(client, membership, "reject")
    membership.refresh_from_db()
    assert membership.status == "REMOVED" and mail.outbox[0].subject == "Your request to join Demo Club"
    assert OperatorAction.objects.get().action == "TURNED_DOWN"


def test_only_people_waiting_never_a_role_change_or_removal(client, operator, run_on_commit):
    member = make_member("sam@example.com", club=default_club()).memberships.get()
    for action, role in (("role", "COMMITTEE"), ("remove", ""), ("approve", "ADMINISTRATOR")):
        decide_joining(client, member, action, role)
    member.refresh_from_db()
    assert (member.status, member.role) == ("APPROVED", "MEMBER")
    waiting = waiting_at(default_club())
    decide_joining(client, waiting, "remove")
    waiting.refresh_from_db()
    assert waiting.status == "WAITING" and not mail.outbox and not OperatorAction.objects.exists()


def test_another_clubs_membership_isnt_reached_through_this_club(client, operator, run_on_commit):
    harbour = make_club("harbour", "Harbour Sailing Club")
    theirs = waiting_at(harbour, "bea@example.com", "Bea")
    url = reverse("races:operator_decide_joining", args=[default_club().pk, theirs.pk])
    assert client.post(url, {"action": "approve", "role": "MEMBER"}, **SERVICE).status_code == 404
    theirs.refresh_from_db()
    assert theirs.status == "WAITING"


def test_not_while_the_club_is_suspended(client, operator, run_on_commit):
    club = default_club()
    club.status = Club.Status.SUSPENDED
    club.save()
    membership = waiting_at(club)
    response = decide_joining(client, membership, "approve")
    page = client.get(response["Location"], **SERVICE).content.decode()
    assert "Reactivate the club first" in page
    membership.refresh_from_db()
    assert membership.status == "WAITING" and not mail.outbox and not OperatorAction.objects.exists()


def test_only_the_operator_on_the_services_own_address(client, run_on_commit):
    membership = waiting_at(default_club())
    for person, expected in ((make_administrator(), 403), (make_member("m@example.com"), 403)):
        client.force_login(person)
        assert decide_joining(client, membership, "approve").status_code == expected
    client.logout()
    assert decide_joining(client, membership, "approve")["Location"].startswith(reverse("admin:login"))
    client.force_login(make_operator())
    assert decide_joining(client, membership, "approve", host=at("demo")).status_code == 404
    membership.refresh_from_db()
    assert membership.status == "WAITING"


def test_the_club_sees_the_operator_approved_them(client, settings, run_on_commit):
    membership = waiting_at(default_club())
    client.force_login(make_operator())
    decide_joining(client, membership, "approve")
    client.force_login(make_administrator())
    page = client.get(reverse("races:members"), **at("demo")).content.decode()
    row = page.split(f'id="member-{membership.pk}"')[1].split("</tr>")[0]
    assert "Approved by the Race Times operator" in row
