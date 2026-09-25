"""Slice 11 part 5: a club's data export, and the operator deleting a club."""

import csv
import io
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from races.club_deletion import delete_club
from races.models import (
    Boat, BoatRequest, Club, ClubInvitation, ClubMembership, EntryRequest, Finish, OperatorAction, Race, RaceEntry,
    ScoringChange, Series, SeriesEntry,
)
from races.scoring import score_series
from races.series_csv import typed
from races.test_isolation import DEMO, HARBOUR, clubs, leaks  # noqa: F401 (clubs is a fixture)
from races.testing import default_club, make_administrator, make_committee, make_member, make_operator

pytestmark = pytest.mark.django_db

SERVICE = {"HTTP_HOST": "localhost"}


def files_in(response):
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"].startswith('attachment; filename="demo race times data ')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {name: archive.read(name).decode("utf-8-sig") for name in archive.namelist()}


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


# --- The club's data export ---------------------------------------------------------------------


def test_the_export_holds_everything_the_club_does(client, clubs):
    client.force_login(make_administrator())
    files = files_in(client.get(reverse("races:export_club_data"), HTTP_HOST=DEMO))
    assert set(files) == {
        "boats.csv", "members.csv", "series.csv", "series_entries.csv", "races.csv", "start_sheets.csv",
        "finishes.csv", "boat_requests.csv", "entry_requests.csv", "history.csv",
        "results/Autumn Series results.csv", "results/Autumn Series Two results.csv",
    }
    assert sorted(b["name"] for b in rows(files["boats.csv"])) == ["Albatross", "Auk", "Avocet"]
    assert {b["owner"] for b in rows(files["boats.csv"])} == {"ann@example.com", "shared@example.com", ""}
    members = {m["email"]: m for m in rows(files["members.csv"])}
    assert members["ann@example.com"]["name"] == "Ann Jones" and members["admin@example.com"]["role"] == \
        "Club administrator"
    assert members["arctic.waiting@example.com"]["status"] == "Waiting for approval"
    assert len(rows(files["finishes.csv"])) == Finish.objects.for_club(default_club()).count() == 4
    assert [h["reason"] for h in rows(files["history.csv"])] == ["Protest"]
    assert {r["kind"] for r in rows(files["boat_requests.csv"])} == {"Register a boat", "Own a boat on record"}
    assert "Series Standings" in files["results/Autumn Series results.csv"]


def test_nothing_of_another_club_is_in_it(client, clubs):
    client.force_login(make_administrator())
    files = files_in(client.get(reverse("races:export_club_data"), HTTP_HOST=DEMO))
    assert all(leaks(text) == [] for text in files.values())


def test_only_the_clubs_administrators_can_download_it(client, clubs):
    url = reverse("races:export_club_data")
    assert client.get(url, HTTP_HOST=DEMO)["Location"].startswith(reverse("races:login"))
    client.force_login(make_committee())
    assert client.get(url, HTTP_HOST=DEMO).status_code == 403
    client.force_login(make_administrator("other@example.com", club=Club.objects.get(subdomain="harbour")))
    assert client.get(url, HTTP_HOST=DEMO).status_code == 403  # an administrator elsewhere


def test_the_members_page_links_to_it(client):
    client.force_login(make_administrator())
    assert reverse("races:export_club_data") in client.get(reverse("races:members")).content.decode()


@pytest.mark.parametrize("value, safe", [
    ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"), ("+44 1234", "'+44 1234"), ("-1", "'-1"),
    ("@SUM(A1)", "'@SUM(A1)"), ("Kittiwake", "Kittiwake"), ("", ""), (None, ""),
])
def test_typed_text_cant_run_as_a_formula(value, safe):
    assert typed(value) == safe


def test_the_export_and_the_series_download_both_guard_typed_text(client, clubs):
    Boat.objects.filter(name="Avocet").update(name="=cmd|' /C calc'!A0")
    client.force_login(make_administrator())
    files = files_in(client.get(reverse("races:export_club_data"), HTTP_HOST=DEMO))
    assert "'=cmd|' /C calc'!A0" in [b["name"] for b in rows(files["boats.csv"])]
    series_file = files["results/Autumn Series results.csv"]
    assert "'=cmd" in series_file and ",=cmd" not in series_file


# --- The operator: the export and deleting a club --------------------------------------------


@pytest.fixture
def operator(client, settings):
    settings.SINGLE_CLUB = ""
    client.force_login(make_operator())


def harbour():
    return Club.objects.get(subdomain="harbour")


def test_the_operator_downloads_a_suspended_clubs_data_and_it_is_logged(client, clubs, operator):
    club = harbour()
    club.status = Club.Status.SUSPENDED
    club.save()
    response = client.get(reverse("races:operator_export_club", args=[club.pk]), **SERVICE)
    assert response["Content-Disposition"].startswith('attachment; filename="harbour race times data ')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "Bittern" in archive.read("boats.csv").decode("utf-8-sig")
    action = OperatorAction.objects.get()
    assert (action.action, action.club_subdomain, action.who) == ("EXPORTED", "harbour", "operator@example.com")


def suspend(club):
    club.status = Club.Status.SUSPENDED
    club.save()
    return club


def test_deleting_a_club_takes_everything_of_its_and_nothing_else(client, clubs, operator):
    demo_before = {model: model.objects.for_club(default_club()).count()
                   for model in (Boat, Series, SeriesEntry, Race, RaceEntry, Finish, ScoringChange, BoatRequest,
                                 EntryRequest)}
    demo_scores = [(r.entry.pk, r.total) for r in score_series(clubs["demo"]["series"]).standings]
    people = get_user_model().objects.count()
    club = suspend(harbour())
    response = client.post(reverse("races:operator_delete_club", args=[club.pk]), {"confirm": "harbour"}, **SERVICE)
    assert response["Location"] == reverse("races:operator_clubs")
    assert not Club.objects.filter(subdomain="harbour").exists()
    for model in (Boat, Series, SeriesEntry, Race, RaceEntry, Finish, ScoringChange, BoatRequest, EntryRequest):
        assert model.objects.count() == demo_before[model], model  # only Demo Club's rows are left
    assert not ClubMembership.objects.filter(club_id=club.pk).exists()
    assert not ClubInvitation.objects.filter(club_id=club.pk).exists()
    assert get_user_model().objects.count() == people  # accounts stay
    assert [(r.entry.pk, r.total) for r in score_series(clubs["demo"]["series"]).standings] == demo_scores
    action = OperatorAction.objects.get(action="DELETED")
    assert action.club_subdomain == "harbour"
    assert action.detail == "Harbour Sailing Club: 3 boats, 2 series, 3 memberships"


def test_an_active_club_isnt_deleted(client, clubs, operator):
    club = harbour()
    page = client.get(reverse("races:operator_delete_club", args=[club.pk]), **SERVICE).content.decode()
    assert "Suspend the club before deleting it" in page and 'name="confirm"' not in page
    client.post(reverse("races:operator_delete_club", args=[club.pk]), {"confirm": "harbour"}, **SERVICE)
    assert Club.objects.filter(pk=club.pk).exists()
    with pytest.raises(ValueError):
        delete_club(club)


def test_the_subdomain_must_be_typed_exactly(client, clubs, operator):
    club = suspend(harbour())
    response = client.post(reverse("races:operator_delete_club", args=[club.pk]), {"confirm": "Harbour "},
                           **SERVICE)
    assert response.status_code == 400 and "Type the club" in response.content.decode()
    assert Club.objects.filter(pk=club.pk).exists() and not OperatorAction.objects.exists()


def test_with_single_club_set_there_are_no_operator_pages_to_delete_from(client, clubs, settings):
    settings.SINGLE_CLUB = "demo"
    client.force_login(make_operator())
    club = suspend(default_club())
    response = client.post(reverse("races:operator_delete_club", args=[club.pk]), {"confirm": "demo"}, **SERVICE)
    assert response.status_code == 404 and Club.objects.filter(pk=club.pk).exists()


def test_the_operator_page_offers_the_download_and_deletion_once_suspended(client, clubs, operator):
    club = harbour()
    page = client.get(reverse("races:operator_club", args=[club.pk]), **SERVICE).content.decode()
    assert reverse("races:operator_export_club", args=[club.pk]) in page
    assert reverse("races:operator_delete_club", args=[club.pk]) not in page
    suspend(club)
    page = client.get(reverse("races:operator_club", args=[club.pk]), **SERVICE).content.decode()
    assert reverse("races:operator_delete_club", args=[club.pk]) in page


def test_only_the_operator(client, clubs, settings):
    settings.SINGLE_CLUB = ""
    club = suspend(harbour())
    client.force_login(make_administrator("bea.admin@example.com", club=club))
    for name in ("races:operator_export_club", "races:operator_delete_club"):
        assert client.get(reverse(name, args=[club.pk]), **SERVICE).status_code == 403
    client.force_login(make_member("x@example.com"))
    client.post(reverse("races:operator_delete_club", args=[club.pk]), {"confirm": "harbour"}, **SERVICE)
    assert Club.objects.filter(pk=club.pk).exists()
