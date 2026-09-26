"""Slice 10: declaring a series final, the lock, the copy, reopening and the email.

Organised by acceptance criterion. The CSV download is tested in
results/test_export.py.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

import nhc
from races import final, notifications
from races.models import EntryRequest, Finish, RaceEntry, ScoringChange, Series, SeriesEntry
from races.scoring import engine_outcome, score_series
from races.test_approvals import decide
from races.test_audit import post_boat, post_series, series_form
from races.testing import enter, make_boat, make_committee, make_member, make_race, make_series, record, start
from tests.scenario_loader import SCENARIOS

pytestmark = pytest.mark.django_db


@pytest.fixture
def run_on_commit(monkeypatch):
    # Emails wait for the transaction to commit, which a test never does.
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())


@pytest.fixture
def committee(client):
    user = make_committee()
    client.force_login(user)
    return user


def publish(*races):
    """Mark races published and their results sent, as the publishing box does."""
    now = timezone.now()
    for race in races:
        race.published_at = race.results_sent_at = now
        race.save(update_fields=["published_at", "results_sent_at"])


@pytest.fixture
def season():
    """Three owned boats; races 1 and 2 sailed and published; race 3 never sailed."""
    series = make_series("Autumn 2026", discards=0)
    owners = [make_member(f"{name}@example.com", first_name=name.capitalize()) for name in ("pat", "sam", "jo")]
    entries = [
        enter(series, make_boat(sail, name=name, base_number=base, owner=owner))
        for (sail, name, base), owner in zip(
            [("GBR42", "Kittiwake", "0.805"), ("GBR77", "Puffin", "0.842"), ("GBR7", "Tern", "0.900")], owners
        )
    ]
    race_1, race_2 = make_race(series, 1), make_race(series, 2, on=date(2026, 9, 30))
    race_3 = make_race(series, 3, on=date(2026, 10, 7))
    for race, times in [(race_1, ["19:05:31", "19:07:02", "19:02:10"]), (race_2, ["19:01:00", "19:06:30", None])]:
        for entry, time in zip(entries, times):
            record(race, entry, time) if time else record(race, entry, status=Finish.Status.DNF)
    publish(race_1, race_2)
    return {"series": series, "entries": entries, "races": [race_1, race_2, race_3], "owners": owners}


def declare(client, series):
    return client.post(reverse("races:declare_final", args=[series.pk]), follow=True)


def refreshed(series):
    return Series.objects.get(pk=series.pk)


def snapshot(series):
    """Everything the pages show about a series' results, to compare before and after."""
    results = score_series(refreshed(series))
    return (
        [(r.entry.pk, r.position, r.total, [(c.points, c.discarded) for c in r.scores]) for r in results.standings],
        [[(row.entry.pk, row.result.position, row.result.points, row.result.tcf_used, row.result.corrected_time,
           row.result.next_tcf) for row in race.rows] for race in results.races],
    )


# --- Declaring ----------------------------------------------------------------------------


def test_declaring_records_who_and_when_and_keeps_a_copy(client, committee, season, run_on_commit):
    before = snapshot(season["series"])
    page = declare(client, season["series"]).content.decode()
    series = refreshed(season["series"])
    assert series.is_final and series.declared_final_by_name == committee.get_username()
    assert series.final_results is not None
    [change] = ScoringChange.objects.filter(kind=ScoringChange.Kind.FINAL)
    assert (change.description, change.changes) == ("Autumn 2026: declared final", {"Final": ["No", "Yes"]})
    assert "Autumn 2026 is final. Final standings sent to 3 boat owners." in page
    assert snapshot(series) == before


def test_races_not_sailed_are_listed_and_dont_block(client, committee, season):
    page = client.get(reverse("races:final", args=[season["series"].pk])).content.decode()
    assert "Ready to declare final." in page
    assert "left out of the standings: race 3 (7 Oct)" in " ".join(page.split())


@pytest.mark.parametrize("problem, expected", [
    ("unpublished", "Race 2 has results but isn&#x27;t published yet."),
    ("amended", "Race 2 has been corrected since its results were sent"),
    ("not recorded", "Race 3: nothing recorded yet for GBR7 Tern."),
])
def test_declaring_is_refused_while_a_race_isnt_settled(client, committee, season, problem, expected):
    race_1, race_2, race_3 = season["races"]
    if problem == "unpublished":
        race_2.published_at = race_2.results_sent_at = None
        race_2.save()
    elif problem == "amended":
        ScoringChange.objects.create(club=season["series"].club, series=season["series"], race=race_2, kind="FINISH", action="CHANGED",
                                     description="x", is_correction=True, reason="Protest")
    else:
        record(race_3, season["entries"][0], "19:00:00")
        start(race_3, season["entries"][2])
        publish(race_3)
    page = client.get(reverse("races:final", args=[season["series"].pk])).content.decode()
    assert expected in page and "Declare final</button>" not in page
    page = declare(client, season["series"]).content.decode()
    assert expected in page
    assert not refreshed(season["series"]).is_final and not mail.outbox


def test_a_series_with_nothing_scored_cant_be_declared(client, committee):
    series = make_series()
    enter(series, make_boat())
    make_race(series)
    assert final.NOTHING_SCORED in declare(client, series).content.decode()
    assert not refreshed(series).is_final


def test_declaring_twice_is_refused(client, committee, season):
    declare(client, season["series"])
    assert final.ALREADY_FINAL in declare(client, season["series"]).content.decode()
    assert ScoringChange.objects.filter(kind=ScoringChange.Kind.FINAL).count() == 1


def test_declaring_marks_nothing_amended(client, committee, season):
    declare(client, season["series"])
    page = client.get(reverse("results:series", args=[season["series"].pk]), {"race": 2}).content.decode()
    assert "Amended" not in page and "Last updated" not in page


# --- The copy scores exactly as the replay does ---------------------------------------------


def test_the_copy_round_trips_exactly(season):
    outcome = engine_outcome(season["series"])
    assert final.load(final.dump(outcome)) == outcome


def test_scen_005_scores_the_same_from_the_copy(client, committee):
    scenario = next(s for s in SCENARIOS if s["scenario_id"].startswith("SCEN-005"))
    series = make_series("SCEN-005")
    race = make_race(series, start="18:30:00")
    for boat in scenario["boats"]:
        entry = enter(series, make_boat(boat["boat_id"], base_number=boat["start_handicap"]))
        if boat["status"] == "FINISHED":
            seconds = 18 * 3600 + 30 * 60 + round(boat["elapsed_seconds"])
            record(race, entry, f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}")
        else:
            record(race, entry, status=boat["status"])
    publish(race)
    outcome = engine_outcome(series)
    live = snapshot(series)
    declare(client, series)
    assert refreshed(series).is_final
    assert final.load(refreshed(series).final_results) == outcome
    assert snapshot(series) == live


def test_codes_ties_and_discards_score_the_same_from_the_copy(client, committee):
    series = make_series("Ties", discards=1)
    a, b, c = (enter(series, make_boat(sail, base_number="1.000")) for sail in ("A1", "B2", "C3"))
    races = [make_race(series, n) for n in (1, 2, 3)]
    record(races[0], a, "19:00:00"); record(races[0], b, "19:00:00"); record(races[0], c, status="DNS")
    record(races[1], a, status="DNF"); record(races[1], b, "19:10:00"); record(races[1], c, "19:05:00")
    record(races[2], a, "19:02:00"); record(races[2], b, "19:03:00"); record(races[2], c, "19:03:00")
    publish(*races)
    live = snapshot(series)
    assert any(cell[1] for row in live[0] for cell in row[3])  # a discard
    declare(client, series)
    assert refreshed(series).is_final and snapshot(series) == live


def test_a_base_number_change_after_declaring_leaves_the_final_series_alone(client, committee, season, admin_client):
    other = make_series("Winter 2026")
    kittiwake = season["entries"][0].boat
    other_entries = [enter(other, kittiwake), enter(other, season["entries"][1].boat)]
    other_race = make_race(other)
    record(other_race, other_entries[0], "19:05:31")
    record(other_race, other_entries[1], "19:07:02")
    declare(client, season["series"])
    final_before, other_before = snapshot(season["series"]), snapshot(other)

    response = post_boat(admin_client, kittiwake, base_number="0.700", reason="Rating certificate")
    assert response.status_code == 302  # saved: boats stay editable

    assert snapshot(season["series"]) == final_before
    assert snapshot(other) != other_before


# --- Locked ------------------------------------------------------------------------------------


@pytest.fixture
def locked(client, committee, season):
    declare(client, season["series"])
    return season


def nothing_written(season, finishes, entries, changes):
    assert Finish.objects.count() == finishes
    assert RaceEntry.objects.count() == entries
    assert ScoringChange.objects.count() == changes


def counts():
    return Finish.objects.count(), RaceEntry.objects.count(), ScoringChange.objects.count()


def test_the_race_day_page_refuses_every_change(client, locked, monkeypatch):
    race_3 = locked["races"][2]
    race_2 = locked["races"][1]
    kittiwake = locked["entries"][0]
    before = counts()
    htmx = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "finish-panel"}
    prefix = f"entry-{kittiwake.pk}"
    responses = [
        client.post(reverse("races:save_finish", args=[race_2.pk, kittiwake.pk]),
                    {f"{prefix}-finish_time": "19:09:00", f"{prefix}-status": "FINISHED", f"{prefix}-reason": "x"}, **htmx),
        client.post(reverse("races:tap_finish", args=[race_3.pk, kittiwake.pk]), **htmx),
        client.post(reverse("races:undo_finish", args=[race_2.pk, kittiwake.pk]), **htmx),
        client.post(reverse("races:save_start_sheet_row", args=[race_3.pk, kittiwake.pk]),
                    {f"{prefix}-racing": "on"}, HTTP_HX_REQUEST="true"),
    ]
    for response in responses:
        assert "This series is final. Reopen it to make changes." in response.content.decode()
    nothing_written(locked, *before)


def test_without_htmx_the_race_day_page_refuses_too(client, locked):
    race_2, kittiwake = locked["races"][1], locked["entries"][0]
    before = counts()
    response = client.post(reverse("races:tap_finish", args=[race_2.pk, kittiwake.pk]), follow=True)
    assert final.LOCKED in response.content.decode()
    nothing_written(locked, *before)


def test_the_race_day_page_shows_the_series_is_final(client, locked):
    race_2 = locked["races"][1]
    page = client.get(reverse("races:race_day", args=[race_2.pk]) + "?view=finish").content.decode()
    assert "This series is final" in page
    # The note sits below the view buttons, not inside them.
    tabs_start = page.index('<nav class="view-tabs"')
    tabs_end = page.index("</nav>", tabs_start)
    assert "locked-note" not in page[tabs_start:tabs_end]
    assert tabs_end < page.index('<p class="note locked-note">')
    assert "Edit</summary>" not in page and "Finished</button>" not in page and 'id="publishing"' not in page
    page = client.get(reverse("races:race_day", args=[race_2.pk]) + "?view=start").content.decode()
    assert '<fieldset class="start-rows" disabled>' in page


def test_publishing_is_refused(client, locked):
    race_2 = locked["races"][1]
    before = race_2.results_sent_at
    page = client.post(reverse("races:publish_results", args=[race_2.pk]), {"send": "updated"}, follow=True)
    assert final.LOCKED in page.content.decode()
    race_2.refresh_from_db()
    assert race_2.results_sent_at == before and not mail.outbox[3:]


@pytest.mark.parametrize("change", ["discards", "race start", "race added", "entry added", "entry removed"])
def test_the_admin_refuses_changes_to_a_final_series(admin_client, locked, change):
    series = locked["series"]
    if change == "discards":
        data = series_form(series, discards="1", reason="x")
    elif change == "race start":
        data = series_form(series, **{"races-2-start_time": "18:30:00"}, reason="x")
    elif change == "race added":
        data = series_form(series)
        data.update({"races-TOTAL_FORMS": 4, "races-3-series": series.pk, "races-3-number": 4,
                     "races-3-date": "2026-10-14", "races-3-start_time": "18:00:00"})
    elif change == "entry added":
        data = series_form(series)
        data.update({"entries-TOTAL_FORMS": 4, "entries-3-series": series.pk,
                     "entries-3-boat": make_boat("GBR99").pk})
    else:
        enter(series, make_boat("GBR99"))  # no results, so only the lock can refuse removing it
        data = series_form(series, **{"entries-3-DELETE": "on"}, reason="x")
    before = counts() + (SeriesEntry.objects.count(), series.races.count(), series.discards)
    response = admin_client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    assert response.status_code == 200 and final.LOCKED in response.content.decode()
    series.refresh_from_db()
    assert counts() + (SeriesEntry.objects.count(), series.races.count(), series.discards) == before


def test_a_final_series_can_still_be_renamed(admin_client, locked):
    response = post_series(admin_client, locked["series"], name="Autumn 2026 (club)")
    assert response.status_code == 302
    assert refreshed(locked["series"]).name == "Autumn 2026 (club)"


def test_approving_an_entry_request_is_refused(client, locked):
    member = make_member("newcomer@example.com")
    boat = make_boat("GBR5", owner=member)
    request = EntryRequest.objects.create(series=locked["series"], boat=boat, requested_by=member)
    response = decide(client, request, "approve")
    assert final.LOCKED in response.content.decode()
    assert request.status == EntryRequest.Status.PENDING
    assert not SeriesEntry.objects.filter(boat=boat).exists()


def test_the_one_check_refuses_a_final_series(locked):
    with pytest.raises(Exception, match="This series is final"):
        final.check_open(refreshed(locked["series"]))


# --- Reopening ----------------------------------------------------------------------------------


def reopen(client, series, reason):
    return client.post(reverse("races:reopen_series", args=[series.pk]), {"reason": reason}, follow=True)


def test_reopening_needs_a_reason(client, locked):
    page = reopen(client, locked["series"], "  ").content.decode()
    assert final.REOPEN_NEEDS_REASON in page
    assert refreshed(locked["series"]).is_final


def test_reopening_unlocks_the_series_and_drops_the_copy(client, locked, run_on_commit):
    sent = len(mail.outbox)
    page = reopen(client, locked["series"], "Protest upheld in race 2").content.decode()
    assert "is reopened" in page
    series = refreshed(locked["series"])
    assert not series.is_final and series.final_results is None
    assert len(mail.outbox) == sent  # reopening emails nobody
    change = ScoringChange.objects.filter(kind=ScoringChange.Kind.FINAL).first()
    assert (change.description, change.reason) == ("Autumn 2026: reopened", "Protest upheld in race 2")
    # It can be changed again.
    kittiwake = locked["entries"][0]
    prefix = f"entry-{kittiwake.pk}"
    client.post(reverse("races:save_finish", args=[locked["races"][1].pk, kittiwake.pk]),
                {f"{prefix}-finish_time": "19:09:00", f"{prefix}-status": "FINISHED", f"{prefix}-reason": "Protest"},
                HTTP_HX_REQUEST="true")
    assert Finish.objects.get(race=locked["races"][1], entry=kittiwake).finish_time.isoformat() == "19:09:00"


def test_reopening_doesnt_mark_the_standings_updated(client, locked):
    reopen(client, locked["series"], "Checking")
    page = client.get(reverse("results:series", args=[locked["series"].pk])).content.decode()
    assert "Last updated" not in page


def test_declaring_again_makes_a_new_copy_and_says_updated(client, locked, run_on_commit):
    mail.outbox.clear()
    reopen(client, locked["series"], "Protest upheld")
    race_2, kittiwake = locked["races"][1], locked["entries"][0]
    finish = Finish.objects.get(race=race_2, entry=kittiwake)
    finish.finish_time = finish.finish_time.replace(minute=30)
    finish.save()
    declare(client, locked["series"])
    series = refreshed(locked["series"])
    assert series.is_final
    assert final.load(series.final_results) == engine_outcome(series)
    assert {m.subject for m in mail.outbox} == {"Updated final standings: Autumn 2026"}


# --- The email ------------------------------------------------------------------------------------


def test_each_owner_gets_one_email_with_their_place(client, committee, season, run_on_commit):
    declare(client, season["series"])
    assert sorted(m.to[0] for m in mail.outbox) == ["jo@example.com", "pat@example.com", "sam@example.com"]
    message = next(m for m in mail.outbox if m.to == ["pat@example.com"])
    assert message.subject == "Final standings: Autumn 2026"
    place = next(r for r in score_series(refreshed(season["series"])).standings if r.entry == season["entries"][0])
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}[place.position]
    assert f"GBR42 Kittiwake finished {ordinal} of 3" in message.body
    assert reverse("results:series", args=[season["series"].pk]) in message.body
    assert refreshed(season["series"]).final_results_sent_at is not None


def test_an_owner_without_an_active_account_gets_no_email(client, committee, season, run_on_commit):
    season["owners"][1].is_active = False
    season["owners"][1].save()
    declare(client, season["series"])
    assert "sam@example.com" not in [m.to[0] for m in mail.outbox]


def test_a_refused_declaration_sends_nothing(client, committee, season, run_on_commit, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("database went away")
    monkeypatch.setattr(final, "_history", fail)
    with pytest.raises(RuntimeError):
        declare(client, season["series"])
    assert not refreshed(season["series"]).is_final and not mail.outbox


def test_a_sending_failure_keeps_it_final_and_offers_send_again(client, committee, season, run_on_commit, monkeypatch):
    def fail(self, messages):
        raise ConnectionRefusedError("mail server down")
    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", fail)
    page = declare(client, season["series"]).content.decode()
    series = refreshed(season["series"])
    assert series.is_final and series.final_results_sent_at is None
    assert "could not be sent" in page and "Send final standings</button>" in page

    monkeypatch.undo()
    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())
    page = client.post(reverse("races:send_final", args=[series.pk]), follow=True).content.decode()
    assert "Final standings sent to 3 boat owners." in page
    assert refreshed(series).final_results_sent_at is not None and len(mail.outbox) == 3


# --- What people see ----------------------------------------------------------------------------------


def test_final_series_are_labelled_on_the_public_pages(client, committee, season):
    declare(client, season["series"])
    client.logout()
    series_page = client.get(reverse("results:series", args=[season["series"].pk])).content.decode()
    assert 'Series Standings <span class="final-badge">Final Results</span>' in series_page
    assert f"Declared final on {timezone.localdate():%-d %B %Y}" in series_page
    home = client.get(reverse("results:home")).content.decode()
    assert 'Autumn 2026 <span class="final-badge">Final Results</span></a>' in home
    boat_page = client.get(reverse("results:boat", args=[season["entries"][0].boat.pk])).content.decode()
    assert '<span class="final-badge">Final Results</span>' in boat_page


def test_a_series_that_isnt_final_has_no_final_label(client, season):
    for url in (reverse("results:series", args=[season["series"].pk]), reverse("results:home")):
        assert "final-badge" not in client.get(url).content.decode()


def test_the_committee_sees_a_link_to_final_results(client, committee, season):
    page = client.get(reverse("results:series", args=[season["series"].pk])).content.decode()
    assert reverse("races:final", args=[season["series"].pk]) in page
    client.logout()
    page = client.get(reverse("results:series", args=[season["series"].pk])).content.decode()
    assert reverse("races:final", args=[season["series"].pk]) not in page
