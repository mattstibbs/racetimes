"""Slice 11 part 5: a person's account page, downloading their data, and deleting their account."""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from races import notifications, throttle
from races.account_deletion import DELETED
from races.models import (
    Boat, BoatRequest, ClubInvitation, ClubMembership, EntryRequest, Finish, OperatorAction, ScoringChange, Series,
)
from races.scoring import score_series
from races.test_members import PASSWORD
from races.testing import (
    default_club, enter, join, make_administrator, make_boat, make_club, make_committee, make_member,
    make_operator, make_race, make_series, record,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def run_on_commit(monkeypatch):
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())


@pytest.fixture
def pat(client):
    """A member of Demo Club and, waiting, of Harbour; with a boat, a request and a change made."""
    pat = make_member("pat@example.com", first_name="Pat", last_name="Jones", password=PASSWORD)
    harbour = make_club("harbour", "Harbour Sailing Club")
    join(pat, harbour, status="WAITING")
    client.force_login(pat)
    return pat


def download(client):
    response = client.get(reverse("races:download_my_data"))
    assert response["Content-Disposition"].startswith('attachment; filename="race-times-my-data-')
    return json.loads(response.content)


# --- The account page -------------------------------------------------------------------------


def test_the_account_page_lists_every_club_with_its_role_and_status(client, pat):
    page = client.get(reverse("races:account")).content.decode()
    assert "Pat Jones" in page and "pat@example.com" in page
    assert "Demo Club" in page and "Harbour Sailing Club" in page and "Waiting for approval" in page
    assert 'href="http://harbour.localhost/"' in page
    assert reverse("races:download_my_data") in page and reverse("races:delete_account") in page


def test_someone_waiting_to_join_has_the_account_link(client):
    client.force_login(make_member("wait@example.com", status="WAITING"))
    assert f'href="{reverse("races:account")}"' in client.get(reverse("races:my_boats")).content.decode()


def test_the_account_pages_need_a_login(client):
    for name in ("races:account", "races:download_my_data", "races:delete_account"):
        assert client.get(reverse(name))["Location"].startswith(reverse("races:login"))


# --- Download my data -------------------------------------------------------------------------


def test_the_download_holds_their_account_memberships_boats_requests_and_changes(client, pat):
    series = make_series("Autumn")
    boat = make_boat("GBR42", name="Kittiwake", owner=pat)
    make_boat("GBR7", name="Tern", owner=make_member("sam@example.com"))  # someone else's
    BoatRequest.objects.create(club=default_club(), kind="CLAIM", boat=boat, requested_by=pat,
                               member_note="It's mine", decided_by_name="committee@example.com")
    EntryRequest.objects.create(series=series, boat=boat, requested_by=pat)
    ScoringChange.objects.create(club=default_club(), series=series, user=pat, user_name="pat@example.com",
                                 kind="SERIES", action="CHANGED", description="Autumn")
    data = download(client)
    assert data["account"]["email"] == "pat@example.com" and data["account"]["first_name"] == "Pat"
    assert {(m["club"], m["status"]) for m in data["memberships"]} == {
        ("Demo Club", "Approved"), ("Harbour Sailing Club", "Waiting for approval")}
    assert [(b["club"], b["sail_number"], b["name"]) for b in data["boats"]] == [("Demo Club", "GBR42", "Kittiwake")]
    assert [(r["kind"], r["member_note"]) for r in data["boat_requests"]] == [("Own a boat on record", "It's mine")]
    assert [r["series"] for r in data["entry_requests"]] == ["Autumn"]
    assert [c["description"] for c in data["changes_made"]] == ["Autumn"]
    text = json.dumps(data)
    assert "sam@example.com" not in text and "Tern" not in text
    assert "committee@example.com" not in text  # who decided is someone else's login


# --- Deleting an account ----------------------------------------------------------------------


@pytest.fixture
def season(pat):
    """A season Pat took part in, as an owner, a committee member and the one who invited someone."""
    series = make_series("Autumn")
    kittiwake = enter(series, make_boat("GBR42", name="Kittiwake", owner=pat))
    tern = enter(series, make_boat("GBR7", name="Tern"))
    race = make_race(series, 1)
    record(race, kittiwake, "19:05:00")
    record(race, tern, "19:06:00")
    ScoringChange.objects.create(club=default_club(), series=series, race=race, user=pat,
                                 user_name="pat@example.com", kind="FINISH", action="CHANGED",
                                 description="Kittiwake, Race 1", is_correction=True, reason="Protest")
    request = BoatRequest.objects.create(club=default_club(), kind="CLAIM", boat=kittiwake.boat, requested_by=pat)
    decided = BoatRequest.objects.create(club=default_club(), kind="CLAIM", boat=tern.boat,
                                         requested_by=make_member("sam@example.com"), status="APPROVED",
                                         decided_by=pat, decided_by_name="pat@example.com")
    ClubMembership.objects.filter(user__username="sam@example.com").update(decided_by_name="pat@example.com")
    Series.objects.filter(pk=series.pk).update(declared_final_by_name="pat@example.com")
    ClubInvitation.objects.create(club=default_club(), email="kim@example.com", invited_by_name="pat@example.com")
    ClubInvitation.objects.create(club=default_club(), email="PAT@example.com")
    OperatorAction.objects.create(who="pat@example.com", action="INVITED", club_subdomain="demo",
                                  detail="Pat@Example.com as club administrator")
    return {"series": series, "request": request, "decided": decided, "boat": kittiwake.boat}


def delete(client, password=PASSWORD):
    return client.post(reverse("races:delete_account"), {"password": password})


def test_deleting_keeps_the_clubs_records_and_names_them_nowhere(client, pat, season):
    before = score_series(season["series"]).standings
    response = delete(client)
    assert response["Location"] == reverse("results:home")
    assert not get_user_model().objects.filter(username="pat@example.com").exists()
    # What goes: memberships and requests.
    assert not ClubMembership.objects.filter(user_id=pat.pk).exists()
    assert not BoatRequest.objects.filter(pk=season["request"].pk).exists()
    # What stays: the boat, with no owner, every finish and the scores.
    season["boat"].refresh_from_db()
    assert season["boat"].owner is None and Finish.objects.count() == 2
    after = score_series(season["series"]).standings
    assert [(r.entry.pk, r.total) for r in after] == [(r.entry.pk, r.total) for r in before]
    # The change history keeps the change, by "a deleted account".
    change = ScoringChange.objects.get()
    assert (change.user, change.user_name, change.reason) == (None, DELETED, "Protest")
    # Every other stored mention of the login, too.
    season["decided"].refresh_from_db()
    assert season["decided"].decided_by_name == DELETED
    assert ClubMembership.objects.get(user__username="sam@example.com").decided_by_name == DELETED
    assert Series.objects.get().declared_final_by_name == DELETED
    assert sorted(ClubInvitation.objects.values_list("email", "invited_by_name")) == [
        (DELETED, ""), ("kim@example.com", DELETED)]
    action = OperatorAction.objects.get()
    assert (action.who, action.detail) == (DELETED, f"{DELETED} as club administrator")


def test_no_stored_text_still_names_them(client, pat, season):
    from django.core import serializers

    delete(client)
    everything = serializers.serialize("json", [
        *ScoringChange.objects.all(), *BoatRequest.objects.all(), *EntryRequest.objects.all(),
        *ClubMembership.objects.all(), *Series.objects.all(), *ClubInvitation.objects.all(),
        *OperatorAction.objects.all(), *Boat.objects.all(),
    ])
    assert "pat@example.com" not in everything.lower()


def test_they_are_logged_out_told_and_emailed_from_the_club(client, pat):
    response = delete(client)
    page = client.get(response["Location"]).content.decode()
    assert "Your account has been deleted." in page and "_auth_user_id" not in client.session
    [message] = mail.outbox
    assert message.to == ["pat@example.com"] and message.subject == "Your Race Times account has been deleted"
    assert "Demo Club via Race Times" in message.from_email and "last email" in message.body


def test_a_wrong_password_deletes_nothing(client, pat):
    response = delete(client, "not-my-password")
    assert response.status_code == 200 and "That isn&#x27;t your password." in response.content.decode()
    assert get_user_model().objects.filter(pk=pat.pk).exists() and not mail.outbox


def test_the_password_check_is_limited_like_a_login(client, pat, monkeypatch):
    monkeypatch.setattr(throttle, "now", lambda: 1_000_000.0)
    for _ in range(10):
        delete(client, "not-my-password")
    response = delete(client)
    assert throttle.LOCKED in response.content.decode()
    assert get_user_model().objects.filter(pk=pat.pk).exists()


def test_a_clubs_only_administrator_must_hand_on_first(client):
    admin = make_administrator("admin@example.com", password=PASSWORD)
    client.force_login(admin)
    page = client.get(reverse("races:delete_account")).content.decode()
    assert "You're the only administrator of <strong>Demo Club</strong>" in page and 'name="password"' not in page
    delete(client)
    assert get_user_model().objects.filter(pk=admin.pk).exists()
    # With a second administrator, they can go.
    make_administrator("other@example.com")
    delete(client)
    assert not get_user_model().objects.filter(pk=admin.pk).exists()


def test_a_waiting_or_removed_administrator_doesnt_count(client):
    admin = make_administrator("admin@example.com", password=PASSWORD)
    make_administrator("gone@example.com", status="REMOVED")
    make_administrator("waiting@example.com", status="WAITING")
    client.force_login(admin)
    delete(client)
    assert get_user_model().objects.filter(pk=admin.pk).exists()


def test_the_operator_cant_delete_their_account_here(client):
    operator = make_operator()
    operator.set_password(PASSWORD)
    operator.save()
    join(operator, default_club())
    client.force_login(operator)
    assert "operator account can" in client.get(reverse("races:delete_account")).content.decode()
    delete(client)
    assert get_user_model().objects.filter(pk=operator.pk).exists()


def test_deleting_one_account_leaves_another_club_member_alone(client, pat):
    sam = make_committee("sam@example.com")
    ScoringChange.objects.create(club=default_club(), user=sam, user_name="sam@example.com",
                                 kind="SERIES", action="CHANGED", description="Autumn")
    delete(client)
    change = ScoringChange.objects.get()
    assert (change.user, change.user_name) == (sam, "sam@example.com")
