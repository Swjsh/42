"""Comprehensive AGG audit: exit types, ribbon_flip quality split, conf+lvl_rec deep dive.

Tasks covered:
  6b403baf - EXIT TYPE AUDIT for AGG (post-L109 fix)
  2207a18a - ribbon_just_flipped_bearish sizing A/B
  6d8e358a - conf+lvl_rec DEEP DIVE (time/VIX/level-type slices)

Single engine pass (IS + OOS). No Alpaca calls. Read-only.
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa
from sniper_matrix import norm_str  # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "comprehensive_audit_v1.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

AGG = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.667, runner_target_premium_pct=5.0,
    f9_vol_mult=0.7, min_triggers_bear=1, min_triggers_bull=1,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True, midday_trendline_gate=True,
    block_elite_bull=True, block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    require_bearish_fill_bar=True, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)


def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    return spy_df, vix_df


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    wr   = sum(p > 0 for p in pnls) / len(pnls)
    return {"n": len(trades), "wr": round(wr, 3),
            "avg": round(sum(pnls)/len(pnls), 1),
            "total": round(sum(pnls), 1)}


def exit_breakdown(trades):
    """Exit type breakdown with P&L by bucket."""
    buckets = defaultdict(list)
    for t in trades:
        reason = str(t.exit_reason).split(".")[-1]
        buckets[reason].append(t.dollar_pnl)
    total_n = len(trades)
    result = {}
    for reason, pnls in sorted(buckets.items(), key=lambda x: -len(x[1])):
        result[reason] = {
            "n": len(pnls),
            "pct": round(len(pnls)/total_n, 3),
            "avg": round(sum(pnls)/len(pnls), 1),
            "total": round(sum(pnls), 1),
        }
    return result


def ribbon_split(trades):
    """Split trades by ribbon_flip in triggers_fired."""
    rf_yes = [t for t in trades if "ribbon_flip" in (t.triggers_fired or [])]
    rf_no  = [t for t in trades if "ribbon_flip" not in (t.triggers_fired or [])]
    yes_s = stats(rf_yes)
    no_s  = stats(rf_no)
    yes_s["avg_qty"] = round(sum(t.qty for t in rf_yes) / len(rf_yes), 1) if rf_yes else 0
    no_s["avg_qty"]  = round(sum(t.qty for t in rf_no)  / len(rf_no),  1) if rf_no  else 0
    return {"ribbon_flip_true": yes_s, "ribbon_flip_false": no_s}


def quality_tier(t):
    """Infer quality tier from triggers_fired (mirrors orchestrator logic)."""
    trig = set(t.triggers_fired or [])
    has_conf   = "confluence"         in trig
    has_rf     = "ribbon_flip"        in trig
    has_seq_rej = "sequence_rejection" in trig
    has_seq_rec = "sequence_reclaim"   in trig
    has_level  = "level_rejection"    in trig or "level_reclaim" in trig
    has_trend  = "trendline_rejection" in trig
    n_triggers = len(trig)
    if (has_conf and has_rf) or n_triggers >= 3:
        return "SUPER"
    elif has_conf or has_seq_rej or has_seq_rec:
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif has_trend:
        return "TRENDLINE"
    else:
        return "BASE"


def quality_tier_split(trades):
    """Stats by quality tier."""
    buckets = defaultdict(list)
    for t in trades:
        tier = quality_tier(t)
        buckets[tier].append(t)
    result = {}
    for tier in ("SUPER", "ELITE", "LEVEL", "TRENDLINE", "BASE"):
        ts = buckets.get(tier, [])
        s = stats(ts)
        s["avg_qty"] = round(sum(t.qty for t in ts)/len(ts), 1) if ts else 0
        rf_in_tier = [t for t in ts if "ribbon_flip" in (t.triggers_fired or [])]
        s["ribbon_flip_count"] = len(rf_in_tier)
        result[tier] = s
    return result


def conf_lvl_rec_deep_dive(trades):
    """
    Decompose conf+lvl_rec trades (setup that includes confluence trigger class).
    Slices: time bucket, VIX bucket, side.
    """
    # conf+lvl_rec = trades with both 'confluence' and ('level_rejection' or 'level_reclaim')
    clr = [t for t in trades
           if "confluence" in (t.triggers_fired or [])
           and ("level_rejection" in (t.triggers_fired or []) or
                "level_reclaim"   in (t.triggers_fired or []))]

    def time_bucket(t):
        h = t.entry_time_et.hour
        m = t.entry_time_et.minute
        tot = h * 60 + m
        if tot < 600:    return "09:35-10:00"
        if tot < 720:    return "10:00-12:00"
        if tot < 840:    return "12:00-14:00"
        return                   "14:00-15:00"

    def vix_bucket(t):
        v = t.entry_vix or 0
        if v <  15: return "<15"
        if v <  18: return "15-18"
        if v <  22: return "18-22"
        return              "22+"

    def lvl_type(t):
        trig = set(t.triggers_fired or [])
        if "level_rejection" in trig: return "level_rejection"
        if "level_reclaim"   in trig: return "level_reclaim"
        return "other"

    result = {
        "total": stats(clr),
        "by_time":     {},
        "by_vix":      {},
        "by_lvl_type": {},
        "by_side":     {},
    }
    for bucket_fn, key in [(time_bucket, "by_time"), (vix_bucket, "by_vix"),
                           (lvl_type, "by_lvl_type")]:
        buckets = defaultdict(list)
        for t in clr:
            buckets[bucket_fn(t)].append(t)
        for k, ts in sorted(buckets.items()):
            result[key][k] = stats(ts)

    for side in ("C", "P"):
        result["by_side"][side] = stats([t for t in clr if t.side == side])

    return result, clr


def ribbon_flip_sizing_simulation(trades, label):
    """
    Simulate effect of boosting ribbon_flip=True trades from TRENDLINE(3) or LEVEL(22)
    to ELITE(10) tier quantity (floor uplift for under-tier ribbon_flip trades).

    Current problem:
    - TRENDLINE+ribbon_flip: qty=3 (too low for a quality signal)
    - LEVEL+ribbon_flip: qty=22 (already high)
    - SUPER (conf+rf): qty=15 (already high)

    Proposal: ribbon_flip-only (no confluence, no level) -> ELITE qty=10 min.
    i.e., upgrade TRENDLINE+ribbon_flip from qty=3 to qty=10.
    """
    sim_pnl_delta = 0.0
    upgraded = 0
    for t in trades:
        trig = set(t.triggers_fired or [])
        if "ribbon_flip" not in trig:
            continue
        tier = quality_tier(t)
        if tier == "TRENDLINE" and t.qty < 10:
            # Scale up P&L linearly
            new_qty = 10
            delta = t.dollar_pnl * (new_qty / t.qty) - t.dollar_pnl
            sim_pnl_delta += delta
            upgraded += 1
    return {"label": label, "upgraded_count": upgraded,
            "sim_pnl_delta": round(sim_pnl_delta, 1)}


def main():
    print("=" * 72)
    print("COMPREHENSIVE AGG AUDIT v1")
    print("Tasks: 6b403baf / 2207a18a / 6d8e358a")
    print("=" * 72)

    spy_df, vix_df = load_data()
    all_fill_days = get_fill_days()
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)

    is_days  = [d for d in all_fill_days if d < IS_CUTOFF  and d not in MDATES_SET]
    oos_days = [d for d in all_fill_days if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]

    print(f"\nIS:  {len(is_days)} days ({is_days[0]} -> {is_days[-1]})")
    print(f"OOS: {len(oos_days)} days ({oos_days[0]} -> {oos_days[-1]})")

    print("\n[1] Running IS...")
    is_r  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **AGG)
    print(f"    n={len(is_r.trades)} total={sum(t.dollar_pnl for t in is_r.trades):+.0f}")

    print("[2] Running OOS...")
    oos_r = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **AGG)
    print(f"    n={len(oos_r.trades)} total={sum(t.dollar_pnl for t in oos_r.trades):+.0f}")

    is_trades  = is_r.trades
    oos_trades = oos_r.trades

    # ---------- A: Exit Type Audit ----------
    print("\n" + "=" * 60)
    print("A. EXIT TYPE BREAKDOWN (task 6b403baf)")
    print("=" * 60)

    is_exits  = exit_breakdown(is_trades)
    oos_exits = exit_breakdown(oos_trades)

    print("\nIS exit breakdown:")
    for reason, d in is_exits.items():
        print(f"  {reason:<35} n={d['n']:3} ({d['pct']:4.0%}) avg={d['avg']:+7.0f} total={d['total']:+8.0f}")

    print("\nOOS exit breakdown:")
    for reason, d in oos_exits.items():
        print(f"  {reason:<35} n={d['n']:3} ({d['pct']:4.0%}) avg={d['avg']:+7.0f} total={d['total']:+8.0f}")

    # ---------- B: Quality Tier Split ----------
    print("\n" + "=" * 60)
    print("B. QUALITY TIER SPLIT (task 2207a18a context)")
    print("=" * 60)

    is_tier  = quality_tier_split(is_trades)
    oos_tier = quality_tier_split(oos_trades)

    print("\nIS by quality tier:")
    for tier, d in is_tier.items():
        if d["n"] == 0:
            continue
        print(f"  {tier:<12} n={d['n']:3} WR={d['wr']:5.1%} avg={d['avg']:+7.0f} "
              f"total={d['total']:+8.0f} qty={d['avg_qty']:4.1f} rf_in_tier={d['ribbon_flip_count']}")

    print("\nOOS by quality tier:")
    for tier, d in oos_tier.items():
        if d["n"] == 0:
            continue
        print(f"  {tier:<12} n={d['n']:3} WR={d['wr']:5.1%} avg={d['avg']:+7.0f} "
              f"total={d['total']:+8.0f} qty={d['avg_qty']:4.1f} rf_in_tier={d['ribbon_flip_count']}")

    # ---------- C: Ribbon_flip split ----------
    print("\n" + "=" * 60)
    print("C. RIBBON_FLIP SPLIT (task 2207a18a)")
    print("=" * 60)

    is_rf  = ribbon_split(is_trades)
    oos_rf = ribbon_split(oos_trades)

    print("\nIS ribbon_flip split:")
    for label, d in is_rf.items():
        print(f"  {label:<22} n={d['n']:3} WR={d['wr']:5.1%} avg={d['avg']:+7.0f} "
              f"total={d['total']:+8.0f} qty={d['avg_qty']:5.1f}")

    print("\nOOS ribbon_flip split:")
    for label, d in oos_rf.items():
        print(f"  {label:<22} n={d['n']:3} WR={d['wr']:5.1%} avg={d['avg']:+7.0f} "
              f"total={d['total']:+8.0f} qty={d['avg_qty']:5.1f}")

    # Simulation: upgrade TRENDLINE+ribbon_flip to ELITE qty=10
    is_sim  = ribbon_flip_sizing_simulation(is_trades,  "IS")
    oos_sim = ribbon_flip_sizing_simulation(oos_trades, "OOS")
    print("\nSizing simulation (TRENDLINE+ribbon_flip qty:3->10):")
    print(f"  IS  upgraded={is_sim['upgraded_count']} sim_pnl_delta={is_sim['sim_pnl_delta']:+.0f}")
    print(f"  OOS upgraded={oos_sim['upgraded_count']} sim_pnl_delta={oos_sim['sim_pnl_delta']:+.0f}")

    # ---------- D: conf+lvl_rec deep dive ----------
    print("\n" + "=" * 60)
    print("D. CONF+LVL_REC DEEP DIVE (task 6d8e358a)")
    print("=" * 60)

    is_clr,  is_clr_trades  = conf_lvl_rec_deep_dive(is_trades)
    oos_clr, oos_clr_trades = conf_lvl_rec_deep_dive(oos_trades)

    print(f"\nIS conf+lvl_rec: n={is_clr['total']['n']} WR={is_clr['total']['wr']:.1%} "
          f"avg={is_clr['total']['avg']:+.0f} total={is_clr['total']['total']:+.0f}")

    for slice_key in ("by_time", "by_vix", "by_lvl_type", "by_side"):
        print(f"\n  IS {slice_key}:")
        for k, d in is_clr[slice_key].items():
            if d["n"] > 0:
                print(f"    {k:<20} n={d['n']:3} WR={d['wr']:5.1%} avg={d['avg']:+7.0f} total={d['total']:+8.0f}")

    print(f"\nOOS conf+lvl_rec: n={oos_clr['total']['n']} WR={oos_clr['total']['wr']:.1%} "
          f"avg={oos_clr['total']['avg']:+.0f} total={oos_clr['total']['total']:+.0f}")

    for slice_key in ("by_time", "by_vix", "by_lvl_type", "by_side"):
        print(f"\n  OOS {slice_key}:")
        for k, d in oos_clr[slice_key].items():
            if d["n"] > 0:
                print(f"    {k:<20} n={d['n']:3} WR={d['wr']:5.1%} avg={d['avg']:+7.0f} total={d['total']:+8.0f}")

    # ---------- Scorecard ----------
    scorecard = {
        "task": "comprehensive-agg-audit-v1",
        "tasks_covered": ["6b403baf", "2207a18a", "6d8e358a"],
        "is_date_range":  [str(is_days[0]),  str(is_days[-1])],
        "oos_date_range": [str(oos_days[0]), str(oos_days[-1])],
        "a_exit_breakdown": {"is": is_exits,  "oos": oos_exits},
        "b_quality_tier":   {"is": is_tier,   "oos": oos_tier},
        "c_ribbon_flip": {
            "is":  is_rf,  "oos": oos_rf,
            "sizing_sim": {"is": is_sim, "oos": oos_sim},
        },
        "d_conf_lvl_rec":   {"is": is_clr,   "oos": oos_clr},
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(scorecard, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("COMPREHENSIVE AUDIT COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
