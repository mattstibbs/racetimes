"""Slice 25, part B: RYA YTC series on the site.

A YTC boat has two numbers (her certificate's, and the non-spinnaker one) and
each series entry chooses which she races on. The worked examples YTC-1 and
YTC-2 (tests/fixtures/ytc.yaml, checked by the project owner) are loaded as
clock times, and these tests are the rules around them: who may be entered on
which number, what changing a number does, and what the history records.
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
    make_race,
    make_series,
    make_ytc_series,
    post_series,
    publish,
    record,
)
from tests.scenario_loader import YTC_FIXTURE

pytestmark = pytest.mark.django_db

YTC_1 = YTC_FIXTURE["YTC-1"]
YTC_2 = YTC_FIXTURE["YTC-2"]
DISPLAY_TOLERANCE = 0.0005
REASON_REQUIRED = "give a reason for the correction"
SPIN, NS = SeriesEntry.NumberUsed.SPINNAKER, SeriesEntry.NumberUsed.NON_SPINNAKER


# --- Helpers ---------------------------------------------------------------------------------


def ytc_boat(sail="Y1", ytc=873, ns=899, **fields):
    return make_boat(
        sail, base_number=None, ytc_number=ytc, ytc_number_non_spinnaker=ns, **fields
    )


def office_enter(client, series, boats, **extra):
    return client.post(
        reverse("races:office_enter_boats", args=[series.pk]),
        {"boat": [boat.pk for boat in boats], **extra},
    )


def office_number(client, entry, used, **extra):
    return client.post(
        reverse("races:office_entry_number", args=[entry.pk]),
        {"ytc_number_used": used, **extra},
    )


def office_boat(client, boat, **changes):
    return client.post(
        reverse("races:office_boat", args=[boat.pk]), boat_form(boat, **changes)
    )


def settings_data(series, **changes):
    data = {
        "name": series.name,
        "handicap_system": series.handicap_system,
        "series_type": series.series_type,
        "discards": series.discards,
        "discard_threshold": series.discard_threshold,
        "minimum_finishers": series.minimum_finishers,
    }
    data.update(changes)
    return data


def office_settings(client, series, **changes):
    return client.post(
        reverse("races:office_series_settings", args=[series.pk]),
        settings_data(series, **changes),
    )


def history(series=None):
    rows = ScoringChange.objects.all()
    return rows.filter(series=series) if series is not None else rows


def check_against(results, races, expected_races, entries):
    for race, expected in zip(races, expected_races, strict=True):
        race_results = results.for_race(race)
        for letter, want in expected.items():
            row = race_results.for_entry(entries[letter])
            assert row.result.points == want["points"], (race.number, letter)
            if "place" in want:
                assert row.result.position == want["place"], (race.number, letter)
                assert row.result.corrected_time == pytest.approx(
                    want["corrected"], abs=DISPLAY_TOLERANCE
                )
            else:
                assert row.result.position is None


@pytest.fixture
def member(client):
    person = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    client.force_login(person)
    return person


@pytest.fixture
def office():
    committee = Client()
    committee.force_login(make_committee())
    return committee


# --- The worked examples, through the database --------------------------------------------------


@pytest.mark.parametrize("example_id", list(YTC_FIXTURE))
def test_the_worked_examples_reproduce_through_the_database(example_id):
    example = YTC_FIXTURE[example_id]
    series, entries, races = make_ytc_series(example)
    results = score_series(series)
    assert not results.error
    check_against(results, races, [r["expected"] for r in example["races"]], entries)
    assert [(s.entry.pk, s.position, s.total) for s in results.standings] == [
        (entries[w["boat"]].pk, w["position"], w["total"]) for w in example["standings"]
    ]
    for race in races:
        for letter, entry in entries.items():
            assert (
                results.for_race(race).for_entry(entry).raced_on
                == example["boats"][letter]
            )


def test_the_entry_decides_which_number_a_boat_is_scored_on():
    """YTC-1: A is second on her YTC number and first on her non-spinnaker one."""
    series, entries, races = make_ytc_series(YTC_1)
    other = YTC_1["with_a_on_her_ytc_number"]
    check_against(
        score_series(series), races, [r["expected"] for r in YTC_1["races"]], entries
    )

    SeriesEntry.objects.filter(pk=entries["A"].pk).update(ytc_number_used=SPIN)
    results = score_series(series)
    check_against(results, races, [r["expected"] for r in other["races"]], entries)
    assert [(s.entry.pk, s.position, s.total) for s in results.standings] == [
        (entries[w["boat"]].pk, w["position"], w["total"]) for w in other["standings"]
    ]


def test_the_same_boat_races_on_a_different_number_in_each_series():
    boat = ytc_boat("TWO", 873, 899, name="Both")
    rival = ytc_boat("RIV", 940, None, name="Rival")
    spin_series = make_series("Spinnaker", handicap_system="YTC")
    white_sails = make_series("White sails", handicap_system="YTC")
    mine = {
        spin_series: enter(spin_series, boat, ytc_number_used=SPIN),
        white_sails: enter(white_sails, boat, ytc_number_used=NS),
    }
    for series in (spin_series, white_sails):
        race = make_race(series, start="18:30:00")
        record(race, mine[series], finish_clock("18:30:00", 3600))
        record(race, enter(series, rival), finish_clock("18:30:00", 3700))
    raced = {
        series.name: score_series(series).races[0].for_entry(mine[series]).raced_on
        for series in mine
    }
    assert raced == {"Spinnaker": 873, "White sails": 899}

    # Changing one entry's choice changes only that series.
    before = score_series(spin_series)
    SeriesEntry.objects.filter(pk=mine[white_sails].pk).update(ytc_number_used=SPIN)
    after = score_series(spin_series)
    assert [r.raced_on for r in before.races[0].rows] == [
        r.raced_on for r in after.races[0].rows
    ]
    assert (
        score_series(white_sails).races[0].for_entry(mine[white_sails]).raced_on == 873
    )


def test_no_handicap_moves_under_ytc_whatever_the_finishes():
    series, _entries, _races = make_ytc_series(YTC_1)
    results = score_series(series)
    for race_results in results.races:
        for row in race_results.rows:
            assert row.is_fixed_number and row.next_handicap is None
            assert not row.capped
            assert row.raced_on == row.entry.number


def test_changing_any_finish_changes_only_that_race():
    series, _entries, races = make_ytc_series(YTC_1)

    def snapshot():
        return [
            [
                (r.entry.pk, r.result.position, r.result.points, r.raced_on)
                for r in rr.rows
            ]
            for rr in score_series(series).races
        ]

    before = snapshot()
    for finish in [
        race_finish
        for race in races
        for race_finish in race.finishes.filter(status="FINISHED")
    ]:
        original = finish.finish_time
        finish.finish_time = finish_clock("18:30:00", 7000)
        finish.save()
        changed = [
            i for i, (a, b) in enumerate(zip(before, snapshot(), strict=True)) if a != b
        ]
        assert changed in ([], [finish.race.number - 1])
        finish.finish_time = original
        finish.save()
    assert snapshot() == before


# --- A series that can't be scored says so ------------------------------------------------------


def test_an_entry_whose_chosen_number_is_missing_says_so_not_a_crash():
    series, entries, _races = make_ytc_series(YTC_1)
    Boat.objects.filter(pk=entries["A"].boat.pk).update(ytc_number_non_spinnaker=None)
    results = score_series(series)
    assert results.races == () and results.standings == ()
    assert "Boat A (YTCA) has no Non-spinnaker YTC number" in results.error


def test_ytc_refuses_nhc_only_settings_when_scoring_too():
    series, _, _ = make_ytc_series(YTC_1)
    Series.objects.filter(pk=series.pk).update(minimum_finishers=2)
    results = score_series(Series.objects.get(pk=series.pk))
    assert "a RYA YTC series can't use a minimum finishers threshold" in results.error


# --- Choosing YTC for a series ------------------------------------------------------------------


def test_the_settings_page_offers_ytc_and_nhc_stays_the_default(committee_client):
    page = committee_client.get(reverse("races:office_new_series")).content.decode()
    assert "RYA YTC" in page
    assert make_series().handicap_system == "NHC"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"series_type": "REGATTA"}, "must be a club series"),
        ({"minimum_finishers": "3"}, "nothing for this to apply to"),
        ({"nhc_cap_extremes": "on"}, "This is an NHC option"),
        ({"nhc_realign_to_base": "on"}, "This is an NHC option"),
    ],
)
def test_ytc_refuses_nhc_only_settings(committee_client, changes, message):
    series = make_series("Cruisers", handicap_system="YTC")
    response = office_settings(committee_client, series, **changes)
    assert message in response.content.decode()


def test_the_admin_refuses_them_too(staff_client):
    series = make_series("Cruisers", handicap_system="YTC")
    response = post_series(staff_client, series, series_type="REGATTA")
    assert "must be a club series" in response.content.decode()


# --- Entering boats -------------------------------------------------------------------------------


def test_a_boat_with_neither_ytc_number_cant_be_entered_and_is_named(committee_client):
    series = make_series("Cruisers", handicap_system="YTC")
    nhc_only = make_boat("N1", base_number="0.950", name="Nhc Only")
    good = ytc_boat("Y1", 873, None, name="Good")
    page = office_enter(committee_client, series, [good, nhc_only]).content.decode()
    assert "Nhc Only (N1) has no YTC number" in page
    assert not SeriesEntry.objects.exists()
    listing = committee_client.get(
        reverse("races:office_enter_boats", args=[series.pk])
    ).content.decode()
    assert f'value="{nhc_only.pk}"' not in listing and "Nhc Only (N1) <span" in listing


def test_the_page_asks_which_number_only_of_a_boat_with_both(committee_client):
    series = make_series("Cruisers", handicap_system="YTC")
    both = ytc_boat("B1", 873, 899, name="Both")
    only_ns = ytc_boat("N1", None, 920, name="White")
    page = committee_client.get(
        reverse("races:office_enter_boats", args=[series.pk])
    ).content.decode()
    assert f'name="number_{both.pk}"' in page
    assert "Non-spinnaker YTC number 899" in page
    assert f'name="number_{only_ns.pk}"' not in page
    assert "races on non-spinnaker YTC number 920" in page


def test_a_search_keeps_the_numbers_chosen(committee_client):
    series = make_series("Cruisers", handicap_system="YTC")
    both = ytc_boat("B1", 873, 899, name="Both")
    page = committee_client.get(
        reverse("races:office_enter_boats", args=[series.pk]),
        {"boat": both.pk, f"number_{both.pk}": NS},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="boat-choices",
    ).content.decode()
    assert f'<option value="{NS}" selected>' in page


def test_entering_boats_records_the_number_each_races_on(committee_client):
    series = make_series("Cruisers", handicap_system="YTC")
    both = ytc_boat("B1", 873, 899, name="Both")
    only_ns = ytc_boat("N1", None, 920, name="White")
    only_spin = ytc_boat("S1", 940, None, name="Spin")
    response = office_enter(
        committee_client,
        series,
        [both, only_ns, only_spin],
        **{f"number_{both.pk}": NS},
    )
    assert response.status_code == 302
    used = {e.boat.name: e.ytc_number_used for e in series.entries.all()}
    assert used == {"Both": NS, "White": NS, "Spin": SPIN}


def test_a_boat_with_both_numbers_is_entered_on_her_ytc_number_unless_told(
    committee_client,
):
    series = make_series("Cruisers", handicap_system="YTC")
    both = ytc_boat("B1")
    office_enter(committee_client, series, [both])
    assert series.entries.get().ytc_number_used == SPIN


def test_a_number_the_boat_doesnt_have_is_refused_naming_her(committee_client):
    series = make_series("Cruisers", handicap_system="YTC")
    spin_only = ytc_boat("S1", 940, None, name="Spin")
    response = office_enter(
        committee_client, series, [spin_only], **{f"number_{spin_only.pk}": NS}
    )
    assert "Spin (S1) does not have the number chosen" in response.content.decode()
    assert not SeriesEntry.objects.exists()


def test_outside_a_ytc_series_the_choice_means_nothing(committee_client):
    series = make_series("Autumn")
    boat = make_boat("N1", base_number="0.950", ytc_number=873)
    office_enter(committee_client, series, [boat], **{f"number_{boat.pk}": NS})
    assert series.entries.get().ytc_number_used == SPIN
    assert (
        "races on"
        not in committee_client.get(
            reverse("races:office_enter_boats", args=[make_series("Other").pk])
        ).content.decode()
    )


def test_the_admin_refuses_an_entry_on_a_number_the_boat_hasnt_got(staff_client):
    series = make_series("Cruisers", handicap_system="YTC")
    boat = ytc_boat("S1", 940, None, name="Spin")
    data = {
        "name": series.name,
        "handicap_system": "YTC",
        "series_type": "CLUB",
        "discards": 1,
        "discard_threshold": 0,
        "minimum_finishers": 0,
        "reason": "",
        "entries-TOTAL_FORMS": 1,
        "entries-INITIAL_FORMS": 0,
        "entries-MIN_NUM_FORMS": 0,
        "entries-MAX_NUM_FORMS": 1000,
        "entries-0-boat": boat.pk,
        "entries-0-ytc_number_used": NS,
        "races-TOTAL_FORMS": 0,
        "races-INITIAL_FORMS": 0,
        "races-MIN_NUM_FORMS": 0,
        "races-MAX_NUM_FORMS": 1000,
    }
    response = staff_client.post(
        reverse("admin:races_series_change", args=[series.pk]), data
    )
    assert "has no Non-spinnaker YTC number" in response.content.decode()
    assert not SeriesEntry.objects.exists()
    data["entries-0-ytc_number_used"] = ""  # left blank: the boat's own default
    staff_client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    assert series.entries.get().ytc_number_used == SPIN


def test_the_model_checks_the_chosen_number_too():
    series = make_series("Cruisers", handicap_system="YTC")
    boat = ytc_boat("S1", 940, None)
    with pytest.raises(ValidationError, match="has no Non-spinnaker YTC number"):
        SeriesEntry(series=series, boat=boat, ytc_number_used=NS).full_clean()
    SeriesEntry(series=series, boat=boat, ytc_number_used=SPIN).full_clean()


# --- Switching a series' system ----------------------------------------------------------------


def test_switching_to_ytc_puts_each_boat_on_her_ytc_number_or_her_only_one(
    committee_client,
):
    series = make_series("Autumn")
    both = enter(
        series,
        make_boat(
            "B1", base_number="0.9", ytc_number=873, ytc_number_non_spinnaker=899
        ),
    )
    only_ns = enter(
        series, make_boat("N1", base_number="0.9", ytc_number_non_spinnaker=920)
    )
    response = office_settings(committee_client, series, handicap_system="YTC")
    assert response.status_code == 302
    both.refresh_from_db()
    only_ns.refresh_from_db()
    assert (both.ytc_number_used, only_ns.ytc_number_used) == (SPIN, NS)


def test_switching_to_ytc_is_refused_while_a_boat_has_neither_number(committee_client):
    series = make_series("Autumn")
    enter(series, make_boat("B1", base_number="0.9", name="Fine", ytc_number=873))
    enter(series, make_boat("N1", base_number="0.9", name="Nhc Only"))
    response = office_settings(committee_client, series, handicap_system="YTC")
    page = response.content.decode()
    assert (
        "Nhc Only (N1)" in page and "Fine (B1)" not in page.split("Nhc Only")[0][-200:]
    )
    assert Series.objects.get().handicap_system == "NHC"


def test_switching_away_from_ytc_resets_the_choice(committee_client):
    series, entries, _ = make_ytc_series(YTC_1)
    for entry in entries.values():
        Boat.objects.filter(pk=entry.boat_id).update(base_number="0.9")
    office_settings(
        committee_client, series, handicap_system="NHC", reason="Changed system"
    )
    assert set(series.entries.values_list("ytc_number_used", flat=True)) == {SPIN}


# --- Changing the number an entry races on -----------------------------------------------------------


def test_the_series_page_shows_each_number_and_ns(committee_client):
    series, entries, _ = make_ytc_series(YTC_1)
    page = committee_client.get(
        reverse("races:office_series", args=[series.pk])
    ).content.decode()
    assert '<th class="num">YTC</th>' in page
    assert "NS</abbr>" in page and "899" in page
    assert reverse("races:office_entry_number", args=[entries["A"].pk]) in page


def test_changing_an_entrys_number_before_any_result_needs_no_reason(committee_client):
    series = make_series("Cruisers", handicap_system="YTC")
    entry = enter(series, ytc_boat("B1"))
    response = office_number(committee_client, entry, NS)
    assert response.status_code == 302
    entry.refresh_from_db()
    assert entry.ytc_number_used == NS
    [change] = history(series)
    assert change.changes == {"Number used": ["YTC number", "Non-spinnaker YTC number"]}
    assert not change.is_correction


def test_changing_it_once_the_series_has_results_is_a_correction(committee_client):
    series, entries, races = make_ytc_series(YTC_1)
    page = committee_client.get(
        reverse("races:office_entry_number", args=[entries["A"].pk])
    ).content.decode()
    assert "Reason for change" in page
    response = office_number(committee_client, entries["A"], SPIN)
    assert REASON_REQUIRED in response.content.decode()
    entries["A"].refresh_from_db()
    assert entries["A"].ytc_number_used == NS and not history()

    response = office_number(
        committee_client, entries["A"], SPIN, reason="Sailed with the spinnaker"
    )
    assert response.status_code == 302
    entries["A"].refresh_from_db()
    assert entries["A"].ytc_number_used == SPIN
    [change] = history(series)
    assert change.is_correction and change.reason == "Sailed with the spinnaker"
    assert change.series == series
    # The results now are the second table.
    other = YTC_1["with_a_on_her_ytc_number"]
    check_against(
        score_series(series), races, [r["expected"] for r in other["races"]], entries
    )


def test_a_save_that_changes_nothing_records_nothing(committee_client):
    _series, entries, _ = make_ytc_series(YTC_1)
    response = office_number(committee_client, entries["A"], NS)
    assert response.status_code == 302
    assert not history()


def test_the_choice_offers_only_the_numbers_the_boat_has(committee_client):
    _series, entries, _ = make_ytc_series(YTC_1)
    page = committee_client.get(
        reverse("races:office_entry_number", args=[entries["B"].pk])
    ).content.decode()
    assert "YTC number 940" in page and "Non-spinnaker YTC number" not in page
    response = office_number(committee_client, entries["B"], NS, reason="x")
    assert "valid choice" in response.content.decode()


def test_a_final_series_is_locked_against_it(committee_client):
    series, entries, races = make_ytc_series(YTC_1)
    publish(*races)
    declare(committee_client, series)
    response = office_number(committee_client, entries["A"], SPIN, reason="x")
    assert response.status_code == 302
    entries["A"].refresh_from_db()
    assert entries["A"].ytc_number_used == NS and not history().filter(kind="ENTRY")


def test_it_is_refused_outside_a_ytc_series(committee_client):
    series = make_series("Autumn")
    entry = enter(series, make_boat("N1", base_number="0.9", ytc_number=873))
    response = committee_client.get(
        reverse("races:office_entry_number", args=[entry.pk]), follow=True
    )
    assert "is not an RYA YTC series" in response.content.decode()


def test_only_the_committee_may_change_it(client, member):
    _series, entries, _ = make_ytc_series(YTC_1)
    url = reverse("races:office_entry_number", args=[entries["A"].pk])
    assert client.get(url).status_code == 403
    assert Client().get(url).status_code == 302  # the public is sent to log in


# --- Changing a boat's numbers ---------------------------------------------------------------------


def test_a_number_the_boat_is_entered_on_cant_be_cleared_but_the_other_can(
    committee_client,
):
    _series, entries, _ = make_ytc_series(YTC_1)
    boat = entries["A"].boat  # entered on her non-spinnaker number, 899
    response = office_boat(
        committee_client, boat, ytc_number_non_spinnaker="", reason="x"
    )
    assert (
        "The Non-spinnaker YTC number can&#x27;t be removed while the boat is entered"
        in response.content.decode()
    )
    boat.refresh_from_db()
    assert boat.ytc_number_non_spinnaker == 899
    # Her YTC number is not in use, so it can go.
    response = office_boat(committee_client, boat, ytc_number="", reason="x")
    assert response.status_code == 302
    boat.refresh_from_db()
    assert boat.ytc_number is None


def test_a_boat_needs_a_number_of_some_kind(committee_client):
    boat = ytc_boat("Y1", 873, None)
    response = office_boat(committee_client, boat, ytc_number="")
    assert "A boat needs a number to race on" in response.content.decode()


def test_changing_the_number_a_boat_raced_on_is_a_correction(committee_client):
    series, entries, _races = make_ytc_series(YTC_1)
    boat = entries["A"].boat
    response = office_boat(committee_client, boat, ytc_number_non_spinnaker="900")
    assert REASON_REQUIRED in response.content.decode()
    response = office_boat(
        committee_client,
        boat,
        ytc_number_non_spinnaker="900",
        reason="Typo on the form",
    )
    assert response.status_code == 302
    [change] = history(series)
    assert change.is_correction and change.reason == "Typo on the form"
    assert change.changes == {"Non-spinnaker YTC number": ["899", "900"]}
    assert score_series(series).races[0].for_entry(entries["A"]).raced_on == 900


def test_changing_a_number_the_boat_never_raced_on_needs_no_reason(committee_client):
    """A has raced on her non-spinnaker number only, so her YTC number is free."""
    _series, entries, _ = make_ytc_series(YTC_1)
    boat = entries["A"].boat
    page = committee_client.get(reverse("races:office_boat", args=[boat.pk]))
    assert "Reason for change" in page.content.decode()  # the boat has results
    response = office_boat(committee_client, boat, ytc_number="880")
    assert response.status_code == 302
    boat.refresh_from_db()
    assert boat.ytc_number == 880
    [change] = history()
    assert not change.is_correction and change.series is None
    assert change.changes == {"YTC number": ["873", "880"]}


def test_a_final_series_keeps_its_results_when_a_boats_numbers_change(committee_client):
    series, entries, races = make_ytc_series(YTC_1)
    publish(*races)
    declare(committee_client, series)
    before = [(s.entry.pk, s.position, s.total) for s in score_series(series).standings]
    Boat.objects.filter(pk=entries["A"].boat.pk).update(
        ytc_number_non_spinnaker=None, ytc_number=700
    )
    results = score_series(Series.objects.get(pk=series.pk))
    assert not results.error
    assert [(s.entry.pk, s.position, s.total) for s in results.standings] == before
    assert results.races[0].for_entry(entries["A"]).raced_on == 899
    assert results.races[0].for_entry(entries["A"]).is_non_spinnaker  # NS still known


# --- Members' requests ----------------------------------------------------------------------------------


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
        "ytc_number": "",
        "ytc_number_non_spinnaker": "",
        "member_note": "",
    }
    data.update(fields)
    return data


def test_a_member_can_register_a_boat_with_both_ytc_numbers(client, office, member):
    client.post(
        reverse("races:register_boat"),
        request_form(ytc_number="873", ytc_number_non_spinnaker="899"),
    )
    request = BoatRequest.objects.get()
    assert (request.ytc_number, request.ytc_number_non_spinnaker) == (873, 899)
    assert not Boat.objects.exists()  # nothing reaches the boat until approved
    page = office.get(reverse("races:requests")).content.decode()
    assert "YTC number" in page and "873" in page and "899" in page
    decide(office, request, "approve")
    boat = Boat.objects.get()
    assert (boat.ytc_number, boat.ytc_number_non_spinnaker, boat.base_number) == (
        873,
        899,
        None,
    )


def test_a_member_can_ask_to_change_a_ytc_number(client, office, member):
    boat = ytc_boat("GBR42", 873, 899, owner=member)
    client.post(
        reverse("races:change_boat", args=[boat.pk]),
        {**boat_form(boat, ytc_number_non_spinnaker="905"), "member_note": ""},
    )
    request = BoatRequest.objects.get()
    boat.refresh_from_db()
    assert boat.ytc_number_non_spinnaker == 899
    decide(office, request, "approve")
    boat.refresh_from_db()
    assert boat.ytc_number_non_spinnaker == 905


def entry_request(client, boat, series, **extra):
    return client.post(
        reverse("races:enter_series", args=[boat.pk]),
        {"series": series.pk, "member_note": "", **extra},
    )


def test_a_member_chooses_the_number_in_an_entry_request(client, office, member):
    boat = ytc_boat("GBR42", 873, 899, owner=member)
    series = make_series("Cruisers", handicap_system="YTC")
    page = client.get(reverse("races:enter_series", args=[boat.pk])).content.decode()
    assert 'name="ytc_number_used"' in page
    entry_request(client, boat, series, ytc_number_used=NS)
    request = EntryRequest.objects.get()
    assert request.ytc_number_used == NS
    assert not SeriesEntry.objects.exists()
    page = office.get(reverse("races:requests")).content.decode()
    assert "Races on:" in page and "Non-spinnaker YTC number 899" in page
    decide(office, request, "approve")
    assert SeriesEntry.objects.get().ytc_number_used == NS


def test_an_unchosen_number_defaults_to_the_boats_ytc_number(client, office, member):
    boat = ytc_boat("GBR42", 873, 899, owner=member)
    series = make_series("Cruisers", handicap_system="YTC")
    entry_request(client, boat, series)
    decide(office, EntryRequest.objects.get(), "approve")
    assert SeriesEntry.objects.get().ytc_number_used == SPIN


def test_a_request_for_a_number_the_boat_hasnt_got_is_refused(client, member):
    boat = ytc_boat("GBR42", 873, None, owner=member)
    series = make_series("Cruisers", handicap_system="YTC")
    response = entry_request(client, boat, series, ytc_number_used=NS)
    assert "has no Non-spinnaker YTC number" in response.content.decode()
    assert not EntryRequest.objects.exists()


def test_a_boat_with_neither_number_cant_ask_to_enter(client, member):
    boat = make_boat("GBR42", owner=member, base_number="0.805")
    series = make_series("Cruisers", handicap_system="YTC")
    response = entry_request(client, boat, series)
    assert "has no YTC number" in response.content.decode()
    assert not EntryRequest.objects.exists()


def test_approving_is_refused_if_the_boat_has_since_lost_that_number(
    client, office, member
):
    boat = ytc_boat("GBR42", 873, 899, owner=member)
    series = make_series("Cruisers", handicap_system="YTC")
    entry_request(client, boat, series, ytc_number_used=NS)
    Boat.objects.filter(pk=boat.pk).update(ytc_number_non_spinnaker=None)
    request = EntryRequest.objects.get()
    response = decide(office, request, "approve")
    assert "no longer has the Non-spinnaker YTC number" in response.content.decode()
    assert request.status == "PENDING" and not SeriesEntry.objects.exists()


def test_the_my_boats_page_shows_both_numbers(client, member):
    ytc_boat("GBR42", 873, 899, owner=member)
    page = client.get(reverse("races:my_boats")).content.decode()
    assert "YTC number 873." in page and "Non-spinnaker YTC number 899." in page


# --- The audit trail covers all three fields -------------------------------------------------------------


def test_the_audited_fields_are_the_ones_pinned():
    assert audit.AUDITED_FIELDS[Boat][-2:] == ["ytc_number", "ytc_number_non_spinnaker"]
    assert audit.AUDITED_FIELDS[SeriesEntry] == ["ytc_number_used"]
    assert audit.fields_for(SeriesEntry(series=make_series())) == []  # not YTC


def test_adding_an_entry_to_a_ytc_series_records_the_number_it_races_on(
    committee_client,
):
    series = make_series("Cruisers", handicap_system="YTC")
    office_enter(committee_client, series, [ytc_boat("B1")])
    [change] = history(series)
    assert change.action == "ADDED"
    assert change.changes == {"Number used": ["", "YTC number"]}
