"""The bridge between the database and the ``nhc`` scoring engine.

The engine takes plain Python data and knows nothing of Django, so this module
does the translation both ways: rows in, an ``nhc.Series`` built from them,
and the engine's results back out, joined to the rows they describe so a
template can show a boat's sail number rather than an id.

Results are computed here on every call and never stored. Replaying a series
is microseconds of arithmetic, and a stored result could go stale when a
finish is corrected; see docs/decisions.md.
"""

import logging
from dataclasses import dataclass

import nhc

from .models import Finish, Race, Series, SeriesEntry

logger = logging.getLogger(__name__)

NOT_SAILED = "No results recorded yet."
NO_FINISHER = (
    "Not scored yet. In a regatta, boats that do not finish are given times "
    "worked out from the boats that do, so this race is scored once at least "
    "one boat has a finish time."
)
WAITING = (
    "Not scored yet: it sails on the handicaps race {number} produces, and "
    "race {number} is not scored yet."
)
UNSCORABLE = (
    "These results cannot be calculated from the finishes recorded. Please let "
    "the race committee know. ({detail})"
)


@dataclass(frozen=True)
class BoatRaceResult:
    """One boat in one race: what was recorded, and what the engine made of it."""

    entry: SeriesEntry
    finish: Finish | None  # None when nothing was recorded, which scores DNC
    result: nhc.RaceResult


@dataclass(frozen=True)
class RaceResults:
    race: Race
    rows: tuple[BoatRaceResult, ...]  # finishing order, then non-finishers

    def for_entry(self, entry):
        return next(row for row in self.rows if row.entry.pk == entry.pk)


@dataclass(frozen=True)
class ScoreCell:
    race: Race
    points: float
    discarded: bool


@dataclass(frozen=True)
class StandingRow:
    entry: SeriesEntry
    position: int
    total: float
    scores: tuple[ScoreCell, ...]  # series order


@dataclass(frozen=True)
class SeriesResults:
    series: Series
    races: tuple[RaceResults, ...]  # scored races, series order
    standings: tuple[StandingRow, ...]
    # Races that exist but are not scored, each with the reason why, for the
    # pages to show instead of a results table.
    unscored: tuple[tuple[Race, str], ...] = ()
    # Set when the engine refused the series; nothing is scored then.
    error: str = ""

    def for_race(self, race):
        """This race's results, or None if it is not scored."""
        return next((r for r in self.races if r.race.pk == race.pk), None)

    def note_for(self, race):
        """Why this race has no results, or "" if it has them."""
        if self.error:
            return self.error
        return next((note for r, note in self.unscored if r.pk == race.pk), "")


def build_engine_series(series, entries, races):
    """The engine's view of a series: boats, races in order, and the rules.

    Entries are the boats; a boat's id is its entry's primary key. Every series
    starts on base numbers (RESET) - carrying handicaps over is not supported
    yet - so ``current_tcf`` is set to the base number too, and never read.
    """
    boats = [
        nhc.Boat(
            boat_id=str(entry.pk),
            base_number=float(entry.boat.base_number),
            current_tcf=float(entry.boat.base_number),
            name=str(entry.boat),
        )
        for entry in entries
    ]
    engine_races = [
        nhc.SeriesRace(
            race_id=str(race.pk),
            finishes=[
                nhc.Finish(
                    boat_id=str(finish.entry_id),
                    status=nhc.RaceStatus(finish.status),
                    elapsed_seconds=finish.elapsed_seconds,
                )
                for finish in race.finishes.all()
            ],
        )
        for race in races
    ]
    return nhc.Series(
        boats=boats,
        races=engine_races,
        series_type=nhc.SeriesType(series.series_type),
        progression=nhc.HandicapProgression.RESET,
        minimum_finishers=series.minimum_finishers,
        apply_a5_3=series.apply_a5_3,
        discards=series.discards,
    )


def score_series(series):
    """Replay a series through the engine and return template-ready results.

    Only races with something recorded are scored: a race that is scheduled
    but not sailed yet would otherwise score every boat DNC, and waste
    everyone's discard on it. In a regatta, a race with results but no finish
    time cannot be scored (the engine needs a finisher to back-calculate the
    others from), and neither can any race after it, since each race sails on
    the handicaps the one before produces. See docs/decisions.md.
    """
    entries = list(series.entries.select_related("boat"))
    races = list(series.races.order_by("number").prefetch_related("finishes"))
    if not entries:
        # The engine refuses a series with no boats, and there is nothing to show.
        return SeriesResults(series=series, races=(), standings=())

    scored, unscored = _scorable_races(series, races)
    if not scored:
        return SeriesResults(series=series, races=(), standings=(), unscored=tuple(unscored))

    try:
        outcome = nhc.score_series(build_engine_series(series, entries, scored))
    except nhc.InvalidInput as error:
        # Validation should stop any input the engine refuses from being saved.
        # If some route slips past it, the pages say so rather than crash.
        logger.exception("Series %s could not be scored", series.pk)
        return SeriesResults(
            series=series, races=(), standings=(), error=UNSCORABLE.format(detail=error)
        )

    entry_by_id = {str(entry.pk): entry for entry in entries}
    race_by_id = {str(race.pk): race for race in scored}

    race_results = []
    for race, race_outcome in zip(scored, outcome.races):
        finishes = {str(finish.entry_id): finish for finish in race.finishes.all()}
        rows = [
            BoatRaceResult(
                entry=entry_by_id[result.boat_id],
                finish=finishes.get(result.boat_id),
                result=result,
            )
            for result in race_outcome.results
        ]
        rows.sort(key=_finishing_order)
        race_results.append(RaceResults(race=race, rows=tuple(rows)))

    standings = tuple(
        StandingRow(
            entry=entry_by_id[standing.boat_id],
            position=standing.position,
            total=standing.total,
            scores=tuple(
                ScoreCell(race=race_by_id[s.race_id], points=s.points, discarded=s.discarded)
                for s in standing.scores
            ),
        )
        for standing in outcome.standings
    )

    return SeriesResults(
        series=series,
        races=tuple(race_results),
        standings=standings,
        unscored=tuple(unscored),
    )


def _scorable_races(series, races):
    """Split races into those to score and those to hold back, with reasons."""
    scored, unscored = [], []
    blocked_by = None
    for race in races:
        finishes = race.finishes.all()
        if not finishes:
            unscored.append((race, NOT_SAILED))
        elif blocked_by is not None:
            unscored.append((race, WAITING.format(number=blocked_by.number)))
        elif series.series_type == Series.SeriesType.REGATTA and not any(
            finish.status == Finish.Status.FINISHED for finish in finishes
        ):
            blocked_by = race
            unscored.append((race, NO_FINISHER))
        else:
            scored.append(race)
    return scored, unscored


def _finishing_order(row):
    position = row.result.position
    return (position is None, position or 0, row.result.status, row.entry.boat.sail_number)
