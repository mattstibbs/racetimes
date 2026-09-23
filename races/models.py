"""The race committee's records: boats, series, races and finishes.

Nothing here stores a handicap, a result or a place. Those are derived by
replaying a series through the ``nhc`` engine on every request (see
``races/scoring.py``), so a corrected finish can never leave a stale number
behind. The brief's rule is that handicaps are never edited directly.
"""

from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Replace, Upper


class Boat(models.Model):
    sail_number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True)
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    owner_name = models.CharField(max_length=100, blank=True)
    length_overall_m = models.DecimalField(
        "length overall (m)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    waterline_length_m = models.DecimalField(
        "waterline length (m)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # A Decimal, not a float, so the number shown is exactly the number typed.
    # It becomes a float only when handed to the engine.
    base_number = models.DecimalField(
        "NHC base number",
        max_digits=4,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="The published NHC base handicap (TCF), e.g. 0.964.",
    )

    class Meta:
        ordering = ["sail_number"]
        constraints = [
            # "GBR 1234" and "gbr1234" are the same boat. The constraint is on an
            # expression rather than a stored normalised copy so that Django's
            # form validation checks it too, and reports it against the sail
            # number field instead of failing on save.
            models.UniqueConstraint(
                Upper(Replace("sail_number", models.Value(" "), models.Value(""))),
                name="boat_sail_number_unique_ignoring_case_and_spaces",
                violation_error_message="A boat with this sail number is already registered.",
            ),
            models.CheckConstraint(
                condition=models.Q(base_number__gt=0),
                name="boat_base_number_positive",
            ),
        ]

    def __str__(self):
        return f"{self.sail_number} {self.name}".strip()


class Series(models.Model):
    """A set of races scored together, and the rules they are scored under.

    Every series starts on base numbers (the engine's RESET). Carrying
    handicaps over from a previous series is deferred until realignment has a
    workflow; see docs/decisions.md.
    """

    class SeriesType(models.TextChoices):
        # Values match nhc.SeriesType, so they convert with SeriesType(value).
        CLUB = "CLUB", "Club series"
        REGATTA = "REGATTA", "Regatta"

    name = models.CharField(max_length=100)
    series_type = models.CharField(
        max_length=10, choices=SeriesType.choices, default=SeriesType.CLUB
    )
    discards = models.PositiveSmallIntegerField(
        default=1, help_text="How many of each boat's worst scores are excluded (RRS A2.1)."
    )
    minimum_finishers = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "With fewer finishers than this, no handicap moves after a race. "
            "0 is off, which is the RYA's rule. Club series only."
        ),
    )
    apply_a5_3 = models.BooleanField(
        "score DNC below DNS and DNF (RRS A5.3)",
        default=False,
        help_text="Leave off for the default RRS A5.2 scoring.",
    )

    class Meta:
        verbose_name_plural = "series"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        # The engine refuses this combination outright. Catching it here puts
        # the error on the form where it can be fixed, rather than on the
        # results page where it cannot.
        if self.series_type == self.SeriesType.REGATTA and self.minimum_finishers:
            raise ValidationError(
                {"minimum_finishers": "A regatta has no minimum-finisher threshold; set this to 0."}
            )


class SeriesEntry(models.Model):
    """A boat entered in a series, and so scored in every race of it (RRS A2.2)."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="entries")
    # PROTECT: a boat's race history must not vanish because the boat record
    # was deleted.
    boat = models.ForeignKey(Boat, on_delete=models.PROTECT, related_name="series_entries")

    class Meta:
        verbose_name_plural = "series entries"
        ordering = ["boat__sail_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["series", "boat"],
                name="series_entry_unique_boat",
                violation_error_message="This boat is already entered in the series.",
            ),
        ]

    def __str__(self):
        return str(self.boat)


def _whole_seconds(value, field):
    if value is not None and value.microsecond:
        raise ValidationError({field: "Times are recorded to the whole second."})


class Race(models.Model):
    """One race in a series, with a single start."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="races")
    number = models.PositiveSmallIntegerField(
        help_text="Races are scored in this order, not by date."
    )
    date = models.DateField()
    # A plain time of day, stored as typed with no timezone: it is what the
    # race officer's watch said. Elapsed time is finish time minus this.
    start_time = models.TimeField()

    class Meta:
        ordering = ["series", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["series", "number"],
                name="race_number_unique_in_series",
                violation_error_message="This series already has a race with this number.",
            ),
        ]

    def __str__(self):
        return f"{self.series} - Race {self.number}"

    def clean(self):
        _whole_seconds(self.start_time, "start_time")


class Finish(models.Model):
    """What the race officer wrote down for one boat: a time, or a code."""

    class Status(models.TextChoices):
        # Values match nhc.RaceStatus. Only the engine's four for now; OCS, RET
        # and DSQ are deferred (see docs/decisions.md).
        FINISHED = "FINISHED", "Finished"
        DNC = "DNC", "DNC - did not come to the start"
        DNS = "DNS", "DNS - did not start"
        DNF = "DNF", "DNF - did not finish"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="finishes")
    # A finish belongs to the series entry rather than the boat, so one cannot
    # be recorded for a boat outside the series. RESTRICT rather than PROTECT:
    # removing an entry with results is refused, but deleting a whole series
    # still works, because the finishes go with its races.
    entry = models.ForeignKey(SeriesEntry, on_delete=models.RESTRICT, related_name="finishes")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.FINISHED)
    finish_time = models.TimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "finishes"
        constraints = [
            models.UniqueConstraint(
                fields=["race", "entry"],
                name="finish_unique_per_entry_per_race",
                violation_error_message="This boat already has a result in this race.",
            ),
            # A time or a code, never both.
            models.CheckConstraint(
                condition=(
                    models.Q(status="FINISHED", finish_time__isnull=False)
                    | (~models.Q(status="FINISHED") & models.Q(finish_time__isnull=True))
                ),
                name="finish_time_xor_code",
            ),
        ]

    def __str__(self):
        return f"{self.entry} in {self.race}"

    def clean(self):
        # Field-keyed errors, so the form shows them on the right box. Django
        # then skips the matching check constraint rather than repeating it.
        if self.status == self.Status.FINISHED and self.finish_time is None:
            raise ValidationError({"finish_time": "Enter a finish time, or choose a code."})
        if self.status != self.Status.FINISHED and self.finish_time is not None:
            raise ValidationError(
                {"finish_time": "A boat with a code has no finish time. Clear it, or choose Finished."}
            )
        _whole_seconds(self.finish_time, "finish_time")

        if not self.race_id:
            return
        if self.entry_id and self.race.series_id != self.entry.series_id:
            raise ValidationError("This boat is not entered in this race's series.")
        start = self.race.start_time
        if self.finish_time is not None and self.finish_time <= start:
            # Races past midnight are out of scope, so an early time is a typo.
            raise ValidationError(
                {"finish_time": f"The finish must be after the start ({start:%H:%M:%S})."}
            )

    @property
    def elapsed_seconds(self):
        """Finish time minus start time, in whole seconds. None without a time."""
        if self.finish_time is None:
            return None
        start = datetime.combine(self.race.date, self.race.start_time)
        return int((datetime.combine(self.race.date, self.finish_time) - start).total_seconds())
