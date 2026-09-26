"""Slice 15: a boat is named "Name (Sail number)", except on the race day page."""

import re

import pytest
from django.urls import reverse

from races.test_race_day import (  # noqa: F401 (fixtures)
    clock,
    committee,
    local,
    racing,
    tap,
)
from races.testing import enter, make_boat, make_series

pytestmark = pytest.mark.django_db


def test_a_boat_is_its_name_then_its_sail_number():
    assert str(make_boat("GBR 1234", name="Kittiwake")) == "Kittiwake (GBR 1234)"


def test_a_boat_with_no_name_is_its_sail_number():
    assert str(make_boat("GBR 1234", name="")) == "GBR 1234"


def test_the_race_day_page_names_boats_sail_number_first(
    client, committee, racing, clock
):  # noqa: F811
    clock(when=local(19, 5, 31))
    html = tap(client, racing["race"], racing["kittiwake"]).content.decode()
    assert "GBR42 Kittiwake finished at 19:05:31." in html
    assert "<strong>GBR42</strong> Kittiwake" in html
    assert "Kittiwake (GBR42)" not in html


def test_follow_a_boat_lists_boats_by_name(client):
    series = make_series()
    for sail_number, name in [
        ("GBR1", "Zephyr"),
        ("GBR2", "avocet"),
        ("GBR3", ""),
        ("GBR4", "Merlin"),
    ]:
        enter(series, make_boat(sail_number, name=name))
    html = client.get(reverse("results:series", args=[series.pk])).content.decode()
    picker = html[html.index('id="follow-boat"') : html.index("</select>")]
    listed = re.findall(r'<option value="\d+">([^<]*)</option>', picker)
    # Case doesn't matter; a boat with no name sorts by its sail number.
    assert listed == ["avocet (GBR2)", "GBR3", "Merlin (GBR4)", "Zephyr (GBR1)"]


def test_pages_never_wrap_a_boat_inside_its_sail_number(client):
    from races.templatetags.racing import boat

    assert (
        boat(make_boat("GBR 1234", name="Serendipity")) == "Serendipity (GBR&nbsp;1234)"
    )
    assert boat(make_boat("IRL 7", name="")) == "IRL&nbsp;7"
    assert (
        boat(make_boat("GBR 1", name="<b>")) == "&lt;b&gt; (GBR&nbsp;1)"
    )  # still escaped
    kittiwake = make_boat("GBR 42", name="Kittiwake")
    html = client.get(reverse("results:boat", args=[kittiwake.pk])).content.decode()
    assert "<h1>Kittiwake (GBR&nbsp;42)</h1>" in html
