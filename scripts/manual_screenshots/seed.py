"""Sample club data for the user manual's screenshots.

Run only by run.sh, against a throwaway SQLite database it creates, never
against a real one. Every account's password is PASSWORD.
"""

from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import Group

from races.models import Boat, BoatRequest, EntryRequest, Finish, Race, Series, SeriesEntry
from races.roles import COMMITTEE_GROUP
from races.testing import make_member

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
kittiwake = Boat.objects.create(
    sail_number="GBR 42", name="Kittiwake", make="Westerly", model="Centaur",
    length_overall_m=Decimal("7.92"), waterline_length_m=Decimal("6.48"),
    base_number=Decimal("0.805"), owner=pat,
)
tern = Boat.objects.create(sail_number="GBR 7", name="Tern", base_number=Decimal("0.900"),
                           owner_name="M. Visitor")
autumn = Series.objects.create(name="Autumn 2026 Series")
race = Race.objects.create(series=autumn, number=1, date=date(2026, 9, 16), start_time=time(18, 30))
for boat, finish in [(kittiwake, time(19, 31, 12)), (tern, time(19, 28, 40))]:
    entry = SeriesEntry.objects.create(series=autumn, boat=boat)
    Finish.objects.create(race=race, entry=entry, finish_time=finish)
wednesdays = Series.objects.create(name="Wednesday Evenings")

# One request of each kind, waiting.
BoatRequest.objects.create(
    kind="REGISTER", requested_by=sam, sail_number="GBR 77", name="Puffin", make="Hunter",
    model="Channel 27", length_overall_m=Decimal("8.23"), waterline_length_m=Decimal("6.71"),
    base_number=Decimal("0.842"),
)
BoatRequest.objects.create(
    kind="CHANGE", boat=kittiwake, requested_by=pat, member_note="New RYA certificate this week",
    **{**{f: getattr(kittiwake, f) for f in BoatRequest.PROPOSED_FIELDS}, "base_number": Decimal("0.812")},
)
BoatRequest.objects.create(kind="CLAIM", boat=tern, requested_by=jo, member_note="Bought her in August")
EntryRequest.objects.create(series=wednesdays, boat=kittiwake, requested_by=pat)
print("Seeded the manual's sample data.")
