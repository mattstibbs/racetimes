"""Model rules the database and model validation enforce."""

from datetime import time
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError, RestrictedError

from races.models import Boat, Finish, Race, Series, SeriesEntry
from races.testing import enter, make_boat, make_race, make_series, record

pytestmark = pytest.mark.django_db


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


# --- Series ----------------------------------------------------------------


def test_series_defaults_match_the_engine():
    series = make_series()
    assert series.series_type == Series.SeriesType.CLUB
    assert series.discards == 1
    assert series.minimum_finishers == 0
    assert series.apply_a5_3 is False


def test_regatta_refuses_a_minimum_finisher_threshold():
    series = Series(name="Regatta", series_type=Series.SeriesType.REGATTA, minimum_finishers=3)
    with pytest.raises(ValidationError) as caught:
        series.full_clean()
    assert "minimum_finishers" in caught.value.message_dict


def test_club_series_accepts_a_minimum_finisher_threshold():
    Series(name="Wednesdays", minimum_finishers=3).full_clean()


# --- SeriesEntry -----------------------------------------------------------


def test_a_boat_is_entered_in_a_series_once():
    series, boat = make_series(), make_boat()
    enter(series, boat)
    with pytest.raises(IntegrityError):
        enter(series, boat)


def test_a_boat_entered_in_a_series_cannot_be_deleted():
    boat = make_boat()
    enter(make_series(), boat)
    with pytest.raises(ProtectedError):
        boat.delete()


def test_an_entry_with_finishes_cannot_be_removed():
    series = make_series()
    entry = enter(series, make_boat())
    record(make_race(series), entry, "19:00:00")
    with pytest.raises(RestrictedError):
        entry.delete()


def test_deleting_a_series_deletes_its_races_entries_and_finishes():
    series = make_series()
    entry = enter(series, make_boat())
    record(make_race(series), entry, "19:00:00")
    series.delete()
    assert not SeriesEntry.objects.exists()
    assert not Race.objects.exists()
    assert not Finish.objects.exists()
    assert Boat.objects.count() == 1


# --- Race ------------------------------------------------------------------


def test_race_numbers_are_unique_within_a_series():
    series = make_series()
    make_race(series, number=1)
    make_race(make_series("Other"), number=1)
    with pytest.raises(IntegrityError):
        make_race(series, number=1)


def test_race_start_is_whole_seconds():
    race = Race(series=make_series(), number=1, date="2026-09-23", start_time=time(18, 0, 0, 500))
    with pytest.raises(ValidationError) as caught:
        race.full_clean()
    assert "start_time" in caught.value.message_dict


# --- Finish ----------------------------------------------------------------


@pytest.fixture
def race_and_entry():
    series = make_series()
    return make_race(series, start="18:00:00"), enter(series, make_boat())


def test_elapsed_seconds_is_finish_minus_start(race_and_entry):
    race, entry = race_and_entry
    assert record(race, entry, "19:02:17").elapsed_seconds == 3737


def test_a_code_has_no_elapsed_time(race_and_entry):
    race, entry = race_and_entry
    assert record(race, entry, status=Finish.Status.DNF).elapsed_seconds is None


@pytest.mark.parametrize(
    "status, finish_time",
    [("FINISHED", None), ("DNF", time(19, 0)), ("DNC", time(19, 0))],
)
def test_a_finish_is_a_time_or_a_code_never_both(race_and_entry, status, finish_time):
    race, entry = race_and_entry
    finish = Finish(race=race, entry=entry, status=status, finish_time=finish_time)
    with pytest.raises(ValidationError) as caught:
        finish.full_clean()
    assert "finish_time" in caught.value.message_dict
    with pytest.raises(IntegrityError):
        finish.save()


def test_one_finish_per_boat_per_race(race_and_entry):
    race, entry = race_and_entry
    record(race, entry, "19:00:00")
    with pytest.raises(IntegrityError):
        record(race, entry, status=Finish.Status.DNF)


@pytest.mark.parametrize("finish_time", [time(18, 0, 0), time(17, 59, 59), time(0, 30)])
def test_a_finish_must_be_after_the_start(race_and_entry, finish_time):
    race, entry = race_and_entry
    finish = Finish(race=race, entry=entry, finish_time=finish_time)
    with pytest.raises(ValidationError) as caught:
        finish.full_clean()
    assert "after the start" in str(caught.value)


def test_a_finish_is_whole_seconds(race_and_entry):
    race, entry = race_and_entry
    finish = Finish(race=race, entry=entry, finish_time=time(19, 0, 0, 1))
    with pytest.raises(ValidationError) as caught:
        finish.full_clean()
    assert "whole second" in str(caught.value)


def test_a_finish_needs_the_boat_entered_in_the_race_series(race_and_entry):
    race, _ = race_and_entry
    outsider = enter(make_series("Other"), make_boat("GBR999"))
    finish = Finish(race=race, entry=outsider, finish_time=time(19, 0))
    with pytest.raises(ValidationError) as caught:
        finish.full_clean()
    assert "not entered" in str(caught.value)
