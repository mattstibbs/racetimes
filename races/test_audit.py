"""Slice 2: the history of changes to anything that feeds a score.

Organised by acceptance criterion. Changes are made the way the committee
makes them - through the finish-entry page and the admin - because a place
that saves a score-affecting value without recording it is exactly the gap
these tests exist to find.
"""

from datetime import datetime, time, timedelta

import pytest
from django.db import IntegrityError
from django.urls import reverse

from races import audit
from races.models import Boat, Finish, Race, ScoringChange, Series
from races.scoring import score_series
from races.testing import default_club, join, enter, make_boat, make_race, make_series, record, start

pytestmark = pytest.mark.django_db

REASON_REQUIRED = "give a reason for the correction"


@pytest.fixture
def staff_user(django_user_model):
    # The superuser is Demo Club's administrator, as the slice 11 migration makes it.
    user = django_user_model.objects.create_user("officer", is_staff=True, is_superuser=True)
    join(user, default_club(), role="ADMINISTRATOR")
    return user


@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def sailed():
    """Three boats, four races, every finish recorded."""
    series = make_series("Wednesday Evenings")
    entries = [
        enter(series, make_boat("GBR1", name="Serendipity", base_number="0.950")),
        enter(series, make_boat("GBR2", name="Blue Moon", base_number="0.900")),
        enter(series, make_boat("GBR3", name="Kestrel", base_number="1.000")),
    ]
    finishes = [
        ["19:00:00", "19:04:00", "18:58:00"],
        ["19:01:00", "19:02:00", "19:00:30"],
        ["18:59:00", "19:05:00", "19:01:00"],
        ["19:02:00", "19:03:00", "18:59:30"],
    ]
    races = []
    for number, times in enumerate(finishes, start=1):
        race = make_race(series, number, start="18:00:00")
        for entry, finish_time in zip(entries, times):
            record(race, entry, finish_time)
        races.append(race)
    return series, races, entries


@pytest.fixture
def unsailed():
    """A series set up but with no finishes recorded yet; the boat is on the start sheet."""
    series = make_series("Spring")
    entry = enter(series, make_boat("GBR1", name="Serendipity"))
    race = make_race(series, 1)
    start(race, entry)
    return series, race, entry


def save_finish(client, race, entry, finish_time="", status="FINISHED", reason=""):
    prefix = f"entry-{entry.pk}"
    return client.post(
        reverse("races:save_finish", args=[race.pk, entry.pk]),
        {
            f"{prefix}-finish_time": finish_time,
            f"{prefix}-status": status,
            f"{prefix}-reason": reason,
        },
        HTTP_HX_REQUEST="true",
    )


def series_form(series, **changes):
    """The series admin form as it stands, with ``changes`` applied on top."""
    data = {
        "name": series.name,
        "series_type": series.series_type,
        "discards": series.discards,
        "minimum_finishers": series.minimum_finishers,
        "reason": "",
    }
    for flag in ("apply_a5_3", "nhc_cap_extremes", "nhc_realign_to_base"):
        if getattr(series, flag):
            data[flag] = "on"
    entries = list(series.entries.all())
    races = list(series.races.all())
    for prefix, rows in [("entries", entries), ("races", races)]:
        data[f"{prefix}-TOTAL_FORMS"] = len(rows)
        data[f"{prefix}-INITIAL_FORMS"] = len(rows)
        data[f"{prefix}-MIN_NUM_FORMS"] = 0
        data[f"{prefix}-MAX_NUM_FORMS"] = 1000
    for i, entry in enumerate(entries):
        data.update({f"entries-{i}-id": entry.pk, f"entries-{i}-series": series.pk,
                     f"entries-{i}-boat": entry.boat_id})
    for i, race in enumerate(races):
        data.update({f"races-{i}-id": race.pk, f"races-{i}-series": series.pk,
                     f"races-{i}-number": race.number, f"races-{i}-date": race.date.isoformat(),
                     f"races-{i}-start_time": race.start_time.strftime("%H:%M:%S")})
    data.update(changes)
    return data


def post_series(client, series, **changes):
    return client.post(
        reverse("admin:races_series_change", args=[series.pk]), series_form(series, **changes)
    )


def boat_form(boat, **changes):
    data = {"sail_number": boat.sail_number, "name": boat.name, "make": boat.make,
            "model": boat.model, "owner_name": boat.owner_name, "length_overall_m": "",
            "waterline_length_m": "", "base_number": str(boat.base_number), "reason": ""}
    data.update(changes)
    return data


def post_boat(client, boat, **changes):
    return client.post(reverse("admin:races_boat_change", args=[boat.pk]), boat_form(boat, **changes))


def only_change():
    [change] = ScoringChange.objects.all()
    return change


# --- Every audited change is recorded, with old and new, who and when --------


def test_correcting_a_finish_records_old_new_who_and_reason(staff_client, staff_user, sailed):
    series, races, entries = sailed
    save_finish(staff_client, races[1], entries[0], "19:11:00", reason="Misread the sheet")
    change = only_change()
    assert (change.kind, change.action) == ("FINISH", "CHANGED")
    assert change.changes == {"Finish time": ["19:01:00", "19:11:00"]}
    assert change.user == staff_user and change.user_name == "officer"
    assert change.reason == "Misread the sheet"
    assert change.is_correction
    assert change.series == series and change.race == races[1]
    assert change.description == "GBR1 Serendipity, Race 2"
    assert change.timestamp is not None


def test_changing_a_code_records_both_fields(staff_client, sailed):
    _, races, entries = sailed
    save_finish(staff_client, races[0], entries[1], status="DNF", reason="Retired, not seen")
    assert only_change().changes == {
        "Status": ["Finished", "DNF - did not finish"],
        "Finish time": ["19:04:00", ""],
    }


def test_a_first_finish_is_recorded_without_a_reason(staff_client, unsailed):
    _, race, entry = unsailed
    response = save_finish(staff_client, race, entry, "19:00:00")
    assert Finish.objects.get(entry=entry).finish_time == time(19, 0)
    change = only_change()
    assert (change.action, change.is_correction, change.reason) == ("ADDED", False, "")
    assert change.changes == {"Status": ["", "Finished"], "Finish time": ["", "19:00:00"]}
    assert "Saved." in response.content.decode()


@pytest.mark.parametrize(
    "field, value, label, old, new",
    [
        ("series_type", "REGATTA", "Series type", "Club series", "Regatta"),
        ("discards", "0", "Discards", "1", "0"),
        ("minimum_finishers", "3", "Minimum finishers", "0", "3"),
        ("apply_a5_3", "on", "Use RRS A5.3", "No", "Yes"),
        # Slice 14: the optional extra NHC steps.
        ("nhc_cap_extremes", "on", "Cap extreme results", "No", "Yes"),
        ("nhc_realign_to_base", "on", "Realign to base handicaps", "No", "Yes"),
    ],
)
def test_series_settings_are_recorded(staff_client, sailed, field, value, label, old, new):
    series, *_ = sailed
    post_series(staff_client, series, reason="Per the notice of race", **{field: value})
    change = only_change()
    assert (change.kind, change.series) == ("SERIES", series)
    assert change.changes == {label: [old, new]}
    assert change.is_correction


def test_a_race_start_time_is_recorded(staff_client, sailed):
    series, races, _ = sailed
    post_series(staff_client, series, reason="Wrong gun time",
                **{"races-2-start_time": "18:01:00"})
    change = only_change()
    assert (change.kind, change.race, change.description) == ("RACE", races[2], "Race 3")
    assert change.changes == {"Start time": ["18:00:00", "18:01:00"]}
    assert change.is_correction and change.reason == "Wrong gun time"


def test_a_race_number_is_recorded(staff_client, sailed):
    series, *_ = sailed
    post_series(staff_client, series, reason="Renumbered", **{"races-3-number": "9"})
    assert only_change().changes == {"Number": ["4", "9"]}


def test_adding_a_race_and_an_entry_is_recorded(staff_client, unsailed):
    series, race, entry = unsailed
    newcomer = make_boat("GBR7", name="Puffin")
    data = series_form(series)
    data.update({
        "entries-TOTAL_FORMS": 2, "entries-1-series": series.pk, "entries-1-boat": newcomer.pk,
        "races-TOTAL_FORMS": 2, "races-1-series": series.pk, "races-1-number": 2,
        "races-1-date": "2026-09-30", "races-1-start_time": "18:30:00",
    })
    staff_client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    added = {c.kind: c for c in ScoringChange.objects.all()}
    assert set(added) == {"ENTRY", "RACE"}
    assert added["ENTRY"].description == "GBR7 Puffin"
    assert added["RACE"].race == Race.objects.get(series=series, number=2)
    assert added["RACE"].changes == {"Number": ["", "2"], "Start time": ["", "18:30:00"]}
    assert not any(c.is_correction for c in added.values())


def test_removing_a_race_with_finishes_is_recorded(staff_client, sailed):
    series, races, _ = sailed
    response = post_series(staff_client, series, reason="Abandoned", **{"races-3-DELETE": "on"})
    assert response.status_code == 302
    change = only_change()
    assert (change.kind, change.action, change.is_correction) == ("RACE", "REMOVED", True)
    assert change.description == "Race 4"
    assert change.race is None  # the race has gone; the record of it has not


def test_removing_an_entry_is_recorded(staff_client, unsailed):
    series, _, entry = unsailed
    post_series(staff_client, series, **{"entries-0-DELETE": "on"})
    change = only_change()
    assert (change.kind, change.action, change.description) == ("ENTRY", "REMOVED", "GBR1 Serendipity")


def test_a_base_number_is_recorded_in_every_series_the_boat_is_in(staff_client, sailed):
    series, _, entries = sailed
    other = make_series("Autumn")
    boat = entries[0].boat
    enter(other, boat)
    post_boat(staff_client, boat, base_number="0.960", reason="New certificate")
    changes = ScoringChange.objects.all()
    assert {c.series for c in changes} == {series, other}
    assert all(c.changes == {"NHC base number": ["0.950", "0.960"]} for c in changes)
    # Only the series that has results is being corrected.
    assert {c.series: c.is_correction for c in changes} == {series: True, other: False}


def test_a_base_number_for_a_boat_in_no_series_is_still_recorded(staff_client):
    boat = make_boat("GBR5")
    post_boat(staff_client, boat, base_number="0.980")
    change = only_change()
    assert (change.series, change.is_correction) == (None, False)


# --- Nothing outside the audited fields is recorded -------------------------


@pytest.mark.parametrize("changes", [{"name": "Tuesdays"}, {"races-0-date": "2026-10-01"}])
def test_series_changes_that_move_no_number_are_not_recorded(staff_client, sailed, changes):
    series, *_ = sailed
    assert post_series(staff_client, series, **changes).status_code == 302
    assert not ScoringChange.objects.exists()


def test_boat_details_that_move_no_number_are_not_recorded(staff_client, sailed):
    _, _, entries = sailed
    boat = entries[0].boat
    assert post_boat(staff_client, boat, name="Serendipity II", owner_name="A. Sailor").status_code == 302
    assert Boat.objects.get(pk=boat.pk).name == "Serendipity II"  # saved, needed no reason
    assert not ScoringChange.objects.exists()


def test_creating_a_boat_or_series_is_not_recorded(staff_client):
    staff_client.post(reverse("admin:races_boat_add"), boat_form(Boat(sail_number="GBR8", base_number="0.9")))
    assert Boat.objects.filter(sail_number="GBR8").exists()
    assert not ScoringChange.objects.exists()


def test_every_audited_field_is_covered_by_a_test_above():
    # Adding a field to AUDITED_FIELDS should come with a test that changes it.
    assert audit.AUDITED_FIELDS == {
        Finish: ["status", "finish_time"],
        Race: ["number", "start_time"],
        Series: [
            "series_type", "discards", "minimum_finishers", "apply_a5_3", "nhc_cap_extremes", "nhc_realign_to_base",
        ],
        audit.SeriesEntry: [],
        Boat: ["base_number"],
    }


# --- A correction without a reason is refused, and nothing is saved ---------


def test_a_finish_correction_without_a_reason_saves_nothing(staff_client, sailed):
    _, races, entries = sailed
    response = save_finish(staff_client, races[0], entries[0], "19:10:00")
    assert REASON_REQUIRED in response.content.decode()
    assert Finish.objects.get(race=races[0], entry=entries[0]).finish_time == time(19, 0)
    assert not ScoringChange.objects.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"discards": "2"},
        {"races-1-start_time": "18:05:00"},
        {"races-3-DELETE": "on"},
    ],
    ids=["setting", "start time", "race removed"],
)
def test_a_series_correction_without_a_reason_saves_nothing(staff_client, sailed, changes):
    series, races, _ = sailed
    response = post_series(staff_client, series, **changes)
    assert response.status_code == 200  # the form again, not a redirect
    assert REASON_REQUIRED in response.content.decode()
    assert Series.objects.get(pk=series.pk).discards == 1
    assert Race.objects.filter(series=series).count() == 4
    assert Race.objects.get(pk=races[1].pk).start_time == time(18, 0)
    assert not ScoringChange.objects.exists()


def test_adding_an_entry_to_a_sailed_series_needs_a_reason(staff_client, sailed):
    series, *_ = sailed
    newcomer = make_boat("GBR7")
    data = series_form(series)
    data.update({"entries-TOTAL_FORMS": 4, "entries-3-series": series.pk,
                 "entries-3-boat": newcomer.pk})
    response = staff_client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    assert REASON_REQUIRED in response.content.decode()
    assert series.entries.count() == 3


def test_a_base_number_correction_without_a_reason_saves_nothing(staff_client, sailed):
    _, _, entries = sailed
    boat = entries[0].boat
    response = post_boat(staff_client, boat, base_number="0.960")
    assert REASON_REQUIRED in response.content.decode()
    assert Boat.objects.get(pk=boat.pk).base_number == boat.base_number


def test_setup_before_any_race_is_sailed_needs_no_reason(staff_client, unsailed):
    series, *_ = unsailed
    response = post_series(staff_client, series, discards="0", **{"races-0-start_time": "18:15:00"})
    assert response.status_code == 302
    assert not any(c.is_correction for c in ScoringChange.objects.all())
    assert ScoringChange.objects.count() == 2


def test_a_whitespace_reason_is_no_reason(staff_client, sailed):
    _, races, entries = sailed
    response = save_finish(staff_client, races[0], entries[0], "19:10:00", reason="   ")
    assert REASON_REQUIRED in response.content.decode()


def test_the_database_refuses_a_correction_without_a_reason(sailed):
    series, *_ = sailed
    with pytest.raises(IntegrityError):
        ScoringChange.objects.create(
            club=series.club, series=series, kind="SERIES", action="CHANGED", description="x", is_correction=True
        )


def test_a_recorded_change_is_never_edited(sailed):
    series, *_ = sailed
    change = ScoringChange.objects.create(club=series.club, series=series, kind="SERIES", action="CHANGED", description="x")
    change.reason = "rewritten"
    with pytest.raises(ValueError):
        change.save()


# --- A save that changes nothing records nothing ---------------------------


def test_resaving_an_unchanged_finish_records_nothing(staff_client, sailed):
    _, races, entries = sailed
    response = save_finish(staff_client, races[0], entries[0], "19:00:00")
    assert "Saved; nothing changed." in response.content.decode()
    assert not ScoringChange.objects.exists()


def test_resaving_an_unchanged_series_or_boat_records_nothing(staff_client, sailed):
    series, _, entries = sailed
    assert post_series(staff_client, series).status_code == 302
    assert post_boat(staff_client, entries[0].boat).status_code == 302
    assert not ScoringChange.objects.exists()


# --- History outlives what it describes, but not its series -----------------


def test_history_survives_the_user_being_deleted(staff_client, staff_user, sailed):
    _, races, entries = sailed
    save_finish(staff_client, races[0], entries[0], "19:10:00", reason="Misread")
    staff_user.delete()
    change = only_change()
    assert change.user is None and change.user_name == "officer"


def test_history_survives_its_race_and_finishes_being_deleted(staff_client, sailed):
    _, races, entries = sailed
    save_finish(staff_client, races[0], entries[0], "19:10:00", reason="Misread")
    races[0].delete()
    change = only_change()
    assert change.race is None
    assert change.description == "GBR1 Serendipity, Race 1"


def test_history_is_deleted_with_its_series(staff_client, sailed):
    series, races, entries = sailed
    save_finish(staff_client, races[0], entries[0], "19:10:00", reason="Misread")
    series.delete()
    assert not ScoringChange.objects.exists()


# --- A change and its history are saved together or not at all -------------


class Boom(Exception):
    pass


def fail_recording(monkeypatch):
    def boom(*args, **kwargs):
        raise Boom

    monkeypatch.setattr(ScoringChange.objects, "bulk_create", boom)


def test_a_failed_recording_undoes_the_finish(staff_client, sailed, monkeypatch):
    _, races, entries = sailed
    fail_recording(monkeypatch)
    with pytest.raises(Boom):
        save_finish(staff_client, races[0], entries[0], "19:10:00", reason="Misread")
    assert Finish.objects.get(race=races[0], entry=entries[0]).finish_time == time(19, 0)


def test_a_failed_recording_undoes_the_admin_save(staff_client, sailed, monkeypatch):
    series, races, _ = sailed
    fail_recording(monkeypatch)
    with pytest.raises(Boom):
        post_series(staff_client, series, discards="2", reason="NoR",
                    **{"races-1-start_time": "18:05:00"})
    assert Series.objects.get(pk=series.pk).discards == 1
    assert Race.objects.get(pk=races[1].pk).start_time == time(18, 0)


# --- A correction reports what it changed ----------------------------------


@pytest.mark.parametrize("race_index", range(4))
@pytest.mark.parametrize("boat_index", range(3))
def test_a_correction_changes_every_later_handicap_and_nothing_earlier(sailed, race_index, boat_index):
    """A sweep over every finish in the series, not one worked example.

    Each finish is moved a quarter of an hour later. The race it is in sails on
    the same handicaps as before, since those came from the races before it;
    every race after it sails on different ones.
    """
    series, races, entries = sailed
    before = score_series(series)
    finish = Finish.objects.get(race=races[race_index], entry=entries[boat_index])
    later = datetime.combine(races[race_index].date, finish.finish_time) + timedelta(minutes=15)
    finish.finish_time = later.time()
    finish.save()

    effect = audit.compare(before, score_series(series))
    assert effect.handicaps == list(range(race_index + 2, 5))
    assert all(number >= race_index + 1 for number in effect.places)


def test_the_finish_row_says_what_the_correction_changed(staff_client, sailed):
    _, races, entries = sailed
    html = save_finish(staff_client, races[1], entries[2], "19:20:00", reason="Misread").content.decode()
    assert "Corrected." in html
    assert "Handicaps changed in races 3-4." in html


def test_the_admin_says_what_a_correction_changed(staff_client, sailed):
    _, _, entries = sailed
    boat = entries[0].boat
    response = staff_client.post(
        reverse("admin:races_boat_change", args=[boat.pk]),
        boat_form(boat, base_number="0.990", reason="New certificate"),
        follow=True,
    )
    messages = [str(m) for m in response.context["messages"]]
    assert "Wednesday Evenings: " in " ".join(messages)
    assert any("Handicaps changed in races 1-4." in m for m in messages)


def test_a_series_correction_reports_in_the_admin(staff_client, sailed):
    series, *_ = sailed
    response = staff_client.post(
        reverse("admin:races_series_change", args=[series.pk]),
        series_form(series, reason="Wrong gun", **{"races-0-start_time": "18:02:00"}),
        follow=True,
    )
    messages = [str(m) for m in response.context["messages"]]
    # The whole fleet shifts together, so nothing visible moves - and it says so.
    assert "Correction recorded. No places, handicaps, or standings were affected by this change." in messages


@pytest.mark.parametrize(
    "numbers, text",
    [([3], "race 3"), ([4, 5, 6], "races 4-6"), ([2, 4, 5, 6], "races 2, 4-6"), ([1, 3], "races 1, 3")],
)
def test_race_numbers_read_as_ranges(numbers, text):
    assert audit.race_list(numbers) == text


# --- Who sees what ----------------------------------------------------------


def test_the_history_page_needs_staff(client, django_user_model, sailed):
    series, *_ = sailed
    url = reverse("races:series_history", args=[series.pk])
    assert client.get(url).status_code == 302
    client.force_login(django_user_model.objects.create_user("member"))
    assert client.get(url).status_code == 403  # refused, not a login loop (slice 11)


def test_the_history_page_shows_who_what_and_why(staff_client, sailed):
    series, races, entries = sailed
    save_finish(staff_client, races[0], entries[0], "19:10:00", reason="Protest upheld")
    save_finish(staff_client, races[2], entries[1], "19:06:00", reason="Misread the sheet")
    page = staff_client.get(reverse("races:series_history", args=[series.pk])).content.decode()
    assert "officer" in page and "Protest upheld" in page and "Misread the sheet" in page
    assert "19:00:00 &rarr; 19:10:00" in page
    assert page.index("Misread the sheet") < page.index("Protest upheld")  # newest first


def test_the_history_page_filters_to_one_race(staff_client, sailed):
    series, races, entries = sailed
    save_finish(staff_client, races[0], entries[0], "19:10:00", reason="Protest upheld")
    save_finish(staff_client, races[2], entries[1], "19:06:00", reason="Misread the sheet")
    url = reverse("races:series_history", args=[series.pk]) + f"?race={races[2].pk}"
    page = staff_client.get(url).content.decode()
    assert "Misread the sheet" in page and "Protest upheld" not in page


def test_results_mark_amended_races_without_saying_who_or_why(staff_client, client, sailed):
    series, races, entries = sailed
    save_finish(staff_client, races[1], entries[0], "19:10:00", reason="Protest upheld")
    url = reverse("results:series", args=[series.pk])
    # The results page shows one race at a time.
    page = client.get(url, {"race": 2}).content.decode()
    # Race 2 says "Amended"; the standings say when they were last updated.
    assert page.count("Amended") == 1 and page.count("Last updated") == 1
    assert page.index("Last updated") < page.index('id="race-2"') < page.index("Amended")
    assert "Protest upheld" not in page and "officer" not in page
    # Race 3 is not marked, but the standings still are.
    page = client.get(url, {"race": 3}).content.decode()
    assert "Amended" not in page and page.count("Last updated") == 1


def test_first_entries_do_not_mark_results_amended(staff_client, client, unsailed):
    series, race, entry = unsailed
    save_finish(staff_client, race, entry, "19:00:00")
    page = client.get(reverse("results:series", args=[series.pk])).content.decode()
    assert "Amended" not in page and "Last updated" not in page


def test_a_settings_correction_marks_only_the_standings(staff_client, client, sailed):
    series, *_ = sailed
    post_series(staff_client, series, discards="0", reason="Per the NoR")
    page = client.get(reverse("results:series", args=[series.pk])).content.decode()
    assert "Amended" not in page and page.count("Last updated") == 1


# --- The admin explains what it refuses, rather than crashing ----------------


def test_removing_an_entry_with_results_is_explained_and_refused(staff_client, sailed):
    series, _, entries = sailed
    response = post_series(staff_client, series, reason="Withdrew", **{"entries-0-DELETE": "on"})
    assert response.status_code == 200
    html = response.content.decode()
    assert "GBR1 Serendipity cannot be removed from this series" in html
    assert "results in races 1-4" in html
    assert "protected related objects" not in html
    assert series.entries.filter(pk=entries[0].pk).exists()
    assert not ScoringChange.objects.exists()


def test_moving_a_start_past_saved_finishes_is_explained_and_refused(staff_client, sailed):
    series, races, _ = sailed
    response = post_series(
        staff_client, series, reason="Wrong gun time", **{"races-0-start_time": "19:30:00"}
    )
    assert response.status_code == 200
    assert "Finishes are already saved from 18:58:00" in response.content.decode()
    races[0].refresh_from_db()
    assert races[0].start_time == time(18, 0)
    assert not ScoringChange.objects.exists()
    # And the results page still works.
    assert staff_client.get(reverse("results:series", args=[series.pk])).status_code == 200


def test_swapping_two_race_numbers_saves(staff_client, sailed):
    """Saved row by row, a swap briefly gives two races one number."""
    series, races, _ = sailed
    response = post_series(
        staff_client, series, reason="Sailed in the other order",
        **{"races-0-number": "2", "races-1-number": "1"},
    )
    assert response.status_code == 302
    races[0].refresh_from_db()
    races[1].refresh_from_db()
    assert (races[0].number, races[1].number) == (2, 1)
    assert sorted(series.races.values_list("number", flat=True)) == [1, 2, 3, 4]
    assert ScoringChange.objects.filter(kind="RACE", action="CHANGED").count() == 2


def test_renumbering_into_a_removed_race_number_saves(staff_client, sailed):
    """Race 1 is saved before race 4 is removed, so this collides without parking."""
    series, races, _ = sailed
    response = post_series(
        staff_client, series, reason="Race 4 was really race 1",
        **{"races-0-number": "4", "races-3-DELETE": "on"},
    )
    assert response.status_code == 302
    races[0].refresh_from_db()
    assert races[0].number == 4
    assert sorted(series.races.values_list("number", flat=True)) == [2, 3, 4]


# --- The admin's own History button shows the reason too ---------------------


def admin_log_message(obj):
    from django.contrib.admin.models import LogEntry
    entry = LogEntry.objects.filter(object_id=str(obj.pk)).latest("action_time")
    return entry.get_change_message()


def test_admin_history_shows_the_reason_for_a_series_change(staff_client, sailed):
    series, _, _ = sailed
    post_series(staff_client, series, reason="Notice of race amended", discards="2")
    message = admin_log_message(series)
    assert "Discards" in message
    assert "Reason: Notice of race amended" in message
    assert "Reason for change" not in message  # the box is not a field of the series


def test_admin_history_shows_the_reason_for_a_boat_change(staff_client, sailed):
    _, _, entries = sailed
    boat = entries[0].boat
    post_boat(staff_client, boat, base_number="0.960", reason="New certificate")
    assert "Reason: New certificate" in admin_log_message(boat)


def test_admin_history_without_a_reason_says_nothing_about_one(staff_client, unsailed):
    series, _, _ = unsailed
    post_series(staff_client, series, discards="2")
    message = admin_log_message(series)
    assert "Discards" in message
    assert "Reason" not in message



# --- Labels ------------------------------------------------------------------


def test_history_labels_keep_their_capitals(staff_client, sailed):
    series, _, entries = sailed
    post_boat(staff_client, entries[0].boat, base_number="0.960", reason="New certificate")
    post_series(staff_client, series, reason="Notice of race", apply_a5_3="on")
    labels = {label for change in ScoringChange.objects.all() for label in change.changes}
    assert labels == {"NHC base number", "Use RRS A5.3"}
