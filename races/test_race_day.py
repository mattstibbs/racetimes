"""Slice 9: the race day page - tapping Finished, Undo, refreshing, the clock.

Organised by acceptance criterion. The clock is fixed in each test: tapping
Finished reads ``race_day.now`` (the site's local time), and Undo's two
minutes are measured with ``timezone.now``.
"""

from datetime import date, datetime, time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from races import race_day
from races.models import Finish, ScoringChange
from races.testing import enter, make_boat, make_committee, make_member, make_race, make_series, record, start

pytestmark = pytest.mark.django_db

RACE_DATE = date(2026, 9, 23)  # make_race's default date; the start is 18:00:00


def local(hh, mm, ss=0, micro=0, on=RACE_DATE):
    return timezone.make_aware(datetime.combine(on, time(hh, mm, ss, micro)))


@pytest.fixture
def clock(monkeypatch):
    """Set the site's clock: ``clock(19, 5, 31)``, or ``clock(when=a_datetime)``."""
    def set_clock(*hms, when=None):
        moment = when or local(*hms)
        monkeypatch.setattr(race_day, "now", lambda: timezone.localtime(moment))
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment
    return set_clock


@pytest.fixture
def committee(client):
    user = make_committee()
    client.force_login(user)
    return user


@pytest.fixture
def racing():
    """Race 1, started 18:00: Kittiwake and Puffin racing, Tern on the start sheet too, Gannet at home."""
    series = make_series("Autumn 2026")
    boats = {
        name: enter(series, make_boat(sail, name=name.capitalize(), base_number=base))
        for name, sail, base in [("kittiwake", "GBR42", "0.805"), ("puffin", "GBR77", "0.842"),
                                 ("tern", "GBR7", "0.900"), ("gannet", "GBR8", "0.950")]
    }
    race = make_race(series)
    for name in ("kittiwake", "puffin", "tern"):
        start(race, boats[name])
    return {"series": series, "race": race, **boats}


def page_url(race, view=None):
    url = reverse("races:race_day", args=[race.pk])
    return f"{url}?view={view}" if view else url


def tap(client, race, entry, htmx=True):
    extra = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "finish-panel"} if htmx else {}
    return client.post(reverse("races:tap_finish", args=[race.pk, entry.pk]), **extra)


def undo(client, race, entry):
    return client.post(reverse("races:undo_finish", args=[race.pk, entry.pk]),
                       HTTP_HX_REQUEST="true", HTTP_HX_TARGET="finish-panel")


def section(html, heading_id, next_id):
    return html[html.index(f'id="{heading_id}"'):html.index(f'id="{next_id}"')]


# --- One page ------------------------------------------------------------------------


@pytest.mark.parametrize("old, view", [("races:start_sheet", "start"), ("races:finish_entry", "finish")])
def test_the_old_addresses_redirect_to_the_race_day_page(client, committee, racing, old, view):
    response = client.get(reverse(old, args=[racing["race"].pk]))
    assert response.status_code == 302
    assert response["Location"] == page_url(racing["race"], view)


def test_the_old_addresses_still_need_the_committee(client, racing):
    client.force_login(make_member("someone@example.com"))
    response = client.get(reverse("races:finish_entry", args=[racing["race"].pk]))
    assert response.status_code == 302 and "login" in response["Location"]


def test_the_page_opens_on_finishing_once_anyone_is_racing(client, committee, racing):
    html = client.get(page_url(racing["race"])).content.decode()
    assert 'id="finish-panel"' in html
    empty = make_race(racing["series"], 2)
    html = client.get(page_url(empty)).content.decode()
    assert 'id="start-sheet-count"' in html and 'id="finish-panel"' not in html


def test_switching_views_over_htmx_swaps_just_the_body(client, committee, racing):
    response = client.get(page_url(racing["race"], "start"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="race-day-body")
    html = response.content.decode()
    assert html.lstrip().startswith('<div id="race-day-body">')
    assert "<html" not in html and 'aria-current="page">Start sheet' in html


# --- Tapping Finished ---------------------------------------------------------------------


def test_tapping_finished_records_the_time_in_whole_seconds(client, committee, racing, clock):
    moment = clock(19, 5, 31, 700000)
    html = tap(client, racing["race"], racing["kittiwake"]).content.decode()
    finish = Finish.objects.get(entry=racing["kittiwake"])
    assert (finish.status, finish.finish_time) == ("FINISHED", time(19, 5, 31))
    assert finish.recorded_at == moment
    change = ScoringChange.objects.get()
    assert (change.action, change.is_correction, change.reason) == ("ADDED", False, "")
    assert "GBR42 Kittiwake finished at 19:05:31." in html
    finished = html[html.index('id="finished"'):]
    assert "GBR42" in finished and "19:05:31" in finished
    assert "GBR42" not in section(html, "still-racing", "finished")


def test_without_htmx_a_tap_returns_to_the_page(client, committee, racing, clock):
    clock(19, 5, 31)
    response = tap(client, racing["race"], racing["kittiwake"], htmx=False)
    assert response.status_code == 302 and response["Location"] == page_url(racing["race"], "finish")
    assert "GBR42 Kittiwake finished at 19:05:31." in client.get(response["Location"]).content.decode()


@pytest.mark.parametrize("when, offered", [
    (local(17, 59, 59), False),               # before the start
    (local(18, 0, 0), True),                  # from the start
    (local(23, 59, 0), True),                 # later that day
    (local(19, 0, on=date(2026, 9, 24)), False),  # the next day: typed times only
])
def test_finished_is_offered_on_race_day_from_the_start(client, committee, racing, clock, when, offered):
    clock(when=when)
    html = client.get(page_url(racing["race"], "finish")).content.decode()
    assert ("Finished</button>" in html) is offered
    assert ("The Finished button appears on" in html) is not offered
    assert reverse("races:save_finish", args=[racing["race"].pk, racing["kittiwake"].pk]) in html


@pytest.mark.parametrize("when", [local(17, 59, 0), local(19, 0, on=date(2026, 9, 22))])
def test_a_tap_outside_race_day_is_refused(client, committee, racing, clock, when):
    clock(when=when)
    html = tap(client, racing["race"], racing["kittiwake"]).content.decode()
    assert "Finished can only be tapped on the race&#x27;s own day" in html
    assert not Finish.objects.exists() and not ScoringChange.objects.exists()


def test_a_tap_for_a_boat_not_racing_is_refused(client, committee, racing, clock):
    clock(19, 0)
    html = tap(client, racing["race"], racing["gannet"]).content.decode()
    assert "not on the race&#x27;s start sheet" in html
    assert not Finish.objects.exists()


def test_a_second_tap_changes_nothing_and_says_when(client, committee, racing, clock):
    clock(19, 5, 31)
    tap(client, racing["race"], racing["kittiwake"])
    clock(19, 5, 40)
    html = tap(client, racing["race"], racing["kittiwake"]).content.decode()
    assert "GBR42 Kittiwake already has a result: finished at 19:05:31. Nothing was changed." in html
    assert Finish.objects.get().finish_time == time(19, 5, 31)
    assert ScoringChange.objects.count() == 1


def test_a_tap_on_a_boat_with_a_code_says_so(client, committee, racing, clock):
    clock(19, 0)
    record(racing["race"], racing["tern"], status=Finish.Status.DNF)
    html = tap(client, racing["race"], racing["tern"]).content.decode()
    assert "already has a result: DNF" in html


# --- The Finished list -------------------------------------------------------------------


def test_finished_boats_are_in_order_across_the_line_then_codes(client, committee, racing, clock):
    clock(when=local(20, 0, on=date(2026, 9, 30)))  # afterwards: no Undo, no Finished button
    race = racing["race"]
    record(race, racing["puffin"], "19:07:02")
    record(race, racing["tern"], status=Finish.Status.DNF)
    record(race, racing["kittiwake"], "19:05:31")
    html = client.get(page_url(race, "finish")).content.decode()
    finished = html[html.index('id="finished"'):]
    assert finished.index("GBR42") < finished.index("GBR77") < finished.index("GBR7 ")
    assert '<div class="order">1.</div>' in finished and '<div class="order">2.</div>' in finished
    assert "elapsed 1:05:31" in finished  # finish and elapsed times, not corrected
    assert "Still racing (0)" in html and "Every boat on the start sheet has a result." in html


def test_boats_tapped_in_the_same_second_stay_in_tap_order(client, committee, racing, clock):
    first = clock(19, 5, 31, 100000)
    tap(client, racing["race"], racing["puffin"])      # GBR77, tapped first
    clock(when=first + timedelta(milliseconds=600))
    tap(client, racing["race"], racing["kittiwake"])   # GBR42: same second, lower sail number
    html = client.get(page_url(racing["race"], "finish")).content.decode()
    finished = html[html.index('id="finished"'):]
    assert finished.index("GBR77") < finished.index("GBR42")


def test_a_typed_time_works_from_either_list(client, committee, racing, clock):
    clock(when=local(20, 0, on=date(2026, 9, 30)))
    race, kittiwake = racing["race"], racing["kittiwake"]
    url = reverse("races:save_finish", args=[race.pk, kittiwake.pk])
    prefix = f"entry-{kittiwake.pk}"
    client.post(url, {f"{prefix}-finish_time": "19:05:31", f"{prefix}-status": "FINISHED"}, HTTP_HX_REQUEST="true")
    assert Finish.objects.get().finish_time == time(19, 5, 31)
    # A correction from the Finished list still needs a reason.
    html = client.post(url, {f"{prefix}-finish_time": "19:05:41", f"{prefix}-status": "FINISHED"},
                       HTTP_HX_REQUEST="true").content.decode()
    assert "give a reason" in html and "details class=\"finish-form\" open" in html
    assert Finish.objects.get().finish_time == time(19, 5, 31)


def test_without_htmx_a_refused_save_shows_the_page_with_the_form_open(client, committee, racing, clock):
    clock(19, 30)
    race, kittiwake = racing["race"], racing["kittiwake"]
    prefix = f"entry-{kittiwake.pk}"
    response = client.post(reverse("races:save_finish", args=[race.pk, kittiwake.pk]),
                           {f"{prefix}-finish_time": "17:00:00", f"{prefix}-status": "FINISHED"})
    html = response.content.decode()
    assert response.status_code == 200 and "<html" in html
    assert "The finish must be after the start" in html and 'details class="finish-form" open' in html


# --- Undo ------------------------------------------------------------------------------------


@pytest.mark.parametrize("after, offered", [(timedelta(minutes=1, seconds=59), True),
                                            (timedelta(minutes=2, seconds=1), False)])
def test_undo_is_offered_for_two_minutes(client, committee, racing, clock, after, offered):
    tapped = clock(19, 5, 31)
    tap(client, racing["race"], racing["kittiwake"])
    clock(when=tapped + after)
    html = client.get(page_url(racing["race"], "finish")).content.decode()
    assert (reverse("races:undo_finish", args=[racing["race"].pk, racing["kittiwake"].pk]) in html) is offered


def test_undo_puts_the_boat_back_and_keeps_the_history(client, committee, racing, clock):
    tapped = clock(19, 5, 31)
    tap(client, racing["race"], racing["kittiwake"])
    clock(when=tapped + timedelta(seconds=30))
    html = undo(client, racing["race"], racing["kittiwake"]).content.decode()
    assert "Undone: GBR42 Kittiwake is racing again." in html
    assert "GBR42" in section(html, "still-racing", "finished")
    assert not Finish.objects.exists()
    added, removed = ScoringChange.objects.order_by("pk")
    assert (added.action, removed.action) == ("ADDED", "REMOVED")
    assert (removed.is_correction, removed.reason) == (False, race_day.UNDO_NOTE)


def test_undo_after_two_minutes_is_refused(client, committee, racing, clock):
    tapped = clock(19, 5, 31)
    tap(client, racing["race"], racing["kittiwake"])
    clock(when=tapped + timedelta(minutes=2, seconds=1))
    html = undo(client, racing["race"], racing["kittiwake"]).content.decode()
    assert "Undo is only possible for two minutes" in html
    assert Finish.objects.exists() and ScoringChange.objects.count() == 1


def test_undo_is_refused_once_published(client, committee, racing, clock):
    tapped = clock(19, 5, 31)
    for name in ("kittiwake", "puffin", "tern"):
        tap(client, racing["race"], racing[name])
    racing["race"].published_at = tapped
    racing["race"].save()
    html = undo(client, racing["race"], racing["kittiwake"]).content.decode()
    assert "Undo is only possible" in html and "/undo/" not in html
    assert Finish.objects.count() == 3


def test_a_finish_from_before_slice_9_never_offers_undo(client, committee, racing, clock):
    clock(19, 10)
    record(racing["race"], racing["kittiwake"], "19:05:31")
    Finish.objects.update(recorded_at=None)  # as the migration left older finishes
    html = client.get(page_url(racing["race"], "finish")).content.decode()
    assert "/undo/" not in html
    assert "Undo is only possible" in undo(client, racing["race"], racing["kittiwake"]).content.decode()


# --- Refreshing itself for a second device ---------------------------------------------------


def poll(client, race, since):
    return client.get(page_url(race, "finish") + f"&since={since}",
                      HTTP_HX_REQUEST="true", HTTP_HX_TARGET="finish-panel")


def test_a_refresh_with_nothing_changed_gets_204(client, committee, racing, clock):
    clock(19, 0)
    assert poll(client, racing["race"], race_day.version(racing["race"])).status_code == 204


def test_a_refresh_after_another_devices_tap_gets_the_lists(client, committee, racing, clock):
    clock(19, 5, 31)
    before = race_day.version(racing["race"])
    tap(client, racing["race"], racing["puffin"])  # the other device
    response = poll(client, racing["race"], before)
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="finish-panel"' in html and "19:05:31" in html and "<html" not in html


def test_an_undo_running_out_counts_as_a_change(client, committee, racing, clock):
    tapped = clock(19, 5, 31)
    tap(client, racing["race"], racing["puffin"])
    during = race_day.version(racing["race"])
    clock(when=tapped + timedelta(minutes=3))
    assert race_day.version(racing["race"]) != during


def test_the_panel_pauses_its_refresh_while_a_form_is_open(client, committee, racing):
    html = client.get(page_url(racing["race"], "finish")).content.decode()
    assert "hx-trigger=\"every 5s [!document.querySelector('#finish-panel details[open]')]\"" in html
    assert 'hx-sync="#finish-panel:replace"' in html


# --- The race clock ---------------------------------------------------------------------------


def test_the_page_carries_the_sites_time_for_the_clock(client, committee, racing, clock):
    moment = clock(19, 5, 31)
    html = client.get(page_url(racing["race"])).content.decode()
    assert f'data-now="{int(moment.timestamp() * 1000)}"' in html
    assert f'data-start="{int(local(18, 0).timestamp() * 1000)}"' in html
    assert 'data-tz="Europe/London"' in html
    assert "Clock <strong class=\"clock-time\">19:05:31</strong>" in html  # before the script runs
    assert '<script src="/static/js/race-clock.js" defer></script>' in html


@pytest.mark.parametrize("on", [date(2026, 9, 22), date(2026, 9, 24)])
def test_the_clock_is_shown_only_on_the_race_date(client, committee, racing, clock, on):
    clock(when=local(19, 0, on=on))
    html = client.get(page_url(racing["race"])).content.decode()
    assert 'id="race-clock"' not in html and "race-clock.js" not in html
    clock(19, 0)  # the race's own date
    html = client.get(page_url(racing["race"])).content.decode()
    assert 'id="race-clock"' in html and 'data-date="2026-09-23"' in html
