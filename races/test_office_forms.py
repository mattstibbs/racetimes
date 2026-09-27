"""Slice 18: the race office's forms - boats, series, races and entries: their
rules, history, emails and the final-series locks.

The same rules the admin's boat form had, now tested through the race office's
pages. The admin's own tests stay in races/test_audit.py and elsewhere, since
the admin uses this form too.
"""

from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from races.models import Boat, Race, ScoringChange, Series
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


# --- Series --------------------------------------------------------------------------------


def series_data(series=None, **changes):
    """The series settings form as it stands (or blank for a new one), with changes."""
    data = {"name": "Autumn", "series_type": "CLUB", "discards": "1"}
    data["minimum_finishers"] = "0"
    if series is not None:
        data = {
            "name": series.name,
            "series_type": series.series_type,
            "discards": series.discards,
            "minimum_finishers": series.minimum_finishers,
        }
        for flag in ("apply_a5_3", "nhc_cap_extremes", "nhc_realign_to_base"):
            if getattr(series, flag):
                data[flag] = "on"
    data.update(changes)
    return data


def post_settings(client, series, **changes):
    return client.post(
        reverse("races:office_series_settings", args=[series.pk]),
        series_data(series, **changes),
    )


def test_a_new_series_joins_this_club_with_its_rules(client):
    harbour = make_club("harbour")
    client.force_login(make_committee(club=harbour))
    page = client.get(reverse("races:office_new_series"), HTTP_HOST=HARBOUR)
    assert "Scoring rules" in page.content.decode()
    assert "Reason for change" not in page.content.decode()
    response = client.post(
        reverse("races:office_new_series"),
        series_data(name="Harbour Autumn", discards="2", apply_a5_3="on"),
        HTTP_HOST=HARBOUR,
    )
    series = Series.objects.get(name="Harbour Autumn")
    assert response["Location"] == reverse("races:office_series", args=[series.pk])
    assert (series.club, series.discards, series.apply_a5_3) == (harbour, 2, True)
    assert not ScoringChange.objects.exists()


def test_a_regatta_with_a_finisher_threshold_is_refused(committee_client):
    response = committee_client.post(
        reverse("races:office_new_series"),
        series_data(series_type="REGATTA", minimum_finishers="3"),
    )
    assert "A regatta has no minimum-finisher threshold" in response.content.decode()
    assert not Series.objects.exists()


def test_settings_before_any_result_need_no_reason(committee_client):
    series = make_series("Autumn")
    page = committee_client.get(
        reverse("races:office_series_settings", args=[series.pk])
    ).content.decode()
    assert "Reason for change" not in page
    assert post_settings(committee_client, series, discards="2").status_code == 302
    change = ScoringChange.objects.get()
    assert (change.changes, change.is_correction) == ({"Discards": ["1", "2"]}, False)


def test_settings_after_results_are_a_correction(committee_client, sailed):
    series = sailed["series"]
    response = post_settings(committee_client, series, discards="0")
    assert REASON_REQUIRED in response.content.decode()
    assert Series.objects.get(pk=series.pk).discards == 1
    response = post_settings(
        committee_client, series, discards="0", reason="Notice of race"
    )
    change = ScoringChange.objects.get()
    assert (change.is_correction, change.reason) == (True, "Notice of race")
    response = committee_client.get(response["Location"])
    assert any(
        str(m).startswith("Correction recorded.") for m in response.context["messages"]
    )


def test_a_new_name_moves_no_score_and_is_not_recorded(committee_client, sailed):
    assert post_settings(committee_client, sailed["series"], name="Weds").status_code
    assert Series.objects.get(pk=sailed["series"].pk).name == "Weds"
    assert not ScoringChange.objects.exists()


@pytest.fixture
def final_season(client, committee, season):
    declare(client, season["series"])
    season["series"].refresh_from_db()
    assert season["series"].is_final
    return season


def test_a_final_series_can_be_renamed_but_nothing_else(client, final_season):
    series = final_season["series"]
    response = post_settings(client, series, discards="2", reason="Oops")
    assert "This series is final." in response.content.decode()
    assert Series.objects.get(pk=series.pk).discards == 0
    assert post_settings(client, series, name="Autumn (final)").status_code == 302
    assert Series.objects.get(pk=series.pk).name == "Autumn (final)"


# --- Races ---------------------------------------------------------------------------------


def race_data(race=None, **changes):
    data = {"number": "1", "date": "2026-10-07", "start_time": "18:30:00"}
    if race is not None:
        data = {
            "number": race.number,
            "date": race.date.isoformat(),
            "start_time": race.start_time.strftime("%H:%M:%S"),
        }
    data.update(changes)
    return data


def test_a_new_race_takes_the_next_number(committee_client):
    series = make_series()
    make_race(series, 1)
    make_race(series, 4)
    page = committee_client.get(
        reverse("races:office_new_race", args=[series.pk])
    ).content.decode()
    assert 'name="number" value="5"' in page
    assert "Reason for change" not in page


def test_adding_a_race_is_recorded(committee_client):
    series = make_series()
    response = committee_client.post(
        reverse("races:office_new_race", args=[series.pk]), race_data(number="1")
    )
    assert response["Location"] == reverse("races:office_series", args=[series.pk])
    race = series.races.get()
    assert (race.number, str(race.start_time)) == (1, "18:30:00")
    change = ScoringChange.objects.get()
    assert (change.action, change.is_correction) == ("ADDED", False)


def test_a_race_number_already_used_is_refused(committee_client):
    series = make_series()
    make_race(series, 3)
    race = make_race(series, 4)
    response = committee_client.post(
        reverse("races:office_race", args=[race.pk]), race_data(race, number="3")
    )
    assert "Race 3 already exists in this series." in response.content.decode()
    assert Race.objects.get(pk=race.pk).number == 4


def test_another_series_race_number_is_no_obstacle(committee_client):
    make_race(make_series("Other"), 1)
    series = make_series()
    response = committee_client.post(
        reverse("races:office_new_race", args=[series.pk]), race_data(number="1")
    )
    assert response.status_code == 302


def test_re_timing_a_race_with_results_needs_a_reason(committee_client, sailed):
    race = sailed["series"].races.get()
    url = reverse("races:office_race", args=[race.pk])
    assert "Reason for change" in committee_client.get(url).content.decode()
    response = committee_client.post(url, race_data(race, start_time="18:05:00"))
    assert REASON_REQUIRED in response.content.decode()
    response = committee_client.post(
        url, race_data(race, start_time="18:05:00", reason="Recall")
    )
    assert response.status_code == 302
    change = ScoringChange.objects.get()
    assert (change.is_correction, change.reason, change.race) == (True, "Recall", race)
    assert change.changes == {"Start time": ["18:00:00", "18:05:00"]}


def test_a_start_after_a_saved_finish_is_refused(committee_client, sailed):
    race = sailed["series"].races.get()
    response = committee_client.post(
        reverse("races:office_race", args=[race.pk]),
        race_data(race, start_time="19:06:00", reason="Recall"),
    )
    assert "the start must be earlier" in response.content.decode()


def test_a_race_without_results_is_removed_after_confirming(committee_client):
    series = make_series()
    race = make_race(series, 1)
    url = reverse("races:office_remove_race", args=[race.pk])
    page = committee_client.get(url).content.decode()
    assert "Remove race 1?" in page and "Reason for change" not in page
    assert committee_client.post(url).status_code == 302
    assert not series.races.exists()
    change = ScoringChange.objects.get()
    assert (change.action, change.is_correction) == ("REMOVED", False)


def test_removing_a_race_with_results_needs_a_reason(committee_client, sailed):
    race = sailed["series"].races.get()
    url = reverse("races:office_remove_race", args=[race.pk])
    response = committee_client.post(url)
    assert REASON_REQUIRED in response.content.decode()
    assert Race.objects.filter(pk=race.pk).exists()
    committee_client.post(url, {"reason": "Abandoned"})
    assert not Race.objects.filter(pk=race.pk).exists()
    change = ScoringChange.objects.get()
    assert (change.action, change.is_correction, change.reason) == (
        "REMOVED",
        True,
        "Abandoned",
    )


# --- Entries -------------------------------------------------------------------------------


def test_only_boats_not_yet_entered_are_offered(committee_client, sailed):
    spare = make_boat("GBR5", name="Tern")
    make_boat("GBR6", name="Faraway", club=make_club("harbour"))
    page = committee_client.get(
        reverse("races:office_enter_boats", args=[sailed["series"].pk])
    ).content.decode()
    assert f'value="{spare.pk}"' in page
    assert "Kittiwake" not in page and "Faraway" not in page


def test_entering_boats_records_them_and_emails_their_owners(
    committee_client, run_on_commit
):
    series = make_series("Autumn")
    pat = make_member("pat@example.com")
    boats = [make_boat("GBR1", owner=pat), make_boat("GBR2")]
    response = committee_client.post(
        reverse("races:office_enter_boats", args=[series.pk]),
        {"boat": [boat.pk for boat in boats]},
    )
    assert response.status_code == 302
    assert {entry.boat for entry in series.entries.all()} == set(boats)
    assert ScoringChange.objects.filter(action="ADDED", kind="ENTRY").count() == 2
    [message] = mail.outbox  # the second boat has no owner to tell
    assert message.to == ["pat@example.com"]
    assert "is entered in Autumn" in message.subject


def test_entering_nothing_says_so(committee_client):
    series = make_series()
    make_boat()
    response = committee_client.post(
        reverse("races:office_enter_boats", args=[series.pk]), {}
    )
    assert "Tick at least one boat to enter." in response.content.decode()


def test_another_clubs_boat_cant_be_entered(committee_client):
    series = make_series()
    make_boat("GBR1")
    far = make_boat("GBR2", club=make_club("harbour"))
    committee_client.post(
        reverse("races:office_enter_boats", args=[series.pk]), {"boat": [far.pk]}
    )
    assert not series.entries.exists()


def test_entering_a_boat_once_there_are_results_needs_a_reason(
    committee_client, sailed
):
    spare = make_boat("GBR5")
    url = reverse("races:office_enter_boats", args=[sailed["series"].pk])
    response = committee_client.post(url, {"boat": [spare.pk]})
    assert REASON_REQUIRED in response.content.decode()
    assert f'value="{spare.pk}" checked' in response.content.decode()  # still ticked
    committee_client.post(url, {"boat": [spare.pk], "reason": "Late entry"})
    change = ScoringChange.objects.get()
    assert (change.is_correction, change.reason) == (True, "Late entry")


def test_a_search_keeps_the_boats_already_ticked(committee_client):
    series = make_series()
    tern = make_boat("GBR5", name="Tern")
    make_boat("GBR6", name="Puffin")
    page = committee_client.get(
        reverse("races:office_enter_boats", args=[series.pk]),
        {"q": "puffin", "boat": [tern.pk]},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="boat-choices",
    ).content.decode()
    assert page.startswith('<fieldset id="boat-choices"')
    assert "Puffin" in page and f'value="{tern.pk}" checked' in page


def test_removing_an_entry_emails_the_owner_and_is_recorded(
    committee_client, run_on_commit
):
    series = make_series("Autumn")
    entry = enter(series, make_boat("GBR1", owner=make_member("pat@example.com")))
    url = reverse("races:office_remove_entry", args=[entry.pk])
    assert "Reason for change" not in committee_client.get(url).content.decode()
    committee_client.post(url)
    assert not series.entries.exists()
    assert ScoringChange.objects.get().action == "REMOVED"
    [message] = mail.outbox
    assert message.to == ["pat@example.com"]


def test_an_entry_with_results_cant_be_removed(committee_client, sailed):
    entry = sailed["kittiwake"].series_entries.get()
    response = committee_client.post(
        reverse("races:office_remove_entry", args=[entry.pk]), follow=True
    )
    assert "cannot be removed from this series" in response.content.decode()
    assert "scored DNC" in response.content.decode()
    assert entry.series.entries.count() == 2


def test_removing_an_entry_once_there_are_results_needs_a_reason(
    committee_client, sailed
):
    entry = enter(sailed["series"], make_boat("GBR5"))
    url = reverse("races:office_remove_entry", args=[entry.pk])
    assert REASON_REQUIRED in committee_client.post(url).content.decode()
    committee_client.post(url, {"reason": "Entered by mistake"})
    assert not sailed["series"].entries.filter(pk=entry.pk).exists()
    assert ScoringChange.objects.get().is_correction


# --- A final series can't be changed through any page --------------------------------------


def test_a_final_series_races_and_entries_are_locked(client, final_season):
    series = final_season["series"]
    race = final_season["races"][2]  # never sailed
    entry = final_season["entries"][0]
    spare = make_boat("GBR5")
    before = (
        list(series.races.values_list("pk", "number", "start_time")),
        list(series.entries.values_list("pk", flat=True)),
        ScoringChange.objects.count(),
    )
    attempts = [
        ("races:office_new_race", series.pk, race_data(number="9")),
        ("races:office_race", race.pk, race_data(race, start_time="18:10:00")),
        ("races:office_remove_race", race.pk, {"reason": "x"}),
        ("races:office_enter_boats", series.pk, {"boat": [spare.pk], "reason": "x"}),
        ("races:office_remove_entry", entry.pk, {"reason": "x"}),
    ]
    for name, pk, data in attempts:
        for response in (
            client.get(reverse(name, args=[pk])),
            client.post(reverse(name, args=[pk]), data),
        ):
            assert response["Location"] == reverse(
                "races:office_series", args=[series.pk]
            ), name
    after = (
        list(series.races.values_list("pk", "number", "start_time")),
        list(series.entries.values_list("pk", flat=True)),
        ScoringChange.objects.count(),
    )
    assert after == before


def test_a_race_form_open_when_the_series_became_final_is_refused(
    client, committee, season
):
    race = season["races"][2]
    form_data = race_data(race, start_time="18:10:00")
    declare(client, season["series"])
    from races.office_forms import RaceForm

    form = RaceForm(form_data, instance=race, series=season["series"])
    assert not form.is_valid()
    assert "This series is final." in str(form.errors)


# --- Deleting a series ---------------------------------------------------------------------


def test_a_series_without_results_is_deleted_after_confirming(
    committee_client, run_on_commit
):
    series = make_series("Autumn")
    make_race(series, 1)
    enter(series, make_boat("GBR1", owner=make_member("pat@example.com")))
    url = reverse("races:office_delete_series", args=[series.pk])
    page = committee_client.get(url).content.decode()
    assert "Delete Autumn?" in page and "1 race and\n  1 entry" in page
    response = committee_client.post(url)
    assert response["Location"] == reverse("races:office")
    assert not Series.objects.exists() and not Race.objects.exists()
    [message] = mail.outbox
    assert message.to == ["pat@example.com"]


def test_a_series_with_results_cant_be_deleted(committee_client, sailed):
    series = sailed["series"]
    for method in (committee_client.get, committee_client.post):
        response = method(reverse("races:office_delete_series", args=[series.pk]))
        assert response["Location"] == reverse("races:office_series", args=[series.pk])
    assert Series.objects.filter(pk=series.pk).exists()
