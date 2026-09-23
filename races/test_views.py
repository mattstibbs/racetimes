"""The results page and the finish-entry page."""

import pytest
from django.urls import reverse

from races.models import Finish
from races.testing import enter, make_boat, make_race, make_series, record

pytestmark = pytest.mark.django_db


@pytest.fixture
def race_night():
    """A two-boat series with one race: GBR1 finished, GBR2 not yet recorded."""
    series = make_series("Wednesday Evenings")
    a = enter(series, make_boat("GBR1", name="Serendipity", base_number="0.950"))
    b = enter(series, make_boat("GBR2", name="Blue Moon", base_number="0.900"))
    race = make_race(series, start="18:00:00")
    record(race, a, "19:00:00")
    return series, race, a, b


@pytest.fixture
def staff_client(client, django_user_model):
    user = django_user_model.objects.create_user("officer", is_staff=True)
    client.force_login(user)
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


# --- Home and results ------------------------------------------------------


def test_home_lists_series(client, race_night):
    series, *_ = race_night
    page = client.get(reverse("races:home")).content.decode()
    assert reverse("races:series_results", args=[series.pk]) in page
    assert "Wednesday Evenings" in page


def test_results_are_public(client, race_night):
    series, *_ = race_night
    assert client.get(reverse("races:series_results", args=[series.pk])).status_code == 200


def test_results_show_race_results_and_standings(client, race_night):
    series, race, a, b = race_night
    page = client.get(reverse("races:series_results", args=[series.pk])).content.decode()
    assert "Serendipity" in page and "Blue Moon" in page
    # GBR1: elapsed 1:00:00 on 0.950, corrected 3420 s.
    assert "1:00:00" in page
    assert "0.950" in page
    assert "0:57:00" in page
    # GBR2 has nothing recorded, so it is scored DNC.
    assert "DNC" in page


def test_results_hide_finish_entry_link_from_the_public(client, race_night):
    series, race, *_ = race_night
    page = client.get(reverse("races:series_results", args=[series.pk])).content.decode()
    assert reverse("races:finish_entry", args=[race.pk]) not in page


def test_results_show_finish_entry_link_to_staff(staff_client, race_night):
    series, race, *_ = race_night
    page = staff_client.get(reverse("races:series_results", args=[series.pk])).content.decode()
    assert reverse("races:finish_entry", args=[race.pk]) in page


def test_results_for_a_series_with_no_entries(client):
    series = make_series()
    make_race(series)
    page = client.get(reverse("races:series_results", args=[series.pk])).content.decode()
    assert "No boats are entered" in page


def test_results_for_an_unknown_series_is_404(client):
    assert client.get(reverse("races:series_results", args=[999])).status_code == 404


# --- Finish entry: access --------------------------------------------------


def test_finish_entry_needs_staff(client, race_night):
    _, race, a, _ = race_night
    response = client.get(reverse("races:finish_entry", args=[race.pk]))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]
    response = client.post(save_url(race, a), row_data(a, "19:10:00"))
    assert response.status_code == 302
    assert Finish.objects.get(entry=a).finish_time.isoformat() == "19:00:00"


def test_non_staff_users_cannot_enter_finishes(client, django_user_model, race_night):
    _, race, *_ = race_night
    client.force_login(django_user_model.objects.create_user("member"))
    assert client.get(reverse("races:finish_entry", args=[race.pk])).status_code == 302


# --- Finish entry: the page ------------------------------------------------


def test_finish_entry_lists_every_entered_boat(staff_client, race_night):
    _, race, a, b = race_night
    page = staff_client.get(reverse("races:finish_entry", args=[race.pk])).content.decode()
    assert save_url(race, a) in page
    assert save_url(race, b) in page
    assert 'value="19:00:00"' in page
    assert "Nothing saved: scored DNC" in page


# --- Finish entry: saving a row --------------------------------------------


def test_saving_a_time_over_htmx_returns_the_row(staff_client, race_night):
    _, race, _, b = race_night
    response = staff_client.post(save_url(race, b), row_data(b, "19:10:00"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    html = response.content.decode()
    assert f'id="finish-{b.pk}"' in html
    # Elapsed 1:10:00 x 0.900 = 1:03:00 corrected.
    assert "1:10:00" in html and "1:03:00" in html
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
    assert response["Location"] == reverse("races:finish_entry", args=[race.pk])


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
