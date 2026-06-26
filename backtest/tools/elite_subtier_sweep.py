"""ELITE sub-tier quality sweep (task 1b77b722).

Current IS: ELITE n=125, WR=20%, pnl=+892, avg=+3/trade.
Low WR but positive due to asymmetric winners.

Stratify ELITE IS trades by:
  1. Sub-tier: confluence_only vs confluence+ribbon_flip vs sequence_only
  2. VIX bucket: <17, 17-20, 20-25, 25+
  3. Time bucket: morning (09:35-11:00), midday (11:00-14:00), afternoon (14:00-15:55)

Propose BLOCK gate if sub-tier WR < 15% AND avg_pnl < -20 AND n >= 10.
No auto-ratify — sub-tier blocks need orchestrator parameter support first.

Output: backtest/autoresearch/results/elite_subtier_sweep.json
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO / "autoresearch" / "results" / "elite_subtier_sweep.json"
RECOUT = REPO.parent / "analysis" / "recommendations" / "elite_subtier_sweep.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}

SAFE_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.3, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)


def classify_tier(t) -> str:
    trig = set(getattr(t, "triggers_fired", []) or [])
    side = getattr(t, "side", "").upper()
    has_conf   = "confluence" in trig
    has_seq    = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_flip   = "ribbon_flip" in trig
    n = len(trig)
    if (has_conf and has_flip) or n >= 3:
        return "SUPER"
    elif has_conf or has_seq:
        return "ELITE"
    elif any(k in trig for k in ("level_rejection", "level_reclaim")):
        return "LEVEL"
    else:
        return "TRENDLINE"


def elite_sub(t) -> str:
    trig = set(getattr(t, "triggers_fired", []) or [])
    has_conf = "confluence" in trig
    has_seq  = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_flip = "ribbon_flip" in trig
    if has_conf and has_flip:
        return "conf+flip"  # near-SUPER
    elif has_conf:
        return "conf_only"
    elif has_seq:
        return "seq_only"
    return "other"


def vix_bucket(t) -> str:
    v = getattr(t, "entry_vix", None)
    if v is None:
        return "unknown"
    if v < 17:
        return "vix<17"
    elif v < 20:
        return "vix_17-20"
    elif v < 25:
        return "vix_20-25"
    return "vix_25+"


def time_bucket(t) -> str:
    et = getattr(t, "entry_time_et", None)
    if et is None:
        return "unknown"
    h = et.hour if et.tzinfo is None else et.replace(tzinfo=None).hour
    m = et.minute
    tod = h * 60 + m
    if tod < 11 * 60:
        return "morning"
    elif tod < 14 * 60:
        return "midday"
    return "afternoon"


def bucket_report(trades, key_fn) -> list:
    groups: dict[str, list] = {}
    for t in trades:
        k = key_fn(t)
        groups.setdefault(k, []).append(t.dollar_pnl)
    rows = []
    for k, pnls in sorted(groups.items()):
        n = len(pnls)
        rows.append({
            "bucket": k, "n": n,
            "wr": round(sum(p > 0 for p in pnls) / n, 3),
            "avg": round(sum(pnls) / n, 1),
            "total": round(sum(pnls), 1),
        })
    return rows


def main():
    print("=" * 70)
    print("ELITE SUB-TIER QUALITY SWEEP (1b77b722)")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES and d in spy_dates]
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    print("\nRunning IS baseline...")
    r_is = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **SAFE_BASE)
    print("Running OOS baseline...")
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **SAFE_BASE)

    # Classify all IS and OOS trades
    elite_is  = [t for t in r_is.trades  if classify_tier(t) == "ELITE"]
    elite_oos = [t for t in r_oos.trades if classify_tier(t) == "ELITE"]
    all_is_by_tier = {}
    for t in r_is.trades:
        tier = classify_tier(t)
        all_is_by_tier.setdefault(tier, []).append(t)

    print(f"\n--- IS TIER DISTRIBUTION ---")
    for tier, ts in sorted(all_is_by_tier.items()):
        pnls = [t.dollar_pnl for t in ts]
        print(f"  {tier:12s}: n={len(ts):3d} WR={sum(p>0 for p in pnls)/len(ts):.1%} "
              f"avg={sum(pnls)/len(ts):+.1f} total={sum(pnls):+.0f}")

    print(f"\n--- ELITE SUB-TIER (IS) ---")
    sub_rows = bucket_report(elite_is, elite_sub)
    for b in sub_rows:
        print(f"  {b['bucket']:20s}: n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f} total={b['total']:+.0f}")

    print(f"\n--- ELITE BY VIX (IS) ---")
    vix_rows = bucket_report(elite_is, vix_bucket)
    for b in vix_rows:
        print(f"  {b['bucket']:15s}: n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f} total={b['total']:+.0f}")

    print(f"\n--- ELITE BY TIME (IS) ---")
    time_rows = bucket_report(elite_is, time_bucket)
    for b in time_rows:
        print(f"  {b['bucket']:12s}: n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f} total={b['total']:+.0f}")

    # OOS breakdown
    print(f"\n--- ELITE OOS ---")
    sub_oos = bucket_report(elite_oos, elite_sub)
    for b in sub_oos:
        print(f"  {b['bucket']:20s}: n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f} total={b['total']:+.0f}")

    # Gate candidates: sub-tiers where IS WR < 15% and avg < -20 and n >= 8
    gate_candidates = []
    for b in sub_rows:
        if b["wr"] < 0.15 and b["avg"] < -20 and b["n"] >= 8:
            gate_candidates.append({"dimension": "elite_sub", **b,
                                    "proposed_action": f"block {b['bucket']} ELITE entries"})
    for b in vix_rows:
        if b["wr"] < 0.15 and b["avg"] < -20 and b["n"] >= 8:
            gate_candidates.append({"dimension": "vix", **b,
                                    "proposed_action": f"block ELITE in {b['bucket']}"})
    for b in time_rows:
        if b["wr"] < 0.15 and b["avg"] < -20 and b["n"] >= 8:
            gate_candidates.append({"dimension": "time", **b,
                                    "proposed_action": f"block ELITE in {b['bucket']}"})

    print(f"\n--- GATE CANDIDATES (WR<15%, avg<-20, n>=8) ---")
    if gate_candidates:
        for gc in gate_candidates:
            print(f"  {gc['dimension']}:{gc['bucket']:20s}: n={gc['n']:3d} WR={gc['wr']:.1%} avg={gc['avg']:+.1f}")
    else:
        print("  None found — ELITE sub-tiers are either profitable or too small to block")

    # Positive insight: sub-tiers worth KEEPING or SUPER-upgrading
    print(f"\n--- HIGH-WR ELITE SUB-TIERS (WR >= 40%) ---")
    for b in sub_rows + vix_rows + time_rows:
        if b.get("wr", 0) >= 0.40 and b["n"] >= 5:
            print(f"  n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f}: {b['bucket']}")

    out = {
        "task": "1b77b722-elite-subtier-sweep",
        "is_tier_distribution": {
            tier: {"n": len(ts), "wr": round(sum(t.dollar_pnl>0 for t in ts)/len(ts), 3),
                   "avg": round(sum(t.dollar_pnl for t in ts)/len(ts), 1),
                   "total": round(sum(t.dollar_pnl for t in ts), 1)}
            for tier, ts in all_is_by_tier.items()
        },
        "elite_sub_tier": sub_rows,
        "elite_vix_buckets": vix_rows,
        "elite_time_buckets": time_rows,
        "elite_oos_sub": sub_oos,
        "gate_candidates": gate_candidates,
        "elite_is_total": round(sum(t.dollar_pnl for t in elite_is), 1),
        "elite_oos_total": round(sum(t.dollar_pnl for t in elite_oos), 1),
    }
    OUT_PATH.parent.mkdir(exist_ok=True, parents=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    RECOUT.parent.mkdir(exist_ok=True)
    RECOUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print(f"       {RECOUT}")


if __name__ == "__main__":
    raise SystemExit(main())
