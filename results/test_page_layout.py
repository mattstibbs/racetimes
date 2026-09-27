"""Slice 15: where the series page's links and notes go, and when they show."""

import pytest
from django.urls import reverse
from django.utils import timezone

from races import final
from races.scoring import engine_outcome
from races.testing import (
    enter,
    make_boat,
    make_committee,
    make_race,
    make_series,
    record,
)

pytestmark = pytest.mark.django_db


def sailed_series(**fields):
    series = make_series(**fields)
    race = make_race(series)
    for sail_number, finish_time in [("GBR1", "19:00:00"), ("GBR2", "19:05:00")]:
        record(race, enter(series, make_boat(sail_number)), finish_time)
    return series, race


def page(client, series, query=""):
    html = client.get(
        reverse("results:series", args=[series.pk]) + query
    ).content.decode()
    return html.split("<main", 1)[1]


def as_committee(client):
    client.force_login(make_committee())
    return client


# --- Item 3: the links -------------------------------------------------------------------------


def test_the_csv_download_is_at_the_bottom_for_everyone(client):
    series, _ = sailed_series()
    html = page(client, series)
    csv = reverse("results:series_csv", args=[series.pk])
    assert html.count(csv) == 1
    assert html.index("Follow a boat") < html.index(csv)
    assert (
        "Series history" not in html
        and "Race history" not in html
        and "Finalise results" not in html
    )


def test_the_committee_s_links(client):
    series, race = sailed_series()
    html = page(as_committee(client), series)
    history = reverse("races:series_history", args=[series.pk])
    # "Finalise results" under the title, before the standings.
    assert html.index("Finalise results") < html.index("Series Standings")
    # "Race history" under the race's table; "Series history" at the bottom, after the CSV link.
    assert html.index("</table>", html.index("race-results")) < html.index(
        f'{history}?race={race.pk}">Race history'
    )
    assert (
        html.index("Follow a boat")
        < html.index("Download (CSV)")
        < html.index(f'{history}">Series history')
    )
    # The old names are gone.
    assert ">History<" not in html and ">Final results<" not in html


def test_a_final_series_offers_to_reopen_the_results(client):
    series, _ = sailed_series()
    series.final_results = final.dump(engine_outcome(series))
    series.declared_final_at = timezone.now()
    series.save()
    html = page(as_committee(client), series)
    assert "Reopen results" in html and "Finalise results" not in html


# --- Item 4: the discards note -----------------------------------------------------------------


@pytest.mark.parametrize("discards, shown", [(0, False), (1, True)])
def test_the_discards_note_shows_only_when_the_series_has_discards(
    client, discards, shown
):
    series, _ = sailed_series(discards=discards)
    note = "<em>Discarded scores are in brackets.</em>"
    assert (note in page(client, series)) is shown
    boat = series.entries.first().boat
    assert (
        note in client.get(reverse("results:boat", args=[boat.pk])).content.decode()
    ) is shown


# --- Item 5: the capping footnote --------------------------------------------------------------


@pytest.mark.parametrize("detail", [False, True])
def test_the_capping_footnote_is_its_own_line_and_only_with_more_detail(client, detail):
    series, race = sailed_series(nhc_cap_extremes=True)
    html = page(
        client, series, f"?race={race.number}" + ("&detail=1" if detail else "")
    )
    assert (
        '<p class="muted">Handicaps adjusted with: extreme-result capping.</p>' in html
    )
    footnote = '<p class="muted">&dagger; Result capped as extreme when working out the next handicap.</p>'
    assert (footnote in html) is detail
    assert "shown with More detail" not in html
