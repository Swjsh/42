"""SIGHT-FRESHNESS GUARD (DECISION-ROW-SPY-STALENESS) regression guard.

Investigation: automation/overnight/queue.md's DECISION-ROW-SPY-STALENESS item (filed
2026-07-20 ~18:30 ET). Proven root cause: heartbeat_core._build_payload's trigger bar is
ALWAYS the 2nd-to-last fetched 5m bar (trig_idx = n-2), so `bc['bar']['close']` -- the SAME
value both the score/gates path AND every extra-setup watcher's entry/stop derive from, AND
what gets logged as `rec['spy']` -- is structurally ~5-10 minutes old by design (matches
backtest fidelity; NOT itself a bug). Live exhibit 2026-07-20 09:51-09:55 ET, safe account,
vix_regime_dayside: bc['bar']['close'] pinned at 747.575 (the 09:45-09:50 bar) across 5
straight ticks while the real 1-min SIP tape sold off 747.62->746.14; 3 CALL entries fired
against a swing-low stop computed off the same stale bars (byte-quoted from
automation/state/core-decisions.jsonl, 2026-07-20 09:51:02/09:54:02/09:55:03 safe rows):
  09:51:24 fill 1.13 (trigger spy=747.575, real SIP 1-min close 747.18, diff=$0.40)
  09:54:19 fill 0.79 (trigger spy=747.575, real SIP 1-min close 746.455, diff=$1.12)
  09:55:24 fill 0.76 (trigger spy=747.575, real SIP 1-min close 746.19, diff=$1.38)
Quantification (analysis/recommendations/decision-row-spy-staleness-2026-07-20.json, n=3860
RTH rows 2026-07-14..2026-07-20): every real-fills entry that week OTHER than this cluster
(and other than the already-guarded SKIP_STALE_TRIGGER session-open rows) topped out at
$0.63 divergence from the contemporaneous SIP 1-min close -- so SIGHT_STALENESS_MAX_
DIVERGENCE_USD=1.00 catches exactly the pathological 09:54/09:55 entries without touching a
single other real entry that week (the 09:51 entry, diff=$0.40, is legitimately below the
bar -- pinned below by design, see test_first_exhibit_entry_09_51_is_not_blocked).

Fix: heartbeat_core._sight_staleness_check cross-checks the trigger spot against a genuinely
tick-level Alpaca latest-trade read (NOT another bar close) ONLY at the moment an entry is
actually attempted (primary ENTER_BEAR/ENTER_BULL path + the extra-setup route, after their
existing gates/cooldown already passed). Fail-open BOTH ways: no live quote available -> never
blocks (NEVER-BLIND doctrine); a live quote diverges past the threshold -> SKIP_STALE_SIGHT,
no order attempted (fail-open to NOT-TRADING, never to trading blind).

Run: backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_sight_staleness_guard.py
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

hc = importlib.import_module("heartbeat_core")
ea = importlib.import_module("exit_actuator")


# =============================================================================
# 1. _sight_staleness_check -- pure unit coverage (no I/O, live quote injected directly)
# =============================================================================
class TestSightStalenessCheckPrimitive:

    def test_missing_trigger_spot_never_blocks(self, monkeypatch):
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 747.0)
        out = hc._sight_staleness_check(None)
        assert out == {"checked": False, "live_spy": None, "divergence": None, "stale": False}

    def test_live_quote_unavailable_fails_open(self, monkeypatch):
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: None)
        out = hc._sight_staleness_check(747.575)
        assert out["checked"] is False
        assert out["stale"] is False

    def test_within_threshold_not_stale(self, monkeypatch):
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 747.18)  # diff $0.395
        out = hc._sight_staleness_check(747.575)
        assert out["checked"] is True
        assert out["divergence"] == pytest.approx(0.395, abs=1e-3)
        assert out["stale"] is False

    def test_exactly_at_threshold_not_stale(self, monkeypatch):
        """Boundary is a strict '>' -- exactly at the threshold must NOT block (matches the
        docstring's 'divergence > SIGHT_STALENESS_MAX_DIVERGENCE_USD' contract)."""
        monkeypatch.setattr(hc, "_fetch_live_spy_quote",
                            lambda: 747.575 - hc.SIGHT_STALENESS_MAX_DIVERGENCE_USD)
        out = hc._sight_staleness_check(747.575)
        assert out["divergence"] == pytest.approx(hc.SIGHT_STALENESS_MAX_DIVERGENCE_USD, abs=1e-6)
        assert out["stale"] is False

    def test_over_threshold_is_stale(self, monkeypatch):
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 746.455)  # diff $1.12
        out = hc._sight_staleness_check(747.575)
        assert out["checked"] is True
        assert out["divergence"] == pytest.approx(1.12, abs=1e-3)
        assert out["stale"] is True

    def test_direction_agnostic(self, monkeypatch):
        """A stale sight can be wrong in either direction -- divergence is abs()."""
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 749.0)  # live ABOVE trigger
        out = hc._sight_staleness_check(747.575)
        assert out["divergence"] == pytest.approx(1.425, abs=1e-3)
        assert out["stale"] is True

    def test_real_exhibit_09_51_entry_is_below_the_bar(self, monkeypatch):
        """The FIRST of the 3 real 07-20 vix_dayside fills (09:51:24, diff=$0.395) is
        legitimately within the threshold -- the guard is calibrated to the pathological
        RE-ENTRIES (09:54/09:55), not to ordinary bar-close lag noise. Pins the threshold
        choice against over-blocking."""
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 747.18)
        assert hc._sight_staleness_check(747.575)["stale"] is False

    def test_real_exhibit_09_54_and_09_55_entries_are_stale(self, monkeypatch):
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 746.455)
        assert hc._sight_staleness_check(747.575)["stale"] is True
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 746.19)
        assert hc._sight_staleness_check(747.575)["stale"] is True

    def test_fetch_raising_never_escapes_the_check(self, monkeypatch):
        """_sight_staleness_check is self-safe (wraps its own body in try/except) -- even if
        _fetch_live_spy_quote's own 'never raise' contract were somehow violated (a broken
        monkeypatch, a future edit), the check must still fail open rather than crash the
        caller, matching every other auxiliary check in this module's fail-open style."""
        def _boom():
            raise RuntimeError("network exploded")
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", _boom)
        out = hc._sight_staleness_check(747.575)
        assert out == {"checked": False, "live_spy": None, "divergence": None, "stale": False}


# =============================================================================
# 2. run_account primary ENTER path
# =============================================================================
def _wire_primary(monkeypatch, *, now: dt.datetime, bar_ts: str, trigger_close: float,
                  verdict: dict, live_quote):
    payload = {"bar_ctx": {
        "timestamp_et": bar_ts,
        "bar": {"close": trigger_close},
        "ribbon_now": {"stack": "BULL", "spread_cents": 47.77},
        "vix_now": 15.73, "vix_prior": 15.74, "htf_15m_stack": "BULL",
    }}
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
    monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: payload)
    monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(verdict))
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: live_quote)
    executed = {"n": 0}

    def _exec(*a, **k):
        executed["n"] += 1
        return {"status": "WOULD_PLACE"}
    monkeypatch.setattr(hc, "_execute", _exec)
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))
    monkeypatch.setitem(sys.modules, "setup_dispatch",
                        types.SimpleNamespace(dispatch_extra_setups=lambda *a, **k: []))
    return logged, executed


_TODAY_NOW = dt.datetime(2026, 7, 20, 9, 55, 24)
_TODAY_BAR = "2026-07-20T09:50:00-04:00"
_ENTER_BULL_VERDICT = {
    "verdict": "ENTER_BULL", "side": "C", "setup_name": "VIX_REGIME_DAYSIDE",
    "bear_score": None, "bull_score": None, "triggers_fired": ["vwap_day_trend", "vix_regime"],
    "reason": "VIX_REGIME_DAYSIDE passed", "rejection_level": 746.87,
}


class TestPrimaryPathSightGuard:

    def test_stale_sight_blocks_enter_and_never_executes(self, monkeypatch):
        logged, executed = _wire_primary(
            monkeypatch, now=_TODAY_NOW, bar_ts=_TODAY_BAR, trigger_close=747.575,
            verdict=dict(_ENTER_BULL_VERDICT), live_quote=746.19,  # the real 09:55 exhibit
        )
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_SIGHT"
        assert rec["sight_check"]["stale"] is True
        assert rec["sight_check"]["live_spy"] == 746.19
        assert executed["n"] == 0, "_execute must NEVER be called on a stale-sight tick"
        assert logged and logged[-1]["action"] == "SKIP_STALE_SIGHT"

    def test_fresh_sight_still_enters(self, monkeypatch):
        logged, executed = _wire_primary(
            monkeypatch, now=_TODAY_NOW, bar_ts=_TODAY_BAR, trigger_close=747.575,
            verdict=dict(_ENTER_BULL_VERDICT), live_quote=747.60,  # tiny divergence
        )
        rec = hc.run_account("safe")
        assert rec["action"] == "WOULD_PLACE"
        assert rec["sight_check"]["checked"] is True
        assert rec["sight_check"]["stale"] is False
        assert executed["n"] == 1

    def test_live_quote_unavailable_fails_open_to_entering(self, monkeypatch):
        """The core NEVER-BLIND contract: an unreachable auxiliary fetch must never itself
        become a reason to refuse a legitimate entry."""
        logged, executed = _wire_primary(
            monkeypatch, now=_TODAY_NOW, bar_ts=_TODAY_BAR, trigger_close=747.575,
            verdict=dict(_ENTER_BULL_VERDICT), live_quote=None,
        )
        rec = hc.run_account("safe")
        assert rec["action"] == "WOULD_PLACE"
        assert rec["sight_check"]["checked"] is False
        assert executed["n"] == 1

    def test_only_one_live_quote_fetch_per_tick(self, monkeypatch):
        """The walrus-reuse in the ladder must not double-fetch (cost + latency) -- pins the
        call-count regardless of stale/fresh outcome."""
        calls = {"n": 0}

        def _quote():
            calls["n"] += 1
            return 747.0
        logged, executed = _wire_primary(
            monkeypatch, now=_TODAY_NOW, bar_ts=_TODAY_BAR, trigger_close=747.575,
            verdict=dict(_ENTER_BULL_VERDICT), live_quote=747.0,
        )
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", _quote)
        hc.run_account("safe")
        assert calls["n"] == 1

    def test_hold_verdict_never_fetches_a_live_quote(self, monkeypatch):
        """Cost discipline: the guard only fires on an actual entry attempt, not every HOLD
        tick (which is the overwhelming majority of ticks) -- pins that a HOLD costs zero
        extra REST calls."""
        calls = {"n": 0}

        def _quote():
            calls["n"] += 1
            return 747.0
        verdict = {"verdict": "HOLD", "side": None, "setup_name": None,
                   "bear_score": 5, "bull_score": 5, "triggers_fired": [],
                   "reason": "no setup passed scoring"}
        _wire_primary(monkeypatch, now=_TODAY_NOW, bar_ts=_TODAY_BAR, trigger_close=747.575,
                      verdict=verdict, live_quote=747.0)
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", _quote)
        rec = hc.run_account("safe")
        assert rec["action"] == "HOLD"
        assert calls["n"] == 0

    def test_stale_trigger_bar_takes_priority_over_sight_check(self, monkeypatch):
        """A cross-session stale bar is already SKIP_STALE_TRIGGER territory (GATE-PROVENANCE-
        SWEEP-2026-07-10) -- the sight-freshness guard must never fire (or fetch) on top of
        that, it only matters for bars that already passed the same-day check."""
        calls = {"n": 0}

        def _quote():
            calls["n"] += 1
            return 700.0  # deliberately wildly stale, to prove this branch is never reached
        _wire_primary(monkeypatch, now=_TODAY_NOW, bar_ts="2026-07-19T15:55:00-04:00",
                      trigger_close=747.575, verdict=dict(_ENTER_BULL_VERDICT), live_quote=700.0)
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", _quote)
        rec = hc.run_account("safe")
        assert rec["action"] == "SKIP_STALE_TRIGGER"
        assert calls["n"] == 0


# =============================================================================
# 3. _route_extra_setups (the exact lane the live exhibit fired on)
# =============================================================================
@pytest.fixture()
def cooldown_file(tmp_path, monkeypatch):
    """Redirect exit_actuator's FLEET_DIR to a scratch dir -- same pattern as
    test_extra_signal_churn_cooldown_2026_07_20.py -- so the cooldown check always returns
    False (never active) here and the sight-staleness branch is reached deterministically."""
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    return tmp_path


def _extra_row(entry_close: float) -> list[dict]:
    return [{"setup_name": "vix_regime_dayside", "fired": True, "direction": "long",
             "triggers": ["vix_dayside"], "stop_price": 746.87}]


class TestExtraSetupRouteSightGuard:

    def test_stale_sight_blocks_extra_route_and_never_executes(self, monkeypatch, cooldown_file):
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        executed = {"n": 0}

        def _exec(*a, **k):
            executed["n"] += 1
            return {"status": "WOULD_PLACE"}
        monkeypatch.setattr(hc, "_execute", _exec)
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 746.455)  # real 09:54 exhibit
        params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-20T09:50:00-04:00",
                               "bar": {"close": 747.575}}}
        out = hc._route_extra_setups("safe", _extra_row(747.575), payload, params)
        assert out[0]["action"] == "SKIP_STALE_SIGHT"
        assert out[0]["sight_check"]["stale"] is True
        assert executed["n"] == 0

    def test_fresh_sight_still_routes_through(self, monkeypatch, cooldown_file):
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        executed = {"n": 0}

        def _exec(*a, **k):
            executed["n"] += 1
            return {"status": "WOULD_PLACE", "symbol": "SPY..C"}
        monkeypatch.setattr(hc, "_execute", _exec)
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 747.18)  # real 09:51 exhibit
        params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-20T09:50:00-04:00",
                               "bar": {"close": 747.575}}}
        out = hc._route_extra_setups("safe", _extra_row(747.575), payload, params)
        assert out[0]["action"] == "WOULD_PLACE"
        assert out[0]["sight_check"]["stale"] is False
        assert executed["n"] == 1

    def test_live_quote_unavailable_fails_open(self, monkeypatch, cooldown_file):
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: None)
        params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-20T09:50:00-04:00",
                               "bar": {"close": 747.575}}}
        out = hc._route_extra_setups("safe", _extra_row(747.575), payload, params)
        assert out[0]["action"] == "WOULD_PLACE"

    def test_sight_check_exception_fails_open(self, monkeypatch, cooldown_file):
        """Even if the sight-staleness primitive itself is broken, the route must still be
        able to place -- fail-open, matching the cooldown check's own exception handling
        immediately above it in the same function."""
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})

        def _boom(*a, **k):
            raise RuntimeError("sight check exploded")
        monkeypatch.setattr(hc, "_sight_staleness_check", _boom)
        params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
        payload = {"bar_ctx": {"timestamp_et": "2026-07-20T09:50:00-04:00",
                               "bar": {"close": 747.575}}}
        out = hc._route_extra_setups("safe", _extra_row(747.575), payload, params)
        assert out[0]["action"] == "WOULD_PLACE"

    def test_real_exhibit_first_entry_passes_this_guard(self, monkeypatch, cooldown_file):
        """Entry 1 of the live exhibit (09:51:24, diff $0.40) passes THIS guard -- it would
        still need the already-shipped same-bar cooldown fix (EXTRA-SIGNAL-CHURN-COOLDOWN,
        commit fd91712) to stop the 2nd/3rd re-entry on the identical trigger bar, which is a
        SEPARATE, already-landed mechanism (see test_extra_signal_churn_cooldown_2026_07_20.py)
        -- not re-tested here to keep this file scoped to the sight guard alone."""
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 747.18)
        payload = {"bar_ctx": {"timestamp_et": "2026-07-20T09:50:00-04:00",
                               "bar": {"close": 747.575}}}
        params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}
        out1 = hc._route_extra_setups("safe", _extra_row(747.575), payload, params)
        assert out1[0]["action"] == "WOULD_PLACE"

    def test_sight_guard_has_teeth_independent_of_cooldown(self, monkeypatch, cooldown_file):
        """Proves the sight guard is NOT redundant with the already-shipped same-bar cooldown:
        a genuinely NEW trigger bar (cooldown never fires -- it only blocks re-entry on the
        SAME bar) whose close has already diverged from the live tape by the time the FIRST
        attempt on that bar is evaluated is still blocked, by sight alone."""
        monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
        monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
        monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})
        params = {"extra_setup_exec_armed": {"vix_regime_dayside": True}}

        # bar A: fresh sight -> placed, cooldown recorded for bar A only.
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 747.60)
        payload_a = {"bar_ctx": {"timestamp_et": "2026-07-20T09:45:00-04:00",
                                 "bar": {"close": 747.62}}}
        out_a = hc._route_extra_setups("safe", _extra_row(747.62), payload_a, params)
        assert out_a[0]["action"] == "WOULD_PLACE"

        # bar B: a DIFFERENT (later) trigger bar -- cooldown does NOT apply (new bar), but the
        # live tape has already moved past this bar's close by $1.38 on the FIRST attempt.
        monkeypatch.setattr(hc, "_fetch_live_spy_quote", lambda: 746.19)
        payload_b = {"bar_ctx": {"timestamp_et": "2026-07-20T09:50:00-04:00",
                                 "bar": {"close": 747.575}}}
        out_b = hc._route_extra_setups("safe", _extra_row(747.575), payload_b, params)
        assert out_b[0]["action"] == "SKIP_STALE_SIGHT", (
            "a NEW trigger bar (cooldown inert) must still be blocked by sight staleness alone"
        )


# =============================================================================
# 4. _fetch_live_spy_quote -- fail-open contract (no network in CI; only exercise the
#    exception path + malformed-payload path, never a real HTTP call)
# =============================================================================
class TestFetchLiveSpyQuoteFailOpen:

    def test_bad_mcp_json_returns_none(self, monkeypatch, tmp_path):
        bogus_repo = tmp_path
        (bogus_repo / ".mcp.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(hc, "REPO", bogus_repo)
        assert hc._fetch_live_spy_quote() is None

    def test_missing_mcp_json_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(hc, "REPO", tmp_path)  # no .mcp.json in this empty tmp dir
        assert hc._fetch_live_spy_quote() is None
