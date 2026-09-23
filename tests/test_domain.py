"""Tests for the engine's domain types and their validation.

The types validate on construction, so an invalid race cannot be built at all.
That is the point of these tests: each one pins a rejection the spec asks for
(section 7) or an invariant the rest of the engine will rely on.
"""

import dataclasses
import math

import pytest

from nhc import (
    InvalidInput,
    Performance,
    RaceEntry,
    RaceInput,
    RaceStatus,
    RealignmentEntry,
    SeriesType,
)
from nhc.domain import Boat
from tests.scenario_loader import (
    RACE_SCENARIOS,
    RACE_SCENARIO_IDS,
    REALIGNMENT_SCENARIOS,
    REALIGNMENT_SCENARIO_IDS,
    build_race_input,
    build_realignment_entries,
)

#: Values that must never be accepted where the spec expects a handicap or a
#: time. Zero and negatives break the formulas; NaN and infinity are worse,
#: because they propagate silently through the fleet-wide sums.
BAD_NUMBERS = [0, -1, -0.001, float("nan"), float("inf"), float("-inf"), None]
BAD_NUMBER_IDS = ["zero", "negative", "small-negative", "nan", "inf", "-inf", "none"]


def finisher(boat_id="A", tcf=0.95, elapsed=3600.0, **kwargs):
    return RaceEntry(
        boat_id=boat_id,
        status=RaceStatus.FINISHED,
        tcf_used=tcf,
        elapsed_seconds=elapsed,
        **kwargs,
    )


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


def test_race_status_members_match_the_spec():
    assert {s.value for s in RaceStatus} == {"FINISHED", "DNC", "DNS", "DNF"}


def test_enums_compare_equal_to_plain_strings():
    # StrEnum, so fixture and JSON strings work without conversion at the edges.
    assert RaceStatus.DNF == "DNF"
    assert SeriesType.CLUB == "CLUB"
    assert Performance.OVER == "OVER"


@pytest.mark.parametrize(
    ("status", "expected"),
    [(RaceStatus.FINISHED, True), (RaceStatus.DNC, False), (RaceStatus.DNS, False), (RaceStatus.DNF, False)],
    ids=lambda v: str(v),
)
def test_only_finished_counts_as_a_finisher(status, expected):
    assert status.is_finisher is expected


# --------------------------------------------------------------------------
# Boat
# --------------------------------------------------------------------------


def test_boat_is_frozen():
    boat = Boat(boat_id="A", base_number=0.95, current_tcf=0.96)
    with pytest.raises(dataclasses.FrozenInstanceError):
        boat.current_tcf = 1.0


def test_boat_requires_an_id():
    with pytest.raises(InvalidInput, match="boat_id is required"):
        Boat(boat_id="", base_number=0.95, current_tcf=0.95)


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_boat_rejects_a_bad_base_number(bad):
    with pytest.raises(InvalidInput, match="base_number"):
        Boat(boat_id="A", base_number=bad, current_tcf=0.95)


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_boat_rejects_a_bad_current_tcf(bad):
    with pytest.raises(InvalidInput, match="current_tcf"):
        Boat(boat_id="A", base_number=0.95, current_tcf=bad)


# --------------------------------------------------------------------------
# RaceEntry
# --------------------------------------------------------------------------


def test_entry_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        finisher().tcf_used = 1.0


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_entry_rejects_a_bad_handicap(bad):
    with pytest.raises(InvalidInput, match="tcf_used"):
        finisher(tcf=bad)


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_finisher_rejects_a_bad_elapsed_time(bad):
    """Spec section 7: FINISHED with elapsed <= 0 is invalid input."""
    with pytest.raises(InvalidInput, match="elapsed_seconds"):
        finisher(elapsed=bad)


@pytest.mark.parametrize("status", [RaceStatus.DNC, RaceStatus.DNS, RaceStatus.DNF], ids=str)
def test_non_finisher_may_not_have_an_elapsed_time(status):
    with pytest.raises(InvalidInput, match="but an elapsed time"):
        RaceEntry(boat_id="A", status=status, tcf_used=0.95, elapsed_seconds=3600)


@pytest.mark.parametrize("no_time", [None, 0, 0.0], ids=["none", "int-zero", "float-zero"])
def test_non_finisher_time_is_normalised_to_none(no_time):
    """The spec writes E = 0 for a DNC and the fixtures follow it, but null is
    what a caller would naturally pass. Both must end up as None so the rest of
    the engine has one thing to test rather than two."""
    entry = RaceEntry(boat_id="A", status=RaceStatus.DNC, tcf_used=0.95, elapsed_seconds=no_time)
    assert entry.elapsed_seconds is None


def test_entry_rejects_a_status_outside_the_enum():
    with pytest.raises(InvalidInput, match="status must be one of"):
        RaceEntry(boat_id="A", status="RETIRED", tcf_used=0.95, elapsed_seconds=3600)


def test_entry_requires_an_id():
    with pytest.raises(InvalidInput, match="boat_id is required"):
        finisher(boat_id="")


def test_entry_base_number_is_optional():
    assert finisher().base_number is None


@pytest.mark.parametrize("bad", BAD_NUMBERS[:-1], ids=BAD_NUMBER_IDS[:-1])
def test_entry_rejects_a_bad_base_number_when_given(bad):
    with pytest.raises(InvalidInput, match="base_number"):
        finisher(base_number=bad)


# --------------------------------------------------------------------------
# RaceInput
# --------------------------------------------------------------------------


def test_entries_are_stored_as_a_tuple():
    """Any sequence in, an immutable tuple out - a caller holding onto its list
    cannot mutate a race after handing it over."""
    entries = [finisher("A"), finisher("B", elapsed=3700)]
    race = RaceInput(series_type=SeriesType.CLUB, entries=entries)
    entries.clear()
    assert isinstance(race.entries, tuple)
    assert len(race.entries) == 2


def test_race_needs_at_least_one_entry():
    with pytest.raises(InvalidInput, match="at least one entry"):
        RaceInput(series_type=SeriesType.CLUB, entries=[])


def test_race_rejects_a_duplicate_boat():
    with pytest.raises(InvalidInput, match="entered twice"):
        RaceInput(series_type=SeriesType.CLUB, entries=[finisher("A"), finisher("A")])


def test_race_rejects_a_series_type_outside_the_enum():
    with pytest.raises(InvalidInput, match="series_type must be one of"):
        RaceInput(series_type="PURSUIT", entries=[finisher()])


def test_finishers_excludes_boats_without_a_time():
    race = RaceInput(
        series_type=SeriesType.CLUB,
        entries=[
            finisher("A"),
            RaceEntry(boat_id="B", status=RaceStatus.DNC, tcf_used=0.98),
            RaceEntry(boat_id="C", status=RaceStatus.DNF, tcf_used=1.05),
        ],
    )
    assert [e.boat_id for e in race.finishers] == ["A"]


def test_club_race_ignores_the_regatta_first_race_flag():
    """Spec section 6 says the flag is ignored for club series, so it is
    accepted rather than rejected."""
    race = RaceInput(
        series_type=SeriesType.CLUB, entries=[finisher()], is_first_race_of_regatta=True
    )
    assert race.is_first_race_of_regatta is True


def test_regatta_requires_base_numbers():
    """Spec section 7: without a Base Number the +/-10% clamp cannot be applied."""
    with pytest.raises(InvalidInput, match="need a base_number"):
        RaceInput(series_type=SeriesType.REGATTA, entries=[finisher("A"), finisher("B")])


def test_regatta_names_every_boat_that_is_missing_one():
    with pytest.raises(InvalidInput, match="A, B"):
        RaceInput(
            series_type=SeriesType.REGATTA,
            entries=[finisher("A"), finisher("B"), finisher("C", base_number=0.9)],
        )


def test_regatta_accepts_entries_with_base_numbers():
    race = RaceInput(
        series_type=SeriesType.REGATTA,
        entries=[finisher("A", base_number=0.95), finisher("B", base_number=0.88)],
    )
    assert len(race.entries) == 2


# --------------------------------------------------------------------------
# RealignmentEntry
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_realignment_rejects_a_bad_base_number(bad):
    with pytest.raises(InvalidInput, match="base_number"):
        RealignmentEntry(boat_id="A", base_number=bad, ending_handicap=0.95)


@pytest.mark.parametrize("bad", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_realignment_rejects_a_bad_ending_handicap(bad):
    with pytest.raises(InvalidInput, match="ending_handicap"):
        RealignmentEntry(boat_id="A", base_number=0.95, ending_handicap=bad)


# --------------------------------------------------------------------------
# The types must be able to express every scenario in the fixtures
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", RACE_SCENARIOS, ids=RACE_SCENARIO_IDS)
def test_every_race_scenario_builds(scenario):
    race = build_race_input(scenario)
    assert len(race.entries) == len(scenario["boats"])
    for entry in race.entries:
        assert entry.tcf_used > 0
        assert (entry.elapsed_seconds is None) != entry.status.is_finisher


@pytest.mark.parametrize("scenario", REALIGNMENT_SCENARIOS, ids=REALIGNMENT_SCENARIO_IDS)
def test_every_realignment_scenario_builds(scenario):
    entries = build_realignment_entries(scenario)
    assert len(entries) == len(scenario["boats"])


def test_full_precision_is_preserved_through_construction():
    """The engine carries handicaps at full precision and never rounds between
    races; construction must not quietly round either. 0.88050096 is the
    realignment canary from SCEN-006, a whisker above the 3 d.p. boundary."""
    canary = 0.88050096
    entry = finisher(tcf=canary)
    assert entry.tcf_used == canary
    assert not math.isclose(round(entry.tcf_used, 3), canary)
