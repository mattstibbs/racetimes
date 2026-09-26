"""Slice 14: a series' optional NHC steps, capping extreme results and realigning to base handicaps.

The engine's own tests (tests/test_nhc_options.py) check the arithmetic against
the MCC race's published figures. These check the site: the settings, where
they apply, that scoring uses them, and what the results show.

A series here starts on base numbers, so the MCC race is set up with each
boat's base number equal to the handicap it raced on. That reproduces the
fixture's "off" and "capping only" columns exactly (neither uses base
numbers). Realignment is checked against the engine given the same boats.
"""

from datetime import datetime, timedelta

import nhc
import pytest
from django.urls import reverse

from races import final
from races.models import Series
from races.scoring import engine_outcome, score_series
from races.test_audit import post_series, staff_client, staff_user  # noqa: F401 (fixtures)
from races.testing import enter, make_boat, make_race, make_series, record
from tests.scenario_loader import MCC_RACE

pytestmark = pytest.mark.django_db

START = "12:00:00"


def mcc_series(base_from="handicap", **options):
    """The MCC race as one race of a club series: its boats, entries and finishes."""
    series = make_series("MCC Tuesdays", discards=0, **options)
    race = make_race(series, 1, start=START)
    entries = {}
    for boat in MCC_RACE["boats"]:
        entry = enter(series, make_boat(boat["boat_id"], name=boat["boat_id"], base_number=boat[base_from]))
        entries[boat["boat_id"]] = entry
        if boat["elapsed_seconds"]:
            finish = datetime(2026, 9, 23, 12) + timedelta(seconds=boat["elapsed_seconds"])
            record(race, entry, finish.strftime("%H:%M:%S"))
        else:
            record(race, entry, status="DNC")
    return series, race, entries


def next_handicaps(series, race, entries):
    race_results = score_series(series).for_race(race)
    return {name: race_results.for_entry(entry).result.next_tcf for name, entry in entries.items()}


def rounded(handicaps):
    return {name: round(tcf, 3) for name, tcf in handicaps.items()}


def expected(column):
    return {boat["boat_id"]: boat["expected"][column] for boat in MCC_RACE["boats"]}


# --- The settings ------------------------------------------------------------------------------


def test_both_are_off_for_a_new_series():
    series = Series.objects.create(club=make_series().club, name="New")
    assert (series.nhc_cap_extremes, series.nhc_realign_to_base) == (False, False)
    assert series.nhc_options == []


def test_both_save_from_the_series_form_in_scoring_rules(staff_client):  # noqa: F811
    series = make_series()
    page = staff_client.get(reverse("admin:races_series_change", args=[series.pk])).content.decode()
    scoring_rules = page.split("Scoring rules")[1].split("</fieldset>")[0]
    assert 'name="nhc_cap_extremes"' in scoring_rules and 'name="nhc_realign_to_base"' in scoring_rules
    assert "Cap extreme results" in scoring_rules and "Realign to base handicaps" in scoring_rules
    post_series(staff_client, series, nhc_cap_extremes="on", nhc_realign_to_base="on")
    series.refresh_from_db()
    assert (series.nhc_cap_extremes, series.nhc_realign_to_base) == (True, True)


@pytest.mark.parametrize("field", ["nhc_cap_extremes", "nhc_realign_to_base"])
def test_a_regatta_refuses_them(staff_client, field):  # noqa: F811
    series = make_series()
    response = post_series(staff_client, series, series_type="REGATTA", **{field: "on"})
    assert response.status_code == 200 and "This is a club-series option" in response.content.decode()
    series.refresh_from_db()
    assert series.series_type == "CLUB" and not getattr(series, field)


# --- Scoring uses them -------------------------------------------------------------------------


def test_with_both_off_the_race_scores_as_it_always_has():
    assert rounded(next_handicaps(*mcc_series())) == expected("off")


def test_capping_matches_the_published_capping_only_figures():
    assert rounded(next_handicaps(*mcc_series(nhc_cap_extremes=True))) == expected("cap_only")


@pytest.mark.parametrize("cap", [False, True])
def test_realignment_is_the_engines_given_the_same_boats(cap):
    series, race, entries = mcc_series(base_from="base_number", nhc_cap_extremes=cap, nhc_realign_to_base=True)
    boats = [nhc.Boat(b["boat_id"], base_number=b["base_number"], current_tcf=b["base_number"])
             for b in MCC_RACE["boats"]]
    finishes = [nhc.Finish(b["boat_id"], nhc.RaceStatus(b["status"]), elapsed_seconds=b["elapsed_seconds"])
                for b in MCC_RACE["boats"]]
    engine = nhc.score_series(nhc.Series(
        boats=boats, races=[nhc.SeriesRace("R1", finishes)], discards=0,
        progression=nhc.HandicapProgression.RESET, cap_extremes=cap, realign_to_base=True,
    ))
    engine_handicaps = {r.boat_id: r.next_tcf for r in engine.races[0].results}
    # Equal to the last few digits only: the site adds the boats up in a different
    # order, and floating-point sums differ in the 16th significant figure.
    assert next_handicaps(series, race, entries) == pytest.approx(engine_handicaps, rel=1e-12)


def test_a_final_series_copy_keeps_what_the_options_did():
    # A final series is scored from a saved copy of the engine's results (slice 10).
    series, race, entries = mcc_series(nhc_cap_extremes=True, nhc_realign_to_base=True)
    live = score_series(series).for_race(race)
    copy = final.load(final.dump(engine_outcome(series)))  # exactly what declaring final saves
    kept = {r.boat_id: r for r in copy.races[0].results}
    for entry in entries.values():
        a, b = kept[str(entry.pk)], live.for_entry(entry).result
        assert (a.next_tcf, a.capped, a.realignment_factor) == (b.next_tcf, b.capped, b.realignment_factor)


def test_a_final_copy_saved_before_slice_14_still_loads():
    series, race, _ = mcc_series()
    data = final.dump(engine_outcome(series))
    for race_data in data["races"]:
        for result in race_data["results"]:
            del result["realignment_factor"]  # as copies saved before slice 14 were
    assert all(r.realignment_factor is None for r in final.load(data).races[0].results)


# --- What the results show ---------------------------------------------------------------------


def series_page(client, series, race, detail=False):
    url = reverse("results:series", args=[series.pk]) + f"?race={race.number}" + ("&detail=1" if detail else "")
    return client.get(url).content.decode()


def test_the_results_say_which_options_were_used_and_mark_capped_boats(client):
    series, race, _ = mcc_series(nhc_cap_extremes=True, nhc_realign_to_base=True)
    page = series_page(client, series, race, detail=True)
    assert "Handicaps adjusted with: extreme-result capping, realignment to base handicaps." in page
    assert "Handicaps adjusted with extreme-result capping and realignment to base handicaps." in page
    rows = page.split('class="race-results')[1].split("</tbody>")[0].split("</tr>")
    capped = [row.split("</a>")[0].rsplit(">", 1)[1] for row in rows if "Result capped as extreme" in row]
    assert capped == ["Lanternledger Lanternledger", "Saltwake Saltwake"]  # sail number and name, both the boat's name here


def test_realignment_alone_says_so_without_the_capping_footnote(client):
    series, race, _ = mcc_series(nhc_realign_to_base=True)
    page = series_page(client, series, race, detail=True)
    assert "Handicaps adjusted with: realignment to base handicaps." in page
    assert "&dagger;" not in page and "†" not in page


def test_with_both_off_the_results_say_nothing_new(client):
    series, race, _ = mcc_series()
    page = series_page(client, series, race, detail=True)
    assert "Handicaps adjusted with" not in page and "capped" not in page


def test_the_csv_download_lists_the_options(client):
    series, _, _ = mcc_series(nhc_cap_extremes=True)
    csv = client.get(reverse("results:series_csv", args=[series.pk])).content.decode()
    assert "Handicaps adjusted with extreme-result capping" in csv
