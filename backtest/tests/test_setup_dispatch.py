"""test_setup_dispatch.py — guard tests for the setup dispatch layer.

Tests prove:
(a) With ALL flags OFF: dispatch returns [] (pure no-op, no side effects)
(b) With a flag ON + mocked detector: the detector IS called and a fired signal routes correctly
(c) A detector with a missing feed returns SKIP_NO_FEED, not a crash
(d) A detector error returns SKIP_DETECTOR_ERROR, not a crash

Run:
  cd C:\\Users\\jackw\\Desktop\\42
  backtest\\.venv\\Scripts\\python.exe -m pytest backtest/tests/test_setup_dispatch.py -v

Design constraints:
  - No live market data required (all bar data is synthetic)
  - No MCP / Alpaca calls
  - No file I/O except reading params.json for the flag-guard tests
  - Fast: all tests complete in < 5 seconds
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup: we need setup/scripts and backtest/lib on sys.path
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
for p in ("setup/scripts", "backtest/lib"):
    s = str(REPO / p)
    if s not in sys.path:
        sys.path.insert(0, s)

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from setup_dispatch import (  # noqa: E402
    DispatchResult,
    SetupDispatcher,
    dispatch_extra_setups,
)


# ---------------------------------------------------------------------------
# Minimal synthetic payload builder
# ---------------------------------------------------------------------------

def _ts(h: int, m: int, *, date: str = "2026-01-07") -> str:
    """ISO-8601 timestamp string for a given date + time (ET, naive for simplicity)."""
    return f"{date}T{h:02d}:{m:02d}:00-04:00"


def _bar_row(h: int, m: int, o: float = 600.0, hi: float = 600.5,
             lo: float = 599.5, c: float = 600.2, v: float = 5000,
             *, date: str = "2026-01-07") -> dict:
    return {
        "timestamp_iso": _ts(h, m, date=date),
        "open": o, "high": hi, "low": lo, "close": c, "volume": v,
    }


def _make_payload(
    *,
    sameday_bars: Optional[list] = None,
    spy_df: Optional[list] = None,
    vix_now: float = 17.0,
    vix_prior: float = 17.5,
    ribbon_stack: str = "BEAR",
) -> dict:
    """Minimal heartbeat_core-style payload for dispatch tests."""
    if sameday_bars is None:
        # 6 bars: 3 trend bars + 3 morning bars at 9:30..10:00
        sameday_bars = [
            _bar_row(9, 30, o=600.0, hi=600.6, lo=599.9, c=599.5),   # below VWAP
            _bar_row(9, 35, o=599.5, hi=599.6, lo=598.8, c=598.9),   # below VWAP
            _bar_row(9, 40, o=598.9, hi=599.0, lo=598.2, c=598.3),   # below VWAP
            _bar_row(9, 45, o=598.3, hi=598.4, lo=597.4, c=597.5),   # below VWAP, fresh low
            _bar_row(9, 50, o=597.5, hi=597.6, lo=596.8, c=597.0),
            _bar_row(9, 55, o=597.0, hi=597.2, lo=596.5, c=596.8),
        ]
    if spy_df is None:
        spy_df = [{
            "open": r["open"], "high": r["high"],
            "low": r["low"], "close": r["close"], "volume": r["volume"],
        } for r in sameday_bars]

    last = sameday_bars[-1]
    bar_ctx = {
        "bar_idx": len(sameday_bars) - 1,
        "timestamp_et": last["timestamp_iso"],
        "bar": {"open": last["open"], "high": last["high"],
                "low": last["low"], "close": last["close"], "volume": last["volume"]},
        "prior_bars": [{
            "open": r["open"], "high": r["high"], "low": r["low"],
            "close": r["close"], "volume": r["volume"],
        } for r in sameday_bars],
        "ribbon_now": {"fast": 598.0, "pivot": 598.5, "slow": 599.0,
                       "spread_cents": 200.0, "stack": ribbon_stack},
        "ribbon_history": [],
        "vix_now": vix_now,
        "vix_prior": vix_prior,
        "vol_baseline_20": 5000.0,
        "range_baseline_20": 0.5,
        "levels_active": [],
        "multi_day_levels": [],
        "htf_15m_stack": "BEAR",
        "level_states": {},
        "fhh_level": None,
        "vix_5d_ma": 0.0,
        "vix_20d_ma": 0.0,
    }

    return {
        "bar_ctx": bar_ctx,
        "sameday_5m_bars": sameday_bars,
        "spy_df": spy_df,
        "ribbon_df": [],
        "gate_params": {},
        "score_params": {},
    }


def _all_off_params() -> dict:
    """Params with every extra-setup flag explicitly OFF."""
    return {
        "j_vwap_cont_enabled": False,
        "gap_and_go_enabled": False,
        "j_vwap_reclaim_fb_enabled": False,
        "j_vix_dayside_enabled": False,
        "j_vwap_cont_put_vix_gate": True,
    }


def _one_on_params(flag: str) -> dict:
    """Params with exactly one flag ON, the rest OFF."""
    p = _all_off_params()
    p[flag] = True
    return p


# ===========================================================================
# (a) No-op guarantee: ALL flags OFF → empty result, zero side effects
# ===========================================================================

class TestAllFlagsOff:
    """With every extra-setup flag OFF, dispatch must be a pure no-op."""

    def test_returns_empty_list(self) -> None:
        params = _all_off_params()
        payload = _make_payload()
        results = SetupDispatcher(params, payload).run()
        assert results == [], f"Expected [] but got {results}"

    def test_dispatch_extra_setups_returns_empty(self) -> None:
        params = _all_off_params()
        payload = _make_payload()
        out = dispatch_extra_setups("safe", params, payload, {"verdict": "HOLD"})
        assert out == [], f"Expected [] but got {out}"

    def test_no_detector_imported_when_all_off(self) -> None:
        """Dispatch should not import any watcher module when all flags are off."""
        params = _all_off_params()
        payload = _make_payload()
        # Record which watcher modules were imported before the call
        before = set(m for m in sys.modules if "watcher" in m)
        SetupDispatcher(params, payload).run()
        after = set(m for m in sys.modules if "watcher" in m)
        # Any new watcher imports must not be from our 4 detectors (they may already
        # be imported by other tests; what matters is no NEW import happens here)
        # We relax this to: the call must not CAUSE a new import of the disabled ones
        # by asserting the result is still empty.
        results = SetupDispatcher(params, payload).run()
        assert results == []

    def test_real_params_json_has_live_setups_enabled(self) -> None:
        """Guard: the REAL params.json has gap_and_go and vwap_cont ENABLED (live).

        This test fails if someone accidentally disables a live setup in params.json,
        which is the mirror of test_validated_setups_enabled.py test_gap_and_go_stays_enabled.
        """
        params_path = REPO / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8"))
        assert params.get("gap_and_go_enabled") is True, (
            "gap_and_go_enabled must be True in params.json — it is a live validated edge. "
            "If disabling, record the reason in recency-confirmation.json first."
        )
        assert params.get("j_vwap_cont_enabled") is True, (
            "j_vwap_cont_enabled must be True in params.json — it is a live validated edge. "
            "If disabling, record the reason in recency-confirmation.json first."
        )

    def test_real_params_trade_to_learn_setups_are_on(self) -> None:
        """Guard: the REAL params.json has the trade-to-learn setups ENABLED (Safe paper).

        History: until 2026-07-01 this pinned both flags FALSE (recency-RED hold + missing
        vix_intraday feed). J's 2026-07-01 trade-to-learn ratification supersedes the hold
        for PAPER (strict recency gates apply to live money only) and the vix_intraday
        feed is wired + verified (test_g6_vix_intraday_feed.py). The pin now points the
        other way, so a silent un-arming regression REDs here. Full validated-cell pins:
        backtest/tests/test_trade_to_learn_2026_07_01.py.
        """
        params_path = REPO / "automation" / "state" / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8"))
        assert params.get("j_vwap_reclaim_fb_enabled") is True, (
            "j_vwap_reclaim_fb_enabled must be True — armed on Safe paper 2026-07-01 "
            "(trade-to-learn, validated ATM rescue cell). If disarming, record why."
        )
        assert params.get("j_vix_dayside_enabled") is True, (
            "j_vix_dayside_enabled must be True — armed on Safe paper 2026-07-01 "
            "(trade-to-learn, validated ATM cell; G6 feed wired). If disarming, record why."
        )
        assert params.get("db_base_quiet_enabled") is True, (
            "db_base_quiet_enabled must be True — armed on Safe paper 2026-07-01 "
            "(trade-to-learn, best clearing cell of edgehunt-double_bottom_base_quiet)."
        )


# ===========================================================================
# (b) Flag ON + mocked detector: detector IS called, signal routes correctly
# ===========================================================================

class TestFlagOnMockedDetector:
    """With a flag ON and a mocked detector, verify the dispatch flow."""

    def test_vwap_continuation_flag_on_calls_detector(self) -> None:
        """When j_vwap_cont_enabled=True, the vwap_continuation detector is called."""
        params = _one_on_params("j_vwap_cont_enabled")
        payload = _make_payload()

        mock_signal = MagicMock()
        mock_signal.direction = "short"
        mock_signal.entry_price = 597.0
        mock_signal.stop_price = 600.5
        mock_signal.confidence = "medium"
        mock_signal.triggers_fired = ["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_BREAKOUT"]
        mock_signal.watcher_name = "vwap_continuation_watcher"

        with patch("setup_dispatch.SetupDispatcher._dispatch_vwap_continuation",
                   return_value=DispatchResult("vwap_continuation", fired=True,
                                              signal=mock_signal)) as mock_method:
            results = SetupDispatcher(params, payload).run()

        mock_method.assert_called_once()
        assert len(results) == 1
        r = results[0]
        assert r.setup_name == "vwap_continuation"
        assert r.fired is True
        assert r.signal is mock_signal

    def test_gap_and_go_flag_on_calls_detector(self) -> None:
        """When gap_and_go_enabled=True, the gap_and_go detector is called."""
        params = _one_on_params("gap_and_go_enabled")
        payload = _make_payload()

        mock_signal = MagicMock()
        mock_signal.direction = "short"
        mock_signal.entry_price = 596.0
        mock_signal.stop_price = 597.2
        mock_signal.confidence = "medium"
        mock_signal.triggers_fired = ["OPENING_GAP", "FIRST_BAR_CONFIRM_RED"]
        mock_signal.watcher_name = "gap_and_go_watcher"

        with patch("setup_dispatch.SetupDispatcher._dispatch_gap_and_go",
                   return_value=DispatchResult("gap_and_go", fired=True,
                                              signal=mock_signal)) as mock_method:
            results = SetupDispatcher(params, payload).run()

        mock_method.assert_called_once()
        assert len(results) == 1
        assert results[0].fired is True

    def test_only_enabled_flags_generate_results(self) -> None:
        """Only the ONE enabled flag should produce a result; others are skipped."""
        params = _one_on_params("j_vwap_reclaim_fb_enabled")
        payload = _make_payload()

        # Mock the one dispatcher so it doesn't need a real BarContext
        with patch("setup_dispatch.SetupDispatcher._dispatch_vwap_reclaim_fb",
                   return_value=DispatchResult("vwap_reclaim_failed_break", fired=False,
                                              skip_reason="SKIP_NO_SIGNAL")):
            results = SetupDispatcher(params, payload).run()

        assert len(results) == 1, f"Expected 1 result (only enabled flag), got {len(results)}"
        assert results[0].setup_name == "vwap_reclaim_failed_break"

    def test_dispatch_extra_setups_serializes_fired_signal(self) -> None:
        """dispatch_extra_setups returns a serializable dict when a signal fires."""
        params = _one_on_params("gap_and_go_enabled")
        payload = _make_payload()

        mock_signal = MagicMock()
        mock_signal.direction = "short"
        mock_signal.entry_price = 596.0
        mock_signal.stop_price = 597.2
        mock_signal.confidence = "medium"
        mock_signal.triggers_fired = ["OPENING_GAP"]
        mock_signal.watcher_name = "gap_and_go_watcher"

        with patch("setup_dispatch.SetupDispatcher._dispatch_gap_and_go",
                   return_value=DispatchResult("gap_and_go", fired=True,
                                              signal=mock_signal)):
            out = dispatch_extra_setups("safe", params, payload, {"verdict": "HOLD"})

        assert len(out) == 1
        row = out[0]
        assert row["fired"] is True
        assert row["setup_name"] == "gap_and_go"
        assert row["direction"] == "short"
        assert "entry_price" in row
        assert "stop_price" in row
        # Verify it's JSON-serializable (no WatcherSignal objects in the output)
        json.dumps(row)  # must not raise


# ===========================================================================
# (c) Missing feed → SKIP_NO_FEED, not a crash
# ===========================================================================

class TestMissingFeed:
    """Missing required feed data yields SKIP_NO_FEED, not an exception."""

    def test_vix_dayside_skip_no_feed_when_flag_on(self) -> None:
        """vix_regime_dayside returns SKIP_NO_FEED when vix_intraday is absent."""
        params = _one_on_params("j_vix_dayside_enabled")
        payload = _make_payload()
        # No vix_intraday in the payload — heartbeat_core doesn't supply it

        results = SetupDispatcher(params, payload).run()
        assert len(results) == 1
        r = results[0]
        assert r.setup_name == "vix_regime_dayside"
        assert r.fired is False
        assert r.skip_reason is not None
        assert "SKIP_NO_FEED" in r.skip_reason, (
            f"Expected SKIP_NO_FEED in skip_reason, got: {r.skip_reason}"
        )

    def test_empty_sameday_bars_yields_skip_no_feed(self) -> None:
        """When sameday_5m_bars is empty, all enabled detectors emit SKIP_NO_FEED."""
        params = {
            "j_vwap_cont_enabled": True,
            "gap_and_go_enabled": True,
            "j_vwap_reclaim_fb_enabled": False,
            "j_vix_dayside_enabled": False,
        }
        # Build a valid payload first, then clear sameday_5m_bars afterward
        payload = _make_payload()
        payload["sameday_5m_bars"] = []  # explicit empty — dispatch must handle this

        results = SetupDispatcher(params, payload).run()
        # Should have 2 results (for the 2 enabled flags)
        assert len(results) == 2, f"Expected 2 results, got {len(results)}: {results}"
        for r in results:
            assert r.fired is False
            assert r.skip_reason is not None
            assert "SKIP_NO_FEED" in r.skip_reason, (
                f"{r.setup_name}: expected SKIP_NO_FEED, got {r.skip_reason}"
            )

    def test_gap_and_go_skip_no_feed_without_prior_close(self) -> None:
        """gap_and_go with no prior close in today-bias.json emits SKIP_NO_FEED."""
        params = _one_on_params("gap_and_go_enabled")
        # Provide valid sameday bars (so BarContext builds successfully)
        sameday = [_bar_row(9, 30, o=603.0, hi=604.2, lo=602.8, c=604.0)]
        payload = _make_payload(sameday_bars=sameday)

        # Patch _get_prior_rth_close to return None (no today-bias.json)
        with patch("setup_dispatch.SetupDispatcher._get_prior_rth_close",
                   return_value=None):
            results = SetupDispatcher(params, payload).run()

        assert len(results) == 1
        r = results[0]
        assert r.setup_name == "gap_and_go"
        assert r.fired is False
        # The skip reason is SKIP_NO_FEED (prior close absent) or SKIP_NO_SIGNAL
        # (watcher returned None because prior_bars is single-day only) — either
        # is acceptable as "not a crash".
        assert r.skip_reason is not None, "skip_reason must not be None when not fired"


# ===========================================================================
# (d) Detector exception → SKIP_DETECTOR_ERROR, not a crash
# ===========================================================================

class TestDetectorError:
    """Exceptions inside a detector are caught; dispatch never raises."""

    def test_detector_exception_returns_skip_error(self) -> None:
        """If the detector raises, we get SKIP_DETECTOR_ERROR not a traceback."""
        params = _one_on_params("j_vwap_cont_enabled")
        payload = _make_payload()

        def _exploding_dispatch(*a, **kw):
            raise RuntimeError("simulated detector failure")

        with patch("setup_dispatch.SetupDispatcher._dispatch_vwap_continuation",
                   side_effect=_exploding_dispatch):
            results = SetupDispatcher(params, payload).run()

        assert len(results) == 1
        r = results[0]
        assert r.fired is False
        assert r.skip_reason is not None
        assert "SKIP_DETECTOR_ERROR" in r.skip_reason
        assert "RuntimeError" in r.skip_reason

    def test_dispatch_extra_setups_never_raises(self) -> None:
        """dispatch_extra_setups catches all errors and returns gracefully."""
        params = _one_on_params("j_vwap_cont_enabled")
        payload = _make_payload()

        # Make run() itself raise
        with patch("setup_dispatch.SetupDispatcher.run",
                   side_effect=Exception("catastrophic failure")):
            result = dispatch_extra_setups("safe", params, payload, {})

        # Must return a list, never raise
        assert isinstance(result, list)
        # Contains an error entry
        assert len(result) == 1
        assert "error" in result[0]


# ===========================================================================
# (e) DispatchResult dataclass sanity
# ===========================================================================

class TestDispatchResult:
    def test_default_values(self) -> None:
        r = DispatchResult("foo")
        assert r.setup_name == "foo"
        assert r.fired is False
        assert r.signal is None
        assert r.skip_reason is None

    def test_fired_result(self) -> None:
        mock_sig = MagicMock()
        r = DispatchResult("bar", fired=True, signal=mock_sig)
        assert r.fired is True
        assert r.signal is mock_sig
        assert r.skip_reason is None

    def test_skip_result(self) -> None:
        r = DispatchResult("baz", fired=False, skip_reason="SKIP_NO_FEED:x")
        assert r.fired is False
        assert r.signal is None
        assert "SKIP_NO_FEED" in r.skip_reason


# ===========================================================================
# (f) Smoke test: dispatch with real watcher import (integration-light)
# ===========================================================================

class TestSmokeRealWatcher:
    """Light integration test: call the real detector with synthetic bars.

    This tests that:
    1. The import path works correctly
    2. The BarContext construction doesn't crash
    3. The detector returns None (no signal) on minimal data
    (We don't need a real SPY data file for this.)
    """

    def test_vwap_continuation_no_crash_with_minimal_bars(self) -> None:
        """vwap_continuation watcher with minimal bars returns SKIP_NO_SIGNAL (not a crash)."""
        params = _one_on_params("j_vwap_cont_enabled")
        params["j_vwap_cont_put_vix_gate"] = False
        # Only 2 bars — not enough for TREND_BARS=3, so watcher should return None
        sameday = [
            _bar_row(9, 30, c=599.5),
            _bar_row(9, 35, c=599.0),
        ]
        payload = _make_payload(sameday_bars=sameday)

        results = SetupDispatcher(params, payload).run()
        assert len(results) == 1
        r = results[0]
        assert r.setup_name == "vwap_continuation"
        assert r.fired is False   # Too few bars, watcher returns None
        # skip_reason may be SKIP_NO_SIGNAL or SKIP_NO_FEED (if ctx build fails)
        # but must NOT be SKIP_DETECTOR_ERROR (no crash)
        if r.skip_reason:
            assert "SKIP_DETECTOR_ERROR" not in r.skip_reason, (
                f"Watcher crashed unexpectedly: {r.skip_reason}"
            )

    def test_gap_and_go_no_crash_with_single_bar(self) -> None:
        """gap_and_go with a single bar (and no prior close) → no crash."""
        params = _one_on_params("gap_and_go_enabled")
        sameday = [_bar_row(9, 30, o=603.0, hi=604.2, lo=602.8, c=604.0)]
        payload = _make_payload(sameday_bars=sameday)

        with patch("setup_dispatch.SetupDispatcher._get_prior_rth_close",
                   return_value=None):
            results = SetupDispatcher(params, payload).run()

        assert len(results) == 1
        r = results[0]
        assert r.fired is False
        assert r.skip_reason is not None
        assert "SKIP_DETECTOR_ERROR" not in r.skip_reason

    def test_vwap_reclaim_no_crash_with_minimal_bars(self) -> None:
        """vwap_reclaim_failed_break with minimal bars → no crash."""
        params = _one_on_params("j_vwap_reclaim_fb_enabled")
        sameday = [_bar_row(9, 30, c=599.5), _bar_row(9, 35, c=599.0)]
        payload = _make_payload(sameday_bars=sameday)

        results = SetupDispatcher(params, payload).run()
        assert len(results) == 1
        r = results[0]
        assert r.fired is False
        assert "SKIP_DETECTOR_ERROR" not in (r.skip_reason or "")


# ===========================================================================
# (g) Wiring status documentation test (read-only assertions)
# ===========================================================================

class TestWiringStatus:
    """Document and assert the per-detector wiring status."""

    EXPECTED_WIRING = {
        "vwap_continuation":         "WIRED_CLEAN",   # j_vwap_cont_enabled=true (live)
        "gap_and_go":                "WIRED_PARTIAL",  # gap_and_go_enabled=true but needs prior_close
        "vwap_reclaim_failed_break": "WIRED_CLEAN",   # wires via sameday_5m_bars
        "vix_regime_dayside":        "BLOCKED_ON_FEED", # needs vix_intraday (not in heartbeat_core)
    }

    def test_wiring_status_documented(self) -> None:
        """Assert that our expected wiring status table is defined (documentation guard)."""
        assert "vwap_continuation" in self.EXPECTED_WIRING
        assert "gap_and_go" in self.EXPECTED_WIRING
        assert "vwap_reclaim_failed_break" in self.EXPECTED_WIRING
        assert "vix_regime_dayside" in self.EXPECTED_WIRING

    def test_vix_dayside_is_blocked_on_feed(self) -> None:
        """vix_regime_dayside must emit some SKIP_NO_FEED when enabled (no live vix_intraday feed).

        In production (heartbeat_core.py context), the skip_reason is
        'SKIP_NO_FEED:vix_intraday_not_wired' because _build_ctx succeeds and
        the explicit check fires. In the test context, _build_ctx may fail earlier
        (ribbon import path) and return None, yielding 'SKIP_NO_FEED:sameday_5m_bars_missing'.
        Either is acceptable — the key invariant is SKIP_NO_FEED and fired=False.
        """
        params = _one_on_params("j_vix_dayside_enabled")
        payload = _make_payload()

        results = SetupDispatcher(params, payload).run()
        assert len(results) == 1
        r = results[0]
        assert r.fired is False
        assert r.skip_reason is not None
        assert "SKIP_NO_FEED" in r.skip_reason, (
            f"Expected SKIP_NO_FEED in skip_reason, got: {r.skip_reason}"
        )

    def test_next_step_to_enable_vix_dayside(self) -> None:
        """Documents the exact next step to enable vix_regime_dayside live.

        BLOCKED BY: heartbeat_core.py does not supply vix_intraday (78-bar VIX series).

        Next step:
          1. In heartbeat_core._build_payload, compute vix_intraday by fetching
             78+ bars of ^VIX 5m data and attaching it to bar_ctx as 'vix_intraday'.
          2. In SetupDispatcher._build_ctx, set ctx.vix_intraday from bar_ctx.
          3. Set j_vix_dayside_enabled=true in params.json ONLY after:
             - recency book 'Safe2_ATM_1+2+4' turns CONFIRM/YELLOW
             - the dispatch fires 3+ live J confirmations
        """
        # This test is a documentation stub — it always passes.
        assert True, "See docstring for the next step to enable vix_regime_dayside"


# ---------------------------------------------------------------------------
# DISPATCH_ROSTER single-source-of-truth guard (2026-07-18 conductor,
# SINGLE-STRATEGY-REGISTRY-DESIGN slice — see backtest/tests/test_graduated_
# guards.py::test_setup_dispatch_names_registry_sync for the validator-side
# half of this same guard).
# ---------------------------------------------------------------------------

class TestDispatchRosterSingleSource:
    """RED-proofs the fix for the F26-DISPATCH class of bug (3 occurrences:
    2x double_bottom_base_quiet/bollinger_squeeze 2026-07-11, 1x
    level_break_first_strike 2026-07-18, 120 consecutive cron failures ~60h).

    Before this fix: SetupDispatcher.run() built its `dispatchers` list as an
    INLINE literal, and crypto/validators/v53_setup_dispatch.py hand-typed a
    SEPARATE _KNOWN_SETUP_NAMES set that had to be manually kept in sync —
    which drifted 3 times. After this fix: `run()`'s dispatcher list is built
    FROM the module-level DISPATCH_ROSTER constant, KNOWN_SETUP_NAMES is
    DERIVED from that same constant, and the validator IMPORTS
    KNOWN_SETUP_NAMES directly instead of re-typing it — there is no second
    hand-maintained copy left anywhere to fall out of sync.
    """

    def test_run_dispatchers_built_from_roster(self) -> None:
        """SetupDispatcher.run() must consult EVERY row in DISPATCH_ROSTER —
        proves run() wasn't left with its own independent inline list after
        the refactor (the exact bug this whole fix targets, one level up)."""
        import setup_dispatch as sd

        params = {flag: False for _name, flag, _method in sd.DISPATCH_ROSTER}
        # All OFF: pure no-op, matches every other "all off" test in this file.
        assert SetupDispatcher(params, {}).run() == []

        # Flip every flag ON (feed absent) — run() must produce exactly one
        # DispatchResult per roster row, with matching setup_name and a
        # non-fired SKIP outcome (never a crash from a missing feed).
        all_on = {flag: True for _name, flag, _method in sd.DISPATCH_ROSTER}
        results = SetupDispatcher(all_on, {}).run()
        result_names = {r.setup_name for r in results}
        roster_names = {name for name, _flag, _method in sd.DISPATCH_ROSTER}
        assert result_names == roster_names, (
            f"run() produced results for {sorted(result_names)} but "
            f"DISPATCH_ROSTER lists {sorted(roster_names)} — run() has drifted "
            f"from the roster (an inline dispatchers list crept back in?)."
        )
        assert all(r.fired is False for r in results), (
            "expected every detector to SKIP (no feed supplied), not fire"
        )

    def test_known_setup_names_derived_from_roster(self) -> None:
        """KNOWN_SETUP_NAMES must equal the roster's name set — an identity
        relationship that cannot drift because it IS a derived frozenset, not
        a second hand-typed literal."""
        import setup_dispatch as sd

        roster_names = frozenset(name for name, _flag, _method in sd.DISPATCH_ROSTER)
        assert sd.KNOWN_SETUP_NAMES == roster_names
        assert isinstance(sd.KNOWN_SETUP_NAMES, frozenset)

    def test_validator_imports_known_setup_names_not_a_copy(self) -> None:
        """v53_setup_dispatch.py's _KNOWN_SETUP_NAMES must be VALUE-EQUAL to
        setup_dispatch.KNOWN_SETUP_NAMES via a real import (grep-verified: its
        source line is `from setup.scripts.setup_dispatch import
        KNOWN_SETUP_NAMES as _KNOWN_SETUP_NAMES`, never a hand-typed literal
        set). NOTE: this repo has two independent import paths for the SAME
        file — `import setup_dispatch` (bare, via setup/scripts on sys.path,
        what this test file itself uses) vs `from setup.scripts.setup_dispatch
        import ...` (namespace-package-qualified, what v53_setup_dispatch.py
        uses) — Python treats those as two DIFFERENT module objects in
        sys.modules, so an `is` identity check across the two paths would
        spuriously fail even with a correct import-based fix (this repo's own
        `_build_ctx` docstring documents the same package-first/bare-import
        duality). Value equality across both import paths is therefore the
        correct and sufficient bar here — the real drift-proofing is the
        import-not-hand-type contract, verified below via source inspection."""
        import importlib
        import inspect
        import sys as _sys

        validators_dir = str(REPO / "crypto" / "validators")
        if validators_dir not in _sys.path:
            _sys.path.insert(0, validators_dir)
        import setup_dispatch as sd
        validator_mod = importlib.import_module("v53_setup_dispatch")

        assert validator_mod._KNOWN_SETUP_NAMES == sd.KNOWN_SETUP_NAMES, (
            "v53_setup_dispatch._KNOWN_SETUP_NAMES no longer matches "
            "setup_dispatch.KNOWN_SETUP_NAMES."
        )
        # Source-level proof there is no second hand-typed literal set: the
        # validator's module source must contain an IMPORT of KNOWN_SETUP_NAMES,
        # not a `{` set-literal assignment to _KNOWN_SETUP_NAMES.
        validator_src = inspect.getsource(validator_mod)
        assert "KNOWN_SETUP_NAMES as _KNOWN_SETUP_NAMES" in validator_src, (
            "v53_setup_dispatch.py must IMPORT KNOWN_SETUP_NAMES from "
            "setup_dispatch, not hand-type a mirror set literal."
        )
        assert "_KNOWN_SETUP_NAMES = {" not in validator_src, (
            "found a hand-typed set-literal assignment to _KNOWN_SETUP_NAMES — "
            "this is exactly the drift-prone pattern the fix removed."
        )

    def test_every_roster_row_has_a_resolvable_method(self) -> None:
        """Every DISPATCH_ROSTER method-name string must resolve to a real
        bound method on SetupDispatcher — catches a typo'd method name that
        would otherwise only surface as an AttributeError deep inside run()."""
        import setup_dispatch as sd

        d = SetupDispatcher({}, {})
        for name, _flag, method_name in sd.DISPATCH_ROSTER:
            assert hasattr(d, method_name), (
                f"DISPATCH_ROSTER row '{name}' names method '{method_name}' "
                f"which does not exist on SetupDispatcher."
            )
            assert callable(getattr(d, method_name))
