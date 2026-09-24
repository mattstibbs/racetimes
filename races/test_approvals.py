"""Slice 3: the race committee deciding members' requests.

Driven through the Requests page as the committee would, because approving is
where a member's request becomes a change to boats, entries and results.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from races import approvals, audit
from races.models import Boat, BoatRequest, EntryRequest, ScoringChange, SeriesEntry
from races.testing import enter, make_boat, make_committee, make_member, make_race, make_series, record

pytestmark = pytest.mark.django_db


@pytest.fixture
def committee(client):
    user = make_committee()
    client.force_login(user)
    return user


@pytest.fixture
def member():
    return make_member("pat@example.com", first_name="Pat", last_name="Jones")


def decide(client, request, decision, reason="", note=""):
    kind = "entry" if isinstance(request, EntryRequest) else "boat"
    response = client.post(
        reverse("races:decide_request", args=[kind, request.pk]),
        {"decision": decision, "reason": reason, "note": note},
        HTTP_HX_REQUEST="true",
    )
    request.refresh_from_db()
    return response


def registration(member, **fields):
    values = dict(sail_number="GBR42", name="Kittiwake", make="Westerly", model="Centaur",
                  base_number=Decimal("0.805"))
    values.update(fields)
    return BoatRequest.objects.create(kind="REGISTER", requested_by=member, **values)


def change(boat, member, **fields):
    values = {name: getattr(boat, name) for name in BoatRequest.PROPOSED_FIELDS}
    values.update(fields)
    return BoatRequest.objects.create(kind="CHANGE", boat=boat, requested_by=member, **values)


@pytest.fixture
def sailed_series(member):
    """A series with a result recorded, and the member's boat entered in it."""
    series = make_series("Autumn 2026")
    boat = make_boat("GBR42", base_number="0.805", owner=member, name="Kittiwake")
    rival = make_boat("GBR7", base_number="0.900")
    entries = [enter(series, boat), enter(series, rival)]
    race = make_race(series)
    record(race, entries[0], "19:00:00")
    record(race, entries[1], "19:05:00")
    return series, boat


# --- Approving applies exactly what was asked --------------------------------


def test_approving_a_registration_creates_the_boat_owned_by_the_member(client, committee, member):
    request = registration(member)
    response = decide(client, request, "approve")
    boat = Boat.objects.get()
    assert (boat.sail_number, boat.name, boat.base_number, boat.owner) == (
        "GBR42", "Kittiwake", Decimal("0.805"), member,
    )
    assert (request.status, request.decided_by, request.decided_by_name) == (
        "APPROVED", committee, committee.get_username(),
    )
    assert "registered to Pat Jones" in response.content.decode()


def test_approving_a_change_applies_every_requested_field(client, committee, member):
    boat = make_boat("GBR42", owner=member, name="Kittiwake")
    request = change(boat, member, name="Kittiwake II", make="Moody", sail_number="GBR 42A")
    decide(client, request, "approve")
    boat.refresh_from_db()
    assert (boat.name, boat.make, boat.sail_number) == ("Kittiwake II", "Moody", "GBR 42A")


def test_approving_a_claim_makes_the_member_the_owner(client, committee, member):
    boat = make_boat(owner_name="Previous owner")
    request = BoatRequest.objects.create(kind="CLAIM", boat=boat, requested_by=member)
    decide(client, request, "approve")
    boat.refresh_from_db()
    assert boat.owner == member
    assert boat.owner_display == "Pat Jones"


def test_approving_an_entry_enters_the_boat_and_records_it(client, committee, member):
    boat, series = make_boat(owner=member), make_series()
    request = EntryRequest.objects.create(series=series, boat=boat, requested_by=member)
    decide(client, request, "approve")
    assert SeriesEntry.objects.filter(series=series, boat=boat).exists()
    change_row = ScoringChange.objects.get()
    assert (change_row.kind, change_row.action, change_row.user) == ("ENTRY", "ADDED", committee)
    assert not change_row.is_correction  # the series has no results yet


# --- Corrections need a reason, as in the admin -------------------------------


def test_a_base_number_change_in_a_sailed_series_needs_a_reason(client, committee, member, sailed_series):
    series, boat = sailed_series
    request = change(boat, member, base_number=Decimal("0.812"))

    response = decide(client, request, "approve")
    assert audit.REASON_REQUIRED in response.content.decode()
    assert request.status == "PENDING"
    boat.refresh_from_db()
    assert boat.base_number == Decimal("0.805")
    assert not ScoringChange.objects.exists()

    response = decide(client, request, "approve", reason="New RYA certificate")
    boat.refresh_from_db()
    assert boat.base_number == Decimal("0.812")
    change_row = ScoringChange.objects.get()
    assert (change_row.is_correction, change_row.reason, change_row.user, change_row.series) == (
        True, "New RYA certificate", committee, series,
    )
    assert change_row.changes == {"Nhc base number": ["0.805", "0.812"]}
    assert "Autumn 2026:" in response.content.decode()  # says what moved


def test_a_late_entry_into_a_sailed_series_needs_a_reason(client, committee, member, sailed_series):
    series, _ = sailed_series
    late = make_boat("GBR9", owner=member)
    request = EntryRequest.objects.create(series=series, boat=late, requested_by=member)
    decide(client, request, "approve")
    assert request.status == "PENDING"
    decide(client, request, "approve", reason="Entry form arrived late")
    assert SeriesEntry.objects.filter(series=series, boat=late).exists()
    assert ScoringChange.objects.get().reason == "Entry form arrived late"


def test_the_page_asks_for_a_reason_only_where_one_is_needed(client, committee, member, sailed_series):
    _, boat = sailed_series
    change(boat, member, base_number=Decimal("0.812"))
    registration(member, sail_number="GBR77")
    page = client.get(reverse("races:requests")).content.decode()
    assert page.count('name="reason"') == 1


def test_a_detail_change_is_not_a_correction(client, committee, member, sailed_series):
    _, boat = sailed_series
    request = change(boat, member, name="Kittiwake II")
    decide(client, request, "approve")
    assert request.status == "APPROVED"
    assert not ScoringChange.objects.exists()  # a name moves no result


# --- Rejecting ---------------------------------------------------------------


def test_rejecting_needs_a_note_the_member_will_see(client, committee, member):
    request = registration(member)
    response = decide(client, request, "reject")
    assert approvals.NOTE_REQUIRED in response.content.decode()
    assert request.status == "PENDING"
    decide(client, request, "reject", note="Base number does not match the RYA list")
    assert (request.status, request.committee_note) == ("REJECTED", "Base number does not match the RYA list")
    assert not Boat.objects.exists()


# --- Nothing is applied twice, or against a world that has moved on ----------


def test_a_request_is_decided_once(client, committee, member):
    request = registration(member)
    decide(client, request, "approve")
    response = decide(client, request, "approve")
    assert approvals.ALREADY_DECIDED in response.content.decode()
    assert Boat.objects.count() == 1


def test_a_withdrawn_request_cannot_be_approved(client, committee, member):
    request = registration(member)
    approvals.withdraw(request)
    decide(client, request, "approve")
    assert request.status == "WITHDRAWN"
    assert not Boat.objects.exists()


def test_a_registration_whose_sail_number_was_taken_since_is_refused(client, committee, member):
    request = registration(member, sail_number="GBR42")
    make_boat("gbr 42")  # the committee added it in the admin meanwhile
    response = decide(client, request, "approve")
    assert "already registered" in response.content.decode()
    assert request.status == "PENDING"
    assert Boat.objects.count() == 1


def test_an_entry_already_made_in_the_admin_is_refused(client, committee, member):
    boat, series = make_boat(owner=member), make_series()
    request = EntryRequest.objects.create(series=series, boat=boat, requested_by=member)
    enter(series, boat)
    response = decide(client, request, "approve")
    assert "already entered" in response.content.decode()
    assert request.status == "PENDING"


# --- The page ----------------------------------------------------------------


def test_the_requests_page_shows_a_change_old_against_new(client, committee, member):
    boat = make_boat("GBR42", owner=member, name="Kittiwake")
    change(boat, member, name="Kittiwake II", member_note="Renamed her")
    page = client.get(reverse("races:requests")).content.decode()
    assert "Kittiwake II" in page and "Renamed her" in page and "pat@example.com" in page
    assert page.count('class="changed"') == 1
    assert "NHC base number" in page


def test_without_htmx_a_decision_redirects_with_a_message(client, committee, member):
    request = registration(member)
    response = client.post(
        reverse("races:decide_request", args=["boat", request.pk]), {"decision": "approve"}, follow=True
    )
    assert response.redirect_chain[-1][0] == reverse("races:requests")
    assert "registered to Pat Jones" in response.content.decode()
