"""Slice 6: race-level entry - the start sheet, and what it changes.

Organised by acceptance criterion. Emails land in Django's in-memory outbox;
``run_on_commit`` makes "after commit" happen straight away, as on the live
site (see races/test_notifications.py for why).
"""

import importlib
from datetime import time

import pytest
from django.apps import apps
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from races import start_sheet
from races.models import Finish, Race, RaceEntry, ScoringChange
from races.scoring import score_series
from races.test_audit import series_form
from races.test_notifications import committee, run_on_commit  # noqa: F401 (fixtures)
from races.testing import (
    enter, make_administrator, make_boat, make_member, make_race, make_series, record, start,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def race_day():
    """Race 1 of a three-boat series, nothing on the start sheet yet.

    Kittiwake is Pat's; Puffin's owner account is switched off; Tern is a
    visitor's boat with no account at all.
    """
    pat = make_member("pat@example.com", first_name="Pat")
    gone = make_member("gone@example.com", is_active=False)
    series = make_series("Autumn 2026")
    kittiwake = enter(series, make_boat("GBR42", name="Kittiwake", base_number="0.805", owner=pat))
    puffin = enter(series, make_boat("GBR77", name="Puffin", base_number="0.842", owner=gone))
    tern = enter(series, make_boat("GBR7", name="Tern", base_number="0.900", owner_name="M. Visitor"))
    race = make_race(series, 1, start="18:30:00")
    return {"series": series, "race": race, "kittiwake": kittiwake, "puffin": puffin, "tern": tern}


def row_url(race, entry):
    return reverse("races:save_start_sheet_row", args=[race.pk, entry.pk])


def tick(client, race, entry, racing=True, persons="", htmx=True):
    prefix = f"entry-{entry.pk}"
    data = {f"{prefix}-persons_on_board": persons}
    if racing:
        data[f"{prefix}-racing"] = "on"
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(row_url(race, entry), data, **extra)


def on_sheet(race):
    return sorted(race.race_entries.values_list("entry__boat__sail_number", flat=True))


def finish_row(entry, finish_time="", status="FINISHED", reason=""):
    prefix = f"entry-{entry.pk}"
    return {f"{prefix}-finish_time": finish_time, f"{prefix}-status": status, f"{prefix}-reason": reason}


# --- The committee keeps the start sheet, one row at a time ----------------------


def test_ticking_a_boat_puts_it_on_the_start_sheet(client, committee, race_day, run_on_commit):
    race, kittiwake = race_day["race"], race_day["kittiwake"]
    with run_on_commit():
        response = tick(client, race, kittiwake, persons="4")
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="start-%d"' % kittiwake.pk in html
    assert "Added to the start sheet. The owner has been emailed." in html
    # The count at the top of the page is updated in place, alongside the row.
    assert 'id="start-sheet-count" hx-swap-oob="true"' in html
    assert "1 of 3 boats racing" in html
    assert on_sheet(race) == ["GBR42"]
    assert RaceEntry.objects.get().persons_on_board == 4


def test_unticking_a_boat_takes_it_off(client, committee, race_day, run_on_commit):
    race, kittiwake = race_day["race"], race_day["kittiwake"]
    start(race, kittiwake)
    response = tick(client, race, kittiwake, racing=False)
    assert "Taken off the start sheet." in response.content.decode()
    assert on_sheet(race) == []


def test_unticking_ignores_whatever_is_left_in_persons_on_board(client, committee, race_day):
    race, tern = race_day["race"], race_day["tern"]
    start(race, tern, persons_on_board=3)
    assert "Taken off" in tick(client, race, tern, racing=False, persons="3").content.decode()
    assert "Saved; nothing changed." in tick(client, race, tern, racing=False, persons="0").content.decode()
    assert on_sheet(race) == []


def test_persons_on_board_can_be_changed_and_cleared(client, committee, race_day):
    race, tern = race_day["race"], race_day["tern"]
    start(race, tern, persons_on_board=3)
    assert "Persons on board saved." in tick(client, race, tern, persons="5").content.decode()
    assert RaceEntry.objects.get().persons_on_board == 5
    tick(client, race, tern, persons="")
    assert RaceEntry.objects.get().persons_on_board is None


@pytest.mark.parametrize(
    "racing, persons, error",
    [
        (True, "0", "greater than or equal to 1"),
        (True, "100", "less than or equal to 99"),
        (True, "two", "Enter a whole number"),
    ],
)
def test_an_invalid_row_is_refused_and_saves_nothing(client, committee, race_day, racing, persons, error):
    race, tern, kittiwake = race_day["race"], race_day["tern"], race_day["kittiwake"]
    start(race, kittiwake, persons_on_board=2)
    response = tick(client, race, tern, racing=racing, persons=persons)
    html = response.content.decode()
    assert error in html
    assert "has-errors" in html
    assert on_sheet(race) == ["GBR42"]  # and the other rows are untouched
    assert RaceEntry.objects.get().persons_on_board == 2


def test_without_htmx_a_row_saves_and_returns_to_the_page(client, committee, race_day, run_on_commit):
    race, tern = race_day["race"], race_day["tern"]
    response = tick(client, race, tern, htmx=False)
    assert response.status_code == 302
    assert response["Location"] == (reverse("races:race_day", args=[race.pk]) + "?view=start")
    assert on_sheet(race) == ["GBR7"]
    page = client.get(response["Location"]).content.decode()
    assert "GBR7 Tern: Added to the start sheet. No email: the boat has no owner account." in page


def test_without_htmx_an_invalid_row_redisplays_the_page(client, committee, race_day):
    race, tern = race_day["race"], race_day["tern"]
    response = tick(client, race, tern, persons="0", htmx=False)
    assert response.status_code == 200
    assert "greater than or equal to 1" in response.content.decode()
    assert on_sheet(race) == []


def test_the_page_lists_every_boat_in_the_series(client, committee, race_day):
    race = race_day["race"]
    start(race, race_day["puffin"], persons_on_board=6)
    page = client.get((reverse("races:race_day", args=[race.pk]) + "?view=start")).content.decode()
    for entry in ("kittiwake", "puffin", "tern"):
        assert row_url(race, race_day[entry]) in page
    assert "1 of 3 boats racing" in page
    assert 'value="6"' in page
    assert 'checked' in page
    # The committee knows which owners it has to tell itself.
    assert page.count("No email: no owner account.") == 2


def test_a_boat_from_another_series_is_not_found(client, committee, race_day):
    outsider = enter(make_series("Other"), make_boat("GBR999"))
    assert tick(client, race_day["race"], outsider).status_code == 404


def test_saving_needs_post(client, committee, race_day):
    assert client.get(row_url(race_day["race"], race_day["tern"])).status_code == 405


# --- Only a boat on the start sheet can have a finish ------------------------------


def test_a_finish_for_a_boat_not_on_the_start_sheet_is_refused(race_day):
    finish = Finish(race=race_day["race"], entry=race_day["tern"], finish_time=time(19, 30))
    with pytest.raises(ValidationError) as caught:
        finish.full_clean()
    assert "not on the race's start sheet" in str(caught.value)


def test_the_finish_page_refuses_a_boat_not_racing(client, committee, race_day):
    race, tern = race_day["race"], race_day["tern"]
    url = reverse("races:save_finish", args=[race.pk, tern.pk])
    response = client.post(url, finish_row(tern, "19:30:00"), follow=True)
    assert "not on the race&#x27;s start sheet" in response.content.decode()
    response = client.post(url, finish_row(tern, "19:30:00"), HTTP_HX_REQUEST="true")
    assert "not on the race&#x27;s start sheet" in response.content.decode()
    assert not Finish.objects.exists()


def test_the_finish_page_only_offers_boats_on_the_start_sheet(client, committee, race_day):
    race = race_day["race"]
    start(race, race_day["kittiwake"], persons_on_board=4)
    page = client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish")).content.decode()
    assert reverse("races:save_finish", args=[race.pk, race_day["kittiwake"].pk]) in page
    assert reverse("races:save_finish", args=[race.pk, race_day["tern"].pk]) not in page
    assert "Not racing (scored DNC): 2 boats" in page
    assert "4 on board" in page
    assert (reverse("races:race_day", args=[race.pk]) + "?view=start") in page


def test_an_empty_start_sheet_says_where_to_start(client, committee, race_day):
    page = client.get((reverse("races:race_day", args=[race_day["race"].pk]) + "?view=finish")).content.decode()
    assert "No boats are on the" in page


def test_a_boat_with_a_result_cannot_be_taken_off(client, committee, race_day):
    race, tern = race_day["race"], race_day["tern"]
    start(race, tern, persons_on_board=2)
    record(race, tern, "19:30:00")
    html = tick(client, race, tern, racing=False, persons="2").content.decode()
    assert "GBR7 Tern has a result recorded in this race" in html
    assert "correct its result to DNC" in html
    assert "checked" in html and 'value="2"' in html  # shown as it really is
    assert on_sheet(race) == ["GBR7"]
    page = client.post(row_url(race, tern), {}, follow=False)  # without HTMX: the page, with the error
    assert "has a result recorded" in page.content.decode()
    # Saving the row without unticking it is still fine.
    assert "has-errors" not in tick(client, race, tern).content.decode()


# --- The data migration ------------------------------------------------------------


def test_the_migration_puts_every_boat_with_a_finish_on_its_start_sheet(race_day):
    race, kittiwake, puffin = race_day["race"], race_day["kittiwake"], race_day["puffin"]
    race_2 = make_race(race_day["series"], 2, start="18:30:00")
    record(race, kittiwake, "19:31:12")
    record(race, puffin, status=Finish.Status.DNF)
    record(race_2, puffin, "19:40:05")
    before = score_series(race_day["series"])
    RaceEntry.objects.all().delete()  # as the database was before slice 6

    migration = importlib.import_module("races.migrations.0008_start_sheets_for_past_races")
    migration.fill_start_sheets(apps, None)

    assert on_sheet(race) == ["GBR42", "GBR77"]
    assert on_sheet(race_2) == ["GBR77"]
    assert _scores(score_series(race_day["series"])) == _scores(before)
    for finish in Finish.objects.all():
        finish.full_clean()  # every existing finish meets the new rule


def _scores(results):
    """Everything a result page shows: positions, points, times and handicaps."""
    return (
        [
            (row.entry.pk, row.result.position, row.result.status, row.result.points,
             row.result.corrected_time, row.result.tcf_used, row.result.effective_next_tcf)
            for race in results.races
            for row in race.rows
        ],
        [(row.entry.pk, row.position, row.total) for row in results.standings],
    )


# --- "Not recorded": shown differently, scored the same ----------------------------


@pytest.fixture
def sailed(race_day):
    """Kittiwake and Puffin finished; Tern is on the start sheet with nothing recorded."""
    race = race_day["race"]
    record(race, race_day["kittiwake"], "19:31:12")
    record(race, race_day["puffin"], "19:40:05")
    start(race, race_day["tern"], persons_on_board=7)
    make_race(race_day["series"], 2, start="18:30:00")
    record(race_day["series"].races.get(number=2), race_day["tern"], "19:20:00")
    return race_day


def test_a_boat_not_recorded_scores_exactly_as_one_left_off(sailed):
    series, race, tern = sailed["series"], sailed["race"], sailed["tern"]
    on_the_sheet = score_series(series)
    row = on_the_sheet.for_race(race).for_entry(tern)
    assert row.not_recorded and row.place == "Not recorded"
    assert row.result.status == "DNC"

    RaceEntry.objects.filter(race=race, entry=tern).delete()
    left_off = score_series(series)
    assert _scores(on_the_sheet) == _scores(left_off)
    row = left_off.for_race(race).for_entry(tern)
    assert not row.not_recorded and row.place == "DNC"


@pytest.mark.parametrize("page", ["series", "boat"])
def test_public_pages_show_not_recorded(client, sailed, page):
    if page == "series":
        url = reverse("results:series", args=[sailed["series"].pk]) + "?race=1"
    else:
        url = reverse("results:boat", args=[sailed["tern"].boat_id])
    html = client.get(url).content.decode()
    # Short in the table, to fit a phone, and spelled out underneath.
    assert '<abbr title="Not recorded">NR</abbr>' in html
    assert "NR: Not recorded." in html


def test_the_finish_page_says_not_recorded_yet(client, committee, sailed):
    # Slice 9: a boat with nothing recorded is listed under "Still racing".
    page = client.get((reverse("races:race_day", args=[sailed["race"].pk]) + "?view=finish")).content.decode()
    still_racing = page[page.index('id="still-racing"'):page.index('id="finished"')]
    assert "Still racing (1)" in still_racing and "GBR7" in still_racing


# --- Publishing waits for every boat on the start sheet -----------------------------


def publish(client, race, send=None):
    data = {"send": send} if send else {}
    return client.post(reverse("races:publish_results", args=[race.pk]), data, follow=True)


def test_publishing_is_refused_while_a_boat_is_not_recorded(client, committee, sailed, run_on_commit):
    race = sailed["race"]
    page = client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish")).content.decode()
    assert "Still to record: GBR7 Tern." in page
    assert "Publish results</button>" not in page
    with run_on_commit():
        html = publish(client, race).content.decode()
    assert "Not sent: record a time or a code for every boat on the start sheet first." in html
    assert "Still to record: GBR7 Tern." in html
    assert Race.objects.get(pk=race.pk).published_at is None
    assert not mail.outbox

    record(race, sailed["tern"], status=Finish.Status.DNS)
    with run_on_commit():
        html = publish(client, race).content.decode()
    assert "Results published and sent" in html


def test_a_boat_added_after_publishing_blocks_updated_results(client, committee, sailed, run_on_commit):
    race, tern = sailed["race"], sailed["tern"]
    record(race, tern, status=Finish.Status.DNF)
    with run_on_commit():
        publish(client, race)
    visitor = enter(sailed["series"], make_boat("GBR8", name="Gannet"))  # forgotten on the day
    start(race, visitor)
    mail.outbox.clear()
    with run_on_commit():
        html = publish(client, race, send="updated").content.decode()
    assert "Still to record: GBR8 Gannet." in html
    assert not mail.outbox

    # A first finish needs no reason (slice 2), but it is in the history, so
    # the race is amended since its results were sent.
    url = reverse("races:save_finish", args=[race.pk, visitor.pk])
    client.post(url, finish_row(visitor, "19:35:00"), HTTP_HX_REQUEST="true")
    assert Finish.objects.filter(entry=visitor).exists()
    page = client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish")).content.decode()
    assert "Amended since results were sent" in page
    with run_on_commit():
        html = publish(client, race, send="updated").content.decode()
    assert "Updated results sent" in html


# --- The emails ------------------------------------------------------------------------


def test_the_owner_is_told_when_their_boat_is_put_on(client, committee, race_day, run_on_commit):
    race, kittiwake = race_day["race"], race_day["kittiwake"]
    with run_on_commit():
        tick(client, race, kittiwake)
    [message] = mail.outbox
    assert message.to == ["pat@example.com"]
    assert message.subject == "GBR42 Kittiwake is entered in race 1 of Autumn 2026"
    assert "Wednesday 23 September 2026, starting at 18:30" in message.body
    assert f"/series/{race.series.pk}/?race=1" in message.body


def test_saving_a_row_again_sends_nothing_more(client, committee, race_day, run_on_commit):
    race, kittiwake = race_day["race"], race_day["kittiwake"]
    with run_on_commit():
        tick(client, race, kittiwake)
        tick(client, race, kittiwake)
        tick(client, race, kittiwake, persons="3")
    assert len(mail.outbox) == 1


def test_taking_a_boat_off_and_back_on_sends_each_email(client, committee, race_day, run_on_commit):
    race, kittiwake = race_day["race"], race_day["kittiwake"]
    with run_on_commit():
        tick(client, race, kittiwake)
        tick(client, race, kittiwake, racing=False)
        tick(client, race, kittiwake)
    assert [message.subject for message in mail.outbox] == [
        "GBR42 Kittiwake is entered in race 1 of Autumn 2026",
        "GBR42 Kittiwake is no longer entered in race 1 of Autumn 2026",
        "GBR42 Kittiwake is entered in race 1 of Autumn 2026",
    ]
    assert "It is scored DNC" in mail.outbox[1].body


def test_a_boat_added_after_the_race_still_gets_its_email(client, committee, sailed, run_on_commit):
    visitor = enter(sailed["series"], make_boat("GBR8", name="Gannet", owner=make_member("g@example.com")))
    with run_on_commit():
        tick(client, sailed["race"], visitor)
    [message] = mail.outbox
    assert message.subject == "GBR8 Gannet is entered in race 1 of Autumn 2026"


@pytest.mark.parametrize("entry", ["puffin", "tern"])  # an inactive account, and no account
def test_only_an_active_owner_account_is_emailed(client, committee, race_day, run_on_commit, entry):
    race = race_day["race"]
    with run_on_commit():
        html = tick(client, race, race_day[entry]).content.decode()
        tick(client, race, race_day[entry], racing=False)
    assert not mail.outbox
    assert "No email: the boat has no owner account." in html


def test_a_rolled_back_change_sends_nothing(race_day, django_capture_on_commit_callbacks, rf):
    request = rf.get("/")
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                start_sheet.save_row(race_day["race"], race_day["kittiwake"], racing=True,
                                     persons_on_board=None, request=request)
                raise RuntimeError("the change failed")
        except RuntimeError:
            pass
    assert not mail.outbox
    assert not RaceEntry.objects.exists()


@pytest.fixture
def mail_server_down(monkeypatch):
    def fail(self, messages):
        raise ConnectionRefusedError("mail server unreachable")
    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", fail)


def test_a_failed_send_keeps_the_boat_on_and_says_so(
    client, committee, race_day, run_on_commit, mail_server_down, caplog
):
    race = race_day["race"]
    with run_on_commit():
        response = tick(client, race, race_day["kittiwake"], htmx=False)
    page = client.get(response["Location"]).content.decode()
    assert "the emails about it could not be sent" in page
    assert on_sheet(race) == ["GBR42"]
    assert "Could not send" in caplog.text


def test_removing_a_boat_from_a_series_tells_the_owner_once(client, race_day, run_on_commit):
    client.force_login(make_administrator())
    series, race, kittiwake = race_day["series"], race_day["race"], race_day["kittiwake"]
    start(race, kittiwake)
    start(make_race(series, 2), kittiwake)
    data = series_form(series)
    index = next(i for i in range(3) if data[f"entries-{i}-id"] == kittiwake.pk)
    data[f"entries-{index}-DELETE"] = "on"
    with run_on_commit():
        response = client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    assert response.status_code == 302
    [message] = mail.outbox  # one email, not one per start sheet as well
    assert message.to == ["pat@example.com"]
    assert message.subject == "GBR42 Kittiwake is no longer entered in Autumn 2026"
    assert not series.entries.filter(pk=kittiwake.pk).exists()
    assert not RaceEntry.objects.exists()


def test_a_boat_with_results_still_cannot_leave_the_series(client, sailed, run_on_commit):
    client.force_login(make_administrator())
    series = sailed["series"]
    data = series_form(series, reason="Left the club")
    index = next(i for i in range(3) if data[f"entries-{i}-id"] == sailed["kittiwake"].pk)
    data[f"entries-{index}-DELETE"] = "on"
    with run_on_commit():
        response = client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    assert "cannot be removed from this series" in response.content.decode()
    assert not mail.outbox


# --- Persons on board is for the committee only ---------------------------------------


def test_persons_on_board_is_on_no_public_page(client, sailed):
    marker = "7 on board"
    public = [
        reverse("results:home"),
        reverse("results:series", args=[sailed["series"].pk]) + "?race=1&detail=1",
        reverse("results:boat", args=[sailed["tern"].boat_id]),
    ]
    for url in public:
        html = client.get(url).content.decode()
        assert marker not in html and "on board" not in html, url
    client.force_login(make_administrator())
    committee_page = client.get((reverse("races:race_day", args=[sailed["race"].pk]) + "?view=finish")).content.decode()
    assert marker in committee_page


# --- The change history is untouched --------------------------------------------------


def test_start_sheet_changes_are_not_in_the_history(client, committee, sailed, run_on_commit):
    race = sailed["race"]
    record(race, sailed["tern"], status=Finish.Status.DNF)
    with run_on_commit():
        publish(client, race)
    changes = ScoringChange.objects.count()
    visitor = enter(sailed["series"], make_boat("GBR8"))
    tick(client, race, visitor)
    tick(client, race, visitor, persons="2")
    tick(client, race, visitor, racing=False)
    assert ScoringChange.objects.count() == changes
    page = client.get((reverse("races:race_day", args=[race.pk]) + "?view=finish")).content.decode()
    assert "Amended since results were sent" not in page


# --- What the database refuses -------------------------------------------------------------


def test_one_row_per_boat_per_race(race_day):
    RaceEntry.objects.create(race=race_day["race"], entry=race_day["tern"])
    with pytest.raises(IntegrityError):
        RaceEntry.objects.create(race=race_day["race"], entry=race_day["tern"])


@pytest.mark.parametrize("persons", [0, 100])
def test_persons_on_board_is_between_1_and_99(race_day, persons):
    with pytest.raises(IntegrityError):
        RaceEntry.objects.create(race=race_day["race"], entry=race_day["tern"], persons_on_board=persons)


def test_a_boat_from_another_series_is_refused_by_the_model(race_day):
    outsider = enter(make_series("Other"), make_boat("GBR999"))
    with pytest.raises(ValidationError) as caught:
        RaceEntry(race=race_day["race"], entry=outsider).full_clean()
    assert "not entered in this race's series" in str(caught.value)


@pytest.mark.parametrize("who", ["public", "member"])
def test_only_the_committee_can_change_a_start_sheet(client, race_day, who):
    if who == "member":
        client.force_login(make_member("someone@example.com"))
    response = tick(client, race_day["race"], race_day["kittiwake"])
    # The public is sent to log in; a member is refused, not sent round a login loop (slice 11).
    if who == "member":
        assert response.status_code == 403
    else:
        assert response.status_code == 302 and "login" in response["Location"]
    assert not RaceEntry.objects.exists()
