"""The bridge between the database and the ``sailscoring`` scoring engine.

The engine takes plain Python data and knows nothing of Django, so this module
does the translation both ways: rows in, an ``sailscoring.Series`` (or, for a
Portsmouth Yardstick series, an ``sailscoring.FixedNumberSeries``) built from them,
and the engine's results back out, joined to the rows they describe so a
template can show a boat's sail number rather than an id.

Results are computed here on every call and never stored. Replaying a series
is microseconds of arithmetic, and a stored result could go stale when a
finish is corrected; see docs/decisions.md. The one exception is a series
declared final (slice 10): it is locked, and scored from the copy of the
engine's output saved when it was declared (``races/final.py``).
"""

import logging
from dataclasses import dataclass

import sailscoring

from . import final
from .models import Finish, Race, Series, SeriesEntry

logger = logging.getLogger(__name__)

NOT_SAILED = "No results recorded yet."
NOT_RECORDED = "Not recorded"
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
    result: sailscoring.RaceResult
    # On the start sheet but nothing recorded yet. Still scored DNC - the
    # engine is not told otherwise - but shown as "Not recorded", and the race
    # cannot be published until it is (slice 6).
    not_recorded: bool = False

    @property
    def place(self):
        """What goes in the Pos column: a place, a code, or "Not recorded"."""
        if self.result.position:
            return self.result.position
        return NOT_RECORDED if self.not_recorded else self.result.status

    @property
    def is_fixed_number(self):
        return isinstance(self.result, sailscoring.FixedNumberResult)

    @property
    def is_non_spinnaker(self):
        """Whether the boat raced on her non-spinnaker YTC number (slice 25)."""
        return self.entry.is_non_spinnaker

    @property
    def raced_on(self):
        """The number the boat raced on: a TCF under NHC, a PN under Portsmouth
        Yardstick (slice 24). The one place a template reads it, so it never
        reaches into either engine type."""
        if self.is_fixed_number:
            return self.result.number
        return self.result.tcf_used

    @property
    def next_handicap(self):
        """The handicap the boat takes into the next race. None where none can
        move (Portsmouth Yardstick)."""
        return None if self.is_fixed_number else self.result.effective_next_tcf

    @property
    def capped(self):
        """Whether the boat's result was capped as extreme (an NHC option)."""
        return False if self.is_fixed_number else self.result.capped


@dataclass(frozen=True)
class RaceResults:
    race: Race
    rows: tuple[BoatRaceResult, ...]  # finishing order, then non-finishers

    def for_entry(self, entry):
        return next(row for row in self.rows if row.entry.pk == entry.pk)

    @property
    def has_not_recorded(self):
        return any(row.not_recorded for row in self.rows)

    @property
    def has_scoring_penalty(self):
        return any(row.result.scoring_penalty for row in self.rows)

    @property
    def has_non_spinnaker(self):
        return any(row.is_non_spinnaker for row in self.rows)


@dataclass(frozen=True)
class ScoreCell:
    race: Race
    points: float
    discarded: bool
    scoring_penalty: bool = False  # SCP: this score includes a scoring penalty


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

    @property
    def has_scoring_penalty(self):
        """Whether any boat in any scored race took a scoring penalty (SCP)."""
        return any(race.has_scoring_penalty for race in self.races)

    @property
    def discards_apply(self):
        """Whether any score is excluded yet: discards set, and enough races scored."""
        return bool(self.series.discards) and (
            len(self.races) >= self.series.discard_threshold
        )

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
    starts on its boats' numbers (the engine's RESET) - carrying handicaps over
    is not supported yet - so an NHC boat's ``current_tcf`` is set to the base
    number too, and never read. A Portsmouth Yardstick series gets an
    ``sailscoring.FixedNumberSeries``, which has no handicap to start or move (slice 24).

    A boat without the series' number reaches the engine as None, which it
    refuses with ``InvalidInput``; ``score_series`` checks first, to say which.
    """
    engine_races = [
        sailscoring.SeriesRace(
            race_id=str(race.pk),
            finishes=[
                sailscoring.Finish(
                    boat_id=str(finish.entry_id),
                    status=sailscoring.RaceStatus(finish.status),
                    elapsed_seconds=finish.elapsed_seconds,
                    scoring_penalty=finish.scoring_penalty,
                )
                for finish in race.finishes.all()
            ],
        )
        for race in races
    ]
    if series.is_fixed_number:
        return sailscoring.FixedNumberSeries(
            boats=[
                sailscoring.FixedNumberBoat(
                    boat_id=str(entry.pk),
                    number=_as_float(entry.number),
                    name=str(entry.boat),
                )
                for entry in entries
            ],
            races=engine_races,
            system=sailscoring.FixedNumberSystem(series.handicap_system),
            apply_a5_3=series.apply_a5_3,
            discards=series.discards,
            discard_threshold=series.discard_threshold,
        )
    boats = [
        sailscoring.Boat(
            boat_id=str(entry.pk),
            base_number=_as_float(entry.boat.base_number),
            current_tcf=_as_float(entry.boat.base_number),
            name=str(entry.boat),
        )
        for entry in entries
    ]
    return sailscoring.Series(
        boats=boats,
        races=engine_races,
        series_type=sailscoring.SeriesType(series.series_type),
        progression=sailscoring.HandicapProgression.RESET,
        minimum_finishers=series.minimum_finishers,
        apply_a5_3=series.apply_a5_3,
        discards=series.discards,
        discard_threshold=series.discard_threshold,
        # Slice 14: the optional extra NHC steps, both off unless the series asks.
        cap_extremes=series.nhc_cap_extremes,
        realign_to_base=series.nhc_realign_to_base,
    )


def _as_float(value):
    return None if value is None else float(value)


def _run_engine(engine_series):
    """Score a series the way its kind says: NHC replay, or fixed numbers."""
    if isinstance(engine_series, sailscoring.FixedNumberSeries):
        return sailscoring.score_fixed_number_series(engine_series)
    return sailscoring.score_series(engine_series)


def setup_problem(series, entries):
    """What stops a series being scored, in words, or "" if nothing does.

    The forms refuse these (slice 24), so this is for a row that got past them.
    The pages then say so, rather than show results that quietly ignore a
    setting or crash on a boat with no number.
    """
    if series.is_fixed_number:
        system = series.get_handicap_system_display()
        unused = [
            reason
            for used, reason in [
                (series.series_type == Series.SeriesType.REGATTA, "a regatta"),
                (series.minimum_finishers, "a minimum finishers threshold"),
                (series.nhc_cap_extremes, "extreme-result capping"),
                (series.nhc_realign_to_base, "realignment to base handicaps"),
            ]
            if used
        ]
        if unused:
            return f"a {system} series can't use {', '.join(unused)}"
    # A boat is scored on the number her entry chose, which under RYA YTC is
    # one of two (slice 25), so each entry says which number it lacks.
    missing = {}
    for entry in entries:
        if entry.number is None:
            missing.setdefault(entry.number_label, []).append(str(entry.boat))
    return "; ".join(
        f"{', '.join(names)} {'has' if len(names) == 1 else 'have'} no {label}, "
        "which this series needs"
        for label, names in missing.items()
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
    entries, races = _load(series)
    if series.final_results is None:
        # A final series is scored from its stored copy, whatever has happened
        # to the boats since.
        problem = setup_problem(series, entries)
        if problem:
            return SeriesResults(
                series=series,
                races=(),
                standings=(),
                error=UNSCORABLE.format(detail=problem),
            )
    if not entries:
        # The engine refuses a series with no boats, and there is nothing to show.
        return SeriesResults(series=series, races=(), standings=())

    scored, unscored = _scorable_races(series, races)
    if not scored:
        return SeriesResults(
            series=series, races=(), standings=(), unscored=tuple(unscored)
        )

    try:
        if series.final_results is not None:
            # A final series is locked, so its races, entries and finishes are
            # as they were when declared. Only its boats can have changed, and
            # the copy keeps their base numbers as they were then.
            outcome = final.load(series.final_results)
        else:
            outcome = _run_engine(build_engine_series(series, entries, scored))
    except sailscoring.InvalidInput as error:
        # Validation should stop any input the engine refuses from being saved.
        # If some route slips past it, the pages say so rather than crash.
        logger.exception("Series %s could not be scored", series.pk)
        return SeriesResults(
            series=series, races=(), standings=(), error=UNSCORABLE.format(detail=error)
        )

    entry_by_id = {str(entry.pk): entry for entry in entries}
    return SeriesResults(
        series=series,
        races=tuple(
            _race_results(race, race_outcome, entry_by_id)
            for race, race_outcome in zip(scored, outcome.races, strict=True)
        ),
        standings=_standings(outcome, entry_by_id, scored),
        unscored=tuple(unscored),
    )


def engine_outcome(series):
    """The engine's own output for the series, replayed live: what a final series copies."""
    entries, races = _load(series)
    scored, _ = _scorable_races(series, races)
    return _run_engine(build_engine_series(series, entries, scored))


def _load(series):
    """The series' entries, and its races in order with their finishes and start sheets."""
    entries = list(series.entries.select_related("boat"))
    races = list(
        series.races.order_by("number").prefetch_related("finishes", "race_entries")
    )
    return entries, races


def _race_results(race, race_outcome, entry_by_id):
    """One race's results from the engine, matched back to its entries and finishes."""
    finishes = {str(finish.entry_id): finish for finish in race.finishes.all()}
    racing = {str(race_entry.entry_id) for race_entry in race.race_entries.all()}
    rows = [
        BoatRaceResult(
            entry=entry_by_id[result.boat_id],
            finish=finishes.get(result.boat_id),
            result=result,
            not_recorded=result.boat_id in racing and result.boat_id not in finishes,
        )
        for result in race_outcome.results
    ]
    rows.sort(key=_finishing_order)
    return RaceResults(race=race, rows=tuple(rows))


def _standings(outcome, entry_by_id, races):
    """The engine's standings, matched back to the series' entries and races."""
    race_by_id = {str(race.pk): race for race in races}
    penalised = {
        (result.boat_id, race.race_id)
        for race in outcome.races
        for result in race.results
        if result.scoring_penalty
    }
    return tuple(
        StandingRow(
            entry=entry_by_id[standing.boat_id],
            position=standing.position,
            total=standing.total,
            scores=tuple(
                ScoreCell(
                    race=race_by_id[score.race_id],
                    points=score.points,
                    discarded=score.discarded,
                    scoring_penalty=(standing.boat_id, score.race_id) in penalised,
                )
                for score in standing.scores
            ),
        )
        for standing in outcome.standings
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
    return (
        position is None,
        position or 0,
        row.result.status,
        row.entry.boat.sail_number,
    )
