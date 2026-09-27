"""Slice 22: the operator changes a live club's name or contact email.

The operator's pages are on the service's own address, which in tests is
``localhost`` with SINGLE_CLUB unset. A club's address is ``<subdomain>.localhost``.
"""

import pytest
from django.core import mail
from django.urls import reverse

from races.models import Club, OperatorAction
from races.testing import (
    join,
    make_administrator,
    make_club,
    make_committee,
    make_member,
    make_operator,
)

pytestmark = pytest.mark.django_db

SERVICE = {"HTTP_HOST": "localhost"}
HARBOUR = {"HTTP_HOST": "harbour.localhost"}


@pytest.fixture(autouse=True)
def service_address(settings):
    settings.SINGLE_CLUB = ""
    settings.SERVICE_CONTACT_EMAIL = "clubs@racetimes.example"


@pytest.fixture
def harbour():
    return make_club(
        "harbour", "Harbour Sailing Club", contact_email="sec@harbour.example"
    )


@pytest.fixture
def operator(client):
    person = make_operator()
    client.force_login(person)
    return person


@pytest.fixture
def emails_at_once(run_on_commit):
    """Send emails at once: they wait for a commit, which a test never makes."""


def save(client, club, name=None, contact_email=None, **extra):
    data = {
        "name": club.name if name is None else name,
        "contact_email": club.contact_email if contact_email is None else contact_email,
        **extra,
    }
    return client.post(
        reverse("races:operator_club_settings", args=[club.pk]), data, **SERVICE
    )


def fresh(club):
    return Club.objects.get(pk=club.pk)


def logged():
    return list(
        OperatorAction.objects.values_list("action", "detail", "club_subdomain")
    )


# --- The page ----------------------------------------------------------------------------------


def test_the_clubs_page_has_its_settings_filled_in(client, operator, harbour):
    page = client.get(
        reverse("races:operator_club", args=[harbour.pk]), **SERVICE
    ).content.decode()
    assert "Club settings" in page
    assert 'name="name"' in page and 'value="Harbour Sailing Club"' in page
    assert 'value="sec@harbour.example"' in page
    assert reverse("races:operator_club_settings", args=[harbour.pk]) in page
    assert "can't be changed" in page


# --- Renaming ----------------------------------------------------------------------------------


def test_renaming_a_club_changes_its_name_and_logs_both_names(
    client, operator, harbour
):
    response = save(client, harbour, name="Harbour Yacht Club")
    assert response.status_code == 302
    assert fresh(harbour).name == "Harbour Yacht Club"
    assert logged() == [
        ("RENAMED", "Harbour Sailing Club → Harbour Yacht Club", "harbour")
    ]
    page = client.get(response.url, **SERVICE).content.decode()
    assert "Renamed Harbour Sailing Club to Harbour Yacht Club." in page
    assert "Renamed a club" in page  # in the club's operator log


def test_the_new_name_shows_on_the_clubs_own_site_at_once(client, operator, harbour):
    save(client, harbour, name="Harbour Yacht Club")
    client.logout()
    page = client.get("/", **HARBOUR).content.decode()
    assert "Harbour Yacht Club" in page and "Harbour Sailing Club" not in page


def test_the_new_name_is_what_find_my_club_finds(client, operator, harbour):
    save(client, harbour, name="Estuary Cruising Club")
    page = client.get("/", {"club": "estuary"}, **SERVICE).content.decode()
    assert "Estuary Cruising Club" in page
    assert (
        "Harbour Sailing Club"
        not in client.get("/", {"club": "harbour"}, **SERVICE).content.decode()
    )


def test_the_address_cant_be_changed_even_by_a_hand_made_post(
    client, operator, harbour
):
    save(client, harbour, name="Harbour Yacht Club", subdomain="stolen")
    assert fresh(harbour).subdomain == "harbour"
    assert not Club.objects.filter(subdomain="stolen").exists()


def test_nor_its_status(client, operator, harbour):
    save(client, harbour, name="Harbour Yacht Club", status="SUSPENDED")
    assert fresh(harbour).is_active


def test_saving_without_a_change_changes_and_logs_nothing(client, operator, harbour):
    response = save(client, harbour)
    assert fresh(harbour).name == "Harbour Sailing Club"
    assert not OperatorAction.objects.exists() and not mail.outbox
    assert "Nothing changed." in client.get(response.url, **SERVICE).content.decode()


def test_spaces_around_a_name_are_trimmed_and_arent_a_change(client, operator, harbour):
    save(client, harbour, name="  Harbour Sailing Club  ")
    assert fresh(harbour).name == "Harbour Sailing Club"
    assert not OperatorAction.objects.exists()


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("", "This field is required."),
        ("   ", "This field is required."),
        ("x" * 101, "Ensure this value has at most 100 characters"),
    ],
)
def test_a_blank_or_over_long_name_is_refused_on_the_page(
    client, operator, harbour, name, error
):
    response = save(client, harbour, name=name)
    assert response.status_code == 400
    page = response.content.decode()
    assert error in page
    # The page still shows the club as it is, not the refused name.
    assert "<h1>Harbour Sailing Club</h1>" in page
    assert fresh(harbour).name == "Harbour Sailing Club"
    assert not OperatorAction.objects.exists() and not mail.outbox


def test_a_suspended_club_can_be_renamed(client, operator):
    gone = make_club(
        "gone",
        "Gone Sailing Club",
        status=Club.Status.SUSPENDED,
        contact_email="sec@gone.example",
    )
    save(client, gone, name="Back Soon Sailing Club")
    assert fresh(gone).name == "Back Soon Sailing Club"
    assert not fresh(gone).is_active


def test_two_clubs_may_share_a_name(client, operator, harbour):
    make_club("exesc", "Exe Sailing Club")
    save(client, harbour, name="Exe Sailing Club")
    assert fresh(harbour).name == "Exe Sailing Club"


def test_renaming_one_club_leaves_the_others_alone(client, operator, harbour):
    exe = make_club("exesc", "Exe Sailing Club")
    save(client, harbour, name="Harbour Yacht Club")
    assert fresh(exe).name == "Exe Sailing Club"


def test_an_unknown_club_is_not_found(client, operator):
    response = client.post(
        reverse("races:operator_club_settings", args=[9999]),
        {"name": "X", "contact_email": "x@example.com"},
        **SERVICE,
    )
    assert response.status_code == 404


def test_the_settings_are_changed_only_by_post(client, operator, harbour):
    url = reverse("races:operator_club_settings", args=[harbour.pk])
    assert client.get(url, **SERVICE).status_code == 405


# --- The contact email -------------------------------------------------------------------------


def test_changing_the_contact_email_is_logged_with_both_addresses(
    client, operator, harbour
):
    response = save(client, harbour, contact_email="new-sec@harbour.example")
    assert fresh(harbour).contact_email == "new-sec@harbour.example"
    assert logged() == [
        (
            "CONTACT_CHANGED",
            "sec@harbour.example → new-sec@harbour.example",
            "harbour",
        )
    ]
    assert (
        "contact email is now new-sec@harbour.example"
        in client.get(response.url, **SERVICE).content.decode()
    )


def test_changing_both_logs_both(client, operator, harbour):
    save(
        client,
        harbour,
        name="Harbour Yacht Club",
        contact_email="new-sec@harbour.example",
    )
    assert sorted(action for action, _, _ in logged()) == [
        "CONTACT_CHANGED",
        "RENAMED",
    ]


def test_a_club_created_without_a_contact_email_can_be_given_one(client, operator):
    bare = make_club("bare", "Bare Sailing Club")  # made before emails were needed
    assert bare.contact_email == ""
    save(client, bare, contact_email="sec@bare.example")
    assert logged() == [("CONTACT_CHANGED", "none → sec@bare.example", "bare")]


@pytest.mark.parametrize("contact_email", ["", "not-an-email"])
def test_the_contact_email_must_be_an_email_address(
    client, operator, harbour, contact_email
):
    response = client.post(
        reverse("races:operator_club_settings", args=[harbour.pk]),
        {"name": harbour.name, "contact_email": contact_email},
        **SERVICE,
    )
    assert response.status_code == 400
    assert fresh(harbour).contact_email == "sec@harbour.example"
    assert not OperatorAction.objects.exists()


# --- Telling the club --------------------------------------------------------------------------


@pytest.fixture
def people(harbour):
    """Harbour's administrators, and people at the club who aren't told."""
    return {
        "admin": make_administrator("ann@harbour.example", club=harbour),
        "second": make_member(
            "bob@harbour.example", "Bob", club=harbour, role="ADMINISTRATOR"
        ),
        "committee": make_committee("cat@harbour.example", club=harbour),
        "member": make_member("dan@harbour.example", club=harbour),
        "waiting": make_member(
            "eve@harbour.example", club=harbour, role="ADMINISTRATOR", status="WAITING"
        ),
        "gone": make_administrator(
            "fay@harbour.example", club=harbour, is_active=False
        ),
        # An administrator somewhere else.
        "elsewhere": make_administrator("gus@example.com"),
    }


def test_renaming_emails_each_of_the_clubs_administrators(
    client, operator, people, harbour, emails_at_once
):
    save(client, harbour, name="Harbour Yacht Club")
    assert sorted(address for m in mail.outbox for address in m.to) == [
        "ann@harbour.example",
        "bob@harbour.example",
    ]
    message = next(m for m in mail.outbox if m.to == ["bob@harbour.example"])
    assert message.subject == "Your club is now called Harbour Yacht Club on Race Times"
    assert "Hello Bob," in message.body
    assert "now Harbour Yacht Club (it was Harbour Sailing Club)" in message.body
    assert "still at http://harbour.localhost/" in message.body
    assert "contact Race Times at clubs@racetimes.example" in message.body
    assert "Replies to your club's emails" not in message.body


def test_the_email_comes_from_the_club_as_it_now_is(
    client, operator, people, harbour, emails_at_once
):
    save(
        client,
        harbour,
        name="Harbour Yacht Club",
        contact_email="new-sec@harbour.example",
    )
    message = mail.outbox[0]
    assert message.from_email.startswith("Harbour Yacht Club via Race Times <")
    assert message.reply_to == ["new-sec@harbour.example"]
    assert "now Harbour Yacht Club" in message.body
    assert (
        "Replies to your club's emails now go to new-sec@harbour.example "
        "(they went to sec@harbour.example)" in message.body
    )


def test_a_contact_email_change_alone_says_so(
    client, operator, people, harbour, emails_at_once
):
    save(client, harbour, contact_email="new-sec@harbour.example")
    message = mail.outbox[0]
    assert message.subject == (
        "Harbour Sailing Club's contact email has changed on Race Times"
    )
    assert "Its name is now" not in message.body
    assert "now go to new-sec@harbour.example" in message.body


def test_nothing_is_emailed_when_nothing_changed(
    client, operator, people, harbour, emails_at_once
):
    save(client, harbour)
    assert not mail.outbox


def test_a_club_with_no_administrators_yet_can_still_be_renamed(
    client, operator, harbour, emails_at_once
):
    save(client, harbour, name="Harbour Yacht Club")
    assert fresh(harbour).name == "Harbour Yacht Club" and not mail.outbox


def test_an_administrator_of_two_clubs_is_told_about_this_one(
    client, operator, harbour, emails_at_once
):
    both = make_administrator("hal@example.com")  # Demo Club's
    join(both, harbour, role="ADMINISTRATOR")
    save(client, harbour, name="Harbour Yacht Club")
    assert [m.to for m in mail.outbox] == [["hal@example.com"]]
    assert "Harbour Yacht Club" in mail.outbox[0].subject


# --- Who can do it -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["member", "committee", "administrator"])
def test_nobody_at_the_club_can_change_its_settings(client, harbour, role):
    maker = {
        "member": make_member,
        "committee": make_committee,
        "administrator": make_administrator,
    }[role]
    client.force_login(maker("someone@harbour.example", club=harbour))
    response = save(client, harbour, name="Mine Now")
    assert response.status_code == 403
    assert fresh(harbour).name == "Harbour Sailing Club"


def test_the_public_is_sent_to_log_in(client, harbour):
    response = save(client, harbour, name="Mine Now")
    assert response.status_code == 302 and "/login/" in response.url
    assert fresh(harbour).name == "Harbour Sailing Club"


def test_on_a_clubs_address_the_page_doesnt_exist(client, operator, harbour):
    response = client.post(
        reverse("races:operator_club_settings", args=[harbour.pk]),
        {"name": "Mine Now", "contact_email": "x@example.com"},
        **HARBOUR,
    )
    assert response.status_code == 404
    assert fresh(harbour).name == "Harbour Sailing Club"
