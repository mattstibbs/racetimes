"""Slice 21: sharing published results and final standings to WhatsApp.

The share buttons are ordinary links to ``https://wa.me/?text=<message>``, so
these tests read the link off the page and decode the message from it.
"""

import html
import re
from urllib.parse import unquote

import pytest
from django.urls import reverse

from races import sharing
from races.models import Finish
from races.scoring import score_series
from races.testing import (
    declare,
    enter,
    make_boat,
    make_club,
    make_committee,
    make_member,
    make_race,
    make_series,
    publish,
    record,
    start,
)

pytestmark = pytest.mark.django_db

SHARE = "Share to WhatsApp"
SHARE_UPDATED = "Share updated results to WhatsApp"
SHARE_FINAL = "Share final standings to WhatsApp"


@pytest.fixture
def club():
    """A sailed race: two member-owned boats, a visitor, and a boat that retired."""
    pat = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    series = make_series("Spring & Summer #1")
    kittiwake = make_boat("GBR 42", name="Kittiwake", base_number="0.805", owner=pat)
    puffin = make_boat("GBR77", name="Puffin", base_number="0.842")
    tern = make_boat("GBR7", name="Tern", base_number="0.900", owner_name="M. Visitor")
    elan = make_boat("FRA 5", name="Élan", base_number="0.900")
    entries = [enter(series, boat) for boat in (kittiwake, puffin, tern, elan)]
    race = make_race(series, 1, start="18:30:00")
    for entry, finish in zip(
        entries[:3], ["19:31:12", "19:40:05", "19:28:40"], strict=True
    ):
        record(race, entry, finish)
    record(race, entries[3], status=Finish.Status.DNF)
    return {"series": series, "race": race, "entries": entries}


@pytest.fixture
def committee(client):
    client.force_login(make_committee())


def race_day(client, race, **headers):
    url = reverse("races:race_day", args=[race.pk])
    return client.get(url, {"view": "finish"}, **headers).content.decode()


def final_page(client, series):
    return client.get(reverse("races:final", args=[series.pk])).content.decode()


def shared(page, label):
    """The message behind the share button with this label, or None if there isn't one."""
    for href, text in re.findall(
        r'<a class="button secondary share-whatsapp" href="([^"]+)"[^>]*><img[^>]*>([^<]+)</a>',
        page,
    ):
        if text == label:
            url = html.unescape(href)
            assert url.startswith("https://wa.me/?text=")
            return unquote(url.removeprefix("https://wa.me/?text="))
    return None


def correct(client, race, entry, finish_time):
    prefix = f"entry-{entry.pk}"
    return client.post(
        reverse("races:save_finish", args=[race.pk, entry.pk]),
        {
            f"{prefix}-finish_time": finish_time,
            f"{prefix}-status": "FINISHED",
            f"{prefix}-reason": "Misread the sheet",
        },
        HTTP_HX_REQUEST="true",
    ).content.decode()


# --- When the buttons show ---------------------------------------------------------------


def test_no_share_button_while_a_race_is_provisional(client, committee, club):
    page = race_day(client, club["race"])
    assert "Publish results" in page
    assert "share-whatsapp" not in page


def test_a_published_race_offers_share_to_whatsapp(client, committee, club):
    publish(club["race"])
    page = race_day(client, club["race"])
    assert shared(page, SHARE) is not None
    assert shared(page, SHARE_UPDATED) is None


def test_no_share_button_when_sending_the_results_failed(client, committee, club):
    race = club["race"]
    publish(race)
    race.results_sent_at = None
    race.save()
    assert "share-whatsapp" not in race_day(client, race)


def test_no_share_button_while_a_boat_on_the_start_sheet_has_nothing_recorded(
    client, committee, club
):
    publish(club["race"])
    late = enter(club["series"], make_boat("GBR 1", name="Latecomer"))
    start(club["race"], late)
    assert "share-whatsapp" not in race_day(client, club["race"])


def test_a_correction_swaps_in_share_updated_results(client, committee, club):
    publish(club["race"])
    panel = correct(client, club["race"], club["entries"][0], "19:32:00")
    assert "<html" not in panel  # the HTMX panel, not a whole page
    assert "Send updated results" in panel
    message = shared(panel, SHARE_UPDATED)
    assert "results have been corrected" in message
    assert shared(panel, SHARE) is None


def test_a_final_series_offers_its_final_standings(client, committee, club):
    assert "share-whatsapp" not in final_page(client, club["series"])
    publish(club["race"])
    declare(client, club["series"])
    assert shared(final_page(client, club["series"]), SHARE_FINAL) is not None


def test_the_race_day_page_of_a_final_series_has_no_share_button(
    client, committee, club
):
    # The publishing card isn't shown once the series is locked; the final
    # results page shares the standings instead.
    publish(club["race"])
    declare(client, club["series"])
    assert "share-whatsapp" not in race_day(client, club["race"])


@pytest.mark.parametrize("who", ["public", "member"])
def test_the_public_and_members_never_see_a_share_button(client, club, who):
    publish(club["race"])
    if who == "member":
        client.force_login(make_member("sam@example.com"))
    for url in (
        reverse("races:race_day", args=[club["race"].pk]) + "?view=finish",
        reverse("races:final", args=[club["series"].pk]),
        reverse("results:series", args=[club["series"].pk]),
        reverse("results:home"),
    ):
        response = client.get(url)
        assert "share-whatsapp" not in response.content.decode()
        assert "wa.me" not in response.content.decode()


# --- The messages ------------------------------------------------------------------------


def test_the_race_message_lists_every_place_and_links_to_the_race(
    client, committee, club
):
    publish(club["race"])
    series = club["series"]
    assert shared(race_day(client, club["race"]), SHARE) == (
        "*Spring & Summer #1, race 1* (Wed 23 Sep): results are published.\n"
        "\n"
        "1. Kittiwake (GBR 42)\n"
        "2. Tern (GBR7)\n"
        "3. Puffin (GBR77)\n"
        "DNF: Élan (FRA 5)\n"
        "\n"
        f"Full results: http://testserver/series/{series.pk}/?race=1"
    )


def test_boats_tied_on_a_place_share_it(rf, club):
    series = make_series("Tied")
    one, two = (
        enter(series, make_boat(sail, name=name, base_number="0.900"))
        for sail, name in (("GBR 1", "Alpha"), ("GBR 2", "Bravo"))
    )
    race = make_race(series, 1, start="18:30:00")
    record(race, one, "19:30:00")
    record(race, two, "19:30:00")
    message = sharing.race_message(race, score_series(series), rf.get("/"))
    assert "1. Alpha (GBR 1)\n1. Bravo (GBR 2)\n" in message


def test_a_race_with_nothing_to_show_just_says_so_with_the_link(rf):
    series = make_series("Calm")
    race = make_race(series, 1)
    enter(series, make_boat("GBR 1", name="Alpha"))  # nobody on the start sheet
    results = score_series(series)
    assert results.for_race(race) is None
    message = sharing.race_message(race, results, rf.get("/"))
    assert message == (
        "*Calm, race 1* (Wed 23 Sep): results are published.\n"
        "\n"
        f"Full results: http://testserver/series/{series.pk}/?race=1"
    )


def test_the_final_message_lists_every_boat_with_its_points(client, committee, club):
    race_2 = make_race(club["series"], 2, start="18:30:00")
    for entry in club["entries"]:
        record(race_2, entry, "19:35:00")
    publish(club["race"], race_2)
    declare(client, club["series"])
    message = shared(final_page(client, club["series"]), SHARE_FINAL)
    lines = message.split("\n")
    assert lines[0] == "*Spring & Summer #1* is final."
    standings = score_series(club["series"]).standings
    assert len(standings) == 4
    assert lines[2:6] == [
        f"{row.position}. {row.entry.boat}, {row.total:g} pt{'' if row.total == 1 else 's'}"
        for row in standings
    ]
    assert lines[2] == "1. Kittiwake (GBR 42), 1 pt"  # one point is singular
    assert lines[-1] == (
        f"Final standings: http://testserver/series/{club['series'].pk}/"
    )


def test_messages_never_name_an_owner(client, committee, club):
    publish(club["race"])
    declare(client, club["series"])
    for message in (
        shared(final_page(client, club["series"]), SHARE_FINAL),
        sharing.race_message(
            club["race"], score_series(club["series"]), client.get("/").wsgi_request
        ),
    ):
        assert "Pat" not in message and "Jones" not in message
        assert "pat@example.com" not in message and "Visitor" not in message


def test_the_link_is_the_clubs_own_address(client, settings):
    settings.SINGLE_CLUB = ""
    harbour = make_club("harbour", "Harbour Sailing Club")
    client.force_login(make_committee("officer@harbour.example", club=harbour))
    series = make_series("Harbour Winter", club=harbour)
    race = make_race(series, 3, start="18:30:00")
    boat = make_boat("GBR 9", name="Bittern", club=harbour)
    record(race, enter(series, boat), "19:30:00")
    publish(race)
    page = client.get(
        reverse("races:race_day", args=[race.pk]),
        {"view": "finish"},
        HTTP_HOST="harbour.localhost",
    ).content.decode()
    message = shared(page, SHARE)
    assert message.endswith(
        f"Full results: http://harbour.localhost/series/{series.pk}/?race=3"
    )
    assert "Demo" not in message


# --- The link --------------------------------------------------------------------------


def test_the_url_decodes_back_to_exactly_the_message():
    message = "*Spring & Summer #1*: 1. Élan (FRA 5)\n2. Kestrel?\n\nhttps://x/?race=1"
    url = sharing.whatsapp_url(message)
    assert url.startswith("https://wa.me/?text=")
    encoded = url.removeprefix("https://wa.me/?text=")
    assert not set("&#*? \n/:") & set(encoded)
    assert unquote(encoded) == message


def test_the_button_opens_whatsapp_in_a_new_tab_without_telling_it_this_page(
    client, committee, club
):
    publish(club["race"])
    page = race_day(client, club["race"])
    button = re.search(r'<a class="button secondary share-whatsapp"[^>]*>', page)[0]
    assert 'target="_blank"' in button and 'rel="noopener noreferrer"' in button
    # WhatsApp's glyph is the site's own file, beside the words.
    assert '<img src="/static/img/whatsapp.svg" alt=""' in page
