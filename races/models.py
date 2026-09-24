"""The race committee's records: boats, series, races and finishes.

Nothing here stores a handicap, a result or a place. Those are derived by
replaying a series through the ``nhc`` engine on every request (see
``races/scoring.py``), so a corrected finish can never leave a stale number
behind. The brief's rule is that handicaps are never edited directly.
"""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Replace, Upper
from django.urls import reverse
from django.utils import timezone


class Boat(models.Model):
    sail_number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True)
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    owner_name = models.CharField(max_length=100, blank=True)
    # The member who owns the boat, set only by the race committee. Cleared if
    # the account is deleted; the boat and its results stay.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="boats",
    )
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

    @property
    def owner_display(self):
        """The owner as shown: the member's name if linked, else the typed name."""
        if self.owner is not None:
            return self.owner.get_full_name() or self.owner.get_username()
        return self.owner_name


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
        "use RRS A5.3",
        default=False,
        help_text=(
            "DNS and DNF score one more than the boats that came to the start, "
            "instead of one more than the series entries. DNC is unchanged. "
            "Only if the notice of race says so; off is RRS A5.2."
        ),
    )

    class Meta:
        verbose_name_plural = "series"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        # Also gives the admin its "View on site" button.
        return reverse("races:series_results", args=[self.pk])

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
    # Slice 4. Results are public as soon as they are saved, but provisional
    # until published. Publishing emails them; the committee can later send
    # them again after corrections, which moves results_sent_at on.
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    results_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

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
        if self.pk and self.start_time is not None:
            # Correcting a start time must not leave a finish at or before it:
            # that would be a zero or negative elapsed time, which no formula
            # can score.
            earliest = self.finishes.aggregate(earliest=models.Min("finish_time"))["earliest"]
            if earliest is not None and earliest <= self.start_time:
                raise ValidationError(
                    {
                        "start_time": (
                            f"Finishes are already saved from {earliest:%H:%M:%S}, so the "
                            "start must be earlier than that. Correct those finishes first "
                            "if the start really was later."
                        )
                    }
                )


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


class ScoringChange(models.Model):
    """One recorded change to something that feeds a score: who, when, what, why.

    Rows are written by ``races/audit.py`` in the same transaction as the change
    they describe, and never edited afterwards. There is deliberately no foreign
    key to the Finish, entry or boat described: the history has to outlive the
    rows it describes, so ``description`` and ``changes`` are kept as text.
    """

    class Kind(models.TextChoices):
        FINISH = "FINISH", "Finish"
        RACE = "RACE", "Race"
        SERIES = "SERIES", "Series settings"
        ENTRY = "ENTRY", "Entry"
        BOAT = "BOAT", "Boat"

    class Action(models.TextChoices):
        ADDED = "ADDED", "Added"
        CHANGED = "CHANGED", "Changed"
        REMOVED = "REMOVED", "Removed"

    timestamp = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # A copy of the username, so the record still says who after the account goes.
    user_name = models.CharField(max_length=150, blank=True)
    # Null only for a boat's base number change when the boat is in no series.
    series = models.ForeignKey(
        Series, on_delete=models.CASCADE, null=True, blank=True, related_name="scoring_changes"
    )
    race = models.ForeignKey(
        Race, on_delete=models.SET_NULL, null=True, blank=True, related_name="scoring_changes"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    action = models.CharField(max_length=10, choices=Action.choices)
    description = models.CharField(max_length=200)
    # {"Finish time": ["19:00:00", "19:05:30"]}: old and new, formatted for display.
    changes = models.JSONField(default=dict, blank=True)
    is_correction = models.BooleanField(default=False)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(is_correction=False) | ~models.Q(reason=""),
                name="scoring_change_correction_has_reason",
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.description}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A recorded change is never edited.")
        super().save(*args, **kwargs)


class Request(models.Model):
    """What a member asks the race committee for, and what the committee decided.

    Members change nothing directly (see docs/brief.md, "Roles and
    permissions"): every registration, change, claim and entry is one of these,
    and only approval by the committee applies it.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Waiting for the race committee"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    member_note = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # A copy of the username, as in the change history, so the record still
    # says who decided after the account goes.
    decided_by_name = models.CharField(max_length=150, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    # Shown to the member. Required when rejecting.
    committee_note = models.CharField(max_length=500, blank=True)

    class Meta:
        abstract = True
        ordering = ["-created_at", "-pk"]

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING


class BoatRequest(Request):
    """A member asking to register a boat, change one of theirs, or own one on record."""

    class Kind(models.TextChoices):
        REGISTER = "REGISTER", "Register a boat"
        CHANGE = "CHANGE", "Change a boat"
        CLAIM = "CLAIM", "Own a boat on record"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    # Empty for a registration, which has no boat until it is approved.
    boat = models.ForeignKey(
        Boat, on_delete=models.CASCADE, null=True, blank=True, related_name="requests"
    )
    # The boat as the member wants it to be. Filled in for a registration or a
    # change; empty for a claim, which changes only who owns the boat.
    sail_number = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=100, blank=True)
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    length_overall_m = models.DecimalField(
        "length overall (m)", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    waterline_length_m = models.DecimalField(
        "waterline length (m)", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    base_number = models.DecimalField(
        "NHC base number", max_digits=4, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    # The fields a registration or change proposes, in display order.
    PROPOSED_FIELDS = [
        "sail_number", "name", "make", "model",
        "length_overall_m", "waterline_length_m", "base_number",
    ]

    class Meta(Request.Meta):
        constraints = [
            # One thing at a time per boat, so two approvals can never race to
            # overwrite each other.
            models.UniqueConstraint(
                fields=["boat"],
                condition=models.Q(status="PENDING"),
                name="boat_request_one_pending_per_boat",
                violation_error_message="This boat already has a request waiting for the race committee.",
            ),
            models.CheckConstraint(
                condition=models.Q(kind="REGISTER", boat__isnull=True)
                | (~models.Q(kind="REGISTER") & models.Q(boat__isnull=False)),
                name="boat_request_boat_matches_kind",
            ),
        ]

    def __str__(self):
        target = self.boat or self.sail_number
        return f"{self.get_kind_display()}: {target}"


class EntryRequest(Request):
    """A member asking to enter one of their boats in a series."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="entry_requests")
    boat = models.ForeignKey(Boat, on_delete=models.CASCADE, related_name="entry_requests")

    class Meta(Request.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["series", "boat"],
                condition=models.Q(status="PENDING"),
                name="entry_request_one_pending_per_series_and_boat",
                violation_error_message="This boat already has an entry request for this series.",
            ),
        ]

    def __str__(self):
        return f"Enter {self.boat} in {self.series}"
