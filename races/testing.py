"""Builders and helpers for the app's tests. Not collected as tests itself.

Shared fixtures are in ``races/conftest.py``; this module holds plain functions.

Each takes only what a test cares about and defaults the rest, so a test reads
as the situation it sets up.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from races.invitations import token_for
from races.models import (
    Boat,
    BoatRequest,
    Club,
    ClubInvitation,
    ClubMembership,
    EntryRequest,
    Finish,
    Race,
    RaceEntry,
    ScoringChange,
    Series,
    SeriesEntry,
)


def default_club():
    """The first club, which the migrations create and tests see by default (slice 11)."""
    return Club.objects.get(subdomain="demo")


def make_club(subdomain, name=None, **fields):
    return Club.objects.create(
        subdomain=subdomain, name=name or subdomain.capitalize(), **fields
    )


def make_boat(sail_number="GBR1234", base_number="0.964", club=None, **fields):
    return Boat.objects.create(
        club=club or default_club(),
        sail_number=sail_number,
        base_number=Decimal(str(base_number)),
        **fields,
    )


def make_series(name="Autumn 2026", club=None, **fields):
    return Series.objects.create(club=club or default_club(), name=name, **fields)


def enter(series, boat):
    return SeriesEntry.objects.create(series=series, boat=boat)


def make_race(series, number=1, start="18:00:00", on=date(2026, 9, 23)):
    return Race.objects.create(
        series=series, number=number, date=on, start_time=time.fromisoformat(start)
    )


def start(race, entry, persons_on_board=None):
    """Put a boat on a race's start sheet (if it is not on it already)."""
    race_entry, _ = RaceEntry.objects.get_or_create(race=race, entry=entry)
    if persons_on_board is not None:
        race_entry.persons_on_board = persons_on_board
        race_entry.save()
    return race_entry


def record(race, entry, finish_time=None, status=None):
    """Record a finish: a clock time like "19:02:17", or a status code.

    The boat goes on the start sheet first, as it must on the real site.
    """
    start(race, entry)
    if status is None:
        status = Finish.Status.FINISHED if finish_time else Finish.Status.DNC
    return Finish.objects.create(
        race=race,
        entry=entry,
        status=status,
        finish_time=time.fromisoformat(finish_time) if finish_time else None,
    )


def finish_clock(start, elapsed_seconds):
    """The clock time a boat finishes, elapsed_seconds after a start like "18:00:00"."""
    moment = datetime.fromisoformat(f"2026-01-01T{start}") + timedelta(
        seconds=elapsed_seconds
    )
    return moment.strftime("%H:%M:%S")


_DEFAULT = object()


def make_member(
    email="member@example.com",
    first_name="Pat",
    last_name="Jones",
    club=_DEFAULT,
    role="MEMBER",
    status="APPROVED",
    **fields,
):
    """An active account, logged in by email, with an approved membership of Demo Club.

    Pass ``club`` for another club, or ``club=None`` for an account that
    belongs to no club. ``role`` and ``status`` are the membership's (slice 11).
    """
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        first_name=first_name,
        last_name=last_name,
        **fields,
    )
    if club is _DEFAULT:
        club = default_club()
    if club is not None:
        ClubMembership.objects.create(user=user, club=club, role=role, status=status)
    return user


def join(user, club, role="MEMBER", status="APPROVED"):
    """Give an existing account a membership of another club."""
    from races.roles import forget_memberships

    forget_memberships(
        user
    )  # the user object may have looked up its memberships already
    return ClubMembership.objects.create(user=user, club=club, role=role, status=status)


def make_committee(email="officer@example.com", club=_DEFAULT, **fields):
    """A race committee member of Demo Club (or ``club``)."""
    return make_member(
        email,
        first_name="Race",
        last_name="Officer",
        club=club,
        role="COMMITTEE",
        **fields,
    )


def make_administrator(email="admin@example.com", club=_DEFAULT, **fields):
    """A club administrator of Demo Club (or ``club``). Not the operator."""
    return make_member(
        email,
        first_name="Club",
        last_name="Admin",
        club=club,
        role="ADMINISTRATOR",
        **fields,
    )


def make_operator(email="operator@example.com"):
    """The service's operator: a superuser with no club membership."""
    return make_member(
        email,
        first_name="Service",
        last_name="Operator",
        club=None,
        is_staff=True,
        is_superuser=True,
    )


# --- Signing up and logging in --------------------------------------------------------


PASSWORD = "correct-horse-battery-staple"


def sign_up(client, email="new@example.com", **fields):
    data = {
        "first_name": "Sam",
        "last_name": "Taylor",
        "email": email,
        "password1": PASSWORD,
        "password2": PASSWORD,
        **fields,
    }
    return client.post(reverse("races:signup"), data)


def log_in(client, email, password=PASSWORD):
    return client.post(
        reverse("races:login"), {"username": email, "password": password}
    )


# --- The admin's series and boat forms ------------------------------------------------


def series_form(series, **changes):
    """The series admin form as it stands, with ``changes`` applied on top."""
    data = {
        "name": series.name,
        "series_type": series.series_type,
        "discards": series.discards,
        "minimum_finishers": series.minimum_finishers,
        "reason": "",
    }
    for flag in ("apply_a5_3", "nhc_cap_extremes", "nhc_realign_to_base"):
        if getattr(series, flag):
            data[flag] = "on"
    entries = list(series.entries.all())
    races = list(series.races.all())
    for prefix, rows in [("entries", entries), ("races", races)]:
        data[f"{prefix}-TOTAL_FORMS"] = len(rows)
        data[f"{prefix}-INITIAL_FORMS"] = len(rows)
        data[f"{prefix}-MIN_NUM_FORMS"] = 0
        data[f"{prefix}-MAX_NUM_FORMS"] = 1000
    for i, entry in enumerate(entries):
        data.update(
            {
                f"entries-{i}-id": entry.pk,
                f"entries-{i}-series": series.pk,
                f"entries-{i}-boat": entry.boat_id,
            }
        )
    for i, race in enumerate(races):
        data.update(
            {
                f"races-{i}-id": race.pk,
                f"races-{i}-series": series.pk,
                f"races-{i}-number": race.number,
                f"races-{i}-date": race.date.isoformat(),
                f"races-{i}-start_time": race.start_time.strftime("%H:%M:%S"),
            }
        )
    data.update(changes)
    return data


def post_series(client, series, **changes):
    return client.post(
        reverse("admin:races_series_change", args=[series.pk]),
        series_form(series, **changes),
    )


def boat_form(boat, **changes):
    data = {
        "sail_number": boat.sail_number,
        "name": boat.name,
        "make": boat.make,
        "model": boat.model,
        "owner_name": boat.owner_name,
        "length_overall_m": "",
        "waterline_length_m": "",
        "base_number": str(boat.base_number),
        "reason": "",
    }
    data.update(changes)
    return data


def post_boat(client, boat, **changes):
    return client.post(
        reverse("admin:races_boat_change", args=[boat.pk]), boat_form(boat, **changes)
    )


# --- Change requests and final results ------------------------------------------------


def decide(client, request, decision, reason="", note=""):
    kind = "entry" if isinstance(request, EntryRequest) else "boat"
    response = client.post(
        reverse("races:decide_request", args=[kind, request.pk]),
        {"decision": decision, "reason": reason, "note": note},
        HTTP_HX_REQUEST="true",
    )
    request.refresh_from_db()
    return response


def publish(*races):
    """Mark races published and their results sent, as the publishing box does."""
    now = timezone.now()
    for race in races:
        race.published_at = race.results_sent_at = now
        race.save(update_fields=["published_at", "results_sent_at"])


def declare(client, series):
    return client.post(reverse("races:declare_final", args=[series.pk]), follow=True)


# --- A fake clock for the login throttle ----------------------------------------------


class Clock:
    def __init__(self):
        self.time = 1_000_000.0

    def __call__(self):
        return self.time

    def minutes_pass(self, minutes):
        self.time += minutes * 60


# --- Two clubs with overlapping data (slice 11) ---------------------------------------

# Used by races/test_isolation.py and the other tests that check one club never
# sees another's data.

DEMO, HARBOUR = "demo.localhost", "harbour.localhost"


# Every name below belongs to Harbour only. None may appear at Demo Club.
HARBOUR_ONLY = [
    "Bittern",
    "Brant",
    "Booby",
    "Harbour Winter",
    "Black Tern",
    "bea@example.com",
    "Harbour Sailing Club",
]


def build_club_data(club, prefix, names, series_name, owner, shared):
    """One club's data: a series with two races, three boats, requests and history."""
    series = make_series(series_name, club=club)
    first, second, third = names
    entries = [
        enter(
            series,
            make_boat("GBR42", name=first, base_number="0.805", owner=owner, club=club),
        ),
        enter(series, make_boat("GBR7", name=second, base_number="0.900", club=club)),
        enter(
            series,
            make_boat(
                "GBR99", name=third, base_number="0.850", owner=shared, club=club
            ),
        ),
    ]
    race_1, race_2 = make_race(series, 1), make_race(series, 2)
    for entry, finish_time in zip(
        entries, ("19:05:31", "19:07:02", "19:03:10"), strict=True
    ):
        record(race_1, entry, finish_time)
    record(race_2, entries[0], "19:01:00")
    now = timezone.now()
    race_1.published_at = race_1.results_sent_at = now
    race_1.save()
    requests = {
        "register": BoatRequest.objects.create(
            club=club,
            kind="REGISTER",
            sail_number="GBR5",
            name=f"{prefix} Tern",
            base_number="0.9",
            requested_by=shared,
        ),
        "claim": BoatRequest.objects.create(
            club=club, kind="CLAIM", boat=entries[1].boat, requested_by=shared
        ),
        "entry": EntryRequest.objects.create(
            series=make_series(f"{series_name} Two", club=club),
            boat=entries[2].boat,
            requested_by=shared,
        ),
    }
    ScoringChange.objects.create(
        club=club,
        series=series,
        race=race_1,
        kind="FINISH",
        action="CHANGED",
        description=f"{first}, Race 1",
        is_correction=True,
        reason="Protest",
    )
    waiting = make_member(
        f"{prefix.lower()}.waiting@example.com",
        first_name=f"{prefix}waiting",
        club=club,
        status="WAITING",
    )
    invitation = ClubInvitation.objects.create(
        club=club, email=f"{prefix.lower()}.invited@example.com"
    )
    return {
        "club": club,
        "series": series,
        "entries": entries,
        "races": [race_1, race_2],
        "requests": requests,
        "membership": waiting.memberships.get(),
        "invitation": token_for(invitation),
    }


def leaks(html):
    return [name for name in HARBOUR_ONLY if name in html]


def log_in_as(client, role, clubs):
    if role == "member":
        client.force_login(clubs["shared"])
    elif role == "committee":
        client.force_login(make_committee())
    elif role == "administrator":
        client.force_login(make_administrator())
    elif role == "operator":
        client.force_login(make_operator())


def urls_for(data, kind=None):
    """Every URL name the site has, with arguments drawn from one club's data."""
    series, (race_1, _), (e1, _, e3) = data["series"], data["races"], data["entries"]
    requests = data["requests"]
    boat = e3.boat  # the shared member's boat, so member pages find it
    return {
        "races:change_boat": [boat.pk],
        "races:claim_boat": [e1.boat.pk],
        "races:decide_request": ["boat", requests["register"].pk],
        "races:declare_final": [series.pk],
        "races:enter_series": [boat.pk],
        "races:final": [series.pk],
        "races:finish_entry": [race_1.pk],
        "races:login": [],
        "races:logout": [],
        "races:my_boats": [],
        "races:password_reset": [],
        "races:password_reset_complete": [],
        "races:password_reset_confirm": ["x", "y"],
        "races:password_reset_done": [],
        "races:publish_results": [race_1.pk],
        "races:race_day": [race_1.pk],
        "races:register_boat": [],
        "races:reopen_series": [series.pk],
        "races:requests": [],
        "races:save_finish": [race_1.pk, e1.pk],
        "races:save_start_sheet_row": [race_1.pk, e1.pk],
        "races:send_final": [series.pk],
        "races:series_history": [series.pk],
        "races:signup": [],
        "races:start_sheet": [race_1.pk],
        "races:tap_finish": [race_1.pk, e1.pk],
        "races:undo_finish": [race_1.pk, e1.pk],
        "races:withdraw_request": ["boat", requests["claim"].pk],
        "results:boat": [e1.boat.pk],
        "results:home": [],
        "results:series": [series.pk],
        "results:series_csv": [series.pk],
        # Slice 11 part 2: accounts and memberships.
        "races:confirm_email": ["x", "y"],
        "races:resend_confirmation": [],
        "races:join_club": [],
        "races:members": [],
        "races:decide_membership": [data["membership"].pk],
        # Slice 11 part 3: invitations, at the club, and the operator's pages, which
        # exist only on the service's own address (a 404 at every club).
        "races:accept_invitation": [data["invitation"]],
        "races:operator_clubs": [],
        "races:operator_create_club": [],
        "races:operator_log": [],
        "races:operator_club": [data["club"].pk],
        "races:operator_invite": [data["club"].pk],
        "races:operator_club_status": [data["club"].pk],
        # Slice 11 part 5: the privacy notice and terms, the same at every address.
        "races:privacy": [],
        "races:terms": [],
        # The account's own pages, which cover every club the person belongs to.
        "races:account": [],
        "races:download_my_data": [],
        "races:delete_account": [],
        "races:change_password": [],
        "races:export_club_data": [],
        "races:operator_export_club": [data["club"].pk],
        "races:operator_delete_club": [data["club"].pk],
        # Slice 13: the operator deciding who's waiting to join.
        "races:operator_decide_joining": [data["club"].pk, data["membership"].pk],
        # Slice 18: the race office.
        "races:office": [],
        "races:office_boats": [],
        "races:office_new_boat": [],
        "races:office_boat": [e1.boat.pk],
        "races:office_delete_boat": [e1.boat.pk],
    }
