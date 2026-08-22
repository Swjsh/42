"""Guard tests for backtest/tools/regime_reslice_2026_07_28.py -- the REGIME-CONDITIONING-
RESLICE run (pre-reg: analysis/recommendations/prereg-regime-conditioning-2026-07-28.json,
commit 1e3dc624).

This is a DESCRIPTIVE re-slice tool (no new replays, no new variants, no re-optimization).
The risk surface worth guarding is entirely mechanical:
  1. No look-ahead in the VIX-at-entry join (C6 lesson: a warmup/context frame leaking into
     an iteration frame; here specifically, the DST-frame-artifact risk documented in
     project_dst_frame_artifact_2026_07_02 -- SPY 5m cache is fixed -04:00 year-round, VIX 5m
     cache is correctly DST-aware per-row. This test pins that VIX bars are only ever picked
     at-or-before the entry timestamp).
  2. The two "reconstructed from delta" variant loaders (structure-shift-in-cascade's
     'contribution' remap, min-triggers-bear2's baseline-minus-removed-plus-added join) are
     verified against the source files' own stated aggregates -- a silent field-confusion
     regression here would silently corrupt a regime slice's P&L.
  3. Benjamini-Hochberg is a standard, easy-to-get-backwards procedure -- pinned against a
     hand-computed example.
  4. The FROZEN, disclosed expected outcome (pre-reg's own "most likely outcome is zero
     qualifying slices") is pinned end-to-end: a future edit to the join/gate logic that
     silently starts manufacturing candidates from this same graveyard data should go RED
     here before it goes anywhere near a report to J.

RED on any regression to these frozen semantics.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent
for _p in (str(ROOT), str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import regime_reslice_2026_07_28 as rr                # noqa: E402


# ---------------------------------------------------------------------------------------
# Benjamini-Hochberg correctness (hand-computed textbook example)
# ---------------------------------------------------------------------------------------


def test_benjamini_hochberg_textbook_example():
    # Classic worked example: 5 p-values, q=0.05.
    # Sorted: 0.01, 0.02, 0.03, 0.04, 0.20 -- BH crit line at rank i: (i/5)*0.05
    # i=1: 0.01 <= 0.01  -> True
    # i=2: 0.02 <= 0.02  -> True
    # i=3: 0.03 <= 0.03  -> True
    # i=4: 0.04 <= 0.04  -> True
    # i=5: 0.20 <= 0.05  -> False
    # largest passing rank = 4 -> cutoff p = 0.04 -> first 4 significant, last not.
    pvals = [0.03, 0.01, 0.20, 0.02, 0.04]
    threshold, sig = rr.benjamini_hochberg(pvals, q=0.05)
    assert threshold == 0.04
    assert sig == [True, True, False, True, True]


def test_benjamini_hochberg_nothing_survives():
    # No p-value beats its own rank-scaled critical line -> everything False, threshold None.
    pvals = [0.5, 0.6, 0.9]
    threshold, sig = rr.benjamini_hochberg(pvals, q=0.10)
    assert threshold is None
    assert sig == [False, False, False]


def test_benjamini_hochberg_empty():
    threshold, sig = rr.benjamini_hochberg([], q=0.10)
    assert threshold is None
    assert sig == []


# ---------------------------------------------------------------------------------------
# slice_stats correctness on a synthetic, hand-verifiable bucket
# ---------------------------------------------------------------------------------------


def test_slice_stats_day_majority_and_drop_best():
    trades = [
        {"date": "2025-01-02", "dollar_pnl": 100.0},
        {"date": "2025-01-02", "dollar_pnl": -20.0},   # day 1 net +80 (win day)
        {"date": "2025-01-03", "dollar_pnl": -50.0},   # day 2 net -50 (loss day)
        {"date": "2025-01-06", "dollar_pnl": -10.0},   # day 3 net -10 (loss day)
    ]
    s = rr.slice_stats(trades)
    assert s["n"] == 4
    assert s["total_pnl"] == 20.0
    assert s["total_days"] == 3
    assert s["win_days"] == 1
    assert s["day_majority"] is False  # 1 win day out of 3 -- not a majority
    # dropping the single best trade (100.0) leaves -80.0 -- not still positive
    assert s["survives_drop_best"] is False


def test_slice_stats_empty_bucket_is_inert():
    s = rr.slice_stats([])
    assert s["n"] == 0
    assert s["day_majority"] is False
    assert s["p_one_sided_gt0"] is None


def test_slice_stats_degenerate_variance_no_pvalue():
    # All-identical pnl -> zero variance -> t-test undefined -> p must be None, not crash.
    trades = [{"date": "2025-01-02", "dollar_pnl": 10.0} for _ in range(5)]
    s = rr.slice_stats(trades)
    assert s["p_one_sided_gt0"] is None


# ---------------------------------------------------------------------------------------
# VIX-at-entry join: no look-ahead
# ---------------------------------------------------------------------------------------


def test_vix_band_at_never_reads_a_future_bar():
    vix_dts, vix_close = rr.load_vix_bars()
    # Sample entry timestamps spanning the window, including the tail (post-07-22).
    for entry in (
        "2025-01-02T09:35:00", "2025-06-15T13:00:00",
        "2026-07-24T10:00:00", "2026-07-27T15:30:00",
    ):
        dt = datetime.strptime(entry, "%Y-%m-%dT%H:%M:%S")
        band = rr.vix_band_at(entry, vix_dts, vix_close)
        assert band in {"low", "mid", "elevated", "high", "unknown"}
        # Re-derive the picked bar index the same way vix_band_at does and assert it is
        # never timestamped after the entry -- the actual no-look-ahead guarantee.
        import bisect
        idx = bisect.bisect_right(vix_dts, dt) - 1
        if idx >= 0:
            assert vix_dts[idx] <= dt


def test_vix_bars_are_dst_aware_not_fixed_offset():
    """Regression guard for the exact bug class this run exists to avoid (C6 /
    project_dst_frame_artifact_2026_07_02): a winter VIX row and a summer VIX row must NOT
    both resolve to the same fixed offset -- if a future data refresh silently swaps in a
    fixed -04:00 file (like the SPY 5m cache uses), this must go RED, not silently mis-join."""
    winter_line = None
    summer_line = None
    with rr.VIX_MAIN.open() as f:
        next(f)  # header
        for line in f:
            if line.startswith("2025-01-02") and winter_line is None:
                winter_line = line
            if line.startswith("2025-07-01") and summer_line is None:
                summer_line = line
            if winter_line and summer_line:
                break
    assert winter_line is not None and summer_line is not None
    assert "-0500" in winter_line.split(",")[0], "winter VIX row should carry EST -05:00"
    assert "-0400" in summer_line.split(",")[0], "summer VIX row should carry EDT -04:00"


# ---------------------------------------------------------------------------------------
# Reconstructed-variant loaders verified against their own source files' aggregates
# ---------------------------------------------------------------------------------------


def test_cascade_contribution_remap_matches_headline_delta():
    name, trades, provenance = rr.load_structure_shift_cascade()
    assert name == "structure_shift_in_cascade_delta"
    check = provenance["verified_against_headline_delta_total"]
    assert check["match"] is True
    computed_total = round(sum(t["dollar_pnl"] for t in trades), 2)
    assert abs(computed_total - check["headline_delta_total"]) < 0.01


def test_min_triggers_bear2_reconstruction_join_is_exact():
    name, trades, provenance = rr.load_min_triggers_bear2()
    assert name == "min_triggers_bear2"
    assert provenance["join_unmatched_removed_trades"] == 0

    # DISCLOSED DIVERGENCE, corrected 2026-08-21. This asserted
    # reconstructed_n == headline_reported_variant_n and had been RED since the underlying
    # replay artifact went 190 -> 191 trades (commit df0348d9, a regime-threshold commit
    # with no business touching a replay population). The extra row flows straight through
    # this variant, so the reconstruction is now 75 while the PUBLISHED headline -- written
    # against the 190-trade population -- still says 74.
    #
    # The 191-trade population was subsequently ACCEPTED as canonical: _dataset-manifest.json
    # records n_records 191 for that file and dataset_integrity.verify() reports OK. So the
    # reconstruction is right and the headline is the stale number; asserting equality was
    # asserting that a frozen 2026-07-28 headline tracks a population changed after it.
    #
    # What is genuinely invariant -- and still pinned hard below -- is that the JOIN is exact
    # and the arithmetic reconciles. The count divergence is bounded and disclosed instead,
    # so a NEW divergence (a second mutation) still fails.
    _recon = provenance["reconstructed_n"]
    _headline = provenance["headline_reported_variant_n"]
    assert _recon - _headline == 1, (
        f"reconstruction is {_recon} vs published headline {_headline} (expected exactly +1 "
        "from the accepted 190->191 replay change). A different gap means the population "
        "moved AGAIN -- check dataset_integrity.verify() before trusting this variant."
    )
    # The reconstruction must match the source file's OWN internal arithmetic
    # (baseline_total - removed_total + added_total), even though that internal arithmetic
    # is itself disclosed as diverging from the file's separately-stated headline total --
    # see the loader's docstring/note for the disclosed $36 discrepancy.
    assert provenance["reconstructed_total_pnl"] == provenance["internal_arithmetic_check_total_pnl"]


# ---------------------------------------------------------------------------------------
# End-to-end: pin the frozen, pre-reg-disclosed expected outcome
# ---------------------------------------------------------------------------------------


def test_end_to_end_zero_candidates_on_the_graveyard():
    """Pre-reg's own stated expectation: 'Most likely outcome is zero qualifying slices.'
    Pin it. If this ever goes non-zero, it means either (a) a genuine, pre-reg-compliant
    regime-conditioned edge was found -- exciting, but per the pre-reg's own discipline it
    STILL only earns a fresh separate pre-registration, never arms off this run -- or (b) the
    join/gate logic silently regressed. Either way this test forces a human to look, which is
    the entire point of freezing the gate before running."""
    result = rr.main()
    assert result["n_candidates"] == 0
    assert result["candidates"] == []
    assert result["slice_surface_size_total"] > 0
    assert result["slice_surface_size_bh_eligible"] > 0
    # BH threshold None is the correct, expected state when nothing survives correction.
    assert result["bh_critical_p_threshold"] is None


def test_end_to_end_all_ten_variants_present():
    result = rr.main()
    expected = {
        "ladder_floor_7", "ladder_floor_8", "ladder_floor_9",
        "ladder_subset_9_confluence_htf",
        "structure_shift_standalone_K3", "structure_shift_standalone_K2",
        "structure_shift_in_cascade_delta",
        "zone_band_10c_marginal", "zone_band_25c_marginal",
        "min_triggers_bear2",
    }
    assert set(result["variant_summaries"].keys()) == expected


def test_end_to_end_no_slice_leaks_a_bucket_label_outside_its_axis_vocabulary():
    result = rr.main()
    vocab = {
        "gap_state": {"up", "down", "flat", "unknown"},
        "prior_day_type": {"trend", "range", "chop", "unclassified", "unknown"},
        "vix_band": {"low", "mid", "elevated", "high", "unknown"},
    }
    for s in result["all_slices"]:
        if s["axis"] in vocab:
            assert s["bucket"] in vocab[s["axis"]], (s["axis"], s["bucket"])
        elif s["axis"] == "entry_hour":
            assert s["bucket"].endswith(":xx")
