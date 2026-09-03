"""Guard suite for setup/scripts/profit_lock_v2_shadow.py -- the forward shadow that
adjudicates prereg-profit-lock-v2-forward-shadow-2026-09-03.md (F1 profit-lock-v2-shadow,
descends from analysis/deep-research/2026-09-03-money/profit-lock-scope.md's H4 finding).

This module's ONLY novel mechanism is `_walk_exit_manager_time_gated`'s profit_lock_arm_scope
MASK -- everything else (bar loading, canonical_shape resolution, CONTROL pricing) is reused,
unmodified, from pdt_blocked_counterfactual.py / money_profit_lock_scope.py. The guards below
prove:

  1. THE 10-MINUTE MASK BINDS. A favorable spike-then-crash entirely inside the first 10
     minutes is NOT protected under the time-gated wrapper (rides to the catastrophe stop)
     but WOULD be protected under the same shape with no time gate (locks a profit floor) --
     a real, provable divergence, not a cosmetic knob.
  2. THE RAISED +20% ARM THRESHOLD ALSO BINDS, independent of the time gate. AFTER the mask
     lifts (elapsed >= 10min), a +10% favorable move does NOT arm the lock at
     profit_lock_arm_pct=0.20 (rides to catastrophe) but WOULD arm it at 0.05 (protected at
     breakeven) -- proving the raised threshold is genuinely enforced, not a no-op.
  3. WITH THE GATE DISABLED (min_arm_minutes=0), the wrapper is BYTE-IDENTICAL to the
     unmodified production `exit_manager_walk.walk_exit_manager` -- the wrapper adds nothing
     when it has nothing to mask.
  4. run() IS IDEMPOTENT (dedup on activity_id) and marks in_sample correctly by date.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "backtest/tools", "backtest/lib", "automation/state/fleet"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import profit_lock_v2_shadow as pv2  # noqa: E402
import exit_manager as em  # noqa: E402
from exit_manager_walk import walk_exit_manager  # noqa: E402

ENTRY = 1.00
QTY = 10


def _shape(arm_pct: float, arm_scope: str = "full") -> dict:
    """A minimal ExitShape dict isolating ONLY the pre-TP1 profit-lock mechanism: TP1 and
    the runner target are placed far out of reach so neither ever fires in these short
    synthetic walks, and stop_mode stays 'premium' (no structure/ribbon feed needed)."""
    return {
        "premium_stop_pct": -0.50, "catastrophe_stop_pct": -0.50,
        "tp1_premium_pct": 5.0, "tp1_qty_fraction": 0.667,
        "runner_target_pct": 99.0,
        "profit_lock_mode": "trailing", "trail_pct": 0.10,
        "profit_lock_arm_pct": arm_pct, "profit_lock_arm_scope": arm_scope,
        "stop_mode": "premium",
    }


def _bars(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """rows: [(HH:MM, price), ...] on 2026-09-03 -- open==high==low==close (point-sample
    convention this project's walkers already use)."""
    return pd.DataFrame({
        "timestamp_et": [pd.Timestamp(f"2026-09-03 {t}:00") for t, _ in rows],
        "open": [p for _, p in rows], "high": [p for _, p in rows],
        "low": [p for _, p in rows], "close": [p for _, p in rows],
    })


def _empty_spy_df() -> pd.DataFrame:
    return pd.DataFrame({"timestamp_et": pd.Series([], dtype="datetime64[ns]"),
                         "close": pd.Series([], dtype=float)})


def _walk(shape: dict, bars: pd.DataFrame, min_arm_minutes: float) -> dict:
    return pv2._walk_exit_manager_time_gated(
        symbol="SPY260903C00700000", side="C", entry_time_et=pd.Timestamp("2026-09-03 10:00:00"),
        entry_premium=ENTRY, qty=QTY, exit_shape=shape, structure_stop_enabled=False,
        trigger_level=None, strategy="RIBBON", time_stop_et=em.TIME_STOP_ET,
        opt_df=bars, ribbon_tick_df=None, five_min_spy_df=_empty_spy_df(),
        min_arm_minutes=min_arm_minutes)


# ---------------------------------------------------------------------------------
# 1. THE 10-MINUTE MASK BINDS
# ---------------------------------------------------------------------------------
def test_mask_binds_spike_and_crash_inside_first_ten_minutes_rides_to_catastrophe():
    """+30% favor at minute 1 (masked -> arm branch suppressed, never arms), crash to -60%
    at minute 2 (also masked) hits the RAW catastrophe stop (0.50) unprotected: pnl =
    (0.50-1.00)*10*100 = -$500.00."""
    bars = _bars([("10:01", 1.30), ("10:02", 0.40)])
    res = _walk(_shape(arm_pct=0.20), bars, min_arm_minutes=10.0)
    assert "error" not in res, res
    assert res["pnl"] == pytest.approx(-500.0)
    assert res["walked_stage"] == "premium_stop"
    assert res["n_masked_ticks"] == 2, "both ticks are inside the 10-minute window"


def test_same_bars_with_gate_disabled_locks_a_profit_floor_instead():
    """IDENTICAL shape and bars, min_arm_minutes=0 (no gate): the +30% tick arms
    immediately (scope='full', unmasked), ratchets the trailing floor to
    1.30*(1-0.10)=1.17, and the crash exits AT that floor instead of the catastrophe cap:
    pnl = (1.17-1.00)*10*100 = +$170.00 -- the opposite sign from the masked run above,
    proving the mask is what changed the outcome, not some other difference."""
    bars = _bars([("10:01", 1.30), ("10:02", 0.40)])
    res = _walk(_shape(arm_pct=0.20), bars, min_arm_minutes=0.0)
    assert "error" not in res, res
    assert res["pnl"] == pytest.approx(170.0)
    assert res["walked_stage"] == "profit_lock_floor"
    assert res["n_masked_ticks"] == 0


# ---------------------------------------------------------------------------------
# 2. THE RAISED +20% ARM THRESHOLD ALSO BINDS (independent of the time gate)
# ---------------------------------------------------------------------------------
def test_arm_pct_020_does_not_arm_on_a_ten_percent_move_after_mask_lifts():
    """Both ticks are AT/AFTER the 10-minute mark (mask already lifted). +10% favor is
    below the 0.20 arm threshold this candidate uses -> never arms -> the crash at minute 11
    hits the raw catastrophe stop: pnl = (0.50-1.00)*10*100 = -$500.00."""
    bars = _bars([("10:10", 1.10), ("10:11", 0.40)])
    res = _walk(_shape(arm_pct=0.20), bars, min_arm_minutes=10.0)
    assert "error" not in res, res
    assert res["pnl"] == pytest.approx(-500.0)
    assert res["walked_stage"] == "premium_stop"
    assert res["n_masked_ticks"] == 0, "elapsed >= 10min at both ticks -- mask never applies here"


def test_arm_pct_005_DOES_arm_on_the_same_ten_percent_move_same_mask_state():
    """Same bars, same mask-lifted timing -- only profit_lock_arm_pct changes (0.05 instead
    of 0.20). +10% now clears the (lower) threshold, arms at breakeven, and the crash exits
    at the floor instead of the cap: pnl = (1.00-1.00)*10*100 = $0.00 (protected, not -$500)."""
    bars = _bars([("10:10", 1.10), ("10:11", 0.40)])
    res = _walk(_shape(arm_pct=0.05), bars, min_arm_minutes=10.0)
    assert "error" not in res, res
    assert res["pnl"] == pytest.approx(0.0)
    assert res["walked_stage"] == "profit_lock_floor"


# ---------------------------------------------------------------------------------
# 3. GATE DISABLED == BYTE-IDENTICAL TO THE UNMODIFIED PRODUCTION WALKER
# ---------------------------------------------------------------------------------
def test_gate_disabled_matches_unmodified_walk_exit_manager_exactly():
    bars = _bars([("10:01", 1.30), ("10:02", 0.40)])
    shape = _shape(arm_pct=0.20)
    gated = _walk(shape, bars, min_arm_minutes=0.0)

    prod = walk_exit_manager(
        symbol="SPY260903C00700000", side="C", entry_time_et=pd.Timestamp("2026-09-03 10:00:00"),
        entry_premium=ENTRY, qty=QTY, exit_shape=shape, structure_stop_enabled=False,
        trigger_level=None, strategy="RIBBON", time_stop_et=em.TIME_STOP_ET,
        opt_df=bars, ribbon_tick_df=None, five_min_spy_df=_empty_spy_df())

    assert gated["pnl"] == pytest.approx(prod.dollar_pnl)
    assert gated["walked_stage"] == ("+".join(l.stage for l in prod.legs) if prod.legs else prod.exit_reason)


# ---------------------------------------------------------------------------------
# 4. helper functions on synthetic rows
# ---------------------------------------------------------------------------------
def _row(date, arm="safe-2", delta=0.0, ts="10:00:00", symbol="X"):
    return {"date": date, "arm": arm, "delta": delta, "ts_et": f"{date}T{ts}", "symbol": symbol}


def test_big_days_all_ge_zero_true_when_all_four_present_and_nonnegative():
    rows = [_row(d, delta=10.0) for d in pv2.WINNER_ANCHOR_DATES]
    out = pv2._big_days(rows)
    assert out["dates_missing"] == []
    assert out["all_ge_zero"] is True


def test_big_days_flags_missing_dates_and_negative_delta():
    rows = [_row(d, delta=10.0) for d in pv2.WINNER_ANCHOR_DATES[:3]]
    rows.append(_row(pv2.WINNER_ANCHOR_DATES[3], delta=-5.0))
    out_missing = pv2._big_days(rows[:3])
    assert out_missing["dates_missing"] == [pv2.WINNER_ANCHOR_DATES[3]]
    out_neg = pv2._big_days(rows)
    assert out_neg["all_ge_zero"] is False


def test_runner_08_04_found_and_summed():
    rows = [_row(pv2.RUNNER_DATE, arm="safe-2", delta=42.0, symbol=pv2.RUNNER_SYMBOL)]
    out = pv2._runner_08_04(rows)
    assert out["found"] is True
    assert out["delta"] == pytest.approx(42.0)


def test_runner_08_04_not_found_is_disclosed_not_fabricated():
    out = pv2._runner_08_04([_row(pv2.RUNNER_DATE, symbol="OTHER")])
    assert out["found"] is False
    assert out["delta"] is None


def test_recent_quarter_delta_takes_the_chronological_last_quartile():
    rows = [_row(f"2026-08-{d:02d}", delta=float(d)) for d in range(1, 9)]  # 8 rows, q=2
    out = pv2._recent_quarter_delta_safe2(rows)
    assert out["n"] == 2
    assert out["delta"] == pytest.approx(7.0 + 8.0)


# ---------------------------------------------------------------------------------
# 5. _summarize status transitions
# ---------------------------------------------------------------------------------
def _fwd_row(date, arm="safe-2", delta=1.0):
    return {"date": date, "arm": arm, "delta": delta, "ts_et": f"{date}T10:00:00",
            "symbol": "X", "in_sample": False, "control_pnl": 0.0, "treatment_pnl": delta,
            "trusted_dollars": arm == "safe-2"}


def test_summarize_status_armed_awaiting_fills_when_no_forward_rows():
    rows = [{"date": "2026-08-01", "arm": "safe-2", "delta": 5.0, "ts_et": "2026-08-01T10:00:00",
             "symbol": "X", "in_sample": True, "control_pnl": 0.0, "treatment_pnl": 5.0,
             "trusted_dollars": True}]
    s = pv2._summarize(rows)
    assert s["status"] == "ARMED_AWAITING_FILLS"
    assert s["n_forward"] == 0


def test_summarize_status_accruing_below_bar():
    rows = [_fwd_row("2026-09-03")]
    s = pv2._summarize(rows)
    assert s["status"] == "ACCRUING"
    assert s["bar"]["bar_met"] is False


def test_summarize_status_bar_met_when_both_thresholds_cleared():
    rows = []
    for i in range(pv2.BAR_FORWARD_SESSIONS):
        d = f"2026-10-{i + 1:02d}"
        rows.append(_fwd_row(d))
    # top up safe-2 forward scored count to the bar independently of session count
    while sum(1 for r in rows if r["arm"] == "safe-2") < pv2.BAR_FORWARD_SAFE2_SCORED:
        rows.append(_fwd_row(rows[-1]["date"]))
    s = pv2._summarize(rows)
    assert s["bar"]["forward_sessions_met"] is True
    assert s["bar"]["forward_safe2_scored_met"] is True
    assert s["status"] == "BAR_MET_AWAITING_VERDICT"


# ---------------------------------------------------------------------------------
# 6. ledger I/O + run() orchestration (score_event monkeypatched -- walker mechanics are
#    already proven directly above; this section tests dedup/in_sample/idempotence only)
# ---------------------------------------------------------------------------------
def test_read_ledger_tolerant_of_a_torn_last_line(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"activity_id": "a1", "delta": 1.0}\n{"activity_id": "a2", "delta"', encoding="utf-8")
    monkeypatch.setattr(pv2, "LEDGER", ledger)
    rows = pv2._read_ledger()
    assert len(rows) == 1
    assert rows[0]["activity_id"] == "a1"


def test_score_event_skips_when_no_bars_available(monkeypatch):
    monkeypatch.setattr(pv2.mpls, "load_1min_cache_only", lambda symbol, date: None)
    monkeypatch.setattr(pv2, "load_contract_bars", lambda symbol: None)
    event = {"activity_id": "a1", "arm": "safe-2", "symbol": "SPY260903C00700000",
             "date_et": "2026-09-03", "qty": 5.0, "price": 1.0, "ts_et": "2026-09-03T10:00:00",
             "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "trigger_level": None}
    row, reason = pv2.score_event(event, {})
    assert row is None
    assert reason == "no_bars"


@pytest.fixture
def _fake_scored_ledger(tmp_path, monkeypatch):
    eql_path = tmp_path / "eql.json"
    out_dir = tmp_path / "out"
    ledger = out_dir / "ledger.jsonl"
    summary = out_dir / "summary.json"

    events = [
        {"activity_id": "old1", "arm": "safe-2", "symbol": "SPY260826C00700000",
         "date_et": "2026-08-26", "qty": 5.0, "price": 1.0, "ts_et": "2026-08-26T10:00:00",
         "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "trigger_level": None,
         "attribution": "engine", "is_option": True, "exit_qty": 5.0, "mfe_pct": 0.1, "pnl": 10.0},
        {"activity_id": "new1", "arm": "safe-2", "symbol": "SPY260903C00700000",
         "date_et": "2026-09-03", "qty": 5.0, "price": 1.0, "ts_et": "2026-09-03T10:00:00",
         "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "trigger_level": None,
         "attribution": "engine", "is_option": True, "exit_qty": 5.0, "mfe_pct": 0.2, "pnl": 20.0},
    ]
    eql_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    def _fake_score_event(e, spy_map):
        return {
            "activity_id": e["activity_id"], "date": e["date_et"], "arm": e["arm"],
            "symbol": e["symbol"], "setup": e["setup"], "qty": int(e["qty"]),
            "entry_price": e["price"], "ts_et": e["ts_et"],
            "control_pnl": 0.0, "treatment_pnl": e["pnl"], "delta": e["pnl"],
            "mfe_pct": e["mfe_pct"], "bars_source": "1min", "trusted_dollars": True,
            "in_sample": bool(e["date_et"] < pv2.FORWARD_START_DATE),
            "control_walked_stage": "premium_stop", "treatment_walked_stage": "profit_lock_floor",
            "treatment_n_masked_ticks": 0, "actual_broker_pnl": e["pnl"],
        }, None

    monkeypatch.setattr(pv2, "ENTRY_QUALITY_LEDGER", eql_path)
    monkeypatch.setattr(pv2, "OUT_DIR", out_dir)
    monkeypatch.setattr(pv2, "LEDGER", ledger)
    monkeypatch.setattr(pv2, "SUMMARY", summary)
    monkeypatch.setattr(pv2, "score_event", _fake_score_event)
    monkeypatch.setattr(pv2.pbc, "spy_by_day", lambda: {})
    return {"ledger": ledger, "summary": summary}


def test_run_writes_both_rows_with_correct_in_sample_flags(_fake_scored_ledger):
    out = pv2.run()
    assert "error" not in out, out
    assert out["new_this_run"] == 2
    rows = pv2._read_ledger()
    by_id = {r["activity_id"]: r for r in rows}
    assert by_id["old1"]["in_sample"] is True
    assert by_id["new1"]["in_sample"] is False


def test_run_is_idempotent_on_a_second_fire(_fake_scored_ledger):
    pv2.run()
    out2 = pv2.run()
    assert out2["new_this_run"] == 0
    rows = pv2._read_ledger()
    assert len(rows) == 2, "re-running must never duplicate a ledger row"
