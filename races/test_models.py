"""Model rules the database and model validation enforce."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from races.models import Boat

pytestmark = pytest.mark.django_db


def make_boat(sail_number="GBR1234", base_number="0.964", **fields):
    return Boat.objects.create(sail_number=sail_number, base_number=Decimal(base_number), **fields)


# --- Boat ------------------------------------------------------------------


def test_boat_base_number_is_stored_exactly():
    boat = make_boat(base_number="0.964")
    boat.refresh_from_db()
    assert boat.base_number == Decimal("0.964")


@pytest.mark.parametrize("duplicate", ["GBR1234", "gbr1234", "GBR 1234", " gbr 12 34"])
def test_sail_numbers_are_unique_ignoring_case_and_spaces(duplicate):
    make_boat("GBR1234")
    with pytest.raises(IntegrityError):
        make_boat(duplicate)


def test_duplicate_sail_number_is_a_validation_error_on_the_field():
    make_boat("GBR1234")
    with pytest.raises(ValidationError) as caught:
        Boat(sail_number="gbr 1234", base_number=Decimal("0.9")).full_clean()
    assert "already registered" in str(caught.value)


def test_different_sail_numbers_are_allowed():
    make_boat("GBR1234")
    make_boat("GBR12345")
    assert Boat.objects.count() == 2


@pytest.mark.parametrize("base_number", ["0", "-0.5"])
def test_base_number_must_be_positive(base_number):
    with pytest.raises(ValidationError):
        Boat(sail_number="GBR1", base_number=Decimal(base_number)).full_clean()
    with pytest.raises(IntegrityError):
        make_boat(base_number=base_number)


def test_base_number_is_required():
    with pytest.raises(ValidationError) as caught:
        Boat(sail_number="GBR1").full_clean()
    assert "base_number" in caught.value.message_dict


def test_optional_boat_fields_may_be_blank():
    Boat(sail_number="GBR1", base_number=Decimal("0.9")).full_clean()
