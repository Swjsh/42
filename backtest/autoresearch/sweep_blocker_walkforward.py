"""Walk-forward validation for BEARISH_SWEEP_BLOCKER confluence carve-out.

Runs the IS/OOS split required by OP-20 disclosure 3.

Train (IS) window:  2025-01-01 to 2025-09-30 (9 months)
Test  (OOS) window: 2025-10-01 to 2026-05-07 (7 months)

Each window runs two passes:
  BASELINE      — sweep_blocker_enabled=False
  WITH_CARVEOUT — sweep_blocker_enabled=True (confluence carve-out already in filters.py)

Gate: delta_sharpe = (WITH_CARVEOUT - BASELINE) > 0 in BOTH windows.

Output: analysis/recommendations/sweep-blocker-walkforward.json
"""
from __future__ import annotations

import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "sweep-blocker-walkforward.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "sweep-blocker-walkforward.stderr.log", "a", buffering=1, encoding="utf-8")
    print(f"[sweep-blocker-walkforward] stdout redirected (pid={_os.getpid()})")

import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest  # noqa: E402

DATA_DIR = REPO / "data"
OUT_DIR = ROOT / "analysis" / "recommendations"
OUT_JSON = OUT_DIR / "sweep-blocker-walkforward.json"

TRAIN_START = dt.date(2025, 1, 1)
TRAIN_END   = dt.date(2025, 9, 30)
TEST_START  = dt.date(2025, 10, 1)
TEST_END    = dt.date(2026, 5, 7)

J_WINNERS = [dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)]
J_LOSERS  = [dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)]
J_ALL = J_WINNERS + J_LOSERS

PROD_KWARGS: dict = dict(
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.50,
    runner_target_premium_pct=2.5,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
    use_real_fills=True,
    min_triggers_bear=1,
    min_triggers_bull=2,
    strike_offset_bear=-3,
    strike_offset_bull=-3,
    f9_vol_mult=0.7,
    enable_bullish=True,
)


def _load_data(full_spy, full_vix, start: dt.date, end: dt.date):
    start_str = start.isoformat()
    end_str = f"{end.isoformat()}T23:59:59"
    spy = full_spy[
        (full_spy["timestamp_et"] >= start_str) & (full_spy["timestamp_et"] < end_str)
    ].reset_index(drop=True)
    vix = full_vix[
        (full_vix["timestamp_et"] >= start_str) & (full_vix["timestamp_et"] < end_str)
    ].reset_index(drop=True)
    return spy, vix


def _sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2:
        return float("nan")
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    if var <= 0:
        return float("nan")
    return (mean / math.sqrt(var)) * math.sqrt(252)


def _max_drawdown(pnls: list[float]) -> float:
    cum = 0.0; peak = 0.0; dd = 0.0
    for p in pnls:
        cum += p; peak = max(peak, cum); dd = min(dd, cum - peak)
    return dd


def _metrics(trades, decisions) -> dict:
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "n_winners": 0, "n_losers": 0, "total_pnl": 0.0,
                "avg_pnl": 0.0, "win_rate": 0.0, "sharpe": float("nan"),
                "max_drawdown": 0.0, "avg_hold_min": 0.0, "trades_per_day": 0.0}
    n_days = len(set(pd.Timestamp(d["timestamp_et"]).date() for d in decisions))
    pnls = [t.dollar_pnl for t in trades]
    n_w = sum(1 for p in pnls if p > 0)
    n_l = sum(1 for p in pnls if p < 0)
    total = sum(pnls)
    return {
        "n_trades": n, "n_winners": n_w, "n_losers": n_l,
        "total_pnl": round(total, 2), "avg_pnl": round(total / n, 2),
        "win_rate": round(n_w / n, 4), "sharpe": round(_sharpe(pnls), 4),
        "max_drawdown": round(_max_drawdown(pnls), 2),
        "avg_hold_min": round(sum(t.hold_minutes for t in trades) / n, 1),
        "trades_per_day": round(n / max(1, n_days), 3),
    }


def _j_edge_check(trades) -> dict:
    by_date: dict[dt.date, list] = {}
    for t in trades:
        d = t.entry_time_et.date(); by_date.setdefault(d, []).append(t.dollar_pnl)
    result = {}
    for d in J_ALL:
        pnls = by_date.get(d, [])
        result[d.isoformat()] = {
            "category": "WINNER" if d in J_WINNERS else "LOSER",
            "engine_pnl": round(sum(pnls), 2),
            "n_trades": len(pnls),
        }
    # Edge capture
    winner_pnl = sum(v["engine_pnl"] for v in result.values() if v["category"] == "WINNER")
    loser_loss  = sum(max(0, -v["engine_pnl"]) for v in result.values() if v["category"] == "LOSER")
    result["edge_capture"] = round(winner_pnl - loser_loss, 2)
    return result


def run_pass(spy, vix, enabled: bool, label: str) -> tuple:
    print(f"  Running {label}...")
    result = run_backtest(spy, vix,
                          sweep_blocker_enabled=enabled,
                          sweep_min_wick_pct=0.0003,
                          sweep_min_close_back_pct=0.0005,
                          **PROD_KWARGS)
    m = _metrics(result.trades, result.decisions)
    print(f"    {label}: {m['n_trades']} trades  P&L=${m['total_pnl']:+.0f}  "
          f"WR={m['win_rate']*100:.0f}%  Sharpe={m['sharpe']:.3f}")
    return result, m


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("BEARISH_SWEEP_BLOCKER Walk-Forward Validation (confluence carve-out)")
    print(f"Train: {TRAIN_START} to {TRAIN_END}  |  Test: {TEST_START} to {TEST_END}")
    print("=" * 70)

    # Load full dataset once
    print("\nLoading full dataset...")
    for cand in [
        "spy_5m_2025-01-01_2026-05-19_merged.csv",
        "spy_5m_2025-01-01_2026-05-15.csv",
        "spy_5m_2025-01-01_2026-05-12.csv",
        "spy_5m_2025-01-01_2026-05-07.csv",
    ]:
        sp = DATA_DIR / cand; vp = DATA_DIR / cand.replace("spy_", "vix_").replace("_merged","")
        if not vp.exists():
            vp = DATA_DIR / cand.replace("spy_", "vix_")
        if sp.exists() and vp.exists():
            full_spy = pd.read_csv(sp); full_vix = pd.read_csv(vp)
            print(f"  Loaded: {cand}")
            break
    else:
        raise FileNotFoundError("No SPY/VIX CSV found")

    windows = [
        ("TRAIN", TRAIN_START, TRAIN_END),
        ("TEST",  TEST_START,  TEST_END),
    ]

    window_results = {}
    for wname, wstart, wend in windows:
        print(f"\n{'='*30} {wname} WINDOW ({wstart} to {wend}) {'='*30}")
        spy_w, vix_w = _load_data(full_spy, full_vix, wstart, wend)
        print(f"  Bars: SPY={len(spy_w):,} VIX={len(vix_w):,}")

        base_result, base_m = run_pass(spy_w, vix_w, enabled=False, label="BASELINE")
        gate_result, gate_m = run_pass(spy_w, vix_w, enabled=True,  label="WITH_CARVEOUT")

        delta_sharpe = gate_m["sharpe"] - base_m["sharpe"] if not math.isnan(gate_m["sharpe"]) and not math.isnan(base_m["sharpe"]) else float("nan")
        delta_pnl = gate_m["total_pnl"] - base_m["total_pnl"]
        print(f"  DELTA: sharpe={delta_sharpe:+.4f}  P&L=${delta_pnl:+.0f}")

        j_edge = _j_edge_check(gate_result.trades)
        window_results[wname] = {
            "window": f"{wstart} to {wend}",
            "baseline": base_m,
            "with_carveout": gate_m,
            "delta_sharpe": round(delta_sharpe, 4) if not math.isnan(delta_sharpe) else None,
            "delta_pnl": round(delta_pnl, 2),
            "walk_forward_pass": delta_sharpe > 0 if not math.isnan(delta_sharpe) else False,
            "j_edge": j_edge if wname == "TEST" else None,
        }

    train_pass = window_results["TRAIN"]["walk_forward_pass"]
    test_pass  = window_results["TEST"]["walk_forward_pass"]
    overall_pass = train_pass and test_pass

    print(f"\n{'='*70}")
    print(f"WALK-FORWARD RESULT: TRAIN={'PASS' if train_pass else 'FAIL'}  TEST={'PASS' if test_pass else 'FAIL'}")
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    print(f"TRAIN delta_sharpe: {window_results['TRAIN']['delta_sharpe']:+.4f}")
    print(f"TEST  delta_sharpe: {window_results['TEST']['delta_sharpe']:+.4f}")

    output = {
        "candidate": "BEARISH_SWEEP_BLOCKER with confluence carve-out",
        "generated_at": dt.datetime.now().isoformat(),
        "train_window": str(TRAIN_START) + " to " + str(TRAIN_END),
        "test_window": str(TEST_START) + " to " + str(TEST_END),
        "windows": window_results,
        "overall_walk_forward_pass": overall_pass,
        "test_j_edge": window_results["TEST"]["j_edge"],
    }

    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nOutput: {OUT_JSON}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
