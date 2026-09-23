"""The race committee's records: boats, series, races and finishes.

Nothing here stores a handicap, a result or a place. Those are derived by
replaying a series through the ``nhc`` engine on every request (see
``races/scoring.py``), so a corrected finish can never leave a stale number
behind. The brief's rule is that handicaps are never edited directly.
"""

from decimal import Decimal

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
