"""SAFE account comprehensive audit.

Maps the Safe account engine's IS/OOS performance using current production params.
SAFE params: OTM-2 at $2K-$10K, premium_stop_bear=-0.10, tp1=0.50, runner=2.5x,
bull_hard_cap=18.0, block_level_rejection=True, block_elite_bull 15-17.5, etc.

Goal: find the same signals as the AGG audit:
  - Exit type breakdown
  - Quality tier breakdown
  - OOS loser dissection
  - Any blockable patterns with positive G1

Security: read-only (except output). No Alpaca calls.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_comprehensive_audit.json"

IS_CUTOFF   = dt.date(2026, 2, 27)
MDATES_SET  = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

# SAFE production params (from automation/state/params.json as of 2026-06-17)
SAFE_PARAMS = dict(
    use_real_fills=True,
    strike_offset=-2,          # OTM-2 at $2K equity tier
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=2,       # SAFE requires 2 bull triggers
    no_trade_before=dt.time(9, 35),
    no_trade_window=(dt.time(11, 30), dt.time(12, 0)),   # 11:30-12:00 blocked
    block_level_rejection=True,
    block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.3,
    enable_bullish=True,
    params_overrides={
        "vix_bear_threshold": 17.3,
        "vix_bull_hard_cap": 18.0,
    },
)


def quality_tier(t):
    trig = set(t.triggers_fired or [])
    if ('confluence' in trig and 'ribbon_flip' in trig) or len(trig) >= 3:
        return "SUPER"
    elif 'confluence' in trig or 'sequence_rejection' in trig or 'sequence_reclaim' in trig:
        return "ELITE"
    elif 'level_rejection' in trig or 'level_reclaim' in trig:
        return "LEVEL"
    elif 'trendline_rejection' in trig:
        return "TRENDLINE"
    return "BASE"


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    return {"n": len(trades), "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
            "avg": round(sum(pnls) / len(pnls), 1), "total": round(sum(pnls), 1)}


def exit_bd(trades):
    ct = defaultdict(int)
    for t in trades:
        ct[str(t.exit_reason).split(".")[-1]] += 1
    total = len(trades)
    return {k: {"n": v, "pct": round(v/total, 3)} for k, v in sorted(ct.items(), key=lambda x: -x[1])}


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    return spy_df, vix_df


def main():
    print("=" * 70)
    print("SAFE COMPREHENSIVE AUDIT")
    print("=" * 70)

    spy_df, vix_df = load_data()
    c = Counter(f.name[3:9] for f in (DATA/"options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k,"%y%m%d").date() for k,v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF  and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    print(f"IS: {len(is_days)} days ({is_days[0]} -> {is_days[-1]})")
    print(f"OOS: {len(oos_days)} days ({oos_days[0]} -> {oos_days[-1]})")

    print("\n[1] Running SAFE baseline...")
    r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **SAFE_PARAMS)
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **SAFE_PARAMS)

    is_stats  = stats(r_is.trades)
    oos_stats = stats(r_oos.trades)
    anchor = sum(t.dollar_pnl for t in r_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
    print(f"  IS: n={is_stats['n']} WR={is_stats['wr']:.1%} avg={is_stats['avg']:+.0f} total={is_stats['total']:+.0f}")
    print(f"  OOS: n={oos_stats['n']} WR={oos_stats['wr']:.1%} avg={oos_stats['avg']:+.0f} total={oos_stats['total']:+.0f}")
    print(f"  OOS anchor (4/29, 5/1, 5/4): {anchor:+.0f}")

    print("\n[2] IS exit breakdown:")
    for k, v in exit_bd(r_is.trades).items():
        print(f"  {k:<35} n={v['n']:3} ({v['pct']:4.0%})")

    print("\nOOS exit breakdown:")
    for k, v in exit_bd(r_oos.trades).items():
        print(f"  {k:<35} n={v['n']:3} ({v['pct']:4.0%})")

    print("\n[3] Quality tier breakdown:")
    for split_label, trades in [("IS", r_is.trades), ("OOS", r_oos.trades)]:
        print(f"  {split_label}:")
        tier_map = defaultdict(list)
        for t in trades:
            tier_map[quality_tier(t)].append(t)
        for tier in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "BASE"]:
            ts = tier_map.get(tier, [])
            if ts:
                s = stats(ts)
                rf = sum(1 for t in ts if 'ribbon_flip' in (t.triggers_fired or []))
                print(f"    {tier:<12} n={s['n']:3} WR={s['wr']:4.0%} avg={s['avg']:+5.0f} total={s['total']:+7.0f} rf={rf}")

    print("\n[4] OOS loser dissection (premium stops):")
    oos_stops = [t for t in r_oos.trades if str(t.exit_reason).endswith("PREMIUM_STOP")]
    oos_wins  = [t for t in r_oos.trades if not str(t.exit_reason).endswith("PREMIUM_STOP")]
    print(f"  Premium stops: {len(oos_stops)}/{len(r_oos.trades)} ({len(oos_stops)/len(r_oos.trades):.0%})")
    print(f"  Non-stops: {len(oos_wins)}")

    tier_map_oos = defaultdict(list)
    for t in oos_stops:
        tier_map_oos[quality_tier(t)].append(t)
    print("  By tier:")
    for tier, ts in sorted(tier_map_oos.items()):
        pnls = [t.dollar_pnl for t in ts]
        print(f"    {tier:<12} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("  By side:")
    side_map = defaultdict(list)
    for t in oos_stops:
        side_map[t.side].append(t)
    for side, ts in sorted(side_map.items()):
        pnls = [t.dollar_pnl for t in ts]
        print(f"    {side:<4} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("  By VIX:")
    for label, vmin, vmax in [("<15",0,15),("15-18",15,18),("18-22",18,22),("22+",22,999)]:
        ts = [t for t in oos_stops if vmin <= t.entry_vix < vmax]
        if ts:
            pnls = [t.dollar_pnl for t in ts]
            print(f"    VIX {label:<6} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("\n  OOS stop trade log:")
    print(f"  {'date':<10} {'time':<6} {'side':<4} {'tier':<10} {'vix':<6} {'pnl':>7}  triggers")
    for t in sorted(oos_stops, key=lambda x: x.entry_time_et):
        trig = "+".join(sorted(t.triggers_fired or []))[:50]
        print(f"  {t.entry_time_et.date()} {t.entry_time_et.strftime('%H:%M')} {t.side:<4} "
              f"{quality_tier(t):<10} {t.entry_vix:<6.1f} {t.dollar_pnl:>+7.0f}  {trig}")

    print("\n[5] SAFE-specific research: block_elite_bull_vix_high 17.5->18.0")
    # With SAFE's bull_hard_cap=18.0 blocking ALL bulls at VIX>=18, the window
    # [17.5, 18.0) is the only gap. Check how many OOS trades are in that window.
    vix_gap = [t for t in r_oos.trades if 17.5 <= t.entry_vix < 18.0 and t.side == "C"]
    print(f"  OOS C trades in VIX [17.5,18.0): n={len(vix_gap)}")
    for t in vix_gap:
        print(f"    {t.entry_time_et.date()} vix={t.entry_vix:.2f} tier={quality_tier(t)} pnl={t.dollar_pnl:+.0f}")

    result = {
        "account": "SAFE",
        "params_date": "2026-06-17",
        "is_stats": is_stats,
        "oos_stats": oos_stats,
        "anchor": anchor,
        "is_exit_bd": exit_bd(r_is.trades),
        "oos_exit_bd": exit_bd(r_oos.trades),
        "oos_premium_stop_pct": round(len(oos_stops) / len(r_oos.trades), 3) if r_oos.trades else 0,
        "oos_stop_count": len(oos_stops),
        "oos_win_count": len(oos_wins),
        "vix_gap_17518": [
            {"date": str(t.entry_time_et.date()), "vix": round(t.entry_vix,2),
             "tier": quality_tier(t), "pnl": round(t.dollar_pnl,1)}
            for t in vix_gap
        ],
    }

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SAFE AUDIT COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
