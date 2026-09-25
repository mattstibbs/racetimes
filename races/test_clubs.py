"""Slice 11 part 1: clubs, found from the address, and the rules that come with them.

The isolation of one club's data from another's is tested in
races/test_isolation.py.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from races.forms import BoatRegistrationForm
from races.models import Boat, Club, Finish, SeriesEntry
from races.scoring import score_series
from races.test_start_sheet import _scores
from races.testing import (
    default_club, enter, make_boat, make_club, make_committee, make_member, make_race, make_series, record,
)

pytestmark = pytest.mark.django_db


def at(subdomain):
    """The Host header for a club's address, in tests (SERVICE_DOMAIN is localhost)."""
    return {"HTTP_HOST": f"{subdomain}.localhost"}


# --- The first club --------------------------------------------------------------------


def test_the_migrations_create_demo_club():
    club = Club.objects.get(subdomain="demo")
    assert (club.name, club.status) == ("Demo Club", "ACTIVE")


@pytest.mark.django_db(transaction=True)
def test_the_migration_moves_existing_rows_into_the_first_club():
    """A database from before slice 11, with no clubs, gets them all in Demo Club, scoring as before."""
    executor = MigrationExecutor(connection)
    executor.migrate([("races", "0010_series_final")])
    old = executor.loader.project_state([("races", "0010_series_final")]).apps
    Series, Boat, SeriesEntry, Race, RaceEntry, Finish, BoatRequest, ScoringChange = (
        old.get_model("races", name) for name in
        ("Series", "Boat", "SeriesEntry", "Race", "RaceEntry", "Finish", "BoatRequest", "ScoringChange")
    )
    from datetime import date, time
    from django.contrib.auth import get_user_model
    member = old.get_model(*get_user_model()._meta.label.split(".")).objects.create(username="pat@example.com")
    series = Series.objects.create(name="Autumn 2026")
    boats = [Boat.objects.create(sail_number=s, base_number=Decimal(b)) for s, b in (("GBR42", "0.805"), ("GBR7", "0.900"))]
    race = Race.objects.create(series=series, number=1, date=date(2026, 9, 23), start_time=time(18, 0))
    for boat, finish in zip(boats, (time(19, 5, 31), time(19, 7, 2))):
        entry = SeriesEntry.objects.create(series=series, boat=boat)
        RaceEntry.objects.create(race=race, entry=entry)
        Finish.objects.create(race=race, entry=entry, status="FINISHED", finish_time=finish)
    BoatRequest.objects.create(kind="REGISTER", sail_number="GBR5", requested_by=member)
    ScoringChange.objects.create(series=series, kind="SERIES", action="CHANGED", description="x")

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    from races.models import Boat as NewBoat, BoatRequest as NewRequest, ScoringChange as NewChange, Series as NewSeries
    demo = Club.objects.get(subdomain="demo")
    assert Club.objects.count() == 1
    for model in (NewBoat, NewSeries, NewRequest, NewChange):
        assert set(model.objects.values_list("club", flat=True)) == {demo.pk}
    results = score_series(NewSeries.objects.get())
    assert [row.entry.boat.sail_number for row in results.races[0].rows] == ["GBR42", "GBR7"]


# --- Finding the club from the address ---------------------------------------------------


@pytest.fixture
def harbour():
    return make_club("harbour", "Harbour Sailing Club")


def test_a_club_address_shows_that_club(client, harbour):
    make_series("Harbour Winter", club=harbour)
    page = client.get(reverse("results:home"), **at("harbour")).content.decode()
    assert "Harbour Sailing Club" in page and "Harbour Winter" in page
    page = client.get(reverse("results:home"), **at("demo")).content.decode()
    assert "Demo Club" in page and "Harbour Winter" not in page


def test_the_address_is_read_ignoring_case_and_port(client, harbour):
    page = client.get(reverse("results:home"), HTTP_HOST="HARBOUR.localhost:8000").content.decode()
    assert "Harbour Sailing Club" in page


def test_an_unknown_club_address_is_a_404(client):
    response = client.get(reverse("results:home"), **at("nowhere"))
    assert response.status_code == 404
    assert "There's no club at this address" in response.content.decode()


def test_a_suspended_club_is_paused_except_for_the_operator(client, harbour, admin_user):
    harbour.status = Club.Status.SUSPENDED
    harbour.save()
    response = client.get(reverse("results:home"), **at("harbour"))
    assert response.status_code == 503 and "Harbour Sailing Club's site is paused" in response.content.decode()
    client.force_login(admin_user)
    assert client.get(reverse("results:home"), **at("harbour")).status_code == 200


def test_an_address_with_no_club_uses_single_club(client, settings, harbour):
    settings.SINGLE_CLUB = "harbour"
    assert "Harbour Sailing Club" in client.get(reverse("results:home")).content.decode()


def test_the_services_own_address_shows_the_service(client, settings):
    settings.SINGLE_CLUB = ""
    page = client.get("/", HTTP_HOST="localhost").content.decode()
    assert "Race Times" in page and "yourclub.racetimes.co.uk" in page and "Demo Club" not in page
    response = client.get(reverse("results:series", args=[make_series().pk]), HTTP_HOST="localhost")
    assert response.status_code == 404


def test_only_the_operator_gets_into_the_admin_on_the_services_address(client, settings, admin_user):
    settings.SINGLE_CLUB = ""
    client.force_login(make_committee())
    response = client.get(reverse("admin:index"), HTTP_HOST="localhost")
    assert response.status_code == 302 and "login" in response["Location"]
    client.force_login(admin_user)
    assert client.get(reverse("admin:index"), HTTP_HOST="localhost").status_code == 200


def test_the_header_names_the_club(client):
    page = client.get(reverse("results:home")).content.decode()
    assert '<span>Demo Club</span> <small class="brand-service">Race Times</small>' in page  # in .brand-text


# --- The rules that come with clubs --------------------------------------------------


def test_two_clubs_can_each_have_the_same_sail_number(harbour):
    make_boat("GBR42")
    make_boat("gbr 42", club=harbour)
    assert Boat.objects.filter(sail_number__iexact="GBR42").count() == 1
    with pytest.raises(ValidationError, match="already registered"):
        Boat(club=harbour, sail_number="GBR 42", base_number=Decimal("0.9")).full_clean()


def test_a_member_can_register_a_sail_number_another_club_has(harbour):
    make_boat("GBR42", club=harbour)
    data = {"sail_number": "GBR42", "base_number": "0.9"}
    assert BoatRegistrationForm(data, club=default_club()).is_valid()
    assert not BoatRegistrationForm(data, club=harbour).is_valid()


def test_a_boat_can_only_be_entered_in_its_own_clubs_series(harbour):
    boat = make_boat("GBR42", club=harbour)
    with pytest.raises(ValidationError, match="belongs to another club"):
        SeriesEntry(series=make_series(), boat=boat).full_clean()


def test_the_admin_puts_a_new_boat_in_the_current_club(client, harbour):
    committee = make_committee(club=harbour)
    client.force_login(committee)
    response = client.post(reverse("admin:races_boat_add"), {
        "sail_number": "GBR42", "name": "Kittiwake", "make": "", "model": "", "owner_name": "",
        "length_overall_m": "", "waterline_length_m": "", "base_number": "0.805", "reason": "",
    }, **at("harbour"))
    assert response.status_code == 302
    assert Boat.objects.get(sail_number="GBR42").club == harbour


def test_the_admin_refuses_a_sail_number_already_in_the_club(client, harbour):
    make_boat("GBR42", club=harbour)
    client.force_login(make_committee(club=harbour))
    response = client.post(reverse("admin:races_boat_add"), {
        "sail_number": "gbr 42", "name": "", "make": "", "model": "", "owner_name": "",
        "length_overall_m": "", "waterline_length_m": "", "base_number": "0.805", "reason": "",
    }, **at("harbour"))
    assert response.status_code == 200 and "A boat with this sail number is already registered." in response.content.decode()


def test_history_rows_belong_to_the_club(client, harbour):
    series = make_series(club=harbour)
    entry = enter(series, make_boat(club=harbour))
    race = make_race(series)
    client.force_login(make_committee(club=harbour))
    prefix = f"entry-{entry.pk}"
    from races.testing import start
    start(race, entry)
    client.post(reverse("races:save_finish", args=[race.pk, entry.pk]),
                {f"{prefix}-finish_time": "19:00:00", f"{prefix}-status": "FINISHED"}, **at("harbour"))
    assert Finish.objects.get().race.series.club == harbour
    assert list(harbour.scoring_changes.values_list("kind", flat=True)) == ["FINISH"]


# --- www (slice 12) --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/privacy/?x=1", "/operator/"])
def test_www_redirects_to_the_services_own_address_keeping_the_path(client, settings, path):
    settings.SINGLE_CLUB = ""
    response = client.get(path, HTTP_HOST="www.localhost:8000")
    assert response.status_code == 301 and response["Location"] == f"http://localhost:8000{path}"


def test_www_is_never_a_club(client, settings):
    settings.SINGLE_CLUB = "demo"  # even on a site that shows one club on addresses with none
    make_club("www", "Sneaky")  # can't be made through the operator's form, but just in case
    assert client.get("/", HTTP_HOST="www.localhost")["Location"] == "http://localhost/"
