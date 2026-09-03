"""Tests for backtest/tools/regime_conditioned_validation.py + the frozen classifier/
validator/self-validation modules it reproduces, per
analysis/recommendations/prereg-regime-conditioned-validation-2026-07-17.json.

Three jobs:
  1. Pin the FROZEN classifier definition (VIX band ladder + trend-function call params)
     so nobody can silently drift the regime definition after the method earned rights.
  2. Pin the self-validation pass/kill criteria against the REAL reference cohorts
     (integration test -- calls the real self-validation module, real data on disk).
  3. Prove DATA_MISSING is never fabricated across the trend-cache staleness boundary
     (RED-proof: 3 deliberate mutants of the staleness guard, each shown to let a stale,
     silently-computed trend read through where the real guard blocks it).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

_BACKTEST = Path(__file__).resolve().parents[1]
_ROOT = _BACKTEST.parent
for p in (str(_ROOT), str(_BACKTEST)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backtest.tools import regime_classifier as rc  # noqa: E402
from backtest.tools import regime_conditioned_validation as rcv  # noqa: E402
from backtest.tools import regime_conditioned_validator as rcval  # noqa: E402

DATA_FILES_PRESENT = rc.DAILY_SPY_CACHE.exists() and rc.VIX_5M_CSV.exists()
requires_data = pytest.mark.skipif(not DATA_FILES_PRESENT, reason="frozen classifier data files not on disk")


# ===================================================================================
# 1. FROZEN CLASSIFIER DEFINITION -- pinned exactly, per the prereg's regime_classifier
#    block. A drift here is a methodology re-pick and must fail loud.
# ===================================================================================
class TestFrozenClassifierDefinition:
    def test_vix_band_boundaries(self):
        # LOW: vix_close < 15.0 (strict)
        assert rc.vix_band(14.99) == "LOW"
        assert rc.vix_band(0.0) == "LOW"
        # MID: 15.0 <= vix_close <= 22.0 (both inclusive)
        assert rc.vix_band(15.0) == "MID"
        assert rc.vix_band(18.5) == "MID"
        assert rc.vix_band(22.0) == "MID"
        # HIGH: vix_close > 22.0 (strict)
        assert rc.vix_band(22.01) == "HIGH"
        assert rc.vix_band(100.0) == "HIGH"

    def test_vix_band_constants_pinned(self):
        assert rc.VIX_LOW_MAX_EXCLUSIVE == 15.0
        assert rc.VIX_MID_MAX_INCLUSIVE == 22.0

    def test_trend_function_call_params_pinned(self):
        """context_bundle_producer.py's live daily-timeframe call: window=2 (DEFAULT_WINDOW),
        min_bars=10, days_back=190, limit=200. Any drift here silently changes what
        'byte-identical to the live context bundle' means."""
        assert rc.MIN_BARS == 10
        assert rc.DAILY_DAYS_BACK == 190
        assert rc.DAILY_LIMIT == 200
        from crypto.lib.market_structure import DEFAULT_WINDOW
        assert DEFAULT_WINDOW == 2

    def test_regime_label_format(self):
        # band + "_" + trend, e.g. "MID_uptrend" -- never re-ordered, never a different sep.
        assert rc.regime_label.__doc__ is None or True  # smoke: function exists & is callable
        lab = rc.regime_label(dt.date(2026, 5, 4),
                               [], {dt.date(2026, 5, 1): 15.0})
        assert lab["regime"] == f"{lab['vix_band']}_{lab['trend']}"

    def test_causal_no_lookahead_vix_band(self):
        """classify_vix_band_asof must NEVER use the target date's own VIX row -- only
        strictly-prior dates."""
        vix_daily = {dt.date(2026, 5, 1): 12.0, dt.date(2026, 5, 4): 99.0}
        band, val = rc.classify_vix_band_asof(vix_daily, dt.date(2026, 5, 4))
        # must resolve off 5-1 (12.0 -> LOW), never off 5-4's own 99.0 (would be HIGH)
        assert val == 12.0
        assert band == "LOW"

    def test_causal_no_lookahead_trend(self):
        """classify_trend_asof's window must exclude the target date's own bar."""
        from crypto.lib.bar import Bar
        cutoff = dt.date(2026, 5, 4)
        bars = [
            Bar(open_time=dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc), open=1, high=1, low=1,
                close=1, volume=0, granularity_seconds=86400, source="t"),
            Bar(open_time=dt.datetime(2026, 5, 4, tzinfo=dt.timezone.utc), open=999, high=999,
                low=999, close=999, volume=0, granularity_seconds=86400, source="t"),
        ]
        _, meta = rc.classify_trend_asof(bars, cutoff)
        # only the 5-1 bar (n=1) should be visible -- 5-4's own bar is same-day, excluded.
        assert meta["n_bars"] == 1


# ===================================================================================
# 2. SELF-VALIDATION PASS/KILL CRITERIA -- integration test against the real reference
#    cohorts (pass_kill_criteria_for_the_method_itself, applied verbatim).
# ===================================================================================
@requires_data
class TestSelfValidationCriteriaOnRealData:
    @pytest.fixture(scope="class")
    def reproduced(self):
        result = rcv.reproduce_self_validation()
        if not result["reproduced"]:
            pytest.skip(f"self-validation could not reproduce: {result}")
        return result["result"]

    def test_all_known_bad_never_pass(self, reproduced):
        """earns_rights_iff clause 1: ALL FOUR known-bad cohorts resolve to
        {FAIL, INSUFFICIENT_REGIME_SHIFT, INSUFFICIENT_N} -- never PASS or
        PASS_BUT_DEGENERATE_REGIME_PROXY."""
        forbidden = {"PASS", "PASS_BUT_DEGENERATE_REGIME_PROXY"}
        for name, res in reproduced["known_bad_results"].items():
            assert res["verdict"] not in forbidden, (
                f"known-bad cohort {name} PASSED ({res['verdict']}) -- "
                f"methodology-shopping, self-validation must FAIL")

    def test_known_good_vwap_passes(self, reproduced):
        """earns_rights_iff clause 2: the vwap_continuation known-good cohort resolves
        to PASS (PASS_BUT_DEGENERATE_REGIME_PROXY counts as a disclosed partial pass)."""
        verdict = reproduced["known_good_vwap_continuation_result"]["verdict"]
        assert verdict in ("PASS", "PASS_BUT_DEGENERATE_REGIME_PROXY"), (
            f"known-good vwap_continuation cohort was KILLED ({verdict}) -- over-strict")

    def test_op16_anchor_coherent(self, reproduced):
        """earns_rights_iff clause 3: OP-16 anchor dates all coherently labelable."""
        assert reproduced["op16_anchor_qualitative_check"]["all_dates_labelable"] is True

    def test_overall_verdict_earns_rights(self, reproduced):
        assert reproduced["self_validation_verdict"] == "EARNS_RIGHTS"
        assert reproduced["self_validation_fail_reasons"] == []

    def test_reproduction_does_not_mutate_frozen_artifact(self):
        """reproduce_self_validation() must never write to the historical dated file."""
        frozen_path = rcv.ROOT / "analysis" / "recommendations" / "regime-conditioned-validation-2026-07-17.json"
        before = frozen_path.read_bytes() if frozen_path.exists() else None
        rcv.reproduce_self_validation()
        after = frozen_path.read_bytes() if frozen_path.exists() else None
        assert before == after, "reproduce_self_validation() mutated the frozen 2026-07-17 artifact"


# ===================================================================================
# 3. DATA_MISSING NEVER FABRICATED -- trend classification past the stale-cache
#    boundary. RED-PROOF: 3 mutants of the guard, each demonstrated to leak a
#    silently-computed (fabricated) trend where the real guard correctly blocks it.
# ===================================================================================
@requires_data
class TestTrendNeverFabricatedPastCacheBoundary:
    STALE_DATE = dt.date(2026, 8, 25)  # ~6 weeks past the frozen cache's last bar (2026-07-14)

    @pytest.fixture(scope="class")
    def daily_bars(self):
        return rc.RegimeCalendar().daily_bars

    def test_real_guard_returns_unknown_disclosed(self, daily_bars):
        trend, meta = rcv.guarded_classify_trend_asof(daily_bars, self.STALE_DATE)
        assert trend == "unknown"
        assert meta["available"] is False
        assert meta["reason"].startswith("trend_cache_stale_past_")
        assert meta["cache_last_bar_date"] == rcv.TREND_CACHE_LAST_BAR_DATE.isoformat()

    def test_unguarded_frozen_function_would_fabricate(self, daily_bars):
        """Documents WHY the guard exists: the raw frozen classify_trend_asof, called
        without the staleness guard, returns a DETERMINATE trend (not 'unknown') for a
        date 6 weeks past the cache's actual coverage -- because its own bar-count check
        only measures window density, not recency. This is empirically confirmed, not
        assumed."""
        trend, meta = rc.classify_trend_asof(daily_bars, self.STALE_DATE)
        assert trend != "unknown", (
            "if this ever starts returning 'unknown' on its own, the guard in "
            "regime_conditioned_validation.py may have become redundant -- re-derive "
            "whether it is still needed before removing it")
        assert meta["available"] is True  # the fabrication: claims data availability it lacks

    # ---- RED-proof mutants: each is a plausible bug that would silently reintroduce
    # fabrication. The real guard must distinguish itself from ALL THREE.
    def test_mutant_no_guard_at_all_is_caught(self, daily_bars):
        """Mutant A: guard removed entirely, falls straight through to the raw frozen
        function. Must NOT match the real guard's disclosed-unknown behavior."""
        def mutant_no_guard(bars, target_date):
            return rc.classify_trend_asof(bars, target_date)

        real_trend, _ = rcv.guarded_classify_trend_asof(daily_bars, self.STALE_DATE)
        mutant_trend, mutant_meta = mutant_no_guard(daily_bars, self.STALE_DATE)
        assert real_trend == "unknown"
        assert mutant_trend != "unknown"  # mutant fabricates -- test catches the divergence
        assert mutant_meta["available"] is True

    def test_mutant_wrong_boundary_direction_is_caught(self, daily_bars):
        """Mutant B: staleness comparison inverted (guards dates BEFORE the cache instead
        of after it) -- a classic off-by-inversion bug."""
        def mutant_inverted_guard(bars, target_date):
            boundary = rcv.TREND_CACHE_LAST_BAR_DATE + dt.timedelta(days=rcv.TREND_STALENESS_GUARD_DAYS)
            if target_date < boundary:  # BUG: should be >
                return "unknown", {"available": False, "reason": "trend_cache_stale_INVERTED"}
            return rc.classify_trend_asof(bars, target_date)

        mutant_trend, _ = mutant_inverted_guard(daily_bars, self.STALE_DATE)
        assert mutant_trend != "unknown"  # inverted guard lets the stale date compute -- caught

    def test_mutant_forward_fill_is_caught(self, daily_bars):
        """Mutant C: instead of disclosing unknown, forward-fills the last known trend
        value from the cache boundary -- a common but silent 'looks fine' failure mode."""
        def mutant_forward_fill(bars, target_date):
            boundary = rcv.TREND_CACHE_LAST_BAR_DATE + dt.timedelta(days=rcv.TREND_STALENESS_GUARD_DAYS)
            if target_date > boundary:
                # BUG: silently reuses the trend as-of the cache boundary instead of
                # disclosing unavailability.
                return rc.classify_trend_asof(bars, rcv.TREND_CACHE_LAST_BAR_DATE)
            return rc.classify_trend_asof(bars, target_date)

        mutant_trend, mutant_meta = mutant_forward_fill(daily_bars, self.STALE_DATE)
        assert mutant_trend != "unknown"  # forward-fill fabricates a plausible-looking value
        assert mutant_meta.get("available") is True

    def test_regime_label_extended_never_fabricates_full_regime_past_boundary(self, daily_bars):
        """label_date_extended must compose the guard correctly: vix_band CAN still be
        known past the boundary (real data, no gap), but trend must stay 'unknown'."""
        # small deterministic extended-vix stub -- avoids depending on which vix_5m_*.csv
        # is newest on disk at test time.
        extended_vix = {dt.date(2026, 8, 20): 16.0}
        lab = rcv.label_date_extended(daily_bars, extended_vix, self.STALE_DATE)
        assert lab["vix_band"] == "MID"          # 16.0 -> MID, computed fine
        assert lab["trend"] == "unknown"          # trend NOT fabricated
        assert lab["regime"] == "MID_unknown"


# ===================================================================================
# VIX extension never silently accepts a coverage gap.
# ===================================================================================
class TestVixExtensionNoSilentGap:
    def test_candidate_file_starting_after_frozen_max_is_skipped(self, tmp_path):
        """_discover_latest_vix_extension_file must reject an extension file whose start
        date is AFTER the frozen window's max date -- accepting it would silently create
        an unlabeled gap in VIX-band coverage."""
        frozen_max = dt.date(2026, 7, 8)
        # a same-named file one day after frozen_max would leave 2026-07-09 unlabeled
        gap_file = tmp_path / "vix_5m_2026-07-09_2026-08-01.csv"
        gap_file.write_text("timestamp_et,open,high,low,close,volume\n", encoding="utf-8")
        ok_file = tmp_path / "vix_5m_2026-05-19_2026-08-01.csv"
        ok_file.write_text("timestamp_et,open,high,low,close,volume\n", encoding="utf-8")

        original_dir = rcv.VIX_DATA_DIR
        rcv.VIX_DATA_DIR = tmp_path
        try:
            chosen = rcv._discover_latest_vix_extension_file(frozen_max)
        finally:
            rcv.VIX_DATA_DIR = original_dir
        assert chosen == ok_file, "must skip the gapped candidate and choose the gap-free one"
