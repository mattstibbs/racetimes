"""Sample club data for the user manual's screenshots.

Run only by run.sh, against a throwaway SQLite database it creates, never
against a real one. Every account's password is PASSWORD.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.utils import timezone

from races.models import Boat, BoatRequest, Club, EntryRequest, Finish, Race, RaceEntry, Series, SeriesEntry
from races.roles import COMMITTEE_GROUP
from races.testing import make_member

# Everything belongs to Demo Club, which the migrations create (slice 11).
club = Club.objects.get(subdomain="demo")

PASSWORD = "manual-screenshots-only"


def account(email, first, last, **fields):
    user = make_member(email, first_name=first, last_name=last, **fields)
    user.set_password(PASSWORD)
    user.save()
    return user


account("admin@example.com", "Chris", "Admin", is_staff=True, is_superuser=True)
officer = account("officer@example.com", "Alex", "Officer", is_staff=True)
officer.groups.add(Group.objects.get(name=COMMITTEE_GROUP))
pat = account("pat@example.com", "Pat", "Jones")
sam = account("sam@example.com", "Sam", "Taylor")
jo = account("jo@example.com", "Jo", "Smith")
# Two sign-ups waiting for the administrator.
account("robin@example.com", "Robin", "Hale", is_active=False)
account("kim@example.com", "Kim", "Park", is_active=False)

# Pat's boat, entered in a series that already has a result.
kittiwake = Boat.objects.create(club=club,
    sail_number="GBR 42", name="Kittiwake", make="Westerly", model="Centaur",
    length_overall_m=Decimal("7.92"), waterline_length_m=Decimal("6.48"),
    base_number=Decimal("0.805"), owner=pat,
)
tern = Boat.objects.create(club=club, sail_number="GBR 7", name="Tern", base_number=Decimal("0.900"),
                           owner_name="M. Visitor")
serendipity = Boat.objects.create(club=club, sail_number="GBR 1234", name="Serendipity", make="Sadler",
                                  model="26", base_number=Decimal("0.857"), owner=sam)
blue_moon = Boat.objects.create(club=club, sail_number="GBR 88", name="Blue Moon", make="Contessa",
                                model="32", base_number=Decimal("0.921"), owner_name="R. Blue")
autumn = Series.objects.create(club=club, name="Autumn 2026 Series")
# Three races sailed and a fourth to come. None is published yet: the
# screenshots below publish race 1.
finishes = {
    1: [time(19, 31, 12), time(19, 28, 40), time(19, 30, 5), time(19, 27, 55)],
    2: [time(19, 24, 30), time(19, 26, 2), time(19, 22, 48), None],
    3: [time(19, 40, 16), time(19, 38, 9), time(19, 41, 30), time(19, 36, 44)],
}
entries = [SeriesEntry.objects.create(series=autumn, boat=boat)
           for boat in (kittiwake, tern, serendipity, blue_moon)]
for number, day in [(1, 16), (2, 23), (3, 30)]:
    race = Race.objects.create(series=autumn, number=number, date=date(2026, 9, day), start_time=time(18, 30))
    for entry, finish in zip(entries, finishes[number]):
        RaceEntry.objects.create(race=race, entry=entry)  # only a boat on the start sheet has a finish
        if finish:
            Finish.objects.create(race=race, entry=entry, finish_time=finish)
        else:
            Finish.objects.create(race=race, entry=entry, status="DNF")
# Race 4 is today, started 40 minutes ago, so the race day page offers its
# Finished buttons whenever the screenshots are taken (from 00:00 just after midnight).
started = max(timezone.localtime() - timedelta(minutes=40), timezone.localtime().replace(hour=0, minute=0, second=0))
race_4 = Race.objects.create(series=autumn, number=4, date=started.date(),
                             start_time=started.time().replace(microsecond=0))
# Race day for race 4: two boats ticked so far. The screenshots add a third.
RaceEntry.objects.create(race=race_4, entry=entries[0], persons_on_board=3)
RaceEntry.objects.create(race=race_4, entry=entries[2], persons_on_board=4)
wednesdays = Series.objects.create(club=club, name="Wednesday Evenings")

# A finished summer series, every race published and sent, ready to be
# declared final (slice 10). Race 3 was cancelled for weather: nothing recorded.
summer = Series.objects.create(club=club, name="Summer 2026 Series")
summer_entries = [SeriesEntry.objects.create(series=summer, boat=boat) for boat in (kittiwake, tern, serendipity)]
summer_finishes = {1: [time(19, 12, 40), time(19, 15, 2), time(19, 14, 21)],
                   2: [time(19, 20, 5), time(19, 18, 33), time(19, 21, 50)]}
sent = timezone.make_aware(datetime(2026, 7, 20, 21, 0))
for number, day in [(1, 1), (2, 8), (3, 15)]:
    race = Race.objects.create(series=summer, number=number, date=date(2026, 7, day), start_time=time(18, 30))
    if number in summer_finishes:
        for entry, finish in zip(summer_entries, summer_finishes[number]):
            RaceEntry.objects.create(race=race, entry=entry)
            Finish.objects.create(race=race, entry=entry, finish_time=finish)
        Race.objects.filter(pk=race.pk).update(published_at=sent, results_sent_at=sent)

# One request of each kind, waiting.
BoatRequest.objects.create(club=club,
    kind="REGISTER", requested_by=sam, sail_number="GBR 77", name="Puffin", make="Hunter",
    model="Channel 27", length_overall_m=Decimal("8.23"), waterline_length_m=Decimal("6.71"),
    base_number=Decimal("0.842"),
)
BoatRequest.objects.create(club=club,
    kind="CHANGE", boat=kittiwake, requested_by=pat, member_note="New RYA certificate this week",
    **{**{f: getattr(kittiwake, f) for f in BoatRequest.PROPOSED_FIELDS}, "base_number": Decimal("0.812")},
)
BoatRequest.objects.create(club=club, kind="CLAIM", boat=tern, requested_by=jo, member_note="Bought her in August")
EntryRequest.objects.create(series=wednesdays, boat=kittiwake, requested_by=pat)
print("Seeded the manual's sample data.")
