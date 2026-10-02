"""Slice 24, part B: choosing a handicap system, and the numbers boats race on.

A series is scored under NHC or Portsmouth Yardstick. A boat has an NHC base
number, a Portsmouth Number, or both, and needs the number of every series it is
entered in. These tests are the rules, through the race office's pages, the
admin, and members' requests, and what the change history records.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from races import audit
from races.models import (
    Boat,
    BoatRequest,
    EntryRequest,
    ScoringChange,
    Series,
    SeriesEntry,
)
from races.scoring import score_series
from races.testing import (
    boat_form,
    decide,
    declare,
    enter,
    finish_clock,
    make_boat,
    make_committee,
    make_member,
    make_py_series,
    make_race,
    make_series,
    post_boat,
    post_series,
    publish,
    record,
    series_form,
)
from tests.scenario_loader import PORTSMOUTH_YARDSTICK_FIXTURE

pytestmark = pytest.mark.django_db

PY_1 = PORTSMOUTH_YARDSTICK_FIXTURE["PY-1"]
REASON_REQUIRED = "give a reason for the correction"


# --- Helpers ---------------------------------------------------------------------------------


def settings_data(series=None, **changes):
    """The race office's series settings form as it stands, or blank, with changes."""
    data = {
        "name": "Autumn",
        "handicap_system": "NHC",
        "series_type": "CLUB",
        "discards": "1",
        "discard_threshold": "0",
        "minimum_finishers": "0",
    }
    if series is not None:
        data = {
            "name": series.name,
            "handicap_system": series.handicap_system,
            "series_type": series.series_type,
            "discards": series.discards,
            "discard_threshold": series.discard_threshold,
            "minimum_finishers": series.minimum_finishers,
        }
        for flag in ("apply_a5_3", "nhc_cap_extremes", "nhc_realign_to_base"):
            if getattr(series, flag):
                data[flag] = "on"
    data.update(changes)
    return data


def office_settings(client, series, **changes):
    return client.post(
        reverse("races:office_series_settings", args=[series.pk]),
        settings_data(series, **changes),
    )


def office_new_series(client, **changes):
    return client.post(reverse("races:office_new_series"), settings_data(**changes))


def office_boat(client, boat, **changes):
    return client.post(
        reverse("races:office_boat", args=[boat.pk]), boat_form(boat, **changes)
    )


def office_enter(client, series, boats, **extra):
    return client.post(
        reverse("races:office_enter_boats", args=[series.pk]),
        {"boat": [boat.pk for boat in boats], **extra},
    )


def history(series=None):
    rows = ScoringChange.objects.all()
    return rows.filter(series=series) if series is not None else rows


@pytest.fixture
def py_boats():
    """Three boats with only a Portsmouth Number, and one with only a base number."""
    return {
        "swift": make_boat("PY1", base_number=None, py_number=1010, name="Swift"),
        "dart": make_boat("PY2", base_number=None, py_number=1072, name="Dart"),
        "nhc": make_boat("N1", base_number="0.950", name="Nhc Only"),
        "both": make_boat("B1", base_number="0.930", py_number=1000, name="Both"),
    }


# --- Choosing the system for a series ------------------------------------------------------


def test_a_new_series_is_nhc_by_default():
    assert make_series().handicap_system == Series.HandicapSystem.NHC


def test_the_race_office_can_start_a_portsmouth_yardstick_series(committee_client):
    response = office_new_series(committee_client, name="Gaffers", handicap_system="PY")
    series = Series.objects.get(name="Gaffers")
    assert response.status_code == 302
    assert series.handicap_system == "PY" and series.is_fixed_number
    assert not history()  # a new series moves nothing


def test_the_settings_page_offers_the_choice(committee_client):
    page = committee_client.get(reverse("races:office_new_series")).content.decode()
    assert 'name="handicap_system"' in page
    assert "RYA NHC" in page and "Portsmouth Yardstick" in page


def test_a_portsmouth_series_cant_be_a_regatta(committee_client):
    response = office_new_series(
        committee_client, handicap_system="PY", series_type="REGATTA"
    )
    assert "must be a club series" in response.content.decode()
    assert not Series.objects.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("minimum_finishers", "3", "nothing for this to apply to"),
        ("nhc_cap_extremes", "on", "This is an NHC option"),
        ("nhc_realign_to_base", "on", "This is an NHC option"),
    ],
)
def test_nhc_only_settings_are_refused_on_a_portsmouth_series(
    committee_client, field, value, message
):
    response = office_new_series(
        committee_client, handicap_system="PY", **{field: value}
    )
    assert message in response.content.decode()
    assert not Series.objects.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("minimum_finishers", "3"),
        ("nhc_cap_extremes", "on"),
        ("nhc_realign_to_base", "on"),
    ],
)
def test_the_same_settings_are_fine_on_an_nhc_series(committee_client, field, value):
    assert office_new_series(committee_client, **{field: value}).status_code == 302


def test_the_discards_and_a5_3_are_shared_by_both_systems(committee_client):
    response = office_new_series(
        committee_client,
        handicap_system="PY",
        discards="2",
        discard_threshold="4",
        apply_a5_3="on",
    )
    series = Series.objects.get()
    assert response.status_code == 302
    assert (series.discards, series.discard_threshold, series.apply_a5_3) == (
        2,
        4,
        True,
    )


def test_the_admin_refuses_the_same_combinations(staff_client):
    series = make_series("Gaffers")
    response = post_series(
        staff_client, series, handicap_system="PY", series_type="REGATTA"
    )
    assert "must be a club series" in response.content.decode()
    assert Series.objects.get().handicap_system == "NHC"
    response = post_series(
        staff_client, series, handicap_system="PY", nhc_cap_extremes="on"
    )
    assert "This is an NHC option" in response.content.decode()


# --- Switching a series with boats ---------------------------------------------------------------


def test_switching_to_portsmouth_is_refused_while_a_boat_has_no_pn_and_names_it(
    committee_client, py_boats
):
    series = make_series("Autumn")
    for key in ("both", "nhc"):
        enter(series, py_boats[key])
    response = office_settings(committee_client, series, handicap_system="PY")
    page = response.content.decode()
    assert response.status_code == 200
    assert "These boats have no Portsmouth Number (PN)" in page
    assert "Nhc Only (N1)" in page and "Both (B1)" not in page
    assert Series.objects.get().handicap_system == "NHC"
    assert not history()


def test_switching_to_portsmouth_works_when_every_boat_has_a_pn(
    committee_client, py_boats
):
    series = make_series("Autumn")
    for key in ("both", "swift"):
        enter(series, py_boats[key])
    assert (
        office_settings(committee_client, series, handicap_system="PY").status_code
        == 302
    )
    assert Series.objects.get().handicap_system == "PY"


def test_switching_back_to_nhc_needs_base_numbers(committee_client, py_boats):
    series = make_series("Gaffers", handicap_system="PY")
    for key in ("both", "swift"):
        enter(series, py_boats[key])
    response = office_settings(committee_client, series, handicap_system="NHC")
    assert "These boats have no NHC base number" in response.content.decode()
    assert "Swift (PY1)" in response.content.decode()
    assert Series.objects.get().handicap_system == "PY"


def test_switching_systems_before_any_result_needs_no_reason(
    committee_client, py_boats
):
    series = make_series("Autumn")
    enter(series, py_boats["both"])
    page = committee_client.get(
        reverse("races:office_series_settings", args=[series.pk])
    ).content.decode()
    assert "Reason for change" not in page
    response = office_settings(committee_client, series, handicap_system="PY")
    assert response.status_code == 302
    # Recorded, but not a correction: nothing has fed through it yet.
    [change] = history(series)
    assert not change.is_correction
    assert change.changes == {"Handicap system": ["RYA NHC", "Portsmouth Yardstick"]}


def test_switching_systems_after_results_is_a_correction_and_needs_a_reason(
    committee_client,
):
    series, _, _ = make_py_series(PY_1)
    # Every boat has a base number too, so the switch itself is allowed.
    Boat.objects.update(base_number="0.950")
    refused = office_settings(committee_client, series, handicap_system="NHC")
    assert REASON_REQUIRED in refused.content.decode()
    assert Series.objects.get().handicap_system == "PY"
    assert not history()

    accepted = office_settings(
        committee_client,
        series,
        handicap_system="NHC",
        reason="Entered under the wrong system",
    )
    assert accepted.status_code == 302
    assert Series.objects.get().handicap_system == "NHC"
    [change] = history(series)
    assert change.is_correction and change.kind == "SERIES"
    assert change.changes == {"Handicap system": ["Portsmouth Yardstick", "RYA NHC"]}
    assert change.reason == "Entered under the wrong system"


def test_saving_a_series_without_changing_its_system_records_nothing(
    committee_client,
):
    series, _, _ = make_py_series(PY_1)
    response = office_settings(committee_client, series, name="Portsmouth, renamed")
    assert response.status_code == 302
    assert not history()


def test_a_final_series_cannot_have_its_system_changed(committee_client):
    series, _, races = make_py_series(PY_1)
    Boat.objects.update(base_number="0.950")
    publish(*races)
    declare(committee_client, series)
    response = office_settings(committee_client, series, handicap_system="NHC")
    assert "This series is final" in response.content.decode()
    assert Series.objects.get().handicap_system == "PY"


def test_the_system_is_recorded_when_the_admin_changes_it(staff_client):
    series, _, _ = make_py_series(PY_1)
    Boat.objects.update(base_number="0.950")
    post_series(staff_client, series, handicap_system="NHC", reason="Wrong system")
    [change] = history(series)
    assert change.changes == {"Handicap system": ["Portsmouth Yardstick", "RYA NHC"]}


# --- A boat's numbers -------------------------------------------------------------------------


def add_boat(client, **fields):
    data = boat_form(Boat(sail_number="GBR8", base_number="0.9"))
    data.update(fields)
    return client.post(reverse("races:office_new_boat"), data)


def test_a_boat_needs_at_least_one_number(committee_client):
    response = add_boat(committee_client, base_number="", py_number="")
    assert "needs a number to race on" in response.content.decode()
    assert not Boat.objects.exists()


def test_a_boat_may_be_added_with_only_a_portsmouth_number(committee_client):
    response = add_boat(committee_client, base_number="", py_number="1072")
    boat = Boat.objects.get()
    assert response.status_code == 302
    assert boat.base_number is None and boat.py_number == 1072


def test_a_boat_may_have_both_numbers(committee_client):
    add_boat(committee_client, base_number="0.964", py_number="1072")
    boat = Boat.objects.get()
    assert (str(boat.base_number), boat.py_number) == ("0.964", 1072)


@pytest.mark.parametrize("value", ["0", "10000", "-3", "1072.5", "abc"])
def test_a_portsmouth_number_is_a_whole_number_from_1_to_9999(committee_client, value):
    response = add_boat(committee_client, base_number="", py_number=value)
    assert response.status_code == 200
    assert not Boat.objects.exists()


@pytest.mark.parametrize("value", ["1", "935", "9999"])
def test_the_ends_of_the_range_are_fine(committee_client, value):
    assert (
        add_boat(committee_client, base_number="", py_number=value).status_code == 302
    )


def test_the_boat_list_shows_both_numbers(committee_client, py_boats):
    page = committee_client.get(reverse("races:office_boats")).content.decode()
    assert '<th class="num">PN</th>' in page
    assert '<td class="num">1072</td>' in page
    assert '<td class="num">0.950</td>' in page


def test_a_pn_cant_be_removed_while_a_portsmouth_series_uses_it(
    committee_client, py_boats
):
    series = make_series("Gaffers", handicap_system="PY")
    enter(series, py_boats["both"])
    response = office_boat(committee_client, py_boats["both"], py_number="")
    page = response.content.decode()
    assert response.status_code == 200
    assert "can&#x27;t be removed while the boat is entered" in page
    assert "Gaffers" in page
    assert Boat.objects.get(pk=py_boats["both"].pk).py_number == 1000
    assert not history()


def test_a_pn_can_be_removed_when_no_portsmouth_series_uses_it(
    committee_client, py_boats
):
    nhc_series = make_series("Autumn")
    enter(nhc_series, py_boats["both"])
    assert (
        office_boat(committee_client, py_boats["both"], py_number="").status_code == 302
    )
    assert Boat.objects.get(pk=py_boats["both"].pk).py_number is None


def test_a_base_number_cant_be_removed_while_an_nhc_series_uses_it(
    committee_client, py_boats
):
    series = make_series("Autumn")
    enter(series, py_boats["both"])
    response = office_boat(committee_client, py_boats["both"], base_number="")
    assert "NHC base number can&#x27;t be removed" in response.content.decode()
    assert Boat.objects.get(pk=py_boats["both"].pk).base_number is not None


def test_removing_the_only_number_is_refused(committee_client, py_boats):
    response = office_boat(committee_client, py_boats["swift"], py_number="")
    assert "needs a number to race on" in response.content.decode()


def test_the_admin_refuses_clearing_a_number_a_series_uses(staff_client, py_boats):
    series = make_series("Gaffers", handicap_system="PY")
    enter(series, py_boats["both"])
    response = post_boat(staff_client, py_boats["both"], py_number="")
    assert (
        "can&#x27;t be removed while the boat is entered" in response.content.decode()
    )
    assert Boat.objects.get(pk=py_boats["both"].pk).py_number == 1000


# --- Entering boats ---------------------------------------------------------------------------


def test_the_entry_itself_refuses_a_boat_with_no_number(py_boats):
    """The forms above check first; this is the layer under them, for any other
    code that validates an entry."""
    gaffers = make_series("Gaffers", handicap_system="PY")
    autumn = make_series("Autumn")
    with pytest.raises(ValidationError, match=r"has no Portsmouth Number \(PN\)"):
        SeriesEntry(series=gaffers, boat=py_boats["nhc"]).full_clean()
    with pytest.raises(ValidationError, match="has no NHC base number"):
        SeriesEntry(series=autumn, boat=py_boats["swift"]).full_clean()
    SeriesEntry(series=gaffers, boat=py_boats["swift"]).full_clean()
    SeriesEntry(series=autumn, boat=py_boats["nhc"]).full_clean()
    SeriesEntry(series=gaffers, boat=py_boats["both"]).full_clean()
    SeriesEntry(series=autumn, boat=py_boats["both"]).full_clean()


def test_the_office_refuses_to_enter_a_boat_with_no_pn_and_names_it(
    committee_client, py_boats
):
    series = make_series("Gaffers", handicap_system="PY")
    response = office_enter(
        committee_client, series, [py_boats["swift"], py_boats["nhc"]]
    )
    page = response.content.decode()
    assert response.status_code == 200
    assert "Nhc Only (N1) has no Portsmouth Number (PN)" in page
    assert "Swift (PY1) has no" not in page  # only the boat that lacks it is named
    assert not SeriesEntry.objects.exists()  # nothing is entered, not even the good one


def test_the_office_names_every_boat_that_lacks_the_number(committee_client, py_boats):
    series = make_series("Gaffers", handicap_system="PY")
    spare = make_boat("N2", base_number="0.800", name="Spare")
    page = office_enter(
        committee_client, series, [py_boats["nhc"], spare]
    ).content.decode()
    assert "Nhc Only (N1), Spare (N2) have no Portsmouth Number (PN)" in page


def test_the_enter_boats_list_says_why_a_boat_cant_be_ticked(
    committee_client, py_boats
):
    series = make_series("Gaffers", handicap_system="PY")
    page = committee_client.get(
        reverse("races:office_enter_boats", args=[series.pk])
    ).content.decode()
    # Boats with a PN can be ticked; the NHC-only boat is listed, disabled, with why.
    assert f'value="{py_boats["swift"].pk}"' in page
    assert f'value="{py_boats["both"].pk}"' in page
    assert f'value="{py_boats["nhc"].pk}"' not in page
    assert "Nhc Only (N1) <span" in page and "has no Portsmouth Number (PN)" in page
    assert '<input type="checkbox" disabled>' in page


def test_an_nhc_series_lists_every_boat_as_tickable_that_has_a_base_number(
    committee_client, py_boats
):
    series = make_series("Autumn")
    page = committee_client.get(
        reverse("races:office_enter_boats", args=[series.pk])
    ).content.decode()
    assert f'value="{py_boats["nhc"].pk}"' in page
    assert f'value="{py_boats["both"].pk}"' in page
    assert f'value="{py_boats["swift"].pk}"' not in page
    assert "Swift (PY1) <span" in page and "has no NHC base number" in page


def test_the_office_enters_boats_that_have_the_number(committee_client, py_boats):
    series = make_series("Gaffers", handicap_system="PY")
    response = office_enter(
        committee_client, series, [py_boats["swift"], py_boats["both"]]
    )
    assert response.status_code == 302
    assert SeriesEntry.objects.filter(series=series).count() == 2


def test_a_pn_only_boat_cant_be_entered_in_an_nhc_series(committee_client, py_boats):
    series = make_series("Autumn")
    response = office_enter(committee_client, series, [py_boats["swift"]])
    assert "has no NHC base number, which this RYA NHC series needs" in (
        response.content.decode()
    )
    assert not SeriesEntry.objects.exists()


def test_the_admin_refuses_an_entry_with_no_pn_on_the_change_page(
    staff_client, py_boats
):
    series = make_series("Gaffers", handicap_system="PY")
    data = series_form(series)
    data.update(
        {
            "entries-TOTAL_FORMS": 1,
            "entries-INITIAL_FORMS": 0,
            "entries-0-boat": py_boats["nhc"].pk,
            "entries-0-series": series.pk,
        }
    )
    response = staff_client.post(
        reverse("admin:races_series_change", args=[series.pk]), data
    )
    assert "has no Portsmouth Number (PN)" in response.content.decode()
    assert not SeriesEntry.objects.exists()


def test_the_admin_refuses_it_on_the_add_page_too(staff_client, py_boats):
    """The new series isn't saved yet, so the entry can't see it: the formset does."""
    data = {
        "name": "New gaffers",
        "handicap_system": "PY",
        "series_type": "CLUB",
        "discards": 1,
        "discard_threshold": 0,
        "minimum_finishers": 0,
        "reason": "",
        "entries-TOTAL_FORMS": 1,
        "entries-INITIAL_FORMS": 0,
        "entries-MIN_NUM_FORMS": 0,
        "entries-MAX_NUM_FORMS": 1000,
        "entries-0-boat": py_boats["nhc"].pk,
        "races-TOTAL_FORMS": 0,
        "races-INITIAL_FORMS": 0,
        "races-MIN_NUM_FORMS": 0,
        "races-MAX_NUM_FORMS": 1000,
    }
    response = staff_client.post(reverse("admin:races_series_add"), data)
    assert "has no Portsmouth Number (PN)" in response.content.decode()
    assert not Series.objects.exists()
    data["entries-0-boat"] = py_boats["swift"].pk
    staff_client.post(reverse("admin:races_series_add"), data)
    assert SeriesEntry.objects.get().boat == py_boats["swift"]


# --- Members' requests ----------------------------------------------------------------------------


@pytest.fixture
def member(client):
    person = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    client.force_login(person)
    return person


@pytest.fixture
def office():
    """The race committee on a client of its own: ``client`` is the member's here."""
    committee = Client()
    committee.force_login(make_committee())
    return committee


def request_form(**fields):
    data = {
        "sail_number": "GBR 7",
        "name": "Tern",
        "make": "",
        "model": "",
        "length_overall_m": "",
        "waterline_length_m": "",
        "base_number": "",
        "py_number": "",
        "member_note": "",
    }
    data.update(fields)
    return data


def test_a_member_can_register_a_boat_with_only_a_portsmouth_number(client, member):
    response = client.post(
        reverse("races:register_boat"), request_form(py_number="1072")
    )
    request = BoatRequest.objects.get()
    assert response.status_code == 302
    assert request.py_number == 1072 and request.base_number is None


def test_a_member_must_give_one_number_to_register_a_boat(client, member):
    response = client.post(reverse("races:register_boat"), request_form())
    assert "Give your boat&#x27;s NHC base number, its Portsmouth Number, or both" in (
        response.content.decode()
    )
    assert not BoatRequest.objects.exists()


def test_approving_a_registration_gives_the_boat_its_portsmouth_number(
    client, office, member
):
    client.post(reverse("races:register_boat"), request_form(py_number="1072"))
    request = BoatRequest.objects.get()
    decide(office, request, "approve")
    boat = Boat.objects.get()
    assert (boat.sail_number, boat.py_number, boat.base_number) == ("GBR 7", 1072, None)
    assert boat.owner == member


def test_a_member_can_ask_to_add_a_portsmouth_number_to_a_boat(client, office, member):
    boat = make_boat("GBR42", owner=member, base_number="0.805")
    form = boat_form(boat, py_number="1050")
    form["member_note"] = ""
    client.post(reverse("races:change_boat", args=[boat.pk]), form)
    request = BoatRequest.objects.get()
    assert request.py_number == 1050 and not Boat.objects.get().py_number
    decide(office, request, "approve")
    boat.refresh_from_db()
    assert boat.py_number == 1050 and str(boat.base_number) == "0.805"


def test_the_requests_page_shows_the_proposed_portsmouth_number(client, office, member):
    client.post(reverse("races:register_boat"), request_form(py_number="1072"))
    page = office.get(reverse("races:requests")).content.decode()
    assert "Portsmouth Number (PN)" in page and "1072" in page


def test_a_member_cant_ask_to_enter_a_series_their_boat_has_no_number_for(
    client, member
):
    boat = make_boat("GBR42", owner=member, base_number="0.805")
    series = make_series("Gaffers", handicap_system="PY")
    response = client.post(
        reverse("races:enter_series", args=[boat.pk]),
        {"series": series.pk, "member_note": ""},
    )
    page = response.content.decode()
    assert (
        "has no Portsmouth Number (PN), which this Portsmouth Yardstick series" in page
    )
    assert "change to your boat" in page
    assert not EntryRequest.objects.exists()


def test_an_entry_request_for_a_boat_with_the_number_is_approved(
    client, office, member
):
    boat = make_boat("GBR42", owner=member, base_number=None, py_number=1050)
    series = make_series("Gaffers", handicap_system="PY")
    client.post(
        reverse("races:enter_series", args=[boat.pk]),
        {"series": series.pk, "member_note": ""},
    )
    request = EntryRequest.objects.get()
    decide(office, request, "approve")
    assert request.status == "APPROVED"
    assert SeriesEntry.objects.get().boat == boat


def test_approval_is_refused_if_the_number_was_removed_after_the_request(
    client, office, member
):
    boat = make_boat("GBR42", owner=member, base_number="0.805", py_number=1050)
    series = make_series("Gaffers", handicap_system="PY")
    client.post(
        reverse("races:enter_series", args=[boat.pk]),
        {"series": series.pk, "member_note": ""},
    )
    Boat.objects.filter(pk=boat.pk).update(py_number=None)
    request = EntryRequest.objects.get()
    response = decide(office, request, "approve")
    assert request.status == "PENDING"  # still waiting, nothing half-done
    assert "has no Portsmouth Number (PN)" in response.content.decode()
    assert not SeriesEntry.objects.exists()


def test_approval_of_an_entry_says_so_before_asking_for_a_reason(office, member):
    """With results recorded, approving would normally ask for a reason; a
    refusal that can never succeed is said first."""
    series, _, _ = make_py_series(PY_1)
    boat = make_boat("GBR42", owner=member, base_number="0.805")
    request = EntryRequest.objects.create(series=series, boat=boat, requested_by=member)
    response = decide(office, request, "approve")
    page = response.content.decode()
    assert "has no Portsmouth Number (PN)" in page
    assert REASON_REQUIRED not in page


# --- The change history -----------------------------------------------------------------------------


def test_a_pn_change_is_recorded_in_the_portsmouth_series_it_feeds(committee_client):
    series, entries, _ = make_py_series(PY_1)
    boat = entries["B"].boat
    office_boat(committee_client, boat, py_number="1050", reason="New certificate")
    [change] = history(series)
    assert change.kind == "BOAT" and change.is_correction
    assert change.changes == {"Portsmouth Number (PN)": ["1072", "1050"]}
    assert change.reason == "New certificate"


def test_a_pn_change_after_results_needs_a_reason(committee_client):
    _, entries, _ = make_py_series(PY_1)
    boat = entries["B"].boat
    response = office_boat(committee_client, boat, py_number="1050")
    assert REASON_REQUIRED in response.content.decode()
    assert Boat.objects.get(pk=boat.pk).py_number == 1072
    assert not history()


def test_a_pn_change_rescores_the_series_and_says_what_moved(committee_client):
    series, entries, _ = make_py_series(PY_1)
    boat = entries["B"].boat
    # B won race 1 at PN 1072 (corrected 3871.269). At PN 900 her corrected time
    # is 4150 x 1000 / 900 = 4611.1, behind everyone, and in race 2 behind C.
    response = office_boat(committee_client, boat, py_number="900", reason="Typo")
    assert response.status_code == 302
    page = committee_client.get(response["Location"]).content.decode()
    assert "Places changed in races 1-2." in page
    assert "andicaps changed" not in page
    first = score_series(series).races[0].for_entry(entries["B"])
    assert first.result.position == 3 and first.raced_on == 900


def test_a_correction_in_a_portsmouth_series_never_says_handicaps_moved():
    series, entries, _ = make_py_series(PY_1)
    before = score_series(series)
    boat = entries["B"].boat
    Boat.objects.filter(pk=boat.pk).update(py_number=900)
    effect = audit.describe_effect(before, score_series(series))
    assert "Places changed in races 1-2." in effect
    assert "andicap" not in effect
    assert audit.compare(before, score_series(series)).handicaps == []


def test_a_change_that_moves_nothing_says_so_without_mentioning_handicaps():
    series, _, _ = make_py_series(PY_1)
    scored = score_series(series)
    assert audit.describe_effect(scored, scored) == (
        "No places or standings were affected by this change."
    )


def test_an_nhc_series_keeps_its_wording():
    series = make_series()
    race = make_race(series, start="18:30:00")
    entry = enter(series, make_boat("GBR1", base_number="0.964"))
    record(race, entry, finish_clock("18:30:00", 3600))
    scored = score_series(series)
    assert audit.describe_effect(scored, scored) == (
        "No places, handicaps, or standings were affected by this change."
    )


def test_a_base_number_change_is_not_recorded_in_a_portsmouth_series(
    committee_client, py_boats
):
    nhc_series = make_series("Autumn")
    py_series = make_series("Gaffers", handicap_system="PY")
    both = py_boats["both"]
    enter(nhc_series, both)
    enter(py_series, both)
    office_boat(committee_client, both, base_number="0.900")
    assert history(py_series).count() == 0
    [change] = history(nhc_series)
    assert change.changes == {"NHC base number": ["0.930", "0.900"]}


def test_each_series_gets_only_the_number_it_is_scored_on(committee_client, py_boats):
    nhc_series = make_series("Autumn")
    py_series = make_series("Gaffers", handicap_system="PY")
    both = py_boats["both"]
    enter(nhc_series, both)
    enter(py_series, both)
    office_boat(committee_client, both, base_number="0.900", py_number="1010")
    [nhc_change] = history(nhc_series)
    [py_change] = history(py_series)
    assert list(nhc_change.changes) == ["NHC base number"]
    assert list(py_change.changes) == ["Portsmouth Number (PN)"]


def test_a_number_no_series_uses_is_still_recorded_for_the_club(
    committee_client, py_boats
):
    series = make_series("Autumn")  # NHC: doesn't use the PN
    both = py_boats["both"]
    enter(series, both)
    office_boat(committee_client, both, py_number="1010")
    [change] = history()
    assert change.series is None
    assert change.changes == {"Portsmouth Number (PN)": ["1000", "1010"]}
    assert not change.is_correction


def test_a_pn_change_needs_no_reason_for_a_boat_only_in_an_nhc_series_with_results(
    committee_client,
):
    """The reason box shows (the boat has results somewhere), but a PN moves no
    NHC result, so it isn't a correction and isn't demanded."""
    series = make_series("Autumn")
    race = make_race(series, start="18:30:00")
    boat = make_boat("GBR1", base_number="0.964", py_number=1000)
    record(race, enter(series, boat), finish_clock("18:30:00", 3600))
    assert office_boat(committee_client, boat, py_number="1010").status_code == 302
    assert Boat.objects.get(pk=boat.pk).py_number == 1010


def test_a_boat_in_no_series_records_a_number_change_for_the_club(
    committee_client, py_boats
):
    office_boat(committee_client, py_boats["swift"], py_number="1020")
    [change] = history()
    assert change.series is None and not change.is_correction


def test_both_new_fields_are_among_the_audited_ones():
    assert "handicap_system" in audit.AUDITED_FIELDS[Series]
    assert "py_number" in audit.AUDITED_FIELDS[Boat]
