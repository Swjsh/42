"""AGG VIX bear-entry threshold sweep.

Motivation (task agg-vix-bear-sweep-001):
  OOS deep dive (5/8-6/16) showed:
    VIX < 17  (n=9):  WR=33.3%  avg=-44  total=-400
    VIX 17-20 (n=16): WR=43.8%  avg=+191 total=+3059
    VIX 20-25 (n=3):  WR=100%   avg=+204 total=+613
  Current AGG vix_bear_threshold=15.0 allows these losing low-VIX entries.
  Hypothesis: raising threshold removes net-negative VIX<17 entries.

Speed optimization: run engine ONCE for IS and OOS with baseline threshold (15.0).
Then post-hoc filter trades by their VIX at entry time. This is an approximation
(doesn't model cascade effects from blocking), but valid for direction/magnitude.
Full engine re-run per threshold is ~18x slower and not needed for gate evaluation.

Sweep: vix_bear_threshold in [15.0 (BASELINE), 16.0, 17.0, 17.3, 17.5, 18.0]
Full IS+OOS+sub-window analysis per OP-22 auto-ratify gates.

Security: read-only. No Alpaca calls. No production state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_vix_bear_threshold_sweep.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}
ANCHOR_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
ANCHOR_LOSERS = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

SW_SPLITS = [
    ("SW1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("SW2_2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2), dt.date(2026, 2, 26)),
]

THRESHOLDS = [15.0, 16.0, 17.0, 17.3, 17.5, 18.0]
BASELINE_THRESHOLD = 15.0

AGG_KWARGS = dict(
    use_real_fills=True,
    strike_offset=-2,
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
    midday_trendline_gate=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5,
    enable_bullish=True,
    params_overrides={"vix_bear_threshold": BASELINE_THRESHOLD},
)


def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def get_spy_vix():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"), key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_name = spy_path.name.replace("spy_5m", "vix_5m")
    vix_path = DATA / vix_name
    print(f"  SPY: {spy_path.name}")
    print(f"  VIX: {vix_path.name}")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    return spy_df, vix_df


def get_vix_at_entry(vix_df, entry_dt):
    """Get VIX at 09:35 ET on the entry date (or closest reading >= 09:35)."""
    date_str = str(entry_dt.date())
    rows = vix_df[vix_df["timestamp_et"].str.startswith(date_str)]
    morning = rows[rows["timestamp_et"].str[11:16] >= "09:35"]
    if len(morning) == 0:
        # Fallback: closest any reading that day
        if len(rows) > 0:
            return float(rows.iloc[0]["close"])
        return None
    return float(morning.iloc[0]["close"])


def run_full_period(spy_df, vix_df, start, end, label):
    """Run full baseline backtest; return list of trade dicts with VIX annotation."""
    print(f"  Running engine [{label}] {start} to {end}...", flush=True)
    r = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **AGG_KWARGS)
    trades = []
    for t in r.trades:
        vix_val = get_vix_at_entry(vix_df, t.entry_time_et)
        trades.append({
            "date": t.entry_time_et.date(),
            "entry_dt": t.entry_time_et,
            "side": "P" if "BEARISH" in t.setup else "C",
            "pnl": round(t.dollar_pnl, 2),
            "setup": t.setup,
            "vix": vix_val,
        })
    print(f"    -> {len(trades)} trades, total={sum(t['pnl'] for t in trades):+.0f}")
    return trades


def compute_stats(trades, threshold):
    """P&L for trades where VIX >= threshold (or bull trades always pass)."""
    kept = [t for t in trades if t["side"] == "C" or (t["vix"] is not None and t["vix"] > threshold)]
    total = round(sum(t["pnl"] for t in kept), 1)
    n = len(kept)
    wins = sum(1 for t in kept if t["pnl"] > 0)
    return {"total_pnl": total, "n": n, "wr": round(wins / n, 3) if n else 0.0,
            "n_blocked": len(trades) - n}


def main():
    print("=" * 70)
    print("AGG VIX BEAR THRESHOLD SWEEP")
    print(f"Thresholds: {THRESHOLDS}")
    print("=" * 70)

    all_days = get_fill_days()
    is_days = [d for d in all_days if d < IS_CUTOFF and d not in MDATES_SET]

    print(f"\n[1] Loading SPY/VIX data...")
    spy_df, vix_df = get_spy_vix()

    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    oos_days_all = [d for d in all_days if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    oos_days = oos_days_all[-60:]

    print(f"\n[2] Date ranges:")
    print(f"    IS:  {len(is_days)} fill days ({is_days[0]} to {is_days[-1]})")
    print(f"    OOS: {len(oos_days)} fill days ({oos_days[0]} to {oos_days[-1]})")

    print(f"\n[3] Running baseline engine (once per period)...")
    is_trades = run_full_period(spy_df, vix_df, is_days[0], is_days[-1], "IS")
    oos_trades = run_full_period(spy_df, vix_df, oos_days[0], oos_days[-1], "OOS")

    # VIX annotation check
    missing_vix_is = sum(1 for t in is_trades if t["vix"] is None)
    missing_vix_oos = sum(1 for t in oos_trades if t["vix"] is None)
    if missing_vix_is or missing_vix_oos:
        print(f"  WARNING: {missing_vix_is} IS + {missing_vix_oos} OOS trades missing VIX reading")

    # VIX distribution for bear trades (side=P)
    bear_oos = [t for t in oos_trades if t["side"] == "P" and t["vix"] is not None]
    print(f"\n[4] OOS bear trade VIX distribution (n={len(bear_oos)}):")
    for lo, hi in [(0, 16), (16, 17), (17, 18), (18, 20), (20, 99)]:
        bucket = [t for t in bear_oos if lo <= t["vix"] < hi]
        if bucket:
            total = sum(t["pnl"] for t in bucket)
            wr = sum(1 for t in bucket if t["pnl"] > 0) / len(bucket)
            print(f"    VIX [{lo:.0f}-{hi:.0f}): n={len(bucket)} WR={wr:.0%} total={total:+.0f}")

    # Sweep each threshold
    print(f"\n[5] Applying threshold filter (post-hoc)...")
    is_baseline = compute_stats(is_trades, BASELINE_THRESHOLD)
    oos_baseline = compute_stats(oos_trades, BASELINE_THRESHOLD)
    print(f"  BASELINE (thr=15.0): IS n={is_baseline['n']} P&L={is_baseline['total_pnl']:+.0f} | "
          f"OOS n={oos_baseline['n']} P&L={oos_baseline['total_pnl']:+.0f}")

    candidates = []
    for thr in THRESHOLDS:
        ir = compute_stats(is_trades, thr)
        or_ = compute_stats(oos_trades, thr)
        is_delta = round(ir["total_pnl"] - is_baseline["total_pnl"], 1)
        oos_delta = round(or_["total_pnl"] - oos_baseline["total_pnl"], 1)
        n_removed_is = is_baseline["n"] - ir["n"]
        n_removed_oos = oos_baseline["n"] - or_["n"]

        wf_norm = None
        if n_removed_is > 0 and is_delta > 0 and n_removed_oos > 0:
            per_trade_is = is_delta / n_removed_is
            per_trade_oos = oos_delta / n_removed_oos
            wf_norm = round(per_trade_oos / per_trade_is, 3)

        # SW_hurt: sub-windows where blocking HURTS (delta < 0)
        sw_hurt = 0
        sw_details = []
        for sw_name, sw_start, sw_end in SW_SPLITS:
            sw_trades = [t for t in is_trades if sw_start <= t["date"] <= sw_end]
            sw_base = compute_stats(sw_trades, BASELINE_THRESHOLD)["total_pnl"]
            sw_thr = compute_stats(sw_trades, thr)["total_pnl"]
            sw_delta = round(sw_thr - sw_base, 1)
            hurt = sw_delta < 0
            if hurt:
                sw_hurt += 1
            sw_details.append({"name": sw_name, "delta": sw_delta, "hurt": hurt})

        # Anchor check: winners not blocked
        anchor_blocked = []
        for d in ANCHOR_WINNERS:
            day_trades = [t for t in oos_trades if t["date"] == d and t["side"] == "P"]
            for t in day_trades:
                if t["vix"] is not None and t["vix"] <= thr:
                    anchor_blocked.append({"date": str(d), "vix": t["vix"], "pnl": t["pnl"]})
        anchor_ok = len(anchor_blocked) == 0

        gate_is = is_delta > 0
        gate_oos = oos_delta > 0
        gate_wf = (wf_norm is not None) and (wf_norm >= 0.70)
        gate_sw = sw_hurt <= 1
        all_pass = gate_is and gate_oos and gate_wf and gate_sw and anchor_ok

        marker = " *** AUTO-RATIFY ***" if (thr != BASELINE_THRESHOLD and all_pass) else ""
        print(f"  thr={thr:<5.1f}: IS n={ir['n']:<4} d={is_delta:>+8.0f} | "
              f"OOS n={or_['n']:<4} d={oos_delta:>+8.0f} | "
              f"WF={str(wf_norm):>7} SW_hurt={sw_hurt} anchor={'OK' if anchor_ok else 'FAIL'}{marker}")

        candidates.append({
            "threshold": thr,
            "is": ir,
            "oos": or_,
            "is_delta": is_delta,
            "oos_delta": oos_delta,
            "n_removed_is": n_removed_is,
            "n_removed_oos": n_removed_oos,
            "wf_norm": wf_norm,
            "sw_hurt": sw_hurt,
            "sw_details": sw_details,
            "anchor_blocked": anchor_blocked,
            "gates": {
                "is_pos": gate_is, "oos_pos": gate_oos,
                "wf": gate_wf, "sw": gate_sw, "anchor": anchor_ok,
            },
            "auto_ratify": (thr != BASELINE_THRESHOLD) and all_pass,
        })

    # Find best
    ratify = [c for c in candidates if c["auto_ratify"]]
    best = max(ratify, key=lambda c: c["oos_delta"]) if ratify else None

    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"{'='*70}")
    if best:
        print(f"  BEST: vix_bear_threshold = {best['threshold']:.1f}")
        print(f"  IS_delta  = {best['is_delta']:+.1f}")
        print(f"  OOS_delta = {best['oos_delta']:+.1f}")
        print(f"  WF_norm   = {best['wf_norm']}")
        print(f"  SW_hurt   = {best['sw_hurt']}")
        print(f"  Anchor    = {'OK' if best['gates']['anchor'] else 'FAIL'}")
        print(f"\n  VERDICT: AUTO-RATIFY vix_bear_threshold = {best['threshold']:.1f}")
        print(f"  Update: automation/state/aggressive/params.json")
        print(f"    vix_entry_thresholds.bear_min_exclusive_and_rising -> {best['threshold']:.1f}")
    else:
        print("  No candidate cleared all gates. REJECT.")

    scorecard = {
        "task": "agg-vix-bear-sweep-001",
        "method": "post-hoc VIX filter (1 engine run per period, O(1) threshold sweep)",
        "baseline_threshold": BASELINE_THRESHOLD,
        "thresholds_tested": THRESHOLDS,
        "is_date_range": [str(is_days[0]), str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "is_trades_baseline": len(is_trades),
        "oos_trades_baseline": len(oos_trades),
        "candidates": candidates,
        "best": {
            "threshold": best["threshold"] if best else None,
            "is_delta": best["is_delta"] if best else None,
            "oos_delta": best["oos_delta"] if best else None,
            "wf_norm": best["wf_norm"] if best else None,
            "sw_hurt": best["sw_hurt"] if best else None,
            "auto_ratify": bool(best["auto_ratify"]) if best else False,
        },
        "implementation": (
            "Update automation/state/aggressive/params.json "
            "vix_entry_thresholds.bear_min_exclusive_and_rising to best_threshold. "
            "Caution: post-hoc filter ignores cascade effects; "
            "confirm with 1 full engine re-run at best threshold."
        ),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SWEEP COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
