"""test_vwap_reclaim_fleet_extension_2026_08_04.py -- guards for
FLEET-VWAP-RECLAIM-EXTENSION-RISKY3 (prereg frozen BEFORE arming:
analysis/recommendations/fleet-vwap-reclaim-extension-prereg-2026-08-04.json).

WHAT THIS PINS (vary-and-assert, C14 -- every knob proven LIVE, not decorative):
  1. DIVERGENCE ON A REAL-SHAPED SIGNAL: given a strategies[] entry mirroring the REAL
     2026-07-28 10:36 ET core Safe-2 vwap_reclaim_failed_break PLACED fill (P side,
     strike 737, entry premium 1.12 -- core-decisions.jsonl), plan_all on the REAL
     accounts.json arms produces: risky-3 ENTER at tier qty / safe-3 HOLD
     "requires confluence/sequence" / risky-1 ENTER clamped to full-send min size.
     This is the J-week-directive contract: the risk arms take a validated speculative
     entry the tight safe arm structurally does not.
  2. STRIKE ROUTING IS A LIVE KNOB: at an equity where PROBE_STRIKE_TIERS and the arm's
     bold_core table disagree ($15K: PROBE=+1 ITM vs bold_core=-1 OTM), the reclaim
     entry prices the PROBE table and a ribbon entry on the SAME signal prices the arm
     table -- routing diverges per-strategy, not per-arm.
  3. EXIT-SHAPE PORT EXACT: the registry cell is the Safe-2 armed ATM cell
     (-0.08 / +0.30 / sell 0.8 / fixed), and risky-3's exit_patch overlays on top
     (structure stop + trailing 0.20) by the existing _exit_shape_dict design.
  4. PRODUCER KILL IS REAL: RUN_VWAP_RECLAIM_FB=False emits NO reclaim entry and never
     even calls the fleet_market block (one-line revert proven, not assumed).
  5. PRODUCER EMISSION: vwap_reclaim_strategy_block emits the correct entry dict off a
     synthetic reclaim tape (watcher self-test case B geometry) with trigger_level_exact
     = the failed-break excursion extreme (the validated chart-stop anchor).

RAIL-4 CLEAR: test-only; reads real configs, mutates nothing, places no orders.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parents[2]
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in (str(_FLEET), str(_REPO / "setup" / "scripts"), str(_REPO / "backtest")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fleet_executor as fx      # noqa: E402
import strategies as fstrat      # noqa: E402
import build_shared_signal as bss  # noqa: E402
import fleet_market              # noqa: E402


@pytest.fixture(autouse=True)
def _fixed_recency_verdict(monkeypatch):
    # Same discipline as test_fleet_arm_parity.py (FLEET-PARITY-TESTS-READ-LIVE-STATE):
    # a guard whose verdict depends on the rig's live recency file is not a guard.
    monkeypatch.setattr(fx, "_recency_verdict", lambda *a, **k: "GREEN")


_ACCOUNTS = json.loads((_FLEET / "accounts.json").read_text(encoding="utf-8"))
_ARM = {a["id"]: a for a in _ACCOUNTS["arms"]}

# REAL-FILL MIRROR (core-decisions.jsonl 2026-07-28T10:36:03-04:00, account=safe,
# extra_exec vwap_reclaim_failed_break PLACED: SPY260728P00737000 q3 @ 1.12).
# spot/stop are labeled reconstructions consistent with that fire's geometry (strike 737
# ATM => spot ~737.3; failed-break HIGH above spot for a P entry).
REAL_SHAPED_ENTRY = {
    "name": "vwap_reclaim_failed_break",
    "side": "P",
    "setup": "VWAP_RECLAIM_FAILED_BREAK",
    "triggers": ["VWAP_TREND_ESTABLISHED", "VWAP_COUNTER_TREND_BREAK_FAILED",
                  "VWAP_WITH_TREND_RECLAIM"],
    "quality": "BASE",
    "est_premium": None,
    "spot": 737.3,
    "trigger_level_exact": 738.42,
    "trigger_level": 738.42,
}

BOLD_PARAMS = {
    "position_sizing_tiers": [
        {"equity_min": 0, "equity_max": 2000, "base_qty": 5, "elite_qty": 5},
        {"equity_min": 2000, "equity_max": 10000, "base_qty": 8, "elite_qty": 12},
        {"equity_min": 10000, "equity_max": 25000, "base_qty": 10, "elite_qty": 15},
    ],
    "min_contracts": 5,
}
SAFE_PARAMS = {
    "position_sizing_tiers": [
        {"equity_min": 0, "equity_max": 2000, "base_qty": 5, "elite_qty": 8},
        {"equity_min": 2000, "equity_max": 10000, "base_qty": 8, "elite_qty": 12},
    ],
    "min_contracts": 3,
}
SIGNAL = {"spot": 737.3, "strategies": [REAL_SHAPED_ENTRY]}
EQ_5K = 5000.0


def _plans(arm_id, params, equity=EQ_5K, signal=SIGNAL):
    return fx.plan_all(_ARM[arm_id], signal, equity, params)


# ---------------------------------------------------------------------------------
# 1. THE DIVERGENCE CONTRACT (risky-3 enters, safe-3 holds, risky-1 min-size)
# ---------------------------------------------------------------------------------
def test_risky3_enters_the_reclaim_entry_at_tier_qty():
    plans = _plans("risky-3", BOLD_PARAMS)
    enters = [p for p in plans if p.action == "ENTER"
              and p.strategy == "vwap_reclaim_failed_break"]
    assert len(enters) == 1, f"risky-3 must ENTER the reclaim entry, got {plans}"
    p = enters[0]
    assert p.side == "P"
    assert p.qty == 8, "BOLD tier base qty at $5K (recency clamp is ribbon_ride-scoped)"
    assert p.trigger_level == pytest.approx(738.42), \
        "failed-break extreme must ride as the chart-stop anchor"


def test_safe3_holds_the_same_entry_on_its_own_gate():
    plans = _plans("safe-3", SAFE_PARAMS)
    mine = [p for p in plans if p.strategy == "vwap_reclaim_failed_break"]
    assert len(mine) == 1
    assert mine[0].action == "HOLD", "safe-3 must gate the reclaim entry out"
    assert "confluence/sequence" in mine[0].reason, mine[0].reason
    # DIVERGENCE, stated as one assertion: same signal, opposite decisions.
    r3 = [p for p in _plans("risky-3", BOLD_PARAMS)
          if p.strategy == "vwap_reclaim_failed_break"][0]
    assert (r3.action, mine[0].action) == ("ENTER", "HOLD")


def test_risky1_enters_at_full_send_min_size():
    plans = _plans("risky-1", BOLD_PARAMS)
    enters = [p for p in plans if p.action == "ENTER"
              and p.strategy == "vwap_reclaim_failed_break"]
    assert len(enters) == 1
    assert enters[0].qty == BOLD_PARAMS["min_contracts"], \
        "full-send arm-level clamp must bind on the reclaim entry too"
    assert "FULL_SEND min size" in enters[0].reason


# ---------------------------------------------------------------------------------
# 2. STRIKE ROUTING IS LIVE (C14): reclaim prices PROBE table, ribbon prices arm table
# ---------------------------------------------------------------------------------
def test_strike_routing_diverges_from_arm_table_where_tables_disagree():
    eq = 15_000.0  # PROBE: +1 (Slight ITM); bold_core: -1 (OTM-1) -- tables DISAGREE here
    plans = _plans("risky-3", BOLD_PARAMS, equity=eq)
    p = [x for x in plans if x.strategy == "vwap_reclaim_failed_break"][0]
    ss = fx.strike_selection  # the module fleet_executor itself resolved (crypto/lib)
    probe_strike = ss.pick_strike(737.3, eq, "P", fx.PROBE_STRIKE_TIERS)
    arm_strike = ss.pick_strike(737.3, eq, "P", fx._tiers_for_arm(_ARM["risky-3"]))
    assert probe_strike != arm_strike, "fixture must exercise a genuinely-different bracket"
    assert p.strike == probe_strike, "reclaim entry must price the PROBE (ATM-class) table"

    ribbon_entry = {
        "name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "triggers": ["level_rejection"], "quality": "BASE", "spot": 737.3,
    }
    plans2 = fx.plan_all(_ARM["risky-3"], {"spot": 737.3, "strategies": [ribbon_entry]},
                          eq, BOLD_PARAMS)
    r = [x for x in plans2 if x.strategy == "ribbon_ride" and x.action == "ENTER"]
    assert r and r[0].strike == arm_strike, \
        "a strategy ABSENT from STRATEGY_STRIKE_TIERS must keep the arm table (vary-and-assert)"


# ---------------------------------------------------------------------------------
# 3. EXIT-SHAPE PORT + per-arm overlay
# ---------------------------------------------------------------------------------
def test_registry_cell_is_the_safe2_armed_atm_cell():
    s = fstrat.by_name("vwap_reclaim_failed_break")
    assert s is not None, "registry entry missing"
    assert (s.exit.premium_stop_pct, s.exit.tp1_premium_pct,
            s.exit.tp1_qty_fraction, s.exit.profit_lock_mode) == (-0.08, 0.30, 0.8, "fixed")


def test_risky3_exit_patch_overlays_on_top():
    shape = fx._exit_shape_dict(fstrat.VWAP_RECLAIM_FAILED_BREAK, _ARM["risky-3"])
    assert shape["premium_stop_pct"] == -0.08 and shape["tp1_premium_pct"] == 0.30
    assert shape["stop_mode"] == "structure" and shape["trail_pct"] == 0.20, \
        "risky-3's accounts.json exit_patch must shallow-merge over the ported cell"


# ---------------------------------------------------------------------------------
# 4. PRODUCER KILL: one-line revert proven
# ---------------------------------------------------------------------------------
def test_flag_off_is_a_real_producer_kill(monkeypatch):
    monkeypatch.setattr(bss, "RUN_VWAP_RECLAIM_FB", False)
    monkeypatch.setattr(fleet_market, "vwap_strategy_block", lambda now: None)

    def _must_not_be_called(now):  # pragma: no cover - the assert IS the coverage
        raise AssertionError("reclaim block called despite RUN_VWAP_RECLAIM_FB=False")
    monkeypatch.setattr(fleet_market, "vwap_reclaim_strategy_block", _must_not_be_called)
    entries = bss._strategies_block({}, {}, 737.3, dt.datetime(2026, 8, 4, 10, 0), True)
    assert all(e.get("name") != "vwap_reclaim_failed_break" for e in entries)


def test_flag_on_appends_the_block(monkeypatch):
    monkeypatch.setattr(bss, "RUN_VWAP_RECLAIM_FB", True)
    monkeypatch.setattr(fleet_market, "vwap_strategy_block", lambda now: None)
    monkeypatch.setattr(fleet_market, "vwap_reclaim_strategy_block",
                        lambda now: dict(REAL_SHAPED_ENTRY))
    entries = bss._strategies_block({}, {}, 737.3, dt.datetime(2026, 8, 4, 10, 0), True)
    assert any(e.get("name") == "vwap_reclaim_failed_break" for e in entries)


# ---------------------------------------------------------------------------------
# 5. PRODUCER EMISSION off a synthetic reclaim tape (watcher case-B geometry, P side)
# ---------------------------------------------------------------------------------
def test_lazy_imports_actually_resolve():
    """IMPORT-CHAIN GUARD (2026-08-04). The original fleet_market imports
    (`from filters import BarContext` off a backtest/lib sys.path entry) could NEVER
    succeed -- filters.py is package-relative (`from .ribbon import ...`) -- and the
    fail-safe except turned that permanent ImportError into 'no vwap signal' on every
    tick since the 2026-06-25 FIX2 ship (0 vwap rows in any fleet ledger, C7/L241).
    This test RED-proofs the fix: it FAILS on the pre-fix import spelling (verified
    live before the fix landed) and pins that both lazy importers now resolve real
    objects, so a future refactor can never silently re-kill the emission."""
    hc, bc, det = fleet_market._lazy_imports()
    assert hc is not None and bc is not None and det is not None, \
        "vwap_continuation lazy imports must resolve (import-dead producer, C7/L241)"
    hc2, bc2, det2 = fleet_market._lazy_imports_reclaim()
    assert hc2 is not None and bc2 is not None and det2 is not None, \
        "vwap_reclaim lazy imports must resolve"


def test_producer_block_emits_on_synthetic_reclaim_tape(monkeypatch):
    pd = pytest.importorskip("pandas")
    from lib.filters import BarContext  # package import (see IMPORT-CHAIN FIX)
    from lib.watchers.vwap_reclaim_failed_break_watcher import (
        detect_vwap_reclaim_failed_break_setup, _reset_day,
    )
    today = dt.date(2026, 8, 4)

    def _ts(h, m):
        return pd.Timestamp(dt.datetime(2026, 8, 4, h, m))

    rows = [
        dict(timestamp=_ts(9, 30), open=600.0, high=600.1, low=599.4, close=599.5, volume=5000),
        dict(timestamp=_ts(9, 35), open=599.5, high=599.6, low=598.8, close=598.9, volume=5000),
        dict(timestamp=_ts(9, 40), open=598.9, high=599.0, low=598.2, close=598.3, volume=5000),
        dict(timestamp=_ts(9, 45), open=598.3, high=600.0, low=598.2, close=599.8, volume=5000),
        dict(timestamp=_ts(9, 50), open=599.8, high=599.9, low=598.0, close=598.1, volume=5000),
    ]
    df = pd.DataFrame(rows)
    fake_hc = SimpleNamespace(_fetch_spy_5m=lambda: df, _fetch_vix=lambda: (17.0, 17.0))
    monkeypatch.setattr(
        fleet_market, "_lazy_imports_reclaim",
        lambda: (fake_hc, BarContext, detect_vwap_reclaim_failed_break_setup))
    _reset_day("none")  # isolate the module singleton's per-day state from other tests
    now = dt.datetime(2026, 8, 4, 9, 55)
    out = fleet_market.vwap_reclaim_strategy_block(now)
    assert out is not None, "case-B reclaim tape must fire"
    assert out["name"] == "vwap_reclaim_failed_break" and out["side"] == "P"
    assert out["setup"] == "VWAP_RECLAIM_FAILED_BREAK"
    assert len(out["triggers"]) == 3
    assert out["trigger_level_exact"] == pytest.approx(600.0), \
        "chart-stop anchor must be the failed-break excursion HIGH (600.0 on this tape)"
    assert out["spot"] == pytest.approx(598.1)
