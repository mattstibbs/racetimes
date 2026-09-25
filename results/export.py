"""A series' standings and race results as one CSV file (slice 10).

It holds exactly what the series page shows, from the same ``score_series``,
formatted the same way, and no owner names or persons on board, like every
public page. Python's own csv module; no new dependency.
"""

import csv
import io

from django.utils import timezone

from races.templatetags.racing import hms, points, tcf

# Excel only reads a CSV as UTF-8 if it starts with a byte-order mark;
# without one, accented boat names come out garbled.
BOM = "﻿"


def series_csv(series, results):
    """The whole file, as text: a heading block, the standings, then each race."""
    out = io.StringIO()
    out.write(BOM)
    writer = csv.writer(out)
    row = writer.writerow

    row([series.name])
    if series.is_final:
        row([f"Final standings (declared {_day(timezone.localtime(series.declared_final_at))})"])
    else:
        row([f"Provisional standings as at {_day(timezone.localtime())} {timezone.localtime():%H:%M}"])
    settings = [series.get_series_type_display(), f"{series.discards} discard{'s' if series.discards != 1 else ''}"]
    if series.apply_a5_3:
        settings.append("Scored under RRS A5.3")
    if series.minimum_finishers:
        settings.append(f"No handicap changes with fewer than {series.minimum_finishers} finishers")
    row(settings)
    row([f"Downloaded {_day(timezone.localtime())} {timezone.localtime():%H:%M}"])

    row([])
    row(["Series Standings"])
    if results.error:
        row([results.error])
    elif not results.standings:
        row(["Nothing is scored in this series yet."])
    else:
        row(["Place", "Sail number", "Boat"] + [f"R{r.race.number}" for r in results.races] + ["Total"])
        for standing in results.standings:
            cells = [
                f"({points(cell.points)})" if cell.discarded else points(cell.points)
                for cell in standing.scores
            ]
            boat = standing.entry.boat
            row([standing.position, boat.sail_number, boat.name, *cells, points(standing.total)])

    for race_results in results.races:
        race = race_results.race
        row([])
        state = f"Published {_day(timezone.localtime(race.published_at))}" if race.published_at else "Provisional"
        row([f"Race {race.number}", _day(race.date), f"Start {race.start_time:%H:%M:%S}", state])
        row(["Place", "Sail number", "Boat", "Finish time", "Elapsed", "Handicap", "Corrected", "Points", "Code"])
        for line in race_results.rows:
            result, boat = line.result, line.entry.boat
            finish_time = line.finish.finish_time if line.finish else None
            row([
                result.position or "",
                boat.sail_number,
                boat.name,
                f"{finish_time:%H:%M:%S}" if finish_time else "",
                hms(result.elapsed_seconds),
                tcf(result.tcf_used),
                hms(result.corrected_time),
                points(result.points),
                "" if result.position else line.place,
            ])
    for race, note in results.unscored:
        row([])
        row([f"Race {race.number}", _day(race.date), note])
    return out.getvalue()


def _day(value):
    # "7 October 2026". strftime's %-d (no leading zero) doesn't work on Windows.
    return f"{value.day} {value:%B %Y}"


def filename(series):
    # Letters, digits, spaces and a few safe marks only, so no browser trips on it.
    safe = "".join(c for c in series.name if c.isalnum() or c in " -_()").strip() or "Series"
    return f"{safe} results.csv"
