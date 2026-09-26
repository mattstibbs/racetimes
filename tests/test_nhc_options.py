"""The optional extra NHC steps: capping extreme results and realigning to base numbers (slice 14).

Checked against one real Medway Cruising Club race, whose published results
used both steps (``tests/fixtures/mcc_full_nhc_method.yaml``). The test cases
follow section 7 of ``docs/slices/14-nhc-capping-realignment-spec.md``.
"""

import statistics

import pytest

from nhc import (
    Boat, Finish, InvalidInput, RaceInput, RaceStatus, Series, SeriesRace, SeriesType, capped_elapsed_times,
    compute_club_adjustment, realignment_factor, score_series,
)
from tests.scenario_loader import MCC_MODES, MCC_RACE, build_mcc_entries

BOATS = [boat["boat_id"] for boat in MCC_RACE["boats"]]
EXPECTED = {boat["boat_id"]: boat["expected"] for boat in MCC_RACE["boats"]}
FINISHERS = [boat["boat_id"] for boat in MCC_RACE["boats"] if boat["status"] == "FINISHED"]


def adjust(mode="off", entries=None, **options):
    cap, realign = MCC_MODES[mode]
    race = RaceInput(series_type=SeriesType.CLUB, entries=entries or build_mcc_entries())
    return {r.boat_id: r for r in compute_club_adjustment(race, cap_extremes=cap, realign_to_base=realign, **options)}


# --- Cases 1 to 4: every combination of the two settings -----------------------------------------


@pytest.mark.parametrize("mode", MCC_MODES)
@pytest.mark.parametrize("boat_id", BOATS)
def test_next_handicaps_match_the_published_figures(mode, boat_id):
    # Case 1 ("off") is today's calculation; case 4 ("both") is MCC's published results.
    assert round(adjust(mode)[boat_id].next_tcf, 3) == pytest.approx(EXPECTED[boat_id][mode], abs=1e-9)


def test_with_both_off_nothing_differs_from_the_rya_calculation():
    # The regression case in full precision, not just at 3 d.p.
    race = RaceInput(series_type=SeriesType.CLUB, entries=build_mcc_entries())
    assert compute_club_adjustment(race) == tuple(adjust("off").values())


def test_handicaps_are_kept_at_full_precision():
    # Rounding is for display only (docs/reference, section 7), with the options on too.
    assert adjust("both")["Lanternledger"].next_tcf != round(adjust("both")["Lanternledger"].next_tcf, 3)


# --- Step A: capping ---------------------------------------------------------------------------


def test_only_the_two_extreme_results_are_capped():
    results = adjust("cap_only")
    assert sorted(b for b, r in results.items() if r.capped) == sorted(MCC_RACE["intermediate"]["capped_boats"])
    assert not any(r.capped for r in adjust("off").values())


def test_the_band_is_the_mean_plus_and_minus_one_sample_standard_deviation():
    finishers = [e for e in build_mcc_entries() if e.status is RaceStatus.FINISHED]
    corrected = [e.elapsed_seconds * e.tcf_used for e in finishers]
    intermediate = MCC_RACE["intermediate"]
    assert statistics.mean(corrected) == pytest.approx(intermediate["mean_corrected_seconds"], abs=5e-4)
    assert statistics.stdev(corrected) == pytest.approx(intermediate["sample_sd_corrected_seconds"], abs=5e-4)
    used = capped_elapsed_times(finishers)
    upper = intermediate["mean_corrected_seconds"] + intermediate["sample_sd_corrected_seconds"]
    lower = intermediate["mean_corrected_seconds"] - intermediate["sample_sd_corrected_seconds"]
    assert used["Saltwake"] * 0.860 == pytest.approx(upper, abs=1e-2)  # slow: pulled back to the upper edge
    assert used["Lanternledger"] * 0.909 == pytest.approx(lower, abs=1e-2)  # fast: pulled up to the lower edge
    assert used["Lanternfold"] == 9932  # within the band: its real time


def test_the_sample_standard_deviation_not_the_population_one():
    # Case 8: with pstdev the band is narrower and Lanternledger would come out 0.950.
    assert round(adjust("both")["Lanternledger"].next_tcf, 3) == 0.955


def test_capping_leaves_the_fleet_ratio_times_places_and_points_alone():
    off, capped = adjust("off"), adjust("cap_only")
    for boat_id in BOATS:
        assert capped[boat_id].corrected_time == off[boat_id].corrected_time
        assert capped[boat_id].position == off[boat_id].position
        assert capped[boat_id].elapsed_seconds == off[boat_id].elapsed_seconds
    # k = sum(handicap) / sum(1 / elapsed) comes from the real times: an uncapped
    # boat's achieved handicap is exactly what it is with capping off.
    assert capped["Lanternfold"].achieved_handicap == off["Lanternfold"].achieved_handicap
    k = capped["Lanternfold"].achieved_handicap * 9932
    assert k == pytest.approx(MCC_RACE["intermediate"]["k"], abs=5e-4)


def test_fewer_than_three_finishers_are_never_capped():
    # Case 6.
    entries = [e for e in build_mcc_entries() if e.boat_id in ("Lanternledger", "Saltwake", "Wrenwake")]
    assert adjust("cap_only", entries) == adjust("off", entries)


# --- Step B: realignment -----------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["realign_only", "both"])
def test_the_finishers_new_handicaps_total_their_base_numbers(mode):
    results = adjust(mode)
    base_total = sum(b["base_number"] for b in MCC_RACE["boats"] if b["boat_id"] in FINISHERS)
    assert sum(results[b].next_tcf for b in FINISHERS) == pytest.approx(base_total, abs=1e-12)
    factor = results["Lanternledger"].realignment_factor
    assert factor == pytest.approx(MCC_RACE["intermediate"]["realignment_factor"][mode], abs=5e-6)
    assert all(results[b].realignment_factor == factor for b in FINISHERS)


def test_a_finisher_without_a_base_number_means_no_realignment_but_capping_still_runs():
    # Case 7. (In the app every boat has a base number; this guards the engine on its own.)
    results = adjust("both", build_mcc_entries(with_base_numbers=False))
    assert all(r.realignment_factor is None for r in results.values())
    assert {b: round(r.next_tcf, 3) for b, r in results.items()} == {b: e["cap_only"] for b, e in EXPECTED.items()}
    assert realignment_factor([], {}) is None


# --- Case 5: non-finishers ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", MCC_MODES)
def test_non_finishers_keep_their_handicap_and_count_in_no_sum(mode):
    results = adjust(mode)
    for boat_id in ("Wrenwake", "Nettlemere", "Gorsestar"):
        assert results[boat_id].next_tcf == results[boat_id].tcf_used
        assert results[boat_id].realignment_factor is None and not results[boat_id].capped
    # Without the non-finishers at all, the finishers come out exactly the same.
    finishers_only = [e for e in build_mcc_entries() if e.boat_id in FINISHERS]
    alone = adjust(mode, finishers_only)
    assert all(alone[b].next_tcf == results[b].next_tcf for b in FINISHERS)


# --- The options through a whole series, and where they don't apply ----------------------------


def mcc_series(**options):
    boats = [Boat(b["boat_id"], base_number=b["base_number"], current_tcf=b["handicap"]) for b in MCC_RACE["boats"]]
    finishes = [
        Finish(b["boat_id"], RaceStatus(b["status"]), elapsed_seconds=b["elapsed_seconds"]) for b in MCC_RACE["boats"]
    ]
    return Series(boats=boats, races=[SeriesRace("R1", finishes)], discards=0, **options)


def test_a_series_passes_the_options_to_each_race():
    outcome = score_series(mcc_series(cap_extremes=True, realign_to_base=True))
    next_handicaps = {r.boat_id: round(r.next_tcf, 3) for r in outcome.races[0].results}
    assert next_handicaps == {b: e["both"] for b, e in EXPECTED.items()}


@pytest.mark.parametrize("option", ["cap_extremes", "realign_to_base"])
def test_the_options_are_refused_on_a_regatta(option):
    boats = [Boat("A", base_number=1.0, current_tcf=1.0)]
    with pytest.raises(InvalidInput, match="club-series options"):
        Series(boats=boats, series_type=SeriesType.REGATTA, **{option: True})


def test_nothing_runs_in_a_race_below_the_minimum_finishers():
    results = adjust("both", minimum_finishers=20)
    assert all(r.next_tcf == r.tcf_used and r.realignment_factor is None for r in results.values())
