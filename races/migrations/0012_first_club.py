"""Slice 11: every existing row joins the first club.

The site held one club's data before clubs existed. This creates that club,
named from FIRST_CLUB_NAME and FIRST_CLUB_SUBDOMAIN (by default "Demo Club" at
demo.racetimes.co.uk, as the project owner chose), and gives it every boat,
series, boat request and change history row. Nothing else changes, so every
series scores exactly as before.

A fresh, empty database gets the club too. It's the club the site shows until
the operator sets up others, and the one tests use by default.
"""

import os

from django.db import migrations


def first_club(apps, schema_editor):
    Club = apps.get_model("races", "Club")
    club, _ = Club.objects.get_or_create(
        subdomain=os.environ.get("FIRST_CLUB_SUBDOMAIN", "demo"),
        defaults={"name": os.environ.get("FIRST_CLUB_NAME", "Demo Club")},
    )
    for model in ("Boat", "Series", "BoatRequest", "ScoringChange"):
        apps.get_model("races", model).objects.filter(club__isnull=True).update(club=club)


class Migration(migrations.Migration):
    dependencies = [("races", "0011_clubs")]

    # Going back leaves the rows' club in place; 0011's reversal drops the
    # column anyway.
    operations = [migrations.RunPython(first_club, migrations.RunPython.noop)]
