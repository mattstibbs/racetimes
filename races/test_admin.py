"""The admin is the committee's setup screen, so its pages must at least load."""

import pytest
from django.urls import reverse

from races.testing import enter, make_boat, make_race, make_series

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "url_name",
    ["admin:races_boat_changelist", "admin:races_boat_add",
     "admin:races_series_changelist", "admin:races_series_add"],
)
def test_admin_pages_load(admin_client, url_name):
    assert admin_client.get(reverse(url_name)).status_code == 200


def test_series_page_links_each_race_to_finish_entry(admin_client):
    series = make_series()
    enter(series, make_boat())
    race = make_race(series)
    page = admin_client.get(reverse("admin:races_series_change", args=[series.pk])).content.decode()
    assert f'href="{reverse("races:race_day", args=[race.pk])}"' in page  # the race day page (slice 9)
    assert reverse("results:series", args=[series.pk]) in page  # "View on site"


def test_regatta_with_a_finisher_threshold_is_refused_on_the_form(admin_client):
    response = admin_client.post(
        reverse("admin:races_series_add"),
        {
            "name": "Regatta", "series_type": "REGATTA", "discards": 1, "minimum_finishers": 3,
            "entries-TOTAL_FORMS": 0, "entries-INITIAL_FORMS": 0,
            "races-TOTAL_FORMS": 0, "races-INITIAL_FORMS": 0,
        },
    )
    assert response.status_code == 200
    assert "A regatta has no minimum-finisher threshold" in response.content.decode()
