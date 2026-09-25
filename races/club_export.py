"""Everything a club holds, as one ZIP of CSV files (slice 11 part 5).

The club's administrators download it from the Members page, and the operator
from the club's operator page, which works while the club is suspended: that
pause before a club is deleted is when the export matters most.

Python's own ``zipfile`` and ``csv``; no new dependency. The files are small
(a club's whole history is a few thousand rows), so the ZIP is built in
memory. Every query starts from the club, so nothing of another club's gets
in; ``races/test_isolation.py`` checks that.
"""

import csv
import io
import json
import zipfile
from datetime import datetime
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone

from . import series_csv
from .models import (
    Boat, BoatRequest, ClubMembership, EntryRequest, Finish, Race, RaceEntry, ScoringChange, Series, SeriesEntry,
)
from .scoring import score_series
from .series_csv import BOM, typed

# Ids mean nothing outside the database; the club is the whole file; a final
# series' stored copy of its results is in its results file, readably.
LEFT_OUT = {"id", "request_ptr", "club", "final_results"}


def club_export(club):
    """The ZIP file's bytes."""
    tables = {
        "boats.csv": Boat.objects.for_club(club).select_related("owner").order_by("sail_number"),
        "members.csv": None,  # written by hand below: people's names aren't fields of the membership
        "series.csv": Series.objects.for_club(club).order_by("pk"),
        "series_entries.csv": SeriesEntry.objects.for_club(club).select_related("series", "boat").order_by("pk"),
        "races.csv": Race.objects.for_club(club).select_related("series").order_by("series", "number"),
        "start_sheets.csv": RaceEntry.objects.for_club(club).select_related("race__series", "entry__boat")
        .order_by("pk"),
        "finishes.csv": Finish.objects.for_club(club).select_related("race__series", "entry__boat").order_by("pk"),
        "boat_requests.csv": BoatRequest.objects.for_club(club).select_related("boat", "requested_by")
        .order_by("pk"),
        "entry_requests.csv": EntryRequest.objects.for_club(club).select_related("series", "boat", "requested_by")
        .order_by("pk"),
        "history.csv": ScoringChange.objects.for_club(club).select_related("series", "race").order_by("pk"),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, rows in tables.items():
            text = _members(club) if rows is None else _table(rows)
            archive.writestr(name, text)
        used = set()
        for series in Series.objects.for_club(club).order_by("pk"):
            name = series_csv.filename(series)
            if name in used:  # two series with the same name
                name = f"{series.pk} {name}"
            used.add(name)
            archive.writestr(f"results/{name}", series_csv.series_csv(series, score_series(series)))
    return out.getvalue()


def download(club):
    """The ZIP as a file to save."""
    response = HttpResponse(club_export(club), content_type="application/zip")
    name = f"{club.subdomain} race times data {timezone.localdate().isoformat()}.zip"
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def _members(club):
    header = ["name", "email", "role", "status", "joined", "decided_by", "decided_at"]
    memberships = ClubMembership.objects.filter(club=club).select_related("user").order_by("user__username")
    rows = [
        [m.user.get_full_name(), m.user.email, m.get_role_display(), m.get_status_display(), m.created_at,
         m.decided_by_name, m.decided_at]
        for m in memberships
    ]
    return _csv(header, rows)


def _table(queryset):
    fields = [f for f in queryset.model._meta.concrete_fields if f.name not in LEFT_OUT]
    rows = ([_cell(obj, field) for field in fields] for obj in queryset)
    return _csv([f.name for f in fields], rows)


def _cell(obj, field):
    if field.is_relation:
        related = getattr(obj, field.name)
        return "" if related is None else str(related)
    if field.choices:
        return getattr(obj, f"get_{field.name}_display")()
    return getattr(obj, field.attname)


def _csv(header, rows):
    out = io.StringIO()
    out.write(BOM)
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_text(value) for value in row])
    return out.getvalue()


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat(sep=" ", timespec="seconds") if timezone.is_aware(value) \
            else value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, (dict, list)):
        return typed(json.dumps(value, ensure_ascii=False))
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return typed(value)
