"""Slice 18: the race office's boat form - its rules, history and emails.

The same rules the admin's boat form had, now tested through the race office's
pages. The admin's own tests stay in races/test_audit.py and elsewhere, since
the admin uses this form too.
"""

from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from races.models import Boat, ScoringChange
from races.testing import (
    HARBOUR,
    boat_form,
    declare,
    enter,
    make_boat,
    make_club,
    make_committee,
    make_member,
    make_race,
    make_series,
    record,
)

pytestmark = pytest.mark.django_db

REASON_REQUIRED = "give a reason for the correction"


def post(client, boat, **changes):
    return client.post(
        reverse("races:office_boat", args=[boat.pk]), boat_form(boat, **changes)
    )


def add(client, **fields):
    data = boat_form(Boat(sail_number="GBR8", base_number="0.9"))
    data.update(fields)
    return client.post(reverse("races:office_new_boat"), data)


@pytest.fixture
def sailed():
    """Two owned boats with a result in a series, and one in an unsailed series."""
    pat = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    sam = make_member("sam@example.com", first_name="Sam", last_name="Taylor")
    series = make_series("Wednesdays")
    kittiwake = make_boat("GBR42", name="Kittiwake", base_number="0.805", owner=pat)
    puffin = make_boat("GBR77", name="Puffin", base_number="0.842", owner=sam)
    entries = [enter(series, kittiwake), enter(series, puffin)]
    race = make_race(series)
    record(race, entries[0], "19:05:31")
    record(race, entries[1], "19:07:02")
    return {"series": series, "kittiwake": kittiwake, "puffin": puffin, "sam": sam}


# --- Adding a boat -------------------------------------------------------------------------


def test_a_new_boat_joins_this_club(client):
    harbour = make_club("harbour")
    client.force_login(make_committee(club=harbour))
    response = client.post(
        reverse("races:office_new_boat"),
        boat_form(Boat(sail_number="GBR42", name="Kittiwake", base_number="0.805")),
        HTTP_HOST=HARBOUR,
    )
    assert response.status_code == 302
    assert Boat.objects.get(sail_number="GBR42").club == harbour


def test_adding_a_boat_records_no_history(committee_client):
    assert add(committee_client).status_code == 302
    assert Boat.objects.filter(sail_number="GBR8").exists()
    assert not ScoringChange.objects.exists()


@pytest.mark.parametrize("typed", ["GBR42", "gbr 42"])
def test_a_sail_number_already_in_the_club_is_refused(committee_client, typed):
    make_boat("GBR42")
    response = add(committee_client, sail_number=typed)
    assert "A boat with this sail number is already registered." in (
        response.content.decode()
    )
    assert Boat.objects.count() == 1


def test_another_clubs_sail_number_is_no_obstacle(committee_client):
    make_boat("GBR42", club=make_club("harbour"))
    assert add(committee_client, sail_number="GBR42").status_code == 302


def test_changing_to_another_boats_sail_number_is_refused(committee_client):
    make_boat("GBR42")
    boat = make_boat("GBR7")
    response = post(committee_client, boat, sail_number="GBR 42")
    assert "already registered" in response.content.decode()
    assert Boat.objects.get(pk=boat.pk).sail_number == "GBR7"


def test_a_boat_keeps_its_own_sail_number(committee_client):
    boat = make_boat("GBR42")
    assert post(committee_client, boat, name="Kittiwake").status_code == 302


# --- Owners --------------------------------------------------------------------------------


def test_owners_are_chosen_from_this_clubs_approved_members(committee_client):
    pat = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    make_member("waiting@example.com", first_name="Wendy", status="WAITING")
    make_member("gone@example.com", first_name="Gus", is_active=False)
    make_member("far@example.com", first_name="Fiona", club=make_club("harbour"))
    page = committee_client.get(reverse("races:office_new_boat")).content.decode()
    assert "Pat Jones (pat@example.com)" in page
    for name in ("Wendy", "Gus", "Fiona"):
        assert name not in page
    response = add(committee_client, owner=pat.pk)
    assert response.status_code == 302
    assert Boat.objects.get(sail_number="GBR8").owner == pat


def test_another_clubs_member_cant_be_made_owner(committee_client):
    far = make_member("far@example.com", club=make_club("harbour"))
    response = add(committee_client, owner=far.pk)
    assert response.status_code == 200
    assert not Boat.objects.filter(sail_number="GBR8").exists()


def test_a_boat_without_an_account_takes_a_typed_owner_name(committee_client):
    add(committee_client, owner_name="M. Visitor")
    assert Boat.objects.get(sail_number="GBR8").owner_display == "M. Visitor"


# --- The reason box, only where it applies -------------------------------------------------


def test_no_reason_box_for_a_new_boat(committee_client):
    page = committee_client.get(reverse("races:office_new_boat")).content.decode()
    assert "Reason for change" not in page


def test_no_reason_box_for_a_boat_in_a_series_without_results(committee_client):
    boat = make_boat()
    enter(make_series(), boat)
    page = committee_client.get(
        reverse("races:office_boat", args=[boat.pk])
    ).content.decode()
    assert "Reason for change" not in page


def test_a_reason_box_once_the_boat_has_results(committee_client, sailed):
    page = committee_client.get(
        reverse("races:office_boat", args=[sailed["kittiwake"].pk])
    ).content.decode()
    assert "Reason for change" in page


def test_the_admin_always_shows_its_reason_box(committee_client):
    page = committee_client.get(reverse("admin:races_boat_add")).content.decode()
    assert "Reason for change" in page


# --- History -------------------------------------------------------------------------------


def test_a_base_number_correction_needs_a_reason(committee_client, sailed):
    boat = sailed["kittiwake"]
    response = post(committee_client, boat, base_number="0.810")
    assert REASON_REQUIRED in response.content.decode()
    assert Boat.objects.get(pk=boat.pk).base_number == boat.base_number
    assert not ScoringChange.objects.exists()


def test_a_base_number_correction_is_recorded_in_every_series(committee_client, sailed):
    boat = sailed["kittiwake"]
    unsailed = make_series("Autumn")
    enter(unsailed, boat)
    response = post(committee_client, boat, base_number="0.810", reason="Certificate")
    assert response.status_code == 302
    changes = ScoringChange.objects.all()
    assert {c.series: c.is_correction for c in changes} == {
        sailed["series"]: True,
        unsailed: False,
    }
    assert all(c.reason == "Certificate" for c in changes)
    assert all(c.changes == {"NHC base number": ["0.805", "0.810"]} for c in changes)
    assert {c.user_name for c in changes} == {"officer@example.com"}


def test_a_base_number_before_any_results_needs_no_reason(committee_client):
    boat = make_boat("GBR5")
    enter(make_series(), boat)
    assert post(committee_client, boat, base_number="0.980").status_code == 302
    change = ScoringChange.objects.get()
    assert (change.is_correction, change.reason) == (False, "")


def test_details_that_move_no_score_are_not_recorded(committee_client, sailed):
    boat = sailed["kittiwake"]
    response = post(committee_client, boat, name="Kittiwake II", make="Sigma")
    assert response.status_code == 302
    assert Boat.objects.get(pk=boat.pk).name == "Kittiwake II"
    assert not ScoringChange.objects.exists()


def test_a_correction_says_what_it_changed(committee_client, sailed):
    response = post(
        committee_client,
        sailed["kittiwake"],
        base_number="0.700",
        reason="Certificate",
    )
    response = committee_client.get(response["Location"])
    messages = [str(m) for m in response.context["messages"]]
    assert any(m.startswith("Wednesdays: ") for m in messages), messages


def test_a_boat_in_a_final_series_can_still_be_changed(client, committee, season):
    # As in the admin (races/test_final.py): the final series keeps its saved
    # results, and the boat's other series move.
    series = season["series"]
    declare(client, series)
    series.refresh_from_db()
    assert series.is_final
    boat = season["entries"][0].boat
    response = post(client, boat, base_number="0.700", reason="Certificate")
    assert response.status_code == 302
    assert Boat.objects.get(pk=boat.pk).base_number == Decimal("0.700")


# --- Emails to the owner -------------------------------------------------------------------


def test_a_change_emails_the_owner_what_changed(
    committee_client, sailed, run_on_commit
):
    boat = sailed["kittiwake"]
    post(committee_client, boat, name="Kittiwake II", owner=boat.owner_id)
    [message] = mail.outbox
    assert message.to == ["pat@example.com"]
    assert "Name: Kittiwake -> Kittiwake II" in message.body


def test_saving_a_boat_unchanged_emails_nobody(committee_client, sailed, run_on_commit):
    boat = sailed["kittiwake"]
    post(committee_client, boat, owner=boat.owner_id)
    assert not mail.outbox


def test_changing_the_owner_tells_both(committee_client, sailed, run_on_commit):
    boat = sailed["kittiwake"]
    post(committee_client, boat, owner=sailed["sam"].pk)
    assert sorted(m.to[0] for m in mail.outbox) == [
        "pat@example.com",
        "sam@example.com",
    ]


def test_a_new_boat_emails_nobody(committee_client, run_on_commit):
    pat = make_member("pat@example.com")
    add(committee_client, owner=pat.pk)
    assert not mail.outbox
