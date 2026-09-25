"""Slice 4: publishing results, and the emails the site sends.

Organised by acceptance criterion. Emails land in Django's in-memory outbox.

The site sends email once the database transaction commits. Each test runs
inside a transaction that is never committed, so the ``run_on_commit`` fixture
makes "after commit" happen straight away, as it does on the live site, where
the site's own pages are not wrapped in a transaction. The rollback test uses
Django's real behaviour instead, since that is what it checks.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from races import notifications, publishing
from races.models import BoatRequest, EntryRequest, Finish, Race
from races.test_audit import boat_form, series_form
from races.testing import (
    default_club,
    enter, make_administrator, make_boat, make_committee, make_member, make_race, make_series, record,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def run_on_commit(monkeypatch):
    """Use as ``with run_on_commit():`` around anything that sends email."""
    from contextlib import nullcontext

    monkeypatch.setattr(notifications.transaction, "on_commit", lambda func, *a, **kw: func())
    return nullcontext


@pytest.fixture
def committee(client):
    user = make_committee()
    client.force_login(user)
    return user


@pytest.fixture
def club():
    """A series with a sailed race: two member-owned boats, a visitor, and a boat from another series."""
    pat = make_member("pat@example.com", first_name="Pat", last_name="Jones")
    sam = make_member("sam@example.com", first_name="Sam", last_name="Taylor")
    series = make_series("Autumn 2026 Series")
    kittiwake = make_boat("GBR42", name="Kittiwake", base_number="0.805", owner=pat)
    puffin = make_boat("GBR77", name="Puffin", base_number="0.842", owner=sam)
    visitor = make_boat("GBR7", name="Tern", base_number="0.900", owner_name="M. Visitor")
    entries = [enter(series, boat) for boat in (kittiwake, puffin, visitor)]
    elsewhere = make_member("jo@example.com")
    enter(make_series("Other"), make_boat("GBR99", owner=elsewhere))
    race = make_race(series, 1, start="18:30:00")
    for entry, finish in zip(entries, ["19:31:12", "19:40:05", "19:28:40"]):
        record(race, entry, finish)
    return {"series": series, "race": race, "entries": entries, "pat": pat, "sam": sam,
            "kittiwake": kittiwake, "puffin": puffin}


def publish(client, race, send=None):
    data = {"send": send} if send else {}
    return client.post(reverse("races:publish_results", args=[race.pk]), data, follow=True)


def recipients():
    return sorted(address for message in mail.outbox for address in message.to)


# --- A race is provisional until published ------------------------------------


def test_an_unpublished_race_is_labelled_provisional(client, club):
    page = client.get(reverse("results:series", args=[club["series"].pk])).content.decode()
    assert "Provisional" in page
    Race.objects.update(published_at=timezone.now())
    page = client.get(reverse("results:series", args=[club["series"].pk])).content.decode()
    assert "Provisional" not in page


def results_page(client, series):
    return client.get(reverse("results:series", args=[series.pk])).content.decode()


def test_a_provisional_race_explains_what_that_means(client, club):
    assert "may still change until the race committee publishes them" in results_page(client, club["series"])


def test_a_published_race_says_when(client, club):
    Race.objects.update(published_at=timezone.now(), results_sent_at=timezone.now())
    page = results_page(client, club["series"])
    assert f"Published {timezone.localdate():%-d %B %Y}." in page
    assert "may still change" not in page
    assert "Amended since published" not in page


def test_a_published_race_corrected_since_says_the_update_is_unsent(client, published):
    correct(client, published["race"], published["entries"][0], "19:32:00")
    page = results_page(client, published["series"])
    assert "Published " in page
    assert "Amended since published; the race committee has not yet sent the updated results." in page


def test_the_amended_since_published_note_goes_once_the_update_is_sent(client, published):
    correct(client, published["race"], published["entries"][0], "19:32:00")
    publish(client, published["race"], send="updated")
    page = results_page(client, published["series"])
    assert "Amended since published" not in page
    assert "Amended " in page  # the slice 2 note, with its date, still says it changed


def test_an_unpublished_correction_keeps_the_plain_amended_note(client, club):
    client.force_login(make_committee())
    correct(client, club["race"], club["entries"][0], "19:32:00")
    page = results_page(client, club["series"])
    assert "Amended since published" not in page
    assert "Amended " in page


def test_a_race_with_nothing_recorded_is_not_labelled_provisional(client, club):
    make_race(club["series"], 2)
    page = client.get(reverse("results:series", args=[club["series"].pk])).content.decode()
    assert page.count("Provisional") == 1  # race 1 only


# --- Publishing emails the owners in the series, and nobody else ---------------


def test_publishing_emails_each_owner_in_the_series(client, committee, club, run_on_commit):
    with run_on_commit():
        response = publish(client, club["race"])
    assert recipients() == ["pat@example.com", "sam@example.com"]
    assert "Results published and sent to 2 boat owners." in response.content.decode()
    race = Race.objects.get(pk=club["race"].pk)
    assert race.published_at is not None and race.results_sent_at is not None


def test_each_owner_gets_their_own_email(client, committee, club, run_on_commit):
    with run_on_commit():
        publish(client, club["race"])
    assert all(len(message.to) == 1 for message in mail.outbox)
    assert not any(message.cc or message.bcc for message in mail.outbox)


def test_the_results_email_has_the_results_and_a_link(client, committee, club, run_on_commit):
    with run_on_commit():
        publish(client, club["race"])
    message = next(m for m in mail.outbox if m.to == ["pat@example.com"])
    assert message.subject == "Results: Autumn 2026 Series, race 1"
    assert "Hello Pat" in message.body
    for text in ["GBR42 Kittiwake", "GBR77 Puffin", "GBR7 Tern", "Series standings",
                 reverse("results:series", args=[club["series"].pk])]:
        assert text in message.body
    assert "&amp;" not in message.body and "&#x27;" not in message.body


def test_an_owner_with_two_boats_gets_one_email(client, committee, club, run_on_commit):
    enter(club["series"], make_boat("GBR43", owner=club["pat"]))
    with run_on_commit():
        publish(client, club["race"])
    assert recipients() == ["pat@example.com", "sam@example.com"]


def test_waiting_and_deactivated_owners_get_nothing(client, committee, club, run_on_commit):
    get_user_model().objects.filter(pk=club["sam"].pk).update(is_active=False)
    with run_on_commit():
        publish(client, club["race"])
    assert recipients() == ["pat@example.com"]


def test_a_race_with_nothing_to_publish_is_refused(client, committee, club, run_on_commit):
    race_2 = make_race(club["series"], 2)
    with run_on_commit():
        response = publish(client, race_2)
    assert "no results to publish" in response.content.decode()
    assert not mail.outbox
    race_2.refresh_from_db()
    assert race_2.published_at is None


def test_only_the_committee_can_publish(client, club, run_on_commit):
    client.force_login(club["pat"])
    with run_on_commit():
        response = client.post(reverse("races:publish_results", args=[club["race"].pk]))
    assert response.status_code == 302 and "login" in response["Location"]
    assert not mail.outbox


# --- After corrections, the committee chooses when to send updates ------------


@pytest.fixture
def published(client, committee, club, run_on_commit):
    with run_on_commit():
        publish(client, club["race"])
    mail.outbox.clear()
    return club


def correct(client, race, entry, finish_time, reason="Misread the sheet"):
    prefix = f"entry-{entry.pk}"
    return client.post(
        reverse("races:save_finish", args=[race.pk, entry.pk]),
        {f"{prefix}-finish_time": finish_time, f"{prefix}-status": "FINISHED", f"{prefix}-reason": reason},
        HTTP_HX_REQUEST="true",
    )


def test_a_correction_marks_the_race_amended_and_sends_nothing(client, published, run_on_commit):
    race = published["race"]
    assert not publishing.amended_since_sent(race)
    with run_on_commit():
        response = correct(client, race, published["entries"][0], "19:32:00")
    assert "Amended since results were sent" in response.content.decode()  # swapped in by HTMX
    race.refresh_from_db()
    assert publishing.amended_since_sent(race)
    assert not mail.outbox


def test_sending_updated_results(client, published, run_on_commit):
    race = published["race"]
    correct(client, race, published["entries"][0], "19:32:00")
    with run_on_commit():
        response = publish(client, race, send="updated")
    assert "Updated results sent to 2 boat owners." in response.content.decode()
    assert {m.subject for m in mail.outbox} == {"Updated results: Autumn 2026 Series, race 1"}
    assert "have been updated" in mail.outbox[0].body
    race.refresh_from_db()
    assert not publishing.amended_since_sent(race)


def test_a_correction_to_an_earlier_race_amends_later_ones(client, published, run_on_commit):
    series, race_1 = published["series"], published["race"]
    race_2 = make_race(series, 2, start="18:30:00")
    record(race_2, published["entries"][0], "19:30:00")
    with run_on_commit():
        publish(client, race_2)
    correct(client, race_1, published["entries"][1], "19:41:00")
    race_2.refresh_from_db()
    assert publishing.amended_since_sent(race_2)  # it sails on race 1's handicaps


def test_a_change_to_a_later_race_does_not_amend_an_earlier_one(client, published):
    race_1 = published["race"]
    race_2 = make_race(published["series"], 2, start="18:30:00")
    correct(client, race_2, published["entries"][0], "19:30:00", reason="")
    race_1.refresh_from_db()
    assert not publishing.amended_since_sent(race_1)


def test_a_series_setting_amends_every_race(client, published):
    admin = make_administrator()
    client.force_login(admin)
    client.post(reverse("admin:races_series_change", args=[published["series"].pk]),
                series_form(published["series"], discards="0", reason="Notice of race"))
    race = published["race"]
    race.refresh_from_db()
    assert publishing.amended_since_sent(race)


# --- Sending never loses a change, and never crashes a page -------------------


@pytest.fixture
def mail_server_down(monkeypatch):
    def fail(self, messages):
        raise ConnectionRefusedError("mail server unreachable")
    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", fail)


def test_a_failed_send_keeps_the_publish_and_offers_to_retry(
    client, committee, club, run_on_commit, mail_server_down, caplog
):
    with run_on_commit():
        response = publish(client, club["race"])
    assert response.status_code == 200
    html = response.content.decode()
    assert "could not be sent" in html
    assert "Send results" in html  # the retry button
    race = Race.objects.get(pk=club["race"].pk)
    assert race.published_at is not None and race.results_sent_at is None
    assert "Could not send" in caplog.text


def test_a_rolled_back_change_sends_nothing(club, django_capture_on_commit_callbacks, rf):
    request = rf.get("/")
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                notifications.account_approved([club["pat"]], request)
                raise RuntimeError("the change failed")
        except RuntimeError:
            pass
    assert not mail.outbox


# --- Accounts ------------------------------------------------------------------


def test_approving_accounts_emails_them(client, run_on_commit):
    waiting = [make_member(f"new{n}@example.com", first_name="New", is_active=False) for n in range(2)]
    client.force_login(make_administrator())
    with run_on_commit():
        client.post(reverse("admin:auth_user_changelist"),
                    {"action": "approve_accounts", "_selected_action": [u.pk for u in waiting]})
    assert recipients() == ["new0@example.com", "new1@example.com"]
    assert mail.outbox[0].subject == "Your Race Times account is approved"
    assert reverse("races:login") in mail.outbox[0].body


def test_ticking_active_on_a_new_account_emails_it(client, run_on_commit):
    new = make_member("new@example.com", is_active=False)
    client.force_login(make_administrator())
    page = client.get(reverse("admin:auth_user_change", args=[new.pk]))
    form = page.context["adminform"].form
    data = {name: value for name, value in form.initial.items() if value is not None and not isinstance(value, list)}
    data.update({"is_active": "on", "date_joined_0": "2026-09-24", "date_joined_1": "09:00:00"})
    data.pop("is_staff", None), data.pop("is_superuser", None), data.pop("last_login", None)
    with run_on_commit():
        client.post(reverse("admin:auth_user_change", args=[new.pk]), data)
    new.refresh_from_db()
    assert new.is_active
    assert recipients() == ["new@example.com"]


def test_reactivating_an_old_account_is_not_an_approval(client, run_on_commit):
    old = make_member("old@example.com", is_active=False, last_login=timezone.now())
    client.force_login(make_administrator())
    with run_on_commit():
        client.post(reverse("admin:auth_user_changelist"),
                    {"action": "approve_accounts", "_selected_action": [old.pk]})
    assert not mail.outbox


# --- Requests: the member hears the decision, once ----------------------------


def decide(client, member_request, decision, reason="", note=""):
    kind = "entry" if isinstance(member_request, EntryRequest) else "boat"
    return client.post(reverse("races:decide_request", args=[kind, member_request.pk]),
                       {"decision": decision, "reason": reason, "note": note}, HTTP_HX_REQUEST="true")


def test_an_approved_change_emails_what_changed_and_nothing_else(client, committee, club, run_on_commit):
    boat = club["kittiwake"]
    values = {name: getattr(boat, name) for name in BoatRequest.PROPOSED_FIELDS}
    request = BoatRequest.objects.create(club=default_club(), kind="CHANGE", boat=boat, requested_by=club["pat"],
                                         **{**values, "name": "Kittiwake II"})
    with run_on_commit():
        decide(client, request, "approve")
    [message] = mail.outbox  # no separate "boat updated" email
    assert message.to == ["pat@example.com"]
    assert message.subject == "Approved: your request to change the details of GBR42 Kittiwake"
    assert "Name: Kittiwake -> Kittiwake II" in message.body
    assert "Make:" not in message.body  # only what changed


def test_an_approved_registration_lists_the_details(client, committee, club, run_on_commit):
    request = BoatRequest.objects.create(club=default_club(), kind="REGISTER", requested_by=club["sam"],
                                         sail_number="GBR5", name="Gannet", base_number="0.880")
    with run_on_commit():
        decide(client, request, "approve")
    [message] = mail.outbox
    assert "Approved: your request to register GBR5 Gannet" == message.subject
    assert "NHC base number: 0.880" in message.body


def test_a_rejection_carries_the_committees_note(client, committee, club, run_on_commit):
    request = BoatRequest.objects.create(club=default_club(), kind="REGISTER", requested_by=club["sam"],
                                         sail_number="GBR5", name="Gannet", base_number="0.880")
    with run_on_commit():
        decide(client, request, "reject", note="Base number does not match the RYA list")
    [message] = mail.outbox
    assert message.subject.startswith("Not approved:")
    assert "Base number does not match the RYA list" in message.body


def test_an_approved_entry_is_one_email(client, committee, club, run_on_commit):
    request = EntryRequest.objects.create(series=make_series("Wednesdays"), boat=club["kittiwake"],
                                          requested_by=club["pat"])
    with run_on_commit():
        decide(client, request, "approve")
    [message] = mail.outbox  # the approval is the entry confirmation
    assert message.subject == "Approved: your request to enter GBR42 Kittiwake in Wednesdays"


def test_an_approved_claim_tells_the_previous_owner(client, committee, club, run_on_commit):
    request = BoatRequest.objects.create(club=default_club(), kind="CLAIM", boat=club["puffin"], requested_by=club["pat"])
    with run_on_commit():
        decide(client, request, "approve")
    by_recipient = {m.to[0]: m for m in mail.outbox}
    assert set(by_recipient) == {"pat@example.com", "sam@example.com"}
    assert "Owner: Sam Taylor -> Pat Jones" in by_recipient["sam@example.com"].body


def test_a_failed_decision_sends_nothing(client, committee, club, run_on_commit):
    request = BoatRequest.objects.create(club=default_club(), kind="REGISTER", requested_by=club["sam"],
                                         sail_number="GBR5", base_number="0.880")
    with run_on_commit():
        decide(client, request, "reject")  # no note: refused
    assert not mail.outbox


# --- Boats and entries changed by the committee --------------------------------


@pytest.fixture
def admin_client(client):
    client.force_login(make_administrator())
    return client


def test_a_committee_edit_emails_the_owner_what_changed(admin_client, club, run_on_commit):
    boat = club["kittiwake"]
    with run_on_commit():
        admin_client.post(reverse("admin:races_boat_change", args=[boat.pk]),
                          boat_form(boat, name="Kittiwake II", owner=boat.owner_id))
    [message] = mail.outbox
    assert message.to == ["pat@example.com"]
    assert message.subject == "Your boat's details have been updated: GBR42 Kittiwake II"
    assert "Name: Kittiwake -> Kittiwake II" in message.body


def test_saving_a_boat_unchanged_sends_nothing(admin_client, club, run_on_commit):
    boat = club["kittiwake"]
    with run_on_commit():
        admin_client.post(reverse("admin:races_boat_change", args=[boat.pk]),
                          boat_form(boat, owner=boat.owner_id))
    assert not mail.outbox


def test_changing_the_owner_tells_both(admin_client, club, run_on_commit):
    boat = club["kittiwake"]
    with run_on_commit():
        admin_client.post(reverse("admin:races_boat_change", args=[boat.pk]),
                          boat_form(boat, owner=club["sam"].pk))
    assert recipients() == ["pat@example.com", "sam@example.com"]


def test_a_boat_entered_in_the_admin_emails_its_owner(admin_client, club, run_on_commit):
    series = make_series("Wednesdays")
    data = series_form(series)
    data.update({"entries-TOTAL_FORMS": 2, "entries-0-boat": club["kittiwake"].pk, "entries-0-series": series.pk,
                 "entries-1-boat": club["entries"][2].boat_id, "entries-1-series": series.pk})
    with run_on_commit():
        admin_client.post(reverse("admin:races_series_change", args=[series.pk]), data)
    [message] = mail.outbox  # the visitor's boat has no owner to tell
    assert message.to == ["pat@example.com"]
    assert message.subject == "GBR42 Kittiwake is entered in Wednesdays"


# --- Password reset --------------------------------------------------------------


def test_password_reset_emails_a_working_link(client, club, run_on_commit):
    club["pat"].set_password("the-old-password-123")  # every member sets one when signing up
    club["pat"].save()
    with run_on_commit():
        response = client.post(reverse("races:password_reset"), {"email": "PAT@example.com"}, follow=True)
    assert "Check your email" in response.content.decode()
    [message] = mail.outbox
    assert message.subject == "Reset your Race Times password"
    link = next(line for line in message.body.splitlines() if "/accounts/password-reset/" in line).strip()
    page = client.get(link, follow=True)
    new = "a-brand-new-sailing-password"
    client.post(page.redirect_chain[-1][0], {"new_password1": new, "new_password2": new})
    club["pat"].refresh_from_db()
    assert club["pat"].check_password(new)


@pytest.mark.parametrize("email", ["nobody@example.com", "waiting@example.com"])
def test_password_reset_does_not_reveal_who_has_an_account(client, email, run_on_commit):
    waiting = make_member("waiting@example.com", is_active=False)
    waiting.set_password("a-password-at-sign-up")
    waiting.save()
    with run_on_commit():
        response = client.post(reverse("races:password_reset"), {"email": email}, follow=True)
    assert "Check your email" in response.content.decode()
    assert not mail.outbox


def test_the_login_page_links_to_password_reset(client):
    assert reverse("races:password_reset") in client.get(reverse("races:login")).content.decode()
