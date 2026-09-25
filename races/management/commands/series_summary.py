"""Print every series' standings, one line each, to compare two databases (slice 12).

After restoring a backup, run it against production and against the restored
copy, and compare: the lines should be identical (docs/production.md).

    python manage.py series_summary

Sail numbers and points only: nobody's name, so the output is safe to paste
into a ticket or a note.
"""

from django.core.management.base import BaseCommand

from races.models import Club, Series
from races.scoring import score_series
from races.templatetags.racing import points


class Command(BaseCommand):
    help = "Print every series' standings, one line each, to compare two databases."

    def handle(self, *args, **options):
        for club in Club.objects.order_by("subdomain"):
            for series in Series.objects.for_club(club).order_by("pk"):
                results = score_series(series)
                standings = ", ".join(
                    f"{row.entry.boat.sail_number} {points(row.total)}" for row in results.standings
                ) or "nothing scored"
                self.stdout.write(f"{club.subdomain} | {series.name} | {standings}")
