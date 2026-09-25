"""Slice 11: one club never sees another's data. The acceptance criterion that matters most.

Two clubs are built with overlapping data: the same sail numbers, and one
person owning a boat at each. Every boat, series and request name is unique
to its club, so any of Harbour's names turning up at Demo Club is a leak.

- Every URL the site has is requested at Demo Club as each role, and must
  show nothing of Harbour's. The test fails if a URL is added without being
  covered here.
- Every URL that takes an id is tried with Harbour's ids at Demo Club's
  address, and must be a 404 that writes nothing.
- The admin, emails and the CSV download are checked the same way.
- A source check fails if a page queries a club's rows without for_club.

Roles are still global until part 2 of slice 11, so the committee here is
the committee of whichever club's address it's on.
"""

import re
from pathlib import Path

import pytest
from django.core import mail
from django.urls import get_resolver, reverse
from django.utils import timezone

from races import notifications
from races.models import (
    Boat, BoatRequest, Club, EntryRequest, Finish, RaceEntry, ScoringChange, Series, SeriesEntry,
)
from races.testing import (
    default_club, enter, make_boat, make_club, make_committee, make_member, make_race, make_series, record,
)

pytestmark = pytest.mark.django_db

DEMO, HARBOUR = "demo.localhost", "harbour.localhost"

# Every name below belongs to Harbour only. None may appear at Demo Club.
HARBOUR_ONLY = ["Bittern", "Brant", "Booby", "Harbour Winter", "Black Tern", "bea@example.com", "Harbour Sailing Club"]


@pytest.fixture
def run_on_commit(monkeypatch):
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())


def build(club, prefix, names, series_name, owner, shared):
    """One club's data: a series with two races, three boats, requests and history."""
    series = make_series(series_name, club=club)
    first, second, third = names
    entries = [
        enter(series, make_boat("GBR42", name=first, base_number="0.805", owner=owner, club=club)),
        enter(series, make_boat("GBR7", name=second, base_number="0.900", club=club)),
        enter(series, make_boat("GBR99", name=third, base_number="0.850", owner=shared, club=club)),
    ]
    race_1, race_2 = make_race(series, 1), make_race(series, 2)
    for entry, time in zip(entries, ("19:05:31", "19:07:02", "19:03:10")):
        record(race_1, entry, time)
    record(race_2, entries[0], "19:01:00")
    now = timezone.now()
    race_1.published_at = race_1.results_sent_at = now
    race_1.save()
    requests = {
        "register": BoatRequest.objects.create(club=club, kind="REGISTER", sail_number="GBR5",
                                              name=f"{prefix} Tern", base_number="0.9", requested_by=shared),
        "claim": BoatRequest.objects.create(club=club, kind="CLAIM", boat=entries[1].boat, requested_by=shared),
        "entry": EntryRequest.objects.create(series=make_series(f"{series_name} Two", club=club),
                                             boat=entries[2].boat, requested_by=shared),
    }
    ScoringChange.objects.create(club=club, series=series, race=race_1, kind="FINISH", action="CHANGED",
                                 description=f"{first}, Race 1", is_correction=True, reason="Protest")
    return {"club": club, "series": series, "entries": entries, "races": [race_1, race_2], "requests": requests}


@pytest.fixture
def clubs():
    harbour = make_club("harbour", "Harbour Sailing Club", contact_email="sec@harbour.example")
    shared = make_member("shared@example.com", first_name="Sam")
    demo = build(default_club(), "Arctic", ["Avocet", "Auk", "Albatross"], "Autumn Series",
                 make_member("ann@example.com", first_name="Ann"), shared)
    harbour_data = build(harbour, "Black", ["Bittern", "Brant", "Booby"], "Harbour Winter",
                         make_member("bea@example.com", first_name="Bea"), shared)
    return {"demo": demo, "harbour": harbour_data, "shared": shared}


def urls_for(data, kind=None):
    """Every URL name the site has, with arguments drawn from one club's data."""
    series, (race_1, _), (e1, _, e3) = data["series"], data["races"], data["entries"]
    requests = data["requests"]
    boat = e3.boat  # the shared member's boat, so member pages find it
    return {
        "races:change_boat": [boat.pk], "races:claim_boat": [e1.boat.pk],
        "races:decide_request": ["boat", requests["register"].pk], "races:declare_final": [series.pk],
        "races:enter_series": [boat.pk], "races:final": [series.pk], "races:finish_entry": [race_1.pk],
        "races:login": [], "races:logout": [], "races:my_boats": [], "races:password_reset": [],
        "races:password_reset_complete": [], "races:password_reset_confirm": ["x", "y"],
        "races:password_reset_done": [], "races:ping": [], "races:publish_results": [race_1.pk],
        "races:race_day": [race_1.pk], "races:register_boat": [], "races:reopen_series": [series.pk],
        "races:requests": [], "races:save_finish": [race_1.pk, e1.pk],
        "races:save_start_sheet_row": [race_1.pk, e1.pk], "races:send_final": [series.pk],
        "races:series_history": [series.pk], "races:signup": [], "races:start_sheet": [race_1.pk],
        "races:tap_finish": [race_1.pk, e1.pk], "races:undo_finish": [race_1.pk, e1.pk],
        "races:withdraw_request": ["boat", requests["claim"].pk],
        "results:boat": [e1.boat.pk], "results:home": [], "results:series": [series.pk],
        "results:series_csv": [series.pk],
    }


def all_url_names():
    resolver = get_resolver()
    return {
        f"{namespace}:{name}"
        for namespace in ("races", "results")
        for name in resolver.namespace_dict[namespace][1].reverse_dict
        if isinstance(name, str)
    }


def test_every_url_is_covered(clubs):
    assert set(urls_for(clubs["demo"])) == all_url_names()


def leaks(html):
    return [name for name in HARBOUR_ONLY if name in html]


def log_in(client, role, clubs):
    if role == "member":
        client.force_login(clubs["shared"])
    elif role == "committee":
        client.force_login(make_committee())


# --- Every page, as every role, shows only its own club ------------------------------------


@pytest.mark.parametrize("role", ["public", "member", "committee"])
def test_no_page_at_demo_club_shows_harbours_data(client, clubs, role):
    log_in(client, role, clubs)
    extras = {"results:home": "?q=GBR", "races:race_day": "?view=start", "results:series": "?detail=1"}
    shown = {}
    for name, args in urls_for(clubs["demo"]).items():
        url = reverse(name, args=args) + extras.get(name, "")
        response = client.get(url, HTTP_HOST=DEMO)
        if response.status_code == 200:
            shown[name] = leaks(response.content.decode())
        # The race day page's other view, and the boat search as a fragment.
    for url, headers in [
        (reverse("races:race_day", args=[clubs["demo"]["races"][0].pk]) + "?view=finish", {}),
        (reverse("results:home") + "?q=GBR", {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "boat-matches"}),
    ]:
        response = client.get(url, HTTP_HOST=DEMO, **headers)
        if response.status_code == 200:
            shown[url] = leaks(response.content.decode())
    assert shown and all(found == [] for found in shown.values()), {k: v for k, v in shown.items() if v}
    assert "results:series_csv" in shown and "results:home" in shown


def test_a_member_of_both_clubs_sees_only_this_clubs_boats_and_requests(client, clubs):
    client.force_login(clubs["shared"])
    page = client.get(reverse("races:my_boats"), HTTP_HOST=DEMO).content.decode()
    # Their boat here, and their entry request for this club's second series.
    assert "Albatross" in page and "Autumn Series Two" in page
    assert leaks(page) == []
    page = client.get(reverse("races:my_boats"), HTTP_HOST=HARBOUR).content.decode()
    assert "Booby" in page and "Harbour Winter Two" in page
    assert "Albatross" not in page and "Autumn Series" not in page


def test_the_committees_requests_and_notices_are_only_this_clubs(client, clubs):
    client.force_login(make_committee())
    page = client.get(reverse("races:requests"), HTTP_HOST=DEMO).content.decode()
    assert "Arctic Tern" in page and leaks(page) == []
    # Two boat requests and one entry request are waiting at each club; the
    # admin's front page counts only this club's.
    index = client.get(reverse("admin:index"), HTTP_HOST=DEMO).content.decode()
    assert "2 boat requests and 1 entry request are waiting" in index  # not 4 and 2


# --- Another club's ids are a 404, and write nothing ----------------------------------------


def counts():
    return [model.objects.count() for model in (Boat, Series, SeriesEntry, Finish, RaceEntry, BoatRequest,
                                                 EntryRequest, ScoringChange)]


@pytest.mark.parametrize("role", ["member", "committee"])
def test_harbours_ids_are_not_found_at_demo_club(client, clubs, role):
    log_in(client, role, clubs)
    harbour_urls = urls_for(clubs["harbour"])
    demo_urls = urls_for(clubs["demo"])
    before = counts()
    checked = []
    for name, args in harbour_urls.items():
        if args == demo_urls[name] or not args or name == "races:password_reset_confirm":
            continue  # no club object in the address
        url = reverse(name, args=args)
        for method in (client.get, client.post):
            response = method(url, HTTP_HOST=DEMO)
            if role == "member" and response.status_code == 302 and "login" in response["Location"]:
                continue  # a committee page: the member is sent to log in before any lookup
            assert response.status_code in (404, 405), (name, method.__name__, response.status_code)
            if response.status_code == 404:
                checked.append(name)
    assert counts() == before
    assert "results:series" in checked and "races:change_boat" in checked
    if role == "committee":
        assert {"races:save_finish", "races:tap_finish", "races:decide_request", "races:declare_final"} <= set(checked)


def test_a_demo_race_with_a_harbour_entry_is_not_found(client, clubs):
    client.force_login(make_committee())
    race = clubs["demo"]["races"][0]
    entry = clubs["harbour"]["entries"][0]
    before = counts()
    for name in ("races:save_finish", "races:tap_finish", "races:undo_finish", "races:save_start_sheet_row"):
        response = client.post(reverse(name, args=[race.pk, entry.pk]), HTTP_HOST=DEMO)
        assert response.status_code == 404, name
    assert counts() == before


# --- The admin -------------------------------------------------------------------------------


def test_the_admin_lists_only_this_clubs_rows(client, clubs):
    client.force_login(make_committee())
    for model in ("boat", "series", "boatrequest", "entryrequest"):
        page = client.get(reverse(f"admin:races_{model}_changelist"), HTTP_HOST=DEMO).content.decode()
        assert leaks(page) == [], model
    page = client.get(reverse("admin:races_series_change", args=[clubs["demo"]["series"].pk]),
                      HTTP_HOST=DEMO).content.decode()
    assert leaks(page) == []


def test_the_admin_wont_open_another_clubs_rows(client, clubs):
    client.force_login(make_committee())
    for model, obj in (("boat", clubs["harbour"]["entries"][0].boat), ("series", clubs["harbour"]["series"])):
        response = client.get(reverse(f"admin:races_{model}_change", args=[obj.pk]), HTTP_HOST=DEMO, follow=True)
        page = response.content.decode()
        assert "doesn’t exist" in page and leaks(page) == []


def test_the_admins_boat_search_offers_only_this_clubs_boats(client, clubs):
    client.force_login(make_committee())
    response = client.get(reverse("admin:autocomplete"), {
        "app_label": "races", "model_name": "seriesentry", "field_name": "boat", "term": "GBR",
    }, HTTP_HOST=DEMO)
    names = {result["text"] for result in response.json()["results"]}
    assert names and all(name.split(" ", 1)[1] in ("Avocet", "Auk", "Albatross") for name in names)


def test_the_admin_wont_enter_another_clubs_boat(client, clubs):
    from races.test_audit import series_form
    client.force_login(make_committee())
    series = clubs["demo"]["series"]
    data = series_form(series)
    data.update({"entries-TOTAL_FORMS": 4, "entries-3-series": series.pk,
                 "entries-3-boat": clubs["harbour"]["entries"][0].boat.pk})
    before = counts()
    response = client.post(reverse("admin:races_series_change", args=[series.pk]), data, HTTP_HOST=DEMO)
    assert response.status_code == 200 and counts() == before


# --- Emails ------------------------------------------------------------------------------------


def test_publishing_at_one_club_emails_only_its_owners(client, clubs, run_on_commit):
    client.force_login(make_committee())
    race_2 = clubs["demo"]["races"][1]
    for entry in clubs["demo"]["entries"][1:]:
        record(race_2, entry, "19:10:00")
    client.post(reverse("races:publish_results", args=[race_2.pk]), HTTP_HOST=DEMO)
    assert sorted(m.to[0] for m in mail.outbox) == ["ann@example.com", "shared@example.com"]
    assert all(leaks(m.subject + m.body) == [] for m in mail.outbox)


# --- The code keeps to for_club -----------------------------------------------------------------

CLUB_MODELS = "Boat|Series|SeriesEntry|Race|RaceEntry|Finish|ScoringChange|BoatRequest|EntryRequest"
# The modules that answer requests. Everything they look up must start from the
# request's club. Helper modules (scoring, audit, final, race_day...) are handed
# rows these have already found, so they don't need to.
REQUEST_MODULES = [
    "races/views.py", "races/member_views.py", "races/admin.py", "races/context_processors.py",
    "results/views.py", "results/export.py", "races/forms.py", "races/approvals.py",
]


def test_every_page_looks_up_club_rows_through_for_club():
    root = Path(__file__).resolve().parent.parent
    # Creating a row, or an empty queryset, can't show another club's data.
    unscoped = re.compile(rf"\b({CLUB_MODELS})\.objects\.(?!for_club\(|create\(|none\(\))")
    bare_404 = re.compile(rf"get_object_or_404\(\s*({CLUB_MODELS})\s*,")
    problems = []
    for module in REQUEST_MODULES:
        for number, line in enumerate((root / module).read_text().splitlines(), 1):
            if unscoped.search(line) or bare_404.search(line):
                if "# for_club: not needed" not in line:
                    problems.append(f"{module}:{number}: {line.strip()}")
    assert problems == []
