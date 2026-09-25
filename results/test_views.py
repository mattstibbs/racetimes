"""The public results pages: home, a series, and a boat."""

from datetime import date, time

import pytest
from django.urls import reverse
from django.utils import timezone

from races.models import Finish, Race
from races.testing import (
    enter, make_boat, make_committee, make_member, make_race, make_series, record,
)

pytestmark = pytest.mark.django_db


def get(client, url, htmx_target=None, **params):
    """A page as text. With htmx_target, asked for the way HTMX asks for that part."""
    headers = {"HX-Request": "true", "HX-Target": htmx_target} if htmx_target else {}
    return client.get(url, params, headers=headers).content.decode()


def home(client, **kwargs):
    return get(client, reverse("results:home"), **kwargs)


def series_page(client, series, **kwargs):
    return get(client, reverse("results:series", args=[series.pk]), **kwargs)


def boat_page(client, boat, **kwargs):
    return get(client, reverse("results:boat", args=[boat.pk]), **kwargs)


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
def three_races():
    """Three boats, three races sailed and a fourth scheduled."""
    series = make_series("Wednesday Evenings", discards=1)
    entries = [
        enter(series, make_boat("GBR1", name="Serendipity", base_number="0.950")),
        enter(series, make_boat("GBR2", name="Blue Moon", base_number="0.900")),
        enter(series, make_boat("GBR3", name="Kestrel", base_number="1.000")),
    ]
    races = []
    for number, times in enumerate(
        [("19:00:00", "19:05:00", "18:55:00"),
         ("19:02:00", "19:01:00", "18:58:00"),
         ("19:00:00", "19:10:00", None)],
        start=1,
    ):
        race = make_race(series, number, on=date(2026, 9, number))
        for entry, finish_time in zip(entries, times):
            if finish_time:
                record(race, entry, finish_time)
            else:
                record(race, entry, status="DNF")
        races.append(race)
    races.append(make_race(series, 4, on=date(2026, 9, 4)))
    return series, races, entries


# --- Home ----------------------------------------------------------------------


def test_home_loads_htmx(client):
    assert "js/htmx.min.js" in home(client)


def test_home_lists_series_newest_first(client):
    old = make_series("Spring 2025")
    make_race(old, on=date(2025, 4, 1))
    new = make_series("Autumn 2026")
    make_race(new, on=date(2026, 9, 1))
    unraced = make_series("Christmas 2026")
    page = home(client)
    positions = [page.index(reverse("results:series", args=[s.pk]) + '"') for s in (new, old, unraced)]
    assert positions == sorted(positions)


def test_home_shows_each_series_latest_race_with_its_top_three(client, three_races):
    series, races, _ = three_races
    page = home(client)
    assert "Latest results" in page
    assert f'{reverse("results:series", args=[series.pk])}?race=3"' in page
    assert "Wednesday Evenings, race 3" in page
    # Race 4 is scheduled but not sailed, so it is not the latest result.
    assert "race 4" not in page
    # Race 3's finishers, first to third; the DNF is not on the podium.
    podium = page[page.index('class="podium"'):page.index("</ol>")]
    assert podium.index("GBR1") < podium.index("GBR2")
    assert "GBR3" not in podium


def test_the_latest_results_say_when_a_race_is_provisional(client, race_night):
    series, race, *_ = race_night
    assert "Provisional" in home(client)
    Race.objects.update(published_at=timezone.now())
    assert "Provisional" not in home(client)


def test_home_has_no_latest_results_before_any_race_is_sailed(client):
    make_race(make_series())
    assert "Latest results" not in home(client)


def test_a_member_sees_their_own_boats_on_home(client):
    member = make_member()
    boat = make_boat("GBR42", name="Kittiwake", owner=member)
    make_boat("GBR7", name="Tern")
    assert "My boats" not in home(client).split("</header>")[1]
    client.force_login(member)
    page = home(client).split("</header>")[1]
    assert "My boats" in page
    assert reverse("results:boat", args=[boat.pk]) in page
    assert "Tern" not in page


# --- Finding a boat ------------------------------------------------------------


@pytest.fixture
def fleet():
    return [
        make_boat("GBR 1234", name="Kittiwake", make="Westerly", model="Centaur"),
        make_boat("GBR 77", name="Puffin"),
        make_boat("FRA 12", name="Mouette"),
    ]


@pytest.mark.parametrize("query", ["gbr1234", "GBR 1234", "r12 34", "1234", "kitti", "KITTIWAKE"])
def test_search_matches_sail_numbers_ignoring_case_and_spaces_and_names(client, fleet, query):
    page = home(client, q=query)
    assert reverse("results:boat", args=[fleet[0].pk]) in page
    assert "Puffin" not in page and "Mouette" not in page


def test_search_shows_make_and_model(client, fleet):
    assert "Westerly Centaur" in home(client, q="kitt")


def test_an_unmatched_search_says_so(client, fleet):
    assert "No boats match &ldquo;Nautilus&rdquo;." in home(client, q="Nautilus")


def test_an_empty_search_says_what_to_type_rather_than_listing_every_boat(client, fleet):
    page = home(client, q="   ")
    assert "Type a sail number or a boat's name." in page
    assert "Puffin" not in page


def test_no_search_shows_no_boats(client, fleet):
    page = home(client)
    assert "Puffin" not in page and "Type a sail number" not in page


def test_a_long_list_of_matches_is_cut_short(client):
    for number in range(25):
        make_boat(f"GBR{number:03d}")
    page = home(client, q="gbr")
    assert page.count('href="/boats/') == 20
    assert "Showing the first 20. Type more to narrow it down." in page


def test_search_over_htmx_returns_only_the_matches(client, fleet):
    fragment = home(client, htmx_target="boat-matches", q="puffin")
    assert fragment.startswith('<div id="boat-matches"')
    assert "<html" not in fragment and "Latest results" not in fragment
    assert fragment in home(client, q="puffin")


# --- Series --------------------------------------------------------------------


def test_series_shows_race_results_and_standings(client, race_night):
    page = series_page(client, race_night[0])
    assert "Serendipity" in page and "Blue Moon" in page
    # GBR1: elapsed 1:00:00 on 0.950, corrected 3420 s.
    assert "1:00:00" in page and "0.950" in page and "0:57:00" in page
    # GBR2 has nothing recorded, so it is scored DNC.
    assert "DNC" in page


def test_series_opens_on_the_latest_race_with_results(client, three_races):
    page = series_page(client, three_races[0])
    assert 'id="race-3"' in page
    assert 'id="race-1"' not in page and 'id="race-4"' not in page


def test_series_shows_the_race_asked_for(client, three_races):
    page = series_page(client, three_races[0], race=1)
    assert 'id="race-1"' in page and 'id="race-3"' not in page


def test_a_scheduled_race_shows_as_not_sailed(client, three_races):
    page = series_page(client, three_races[0], race=4)
    assert "Race 4" in page and "No results recorded yet." in page


@pytest.mark.parametrize("race", ["9", "x", "1.0"])
def test_an_unknown_race_is_404(client, three_races, race):
    url = reverse("results:series", args=[three_races[0].pk])
    assert client.get(url, {"race": race}).status_code == 404


def test_an_unknown_series_is_404(client):
    assert client.get(reverse("results:series", args=[999])).status_code == 404


def test_the_race_buttons_mark_the_current_race_and_keep_the_other_choices(client, three_races):
    series, _, entries = three_races
    boat = entries[1].boat
    page = series_page(client, series, race=2, boat=boat.pk)
    assert f'href="?race=1&amp;boat={boat.pk}"' in page
    assert f'href="?race=2&amp;boat={boat.pk}" hx-get="?race=2&amp;boat={boat.pk}" hx-target="#series-body" hx-swap="outerHTML" hx-push-url="true" aria-current="page"' in page


def test_following_a_boat_highlights_it_in_the_standings_and_the_race(client, three_races):
    series, _, entries = three_races
    page = series_page(client, series, boat=entries[1].boat.pk)
    assert page.count('<tr class="followed">') == 2
    for row in page.split('<tr class="followed">')[1:]:
        assert "GBR2 Blue Moon" in row.split("</tr>")[0]
    assert f'<option value="{entries[1].boat.pk}" selected>' in page


def test_follow_a_boat_comes_after_the_results(client, three_races):
    """The standings and the race come first; choosing a boat to follow is below them."""
    page = series_page(client, three_races[0], race=2)
    follow = page.index('class="follow"')
    assert page.index("<h2>Series Standings</h2>") < page.index('class="race-results') < follow
    # Still inside the part HTMX swaps, so following a boat updates the tables above it.
    assert follow < page.index("</div>", page.rindex('id="follow-boat"'))
    assert page.index('id="series-body"') < follow


def test_following_nobody_highlights_nothing(client, three_races):
    page = series_page(client, three_races[0], boat="")
    assert 'class="followed"' not in page


def test_following_a_boat_not_in_the_series_is_404(client, three_races):
    stranger = make_boat("GBR999")
    url = reverse("results:series", args=[three_races[0].pk])
    assert client.get(url, {"boat": stranger.pk}).status_code == 404


def test_more_detail_is_a_link_that_keeps_the_race(client, three_races):
    series = three_races[0]
    page = series_page(client, series, race=2)
    assert 'href="?race=2&amp;detail=1"' in page and "More detail" in page
    assert 'class="race-results"' in page
    page = series_page(client, series, race=2, detail=1)
    assert 'class="race-results all-columns"' in page
    assert 'href="?race=2"' in page and "Less detail" in page


@pytest.mark.parametrize("params", [{}, {"race": 2}, {"race": 1, "boat": "first"}, {"detail": 1}])
def test_over_htmx_the_series_page_returns_just_its_body(client, three_races, params):
    series, _, entries = three_races
    if params.get("boat") == "first":
        params["boat"] = entries[0].boat.pk
    fragment = series_page(client, series, htmx_target="series-body", **params)
    assert fragment.strip().startswith('<div id="series-body">')
    assert "<html" not in fragment
    assert fragment.strip() in series_page(client, series, **params)


def test_a_history_restore_gets_the_whole_page(client, three_races):
    url = reverse("results:series", args=[three_races[0].pk])
    page = client.get(url, headers={
        "HX-Request": "true", "HX-Target": "series-body", "HX-History-Restore-Request": "true",
    }).content.decode()
    assert "<html" in page


def test_caches_are_told_the_fragment_and_the_page_differ(client, three_races):
    response = client.get(reverse("results:series", args=[three_races[0].pk]))
    assert "HX-Request" in response["Vary"] and "HX-Target" in response["Vary"]


def test_series_hides_committee_links_from_the_public(client, race_night):
    series, race, *_ = race_night
    page = series_page(client, series)
    assert (reverse("races:race_day", args=[race.pk]) + "?view=finish") not in page
    assert reverse("races:series_history", args=[series.pk]) not in page


def test_series_shows_committee_links_to_the_committee(client, race_night):
    series, race, *_ = race_night
    client.force_login(make_committee())
    page = series_page(client, series)
    assert f'href="{reverse("races:race_day", args=[race.pk])}"' in page  # the race day page (slice 9)
    assert reverse("races:series_history", args=[series.pk]) in page


def test_a_series_with_no_entries(client):
    series = make_series()
    make_race(series)
    page = series_page(client, series)
    assert "No boats are entered" in page and "Follow a boat" not in page


def test_a_series_with_no_races(client):
    series = make_series()
    enter(series, make_boat())
    page = series_page(client, series)
    assert "No races scheduled yet." in page and "No races sailed yet." in page


def test_results_that_cannot_be_calculated_show_a_message(client, race_night):
    series, race, a, _ = race_night
    # Bypass validation, as a bug or a direct database edit might.
    Finish.objects.filter(race=race).update(finish_time=time(17, 0))
    for page in [series_page(client, series), boat_page(client, a.boat), home(client)]:
        assert "<html" in page
    assert "cannot be calculated" in series_page(client, series)
    assert "cannot be calculated" in boat_page(client, a.boat)


# --- Boat ----------------------------------------------------------------------


def test_the_boat_page_shows_each_race(client, three_races):
    series, races, entries = three_races
    page = boat_page(client, entries[2].boat)
    for number in range(1, 5):
        assert f"?race={number}&amp;boat={entries[2].boat.pk}" in page
    assert "DNF" in page
    assert "No results recorded yet." in page  # race 4


def test_the_boat_page_shows_the_standing(client, three_races):
    series, _, entries = three_races
    from races.scoring import score_series
    standing = next(r for r in score_series(series).standings if r.entry == entries[2])
    page = boat_page(client, entries[2].boat)
    assert f"{standing.position}{['st', 'nd', 'rd'][standing.position - 1]} of 3</strong>" in page


def test_the_boat_page_marks_provisional_races(client, three_races):
    series, races, entries = three_races
    page = boat_page(client, entries[0].boat)
    assert page.count('<abbr title="Provisional">*</abbr>') == 3
    assert "* Provisional: may still change" in page
    Race.objects.update(published_at=timezone.now())
    page = boat_page(client, entries[0].boat)
    assert "Provisional" not in page


def test_the_boat_page_brackets_discarded_points(client, three_races):
    series, _, entries = three_races
    # Three races, one discard: GBR3's DNF (4 points) is its worst.
    assert '<td class="num discarded">(4)</td>' in boat_page(client, entries[2].boat)


def test_the_next_handicap_is_the_last_scored_race_s_next_handicap(client, three_races):
    series, _, entries = three_races
    from races.scoring import score_series
    from races.templatetags.racing import tcf
    last = score_series(series).races[-1]
    for entry in entries:
        expected = tcf(last.for_entry(entry).result.effective_next_tcf)
        assert f"sails race 4 on <strong>{expected}</strong>" in boat_page(client, entry.boat)


def test_after_the_last_race_the_next_handicap_says_so(client, three_races):
    series, races, entries = three_races
    races[3].delete()
    page = boat_page(client, entries[0].boat)
    assert "handicap after race 3, the last race so far:" in page


def test_before_any_race_a_boat_sails_on_its_base_number(client):
    series = make_series("Autumn 2026")
    entry = enter(series, make_boat(base_number="0.964"))
    page = boat_page(client, entry.boat)
    assert "no races scheduled yet." in page
    make_race(series)
    page = boat_page(client, entry.boat)
    assert "sails race 1 on <strong>0.964</strong>, its base number." in page


def test_the_boat_page_lists_series_newest_first(client):
    boat = make_boat()
    old, new, coming = make_series("Spring"), make_series("Summer"), make_series("Autumn")
    for series, on in [(old, date(2026, 4, 1)), (new, date(2026, 7, 1))]:
        enter(series, boat)
        make_race(series, on=on)
    enter(coming, boat)
    page = boat_page(client, boat).split("boat-series")[1:]
    assert [s.split("</a></h2>")[0].rsplit(">", 1)[1] for s in page] == ["Autumn", "Summer", "Spring"]


def test_a_boat_in_no_series_still_has_a_page(client):
    assert "This boat is not entered in any series." in boat_page(client, make_boat())


def test_an_unknown_boat_is_404(client):
    assert client.get(reverse("results:boat", args=[999])).status_code == 404


# --- No owner names on the public pages ------------------------------------------


def test_no_page_shows_an_owner_s_name(client):
    member = make_member(first_name="Pat", last_name="Jones")
    owned = make_boat("GBR42", name="Kittiwake", owner=member)
    typed = make_boat("GBR7", name="Tern", owner_name="M. Visitor")
    series = make_series()
    race = make_race(series)
    for boat in (owned, typed):
        record(race, enter(series, boat), "19:00:00")
    pages = [
        home(client), home(client, q="GBR"), series_page(client, series),
        series_page(client, series, boat=owned.pk, detail=1),
        boat_page(client, owned), boat_page(client, typed),
    ]
    for page in pages:
        assert "Jones" not in page and "Visitor" not in page


def test_find_a_boat_comes_last_on_the_home_page(client, three_races):
    """The latest results and every series come first; the search is at the bottom."""
    page = client.get(reverse("results:home")).content.decode()
    assert page.index('id="latest-results"') < page.index('id="all-series"') < page.index('id="find-a-boat"')
    # Without JavaScript a search reloads the page; the fragment brings it back down to the matches.
    assert 'action="/#find-a-boat"' in page
