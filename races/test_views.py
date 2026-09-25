"""The finish-entry page. The public results pages are tested in results/."""

from datetime import time

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from races.models import Finish, Series
from races.testing import enter, make_boat, make_committee, make_race, make_series, record, start

pytestmark = pytest.mark.django_db


@pytest.fixture
def race_night():
    """A two-boat series with one race: GBR1 finished, GBR2 racing but not yet recorded."""
    series = make_series("Wednesday Evenings")
    a = enter(series, make_boat("GBR1", name="Serendipity", base_number="0.950"))
    b = enter(series, make_boat("GBR2", name="Blue Moon", base_number="0.900"))
    race = make_race(series, start="18:00:00")
    record(race, a, "19:00:00")
    start(race, b)
    return series, race, a, b


@pytest.fixture
def staff_client(client):
    """Logged in as the race committee: staff, in the Race committee group."""
    client.force_login(make_committee())
    return client


def save_url(race, entry):
    return reverse("races:save_finish", args=[race.pk, entry.pk])


def row_data(entry, finish_time="", status="FINISHED", reason=""):
    prefix = f"entry-{entry.pk}"
    return {
        f"{prefix}-finish_time": finish_time,
        f"{prefix}-status": status,
        f"{prefix}-reason": reason,
    }


# --- Finish entry: access --------------------------------------------------


def test_finish_entry_needs_staff(client, race_night):
    _, race, a, _ = race_night
    response = client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish"))
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("races:login"))
    response = client.post(save_url(race, a), row_data(a, "19:10:00"))
    assert response.status_code == 302
    assert Finish.objects.get(entry=a).finish_time.isoformat() == "19:00:00"


def test_non_staff_users_cannot_enter_finishes(client, django_user_model, race_night):
    _, race, *_ = race_night
    client.force_login(django_user_model.objects.create_user("member"))
    assert client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish")).status_code == 403


# --- Finish entry: the page ------------------------------------------------


def test_finish_entry_lists_every_boat_on_the_start_sheet(staff_client, race_night):
    _, race, a, b = race_night
    page = staff_client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish")).content.decode()
    assert save_url(race, a) in page
    assert save_url(race, b) in page
    assert 'value="19:00:00"' in page
    # Slice 9: a boat with nothing recorded is listed under "Still racing".
    assert "Still racing (1)" in page


# --- Finish entry: saving a row --------------------------------------------


def test_saving_a_time_over_htmx_returns_the_row(staff_client, race_night):
    _, race, _, b = race_night
    response = staff_client.post(save_url(race, b), row_data(b, "19:10:00"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    html = response.content.decode()
    assert f'id="finish-{b.pk}"' in html
    # Slice 9: the Finished list shows the finish and elapsed times; corrected
    # times are on the results page.
    assert "19:10:00" in html and "elapsed 1:10:00" in html
    assert "Saved" in html
    assert Finish.objects.get(entry=b).finish_time.isoformat() == "19:10:00"


def test_saving_a_code(staff_client, race_night):
    _, race, _, b = race_night
    staff_client.post(save_url(race, b), row_data(b, status="DNF"), HTTP_HX_REQUEST="true")
    finish = Finish.objects.get(entry=b)
    assert finish.status == "DNF" and finish.finish_time is None


def test_correcting_a_saved_finish_updates_it(staff_client, race_night):
    _, race, a, _ = race_night
    staff_client.post(
        save_url(race, a), row_data(a, "19:05:30", reason="Misread"), HTTP_HX_REQUEST="true"
    )
    assert Finish.objects.get(entry=a).finish_time.isoformat() == "19:05:30"
    assert Finish.objects.filter(entry=a).count() == 1


@pytest.mark.parametrize(
    "finish_time, status, message",
    [
        ("", "FINISHED", "Enter a finish time"),
        ("19:10:00", "DNF", "A boat with a code has no finish time"),
        ("17:59:00", "FINISHED", "The finish must be after the start"),
        ("not a time", "FINISHED", "Enter a valid time"),
    ],
)
def test_an_invalid_row_shows_its_error_and_saves_nothing(
    staff_client, race_night, finish_time, status, message
):
    _, race, _, b = race_night
    response = staff_client.post(
        save_url(race, b), row_data(b, finish_time, status), HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200  # HTMX only swaps in 2xx responses
    assert message in response.content.decode()
    assert not Finish.objects.filter(entry=b).exists()


def test_an_invalid_row_leaves_other_rows_alone(staff_client, race_night):
    _, race, a, b = race_night
    staff_client.post(save_url(race, b), row_data(b, "17:00:00"), HTTP_HX_REQUEST="true")
    assert Finish.objects.get(entry=a).finish_time.isoformat() == "19:00:00"


def test_without_htmx_a_save_redirects_back_to_the_page(staff_client, race_night):
    _, race, _, b = race_night
    response = staff_client.post(save_url(race, b), row_data(b, "19:10:00"))
    assert response.status_code == 302
    assert response["Location"] == (reverse("races:race_day", args=[race.pk]) + "?view=finish")


def test_without_htmx_an_error_redisplays_the_page(staff_client, race_night):
    _, race, a, b = race_night
    response = staff_client.post(save_url(race, b), row_data(b, "17:00:00"))
    html = response.content.decode()
    assert "The finish must be after the start" in html
    assert save_url(race, a) in html  # the rest of the page is still there


def test_a_boat_outside_the_series_is_404(staff_client, race_night):
    _, race, *_ = race_night
    outsider = enter(make_series("Other"), make_boat("GBR999"))
    response = staff_client.post(save_url(race, outsider), row_data(outsider, "19:10:00"))
    assert response.status_code == 404


def test_saving_needs_post(staff_client, race_night):
    _, race, a, _ = race_night
    assert staff_client.get(save_url(race, a)).status_code == 405


# --- Races that are not scored: the pages explain instead of crashing ------


@pytest.fixture
def regatta_night(race_night):
    series, race, a, b = race_night
    series.series_type = Series.SeriesType.REGATTA
    series.save()
    record(race, b, "19:05:00")
    return series, race, a, b


def test_a_scheduled_regatta_race_does_not_break_the_pages(staff_client, regatta_night):
    series, _, a, _ = regatta_night
    race_2 = make_race(series, 2)
    assert staff_client.get(reverse("results:series", args=[series.pk])).status_code == 200
    page = staff_client.get((reverse("races:race_day", args=[race_2.pk]) + "?view=finish"))
    assert page.status_code == 200
    assert "No boats are on the" in page.content.decode()


def test_saving_only_a_code_in_a_regatta_race_explains_the_wait(staff_client, regatta_night):
    series, _, a, _ = regatta_night
    race_2 = make_race(series, 2)
    start(race_2, a)
    response = staff_client.post(
        save_url(race_2, a), row_data(a, status="DNF"), HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    html = response.content.decode()
    # Slice 9: the whole Finishing panel comes back, the race's note included.
    assert 'id="finish-panel"' in html and 'id="race-note"' in html
    assert "at least one boat has a finish time" in html
    assert Finish.objects.get(race=race_2, entry=a).status == "DNF"

    page = staff_client.get(reverse("results:series", args=[series.pk]), {"race": 2}).content.decode()
    assert "at least one boat has a finish time" in page


def test_the_error_page_is_plain_and_standalone():
    html = render_to_string("500.html")
    assert "Something went wrong" in html
    assert "nothing was saved" in html
