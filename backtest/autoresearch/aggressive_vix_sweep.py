"""
Aggressive account VIX gate sweep.

Aggressive has fundamentally different VIX params than SAFE:
  - bear_min = 15.0  (SAFE: 17.30)
  - bull_hard_cap = 30.0  (SAFE: 18.0 after Rank 35)

SAFE confirmed: vix_bull_max=18 is better than 22 (WF=5.946 PASS).
Q: For Aggressive with its higher risk tolerance, what bull cap is right?
Q: Is the 15.0 bear threshold optimal, or would 14/16/17.30 be better?

Baseline for Aggressive:
  - same deployed gates: block_level_rejection, block_elite_bull (VIX 15-17.5)
  - premium_stop_pct_bear=-0.10 (aligned after Rank 33)
  - runner_target_premium_pct=5.0  (Aggressive uses 5x runner, not 2.5x)
  - per_trade_risk_cap_pct=0.50 (Aggressive: 50%, not 30%)
  - NO midday_trendline_gate (Aggressive heartbeat doesn't have this)
  - vix_bull_max=30.0, vix_bear_threshold=15.0 (Aggressive production values)

Note: tp1_premium_pct=0.75 (Aggressive) vs 0.30 (SAFE) is not wired in orchestrator.
For directional gate research, the TP1 target changes P&L magnitude but NOT which
VIX levels are profitable vs not. Gate direction is valid regardless.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

# Aggressive-specific baseline (production-aligned)
AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,       # Aggressive has no midday gate
    premium_stop_pct_bear=-0.07,        # C14 fix: production is -0.07 (TIGHTER_STOP_2)
    tp1_premium_pct=0.75,              # C14 fix: must match production (default is 0.30)
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,     # Aggressive: 5x runner
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,       # Aggressive: 50% risk
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={
        "vix_bull_max": 30.0,          # Aggressive: cap at 30
        "vix_bear_threshold": 15.0,    # Aggressive: bear entry at VIX>=15
    },
)

# SAFE baseline for comparison
SAFE_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},  # SAFE: cap at 18 (Rank 35)
)


def vix_bucket(v):
    if v < 15:
        return "<15"
    elif v < 17:
        return "15-17"
    elif v < 18:
        return "17-18"
    elif v < 20:
        return "18-20"
    elif v < 22:
        return "20-22"
    elif v < 25:
        return "22-25"
    elif v < 30:
        return "25-30"
    else:
        return "30+"


def direction_breakdown(result, label):
    """Break down trades by direction (CALL=bull, PUT=bear) and VIX."""
    bears = [t for t in result.trades if getattr(t, "side", "?") == "P"]
    bulls = [t for t in result.trades if getattr(t, "side", "?") == "C"]
    other = [t for t in result.trades if getattr(t, "side", "?") not in ("P", "C")]

    total_pnl = sum(t.dollar_pnl for t in result.trades)
    bear_pnl = sum(t.dollar_pnl for t in bears)
    bull_pnl = sum(t.dollar_pnl for t in bulls)

    print(f"\n=== {label} DIRECTION BREAKDOWN ===")
    print(f"  TOTAL:  n={len(result.trades)} pnl={total_pnl:+.0f}")
    print(f"  BEAR (PUT): n={len(bears)} pnl={bear_pnl:+.0f} avg={bear_pnl/len(bears):+.0f}" if bears else "  BEAR (PUT): n=0")
    print(f"  BULL (CALL): n={len(bulls)} pnl={bull_pnl:+.0f} avg={bull_pnl/len(bulls):+.0f}" if bulls else "  BULL (CALL): n=0")
    if other:
        print(f"  UNKNOWN: n={len(other)}")

    # VIX breakdown for bull trades specifically
    if bulls:
        print(f"\n  BULL by VIX:")
        bull_bkts = {}
        for t in bulls:
            v = float(getattr(t, "entry_vix", 0) or 0)
            bkt = vix_bucket(v)
            bull_bkts.setdefault(bkt, []).append(t)
        for bkt in ["<15", "15-17", "17-18", "18-20", "20-22", "22-25", "25-30", "30+"]:
            ts = bull_bkts.get(bkt, [])
            if not ts:
                continue
            pnl = sum(t.dollar_pnl for t in ts)
            wins = sum(1 for t in ts if t.dollar_pnl > 0)
            wr = wins / len(ts)
            print(f"    VIX {bkt:<7}: n={len(ts):3d} WR={wr:.0%} pnl={pnl:+.0f} avg={pnl/len(ts):+.0f}")

    # VIX breakdown for bear trades
    if bears:
        print(f"\n  BEAR by VIX:")
        bear_bkts = {}
        for t in bears:
            v = float(getattr(t, "entry_vix", 0) or 0)
            bkt = vix_bucket(v)
            bear_bkts.setdefault(bkt, []).append(t)
        for bkt in ["<15", "15-17", "17-18", "18-20", "20-22", "22-25", "25-30", "30+"]:
            ts = bear_bkts.get(bkt, [])
            if not ts:
                continue
            pnl = sum(t.dollar_pnl for t in ts)
            wins = sum(1 for t in ts if t.dollar_pnl > 0)
            wr = wins / len(ts)
            print(f"    VIX {bkt:<7}: n={len(ts):3d} WR={wr:.0%} pnl={pnl:+.0f} avg={pnl/len(ts):+.0f}")

    return bears, bulls


def run_bull_cap_sweep(spy_df, vix_df, label, base_kwargs):
    """Sweep vix_bull_max to find optimal cap for this account type."""
    print(f"\n\n=== {label}: VIX_BULL_HARD_CAP SWEEP (IS) ===")
    base = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **base_kwargs)
    base_pnl = sum(t.dollar_pnl for t in base.trades)
    base_n = len(base.trades)
    print(f"BASE: n={base_n} pnl={base_pnl:+.0f}")

    caps = [18.0, 20.0, 22.0, 25.0, 30.0]
    results = []
    for cap in caps:
        kwarg_override = dict(base_kwargs)
        po = dict(kwarg_override.get("params_overrides", {}))
        po["vix_bull_max"] = cap
        kwarg_override["params_overrides"] = po
        r = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **kwarg_override)
        r_pnl = sum(t.dollar_pnl for t in r.trades)
        delta = r_pnl - base_pnl
        n_diff = base_n - len(r.trades)
        sign = "+" if delta >= 0 else "-"
        print(f"  cap={cap:.0f}: n={len(r.trades):3d} (removed={n_diff:2d}) pnl={r_pnl:+.0f} delta={delta:+.0f}")
        results.append({"cap": cap, "n": len(r.trades), "pnl": r_pnl, "delta": delta, "n_removed": n_diff})

    return results


def run_bear_thresh_sweep(spy_df, vix_df, label, base_kwargs):
    """Sweep vix_bear_threshold to find optimal bear entry VIX floor."""
    print(f"\n\n=== {label}: VIX_BEAR_THRESHOLD SWEEP (IS) ===")
    base = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **base_kwargs)
    base_pnl = sum(t.dollar_pnl for t in base.trades)
    base_n = len(base.trades)
    print(f"BASE: n={base_n} pnl={base_pnl:+.0f}")

    thresholds = [14.0, 15.0, 16.0, 17.30]
    results = []
    for thresh in thresholds:
        kwarg_override = dict(base_kwargs)
        po = dict(kwarg_override.get("params_overrides", {}))
        po["vix_bear_threshold"] = thresh
        kwarg_override["params_overrides"] = po
        r = run_backtest(spy_df, vix_df, start_date=IS_S, end_date=IS_E, **kwarg_override)
        r_pnl = sum(t.dollar_pnl for t in r.trades)
        delta = r_pnl - base_pnl
        n_diff = base_n - len(r.trades)
        print(f"  bear_thresh={thresh:.2f}: n={len(r.trades):3d} (removed={n_diff:2d}) pnl={r_pnl:+.0f} delta={delta:+.0f}")
        results.append({"thresh": thresh, "n": len(r.trades), "pnl": r_pnl, "delta": delta, "n_removed": n_diff})

    return results


def run_full_bull_ab(spy_df, vix_df, label, base_kwargs, cap):
    """Full IS + OOS A/B for a given bull cap."""
    print(f"\n\n=== {label}: FULL A/B vix_bull_max={cap} ===")

    def run_at_cap(start, end, c):
        kw = dict(base_kwargs)
        po = dict(kw.get("params_overrides", {}))
        po["vix_bull_max"] = c
        kw["params_overrides"] = po
        return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **kw)

    def run_base(start, end):
        return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **base_kwargs)

    is_base = run_base(IS_S, IS_E)
    is_cand = run_at_cap(IS_S, IS_E, cap)
    is_base_pnl = sum(t.dollar_pnl for t in is_base.trades)
    is_cand_pnl = sum(t.dollar_pnl for t in is_cand.trades)
    is_delta = is_cand_pnl - is_base_pnl
    n_is_blocked = len(is_base.trades) - len(is_cand.trades)

    oos_base = run_base(OOS_S, OOS_E)
    oos_cand = run_at_cap(OOS_S, OOS_E, cap)
    oos_base_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    oos_cand_pnl = sum(t.dollar_pnl for t in oos_cand.trades)
    oos_delta = oos_cand_pnl - oos_base_pnl
    n_oos_blocked = len(oos_base.trades) - len(oos_cand.trades)

    print(f"  IS:  base n={len(is_base.trades)} pnl={is_base_pnl:+.0f} | cand n={len(is_cand.trades)} pnl={is_cand_pnl:+.0f} | delta={is_delta:+.0f} (n_blocked={n_is_blocked})")
    print(f"  OOS: base n={len(oos_base.trades)} pnl={oos_base_pnl:+.0f} | cand n={len(oos_cand.trades)} pnl={oos_cand_pnl:+.0f} | delta={oos_delta:+.0f} (n_blocked={n_oos_blocked})")

    n_is = len(is_base.trades)
    n_oos = len(oos_base.trades)
    wf = None
    if n_is_blocked > 0 and n_oos_blocked > 0 and is_delta != 0:
        wf = (oos_delta / n_oos) / (is_delta / n_is)
        print(f"  WF_norm={wf:.3f} (gate=0.70)")
    elif n_is_blocked > 0 and n_oos_blocked == 0:
        print(f"  WARNING: n_oos_blocked=0 (WF inconclusive, but OOS economically unaffected)")
    else:
        print(f"  WARNING: n_is_blocked={n_is_blocked} insufficient")

    # Sub-windows
    windows = [
        ("W1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
        ("W2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        ("W3_Q12026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
        ("W4_Apr26",  dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
    ]
    print(f"\n  IS sub-windows:")
    hurt = 0
    for name, ws, we in windows:
        sw_base = run_base(ws, we)
        sw_cand = run_at_cap(ws, we, cap)
        sw_base_pnl = sum(t.dollar_pnl for t in sw_base.trades)
        sw_cand_pnl = sum(t.dollar_pnl for t in sw_cand.trades)
        sw_delta = sw_cand_pnl - sw_base_pnl
        sw_blocked = len(sw_base.trades) - len(sw_cand.trades)
        verdict = "HELP" if sw_delta > 0 else "FLAT" if sw_delta == 0 else "HURT"
        if verdict == "HURT":
            hurt += 1
        print(f"    {name}: n_blocked={sw_blocked} delta={sw_delta:+.0f} -> {verdict}")
    print(f"  SW hurt: {hurt}/4 (gate: <=1)")

    oos_pos = oos_delta > 0
    sw_ok = hurt <= 1
    wf_pass = wf is not None and wf >= 0.70
    verdict_str = "CANDIDATE" if oos_pos and sw_ok and (wf_pass or n_oos_blocked == 0) else "REJECT"
    print(f"\n  VERDICT: OOS_pos={oos_pos} SW_ok={sw_ok} WF={'PASS' if wf_pass else 'FAIL'} -> {verdict_str}")

    return {
        "cap": cap, "label": label,
        "is_delta": is_delta, "oos_delta": oos_delta,
        "n_is_blocked": n_is_blocked, "n_oos_blocked": n_oos_blocked,
        "wf": wf, "sw_hurt": hurt,
    }


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    # ---- STEP 1: Direction breakdown for Aggressive vs SAFE ----
    print("\n\n" + "="*60)
    print("STEP 1: DIRECTION + VIX BREAKDOWN (AGGRESSIVE vs SAFE BASELINE)")
    print("="*60)

    agg_is = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **AGG_BASE_KWARGS)
    agg_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **AGG_BASE_KWARGS)
    agg_is_bears, agg_is_bulls = direction_breakdown(agg_is, "AGGRESSIVE IS")
    agg_oos_bears, agg_oos_bulls = direction_breakdown(agg_oos, "AGGRESSIVE OOS")

    safe_is = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **SAFE_BASE_KWARGS)
    safe_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **SAFE_BASE_KWARGS)
    direction_breakdown(safe_is, "SAFE IS (reference)")
    direction_breakdown(safe_oos, "SAFE OOS (reference)")

    # ---- STEP 2: VIX_BULL_HARD_CAP sweep for Aggressive ----
    print("\n\n" + "="*60)
    print("STEP 2: VIX_BULL_HARD_CAP SWEEP FOR AGGRESSIVE")
    print("="*60)
    bull_sweep = run_bull_cap_sweep(spy, vix, "AGGRESSIVE", AGG_BASE_KWARGS)

    # ---- STEP 3: VIX_BEAR_THRESHOLD sweep for Aggressive ----
    print("\n\n" + "="*60)
    print("STEP 3: VIX_BEAR_THRESHOLD SWEEP FOR AGGRESSIVE")
    print("="*60)
    bear_sweep = run_bear_thresh_sweep(spy, vix, "AGGRESSIVE", AGG_BASE_KWARGS)

    # ---- STEP 4: Full A/B for best IS bull cap ----
    print("\n\n" + "="*60)
    print("STEP 4: FULL A/B FOR BEST AGGRESSIVE BULL CAP")
    print("="*60)
    best_bull = min(bull_sweep, key=lambda r: abs(r["delta"] - max(x["delta"] for x in bull_sweep if x["delta"] > 0)))

    if any(r["delta"] > 0 for r in bull_sweep):
        best_bull = max((r for r in bull_sweep if r["delta"] > 0), key=lambda r: r["delta"])
        if best_bull["cap"] != AGG_BASE_KWARGS["params_overrides"]["vix_bull_max"]:
            print(f"Best IS candidate: cap={best_bull['cap']} (IS_delta={best_bull['delta']:+.0f})")
            run_full_bull_ab(spy, vix, "AGGRESSIVE", AGG_BASE_KWARGS, best_bull["cap"])
        else:
            print(f"Base cap={best_bull['cap']} is already optimal (no improvement found)")
    else:
        print("No positive IS improvement found for bull cap reduction. Current cap=30 may be optimal.")

    # ---- STEP 5: Full A/B for best IS bear threshold ----
    print("\n\n" + "="*60)
    print("STEP 5: FULL A/B FOR BEST AGGRESSIVE BEAR THRESHOLD")
    print("="*60)
    current_thresh = AGG_BASE_KWARGS["params_overrides"]["vix_bear_threshold"]
    better_thresh = [r for r in bear_sweep if r["delta"] > 0 and r["thresh"] != current_thresh]
    if better_thresh:
        best_bear = max(better_thresh, key=lambda r: r["delta"])
        print(f"Best IS candidate: thresh={best_bear['thresh']} (IS_delta={best_bear['delta']:+.0f})")
        kwarg_override = dict(AGG_BASE_KWARGS)
        po = dict(kwarg_override.get("params_overrides", {}))
        po["vix_bear_threshold"] = best_bear["thresh"]
        kwarg_override["params_overrides"] = po
        oos_base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **AGG_BASE_KWARGS)
        oos_cand = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **kwarg_override)
        oos_delta = sum(t.dollar_pnl for t in oos_cand.trades) - sum(t.dollar_pnl for t in oos_base.trades)
        n_oos_blocked = len(oos_base.trades) - len(oos_cand.trades)
        print(f"  OOS: delta={oos_delta:+.0f} (n_blocked={n_oos_blocked})")
    else:
        print(f"No IS improvement found for bear threshold change. Current thresh={current_thresh} is optimal.")

    print("\n\n=== SUMMARY ===")
    print("Aggressive account VIX research complete.")


if __name__ == "__main__":
    main()
