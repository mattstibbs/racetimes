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
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Replace, Upper
from django.urls import reverse
from django.utils import timezone


# --- Clubs (slice 11) ----------------------------------------------------------------


class Club(models.Model):
    """One sailing club using the service. Every boat and series belongs to one.

    A club is found from the address of each request: ``<subdomain>.<service
    domain>`` (see ``races/clubs.py``). Everything a page shows is filtered to
    that club with the ``for_club`` querysets below, so clubs never see each
    other's data.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"

    name = models.CharField(max_length=100)
    subdomain = models.CharField(
        max_length=40, unique=True,
        help_text="The club's address: <subdomain>.racetimes.co.uk. Lower-case letters, digits and hyphens.",
    )
    # Where replies to the club's emails go (slice 11, part 4).
    contact_email = models.EmailField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE


class ClubMembership(models.Model):
    """A person's place in a club: their role there, and whether it's approved (slice 11).

    Roles belong to a membership, not to the account, so one person can be a
    member at one club and on the race committee at another. Nobody has any
    access at a club until a club administrator approves their membership.
    """

    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        COMMITTEE = "COMMITTEE", "Race committee"
        ADMINISTRATOR = "ADMINISTRATOR", "Club administrator"

    class Status(models.TextChoices):
        WAITING = "WAITING", "Waiting for approval"
        APPROVED = "APPROVED", "Approved"
        REMOVED = "REMOVED", "Removed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=15, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    created_at = models.DateTimeField(default=timezone.now)
    # Who decided, kept as text so it survives their account being deleted.
    decided_by_name = models.CharField(max_length=150, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]
        constraints = [
            models.UniqueConstraint(fields=["user", "club"], name="one_membership_per_club"),
        ]

    def __str__(self):
        return f"{self.user} at {self.club}: {self.get_role_display()}, {self.get_status_display().lower()}"

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED


class ClubInvitation(models.Model):
    """The operator's invitation to someone to run a club (slice 11 part 3).

    The emailed link is a signed token naming this row (``races/invitations.py``),
    so the link itself isn't stored. Accepting it gives the person an approved
    membership in ``role``; the row then records when.
    """

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(
        max_length=15, choices=ClubMembership.Role.choices, default=ClubMembership.Role.ADMINISTRATOR
    )
    # Kept as text, like decided_by_name, so it survives the account going.
    invited_by_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} to {self.club}"


class OperatorAction(models.Model):
    """The operator log: one row for everything the operator does (slice 11 part 3).

    Who and which club are kept as text, so the log still reads the same after
    the account or the club is deleted.
    """

    class Action(models.TextChoices):
        CREATED = "CREATED", "Created a club"
        INVITED = "INVITED", "Invited an administrator"
        SUSPENDED = "SUSPENDED", "Suspended a club"
        REACTIVATED = "REACTIVATED", "Reactivated a club"

    who = models.CharField(max_length=150)
    action = models.CharField(max_length=15, choices=Action.choices)
    club_subdomain = models.CharField(max_length=40)
    detail = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-timestamp", "-pk"]

    def __str__(self):
        return f"{self.who}: {self.get_action_display()} ({self.club_subdomain})"


def _club_manager(path):
    """A manager whose ``for_club(club)`` keeps only that club's rows.

    ``path`` is how the model reaches its club, e.g. ``"race__series__club"``.
    Every page asks for club-owned rows through ``for_club`` (or through a row
    already found that way), so one club's data can never reach another's pages.
    ``races/test_isolation.py`` checks the code keeps to that.
    """

    class ClubQuerySet(models.QuerySet):
        club_path = path

        def for_club(self, club):
            return self.filter(**{path: club})

    return models.Manager.from_queryset(ClubQuerySet)()


class Boat(models.Model):
    # Only this club's rows: Boat.objects.for_club(club) (slice 11).
    objects = _club_manager("club")

    club = models.ForeignKey(Club, on_delete=models.CASCADE, editable=False, related_name="boats")
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
            # Unique within a club (slice 11): two clubs can each have a GBR 42.
            models.UniqueConstraint(
                "club",
                Upper(Replace("sail_number", models.Value(" "), models.Value(""))),
                name="boat_sail_number_unique_in_club",
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

    # Only this club's rows: Series.objects.for_club(club) (slice 11).
    objects = _club_manager("club")

    class SeriesType(models.TextChoices):
        # Values match nhc.SeriesType, so they convert with SeriesType(value).
        CLUB = "CLUB", "Club series"
        REGATTA = "REGATTA", "Regatta"

    club = models.ForeignKey(Club, on_delete=models.CASCADE, editable=False, related_name="series")
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
    # Slice 10: a series declared final is locked, and scored from a copy of
    # the engine's results saved when it was declared (races/final.py).
    declared_final_at = models.DateTimeField(null=True, blank=True, editable=False)
    declared_final_by_name = models.CharField(max_length=150, blank=True, editable=False)
    final_results = models.JSONField(null=True, blank=True, editable=False)
    final_results_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name_plural = "series"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_final(self):
        return self.declared_final_at is not None

    def get_absolute_url(self):
        # Also gives the admin its "View on site" button.
        return reverse("results:series", args=[self.pk])

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

    # Only this club's rows: SeriesEntry.objects.for_club(club) (slice 11).
    objects = _club_manager("series__club")

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

    def clean(self):
        # A boat belongs to one club, and races only in that club's series (slice 11).
        if self.boat_id and self.series_id and self.boat.club_id != self.series.club_id:
            raise ValidationError({"boat": "This boat belongs to another club."})


NOT_ON_START_SHEET = "This boat is not on the race's start sheet. Add it there first."


def _whole_seconds(value, field):
    if value is not None and value.microsecond:
        raise ValidationError({field: "Times are recorded to the whole second."})


class Race(models.Model):
    """One race in a series, with a single start."""

    # Only this club's rows: Race.objects.for_club(club) (slice 11).
    objects = _club_manager("series__club")

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


class RaceEntry(models.Model):
    """A boat on a race's start sheet: the committee says it came to race.

    Only a boat on the start sheet can have a finish recorded, and each one
    must have a time or a code before the race's results are published. A boat
    in the series but not on the start sheet stayed at home and scores DNC.
    Nothing here moves a score, so none of it is in the change history.
    """

    # Only this club's rows: RaceEntry.objects.for_club(club) (slice 11).
    objects = _club_manager("race__series__club")

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="race_entries")
    # CASCADE is safe: a series entry with finishes cannot be deleted at all
    # (Finish.entry is RESTRICT), so this only removes start sheet ticks.
    entry = models.ForeignKey(SeriesEntry, on_delete=models.CASCADE, related_name="race_entries")
    # For the committee only; public pages never show it.
    persons_on_board = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
    )

    class Meta:
        verbose_name = "start sheet entry"
        verbose_name_plural = "start sheet entries"
        ordering = ["race", "entry__boat__sail_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["race", "entry"],
                name="race_entry_unique_per_race",
                violation_error_message="This boat is already on the start sheet.",
            ),
            models.CheckConstraint(
                condition=models.Q(persons_on_board__isnull=True)
                | models.Q(persons_on_board__gte=1, persons_on_board__lte=99),
                name="race_entry_persons_on_board_range",
            ),
        ]

    def __str__(self):
        return f"{self.entry} in {self.race}"

    def clean(self):
        # A database constraint cannot compare two tables' series, so it is here.
        if self.race_id and self.entry_id and self.race.series_id != self.entry.series_id:
            raise ValidationError("This boat is not entered in this race's series.")


class Finish(models.Model):
    """What the race officer wrote down for one boat: a time, or a code."""

    # Only this club's rows: Finish.objects.for_club(club) (slice 11).
    objects = _club_manager("race__series__club")

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
    # Slice 9: when this finish was first saved, tapped or typed. The race day
    # page's two-minute Undo is measured from it. Empty for finishes saved
    # before slice 9, which therefore never offer Undo.
    recorded_at = models.DateTimeField(null=True, blank=True, editable=False)

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
        if self.entry_id and not RaceEntry.objects.filter(race=self.race, entry=self.entry).exists():
            raise ValidationError(NOT_ON_START_SHEET)
        start = self.race.start_time
        if self.finish_time is not None and self.finish_time <= start:
            # Races past midnight are out of scope, so an early time is a typo.
            raise ValidationError(
                {"finish_time": f"The finish must be after the start ({start:%H:%M:%S})."}
            )

    def save(self, *args, **kwargs):
        if self._state.adding and self.recorded_at is None:
            self.recorded_at = timezone.now()
        super().save(*args, **kwargs)

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

    # Only this club's rows: ScoringChange.objects.for_club(club) (slice 11).
    objects = _club_manager("club")

    class Kind(models.TextChoices):
        FINISH = "FINISH", "Finish"
        RACE = "RACE", "Race"
        SERIES = "SERIES", "Series settings"
        ENTRY = "ENTRY", "Entry"
        BOAT = "BOAT", "Boat"
        # Slice 10: declaring a series final, and reopening it. These move no
        # score, so they don't mark results amended.
        FINAL = "FINAL", "Final results"

    class Action(models.TextChoices):
        ADDED = "ADDED", "Added"
        CHANGED = "CHANGED", "Changed"
        REMOVED = "REMOVED", "Removed"

    # Every change belongs to a club, even a base number change for a boat in
    # no series, which has no series to say which club it was.
    club = models.ForeignKey(Club, on_delete=models.CASCADE, editable=False, related_name="scoring_changes")
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

    # Only this club's rows: BoatRequest.objects.for_club(club) (slice 11).
    objects = _club_manager("club")

    class Kind(models.TextChoices):
        REGISTER = "REGISTER", "Register a boat"
        CHANGE = "CHANGE", "Change a boat"
        CLAIM = "CLAIM", "Own a boat on record"

    # A registration has no boat yet, so the request says which club it's for.
    club = models.ForeignKey(Club, on_delete=models.CASCADE, editable=False, related_name="boat_requests")
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

    # Only this club's rows: EntryRequest.objects.for_club(club) (slice 11).
    objects = _club_manager("series__club")

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="entry_requests")
    boat = models.ForeignKey(Boat, on_delete=models.CASCADE, related_name="entry_requests")

    @property
    def club(self):
        # An entry request's club is its series' club; BoatRequest stores its own.
        return self.series.club

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
