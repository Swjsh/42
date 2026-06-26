"""OOS premium-stop loser dissection.

With block_elite_bull_vix_high=18.0, OOS baseline is n=28, +$6,032.
20/28 exits (71%) are premium stops averaging -$165 = -$3,300 total losses.
Goal: find a sub-pattern among those 20 losers that can be blocked with IS G1>=0.

Slice OOS losers by:
  - Setup type / quality tier
  - Entry time bucket
  - VIX at entry
  - Side (C/P)
  - triggers_fired composition

Security: read-only. No Alpaca calls.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "agg_oos_loser_dissect.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SW_SPLITS = [
    ("SW1_2025H1",  dt.date(2025,1,2),  dt.date(2025,6,30)),
    ("SW2_2025H2",  dt.date(2025,7,1),  dt.date(2025,12,31)),
    ("SW3_early26", dt.date(2026,1,2),  dt.date(2026,2,26)),
]

PROD_PARAMS = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.07, premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75, tp1_qty_fraction=0.667, runner_target_premium_pct=5.0,
    f9_vol_mult=0.7, min_triggers_bear=1, min_triggers_bull=1,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True, midday_trendline_gate=True,
    block_elite_bull=True, block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,
    require_bearish_fill_bar=True, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)

TIME_BUCKETS = [
    ("09:35-10:00", dt.time(9,35), dt.time(10,0)),
    ("10:00-11:30", dt.time(10,0), dt.time(11,30)),
    ("11:30-12:00", dt.time(11,30), dt.time(12,0)),
    ("12:00-14:00", dt.time(12,0), dt.time(14,0)),
    ("14:00-15:00", dt.time(14,0), dt.time(15,0)),
    ("15:00+",      dt.time(15,0), dt.time(16,0)),
]

VIX_BUCKETS = [
    ("<15",   0,    15),
    ("15-18", 15,   18),
    ("18-22", 18,   22),
    ("22-28", 22,   28),
    ("28+",   28,  999),
]


def quality_tier(t):
    trig = set(t.triggers_fired or [])
    if ('confluence' in trig and 'ribbon_flip' in trig) or len(trig) >= 3:
        return 'SUPER'
    elif 'confluence' in trig or 'sequence_rejection' in trig or 'sequence_reclaim' in trig:
        return 'ELITE'
    elif 'level_rejection' in trig or 'level_reclaim' in trig:
        return 'LEVEL'
    elif 'trendline_rejection' in trig:
        return 'TRENDLINE'
    return 'BASE'


def is_premium_stop(t):
    return str(t.exit_reason).endswith("PREMIUM_STOP")


def stats(trades):
    if not trades:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in trades]
    return {"n": len(trades), "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
            "avg": round(sum(pnls) / len(pnls), 1), "total": round(sum(pnls), 1)}


def fmt_trig(t):
    trig = sorted(t.triggers_fired or [])
    return "+".join(trig) if trig else "(none)"


def load_data():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    return spy_df, vix_df


def get_fill_days(spy_df):
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    return is_days, oos_days


def sw_delta(candidate_is_trades, base_is_pnl):
    """Count sub-windows hurt by candidates vs base."""
    hurt = 0
    for _name, sw_start, sw_end in SW_SPLITS:
        sw = [t for t in candidate_is_trades if sw_start <= t.entry_time_et.date() <= sw_end]
        sw_pnl = sum(t.dollar_pnl for t in sw)
        if sw_pnl < 0:
            hurt += 1
    return hurt


def try_block_pattern(spy_df, vix_df, is_days, oos_days, base_is, base_oos,
                      block_fn, label, extra_kw):
    """Run engine with extra_kw (a block param) and check OP-22 gates."""
    r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **extra_kw)
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **extra_kw)

    base_is_pnl  = sum(t.dollar_pnl for t in base_is)
    base_oos_pnl = sum(t.dollar_pnl for t in base_oos)
    base_anchor  = sum(t.dollar_pnl for t in base_oos if t.entry_time_et.date() in ANCHOR_WINNERS)

    is_d  = round(sum(t.dollar_pnl for t in r_is.trades)  - base_is_pnl,  1)
    oos_d = round(sum(t.dollar_pnl for t in r_oos.trades) - base_oos_pnl, 1)

    wf = None
    n_is = len(r_is.trades) or 1
    n_oos = len(r_oos.trades) or 1
    if is_d != 0:
        per_is  = is_d / n_is
        per_oos = oos_d / n_oos
        if per_is != 0:
            wf = round(per_oos / per_is, 3)

    sw_h = sw_delta(r_is.trades, base_is_pnl)
    curr_anchor = sum(t.dollar_pnl for t in r_oos.trades if t.entry_time_et.date() in ANCHOR_WINNERS)
    anchor_tol  = abs(base_anchor) * 0.10
    g5 = curr_anchor >= base_anchor - anchor_tol

    g1 = is_d >= 0
    g2 = oos_d > 0
    g3 = wf is not None and wf >= 0.70
    g4 = sw_h <= 1
    passed = g1 and g2 and g3 and g4 and g5

    return {
        "label":     label,
        "is_delta":  is_d,
        "oos_delta": oos_d,
        "wf_norm":   wf,
        "sw_hurt":   sw_h,
        "anchor_ok": g5,
        "gates":     {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "all": passed},
        "n_is":  len(r_is.trades),
        "n_oos": len(r_oos.trades),
    }


def main():
    print("=" * 70)
    print("OOS PREMIUM-STOP LOSER DISSECTION")
    print("=" * 70)

    spy_df, vix_df = load_data()
    is_days, oos_days = get_fill_days(spy_df)
    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")

    print("\n[1] Running production baseline...")
    base_r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **PROD_PARAMS)
    base_r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **PROD_PARAMS)
    base_is  = base_r_is.trades
    base_oos = base_r_oos.trades
    print(f"  IS: n={len(base_is)} total={sum(t.dollar_pnl for t in base_is):+.0f}")
    print(f"  OOS: n={len(base_oos)} total={sum(t.dollar_pnl for t in base_oos):+.0f}")

    # Identify premium-stop losers in OOS
    oos_stops = [t for t in base_oos if is_premium_stop(t)]
    oos_wins  = [t for t in base_oos if not is_premium_stop(t)]
    print(f"\n  OOS premium stops: {len(oos_stops)} | OOS wins: {len(oos_wins)}")

    print("\n[2] OOS loser profile:")
    print("\n  Tier breakdown:")
    tier_map = defaultdict(list)
    for t in oos_stops:
        tier_map[quality_tier(t)].append(t)
    for tier, ts in sorted(tier_map.items()):
        pnls = [t.dollar_pnl for t in ts]
        print(f"    {tier:<12} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("\n  Side breakdown:")
    side_map = defaultdict(list)
    for t in oos_stops:
        side_map[t.side].append(t)
    for side, ts in sorted(side_map.items()):
        pnls = [t.dollar_pnl for t in ts]
        print(f"    {side:<12} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("\n  Time bucket breakdown:")
    for label, t_start, t_end in TIME_BUCKETS:
        ts = [t for t in oos_stops
              if t_start <= t.entry_time_et.time() < t_end]
        if ts:
            pnls = [t.dollar_pnl for t in ts]
            print(f"    {label:<14} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("\n  VIX breakdown:")
    for label, vmin, vmax in VIX_BUCKETS:
        ts = [t for t in oos_stops
              if vmin <= t.entry_vix < vmax]
        if ts:
            pnls = [t.dollar_pnl for t in ts]
            print(f"    {label:<8} n={len(ts):2} avg={sum(pnls)/len(pnls):+.0f} total={sum(pnls):+.0f}")

    print("\n  Trigger composition (top 10 by n):")
    trig_map = defaultdict(list)
    for t in oos_stops:
        trig_map[fmt_trig(t)].append(t)
    for trig, ts in sorted(trig_map.items(), key=lambda x: -len(x[1]))[:10]:
        pnls = [t.dollar_pnl for t in ts]
        print(f"    [{len(ts):2}] {trig[:60]:<60} avg={sum(pnls)/len(pnls):+.0f}")

    print("\n[3] Trade-by-trade OOS loser log:")
    print(f"  {'date':<10} {'time':<6} {'side':<4} {'tier':<10} {'vix':<6} {'pnl':>7}  triggers")
    for t in sorted(oos_stops, key=lambda x: x.entry_time_et):
        d = t.entry_time_et.date()
        tm = t.entry_time_et.strftime("%H:%M")
        trig = fmt_trig(t)[:50]
        print(f"  {d} {tm} {t.side:<4} {quality_tier(t):<10} {t.entry_vix:<6.1f} {t.dollar_pnl:>+7.0f}  {trig}")

    # Identify high-concentration loser patterns
    print("\n[4] Candidate blocks to test:")
    candidates = []

    # Pattern A: C (bull) side all tiers — are OOS bull premium stops blockable?
    n_c_stops = len([t for t in oos_stops if t.side == "C"])
    n_p_stops = len([t for t in oos_stops if t.side == "P"])
    print(f"  C-side stops: {n_c_stops} | P-side stops: {n_p_stops}")

    # Pattern B: trendline-only (BASE tier, single trigger)
    tl_only_stops = [t for t in oos_stops if quality_tier(t) == "TRENDLINE"]
    print(f"  TRENDLINE-tier stops: {len(tl_only_stops)}")

    # Pattern C: BASE tier stops
    base_stops = [t for t in oos_stops if quality_tier(t) == "BASE"]
    print(f"  BASE-tier stops: {len(base_stops)}")

    # Pattern D: 11:30-14:00 P stops (midday bear)
    mid_p_stops = [t for t in oos_stops
                   if t.side == "P" and dt.time(11,30) <= t.entry_time_et.time() < dt.time(14,0)]
    print(f"  Midday (11:30-14:00) P stops: {len(mid_p_stops)}")

    # Pattern E: 11:30-14:00 TRENDLINE P
    mid_tl_p = [t for t in oos_stops
                if t.side == "P"
                and quality_tier(t) == "TRENDLINE"
                and dt.time(11,30) <= t.entry_time_et.time() < dt.time(14,0)]
    print(f"  Midday TRENDLINE P stops: {len(mid_tl_p)}")

    # Pattern F: VIX < 15 all stops
    low_vix_stops = [t for t in oos_stops if t.entry_vix < 15]
    print(f"  VIX<15 stops: {len(low_vix_stops)}")

    # Pattern G: LEVEL tier P stops (not blocked by block_level_rejection which only blocks LEVEL-tier bears)
    # Wait — block_level_rejection blocks LEVEL P. Let me check what's left.
    level_p_stops = [t for t in oos_stops if quality_tier(t) == "LEVEL" and t.side == "P"]
    level_c_stops = [t for t in oos_stops if quality_tier(t) == "LEVEL" and t.side == "C"]
    print(f"  LEVEL P stops (residual after block_level_rejection): {len(level_p_stops)}")
    print(f"  LEVEL C stops: {len(level_c_stops)}")

    # Now check IS profile of each pattern
    print("\n[5] IS mirror of identified patterns:")
    patterns = [
        ("TRENDLINE stops", oos_stops, [t for t in base_is if quality_tier(t)=="TRENDLINE" and is_premium_stop(t)]),
        ("BASE stops",      oos_stops, [t for t in base_is if quality_tier(t)=="BASE"      and is_premium_stop(t)]),
        ("C-side stops",    oos_stops, [t for t in base_is if t.side=="C"                  and is_premium_stop(t)]),
        ("P-side stops",    oos_stops, [t for t in base_is if t.side=="P"                  and is_premium_stop(t)]),
        ("VIX<15 stops",    oos_stops, [t for t in base_is if t.entry_vix<15               and is_premium_stop(t)]),
        ("mid P stops",     mid_p_stops, [t for t in base_is
                                          if t.side=="P"
                                          and dt.time(11,30) <= t.entry_time_et.time() < dt.time(14,0)
                                          and is_premium_stop(t)]),
    ]
    for label, oos_ts, is_ts in patterns:
        oos_pnl = sum(t.dollar_pnl for t in oos_ts) if oos_ts else 0
        is_pnl  = sum(t.dollar_pnl for t in is_ts)  if is_ts  else 0
        # Winners in IS from that bucket (unlocked if pattern blocked)
        print(f"  {label:<25} OOS n={len(oos_ts):2} {oos_pnl:+.0f} | IS n={len(is_ts):2} {is_pnl:+.0f}")

    # Check: is there a pattern where IS is near-zero or positive while OOS is negative?
    print("\n[6] VIX<15 P-side stops (low-VIX bearish losers):")
    low_vix_p = [t for t in oos_stops if t.entry_vix < 15 and t.side == "P"]
    for t in sorted(low_vix_p, key=lambda x: x.entry_time_et):
        print(f"  {t.entry_time_et.date()} {t.entry_time_et.strftime('%H:%M')} P vix={t.entry_vix:.1f} "
              f"pnl={t.dollar_pnl:+.0f} tier={quality_tier(t)} trig={fmt_trig(t)[:40]}")

    is_low_vix_p = [t for t in base_is if t.entry_vix < 15 and t.side == "P" and is_premium_stop(t)]
    is_low_vix_p_wins = [t for t in base_is if t.entry_vix < 15 and t.side == "P" and not is_premium_stop(t)]
    print(f"  IS mirror: stops n={len(is_low_vix_p)} total={sum(t.dollar_pnl for t in is_low_vix_p):+.0f}")
    print(f"  IS mirror: winners n={len(is_low_vix_p_wins)} total={sum(t.dollar_pnl for t in is_low_vix_p_wins):+.0f}")

    print("\n[7] VIX threshold for P-side entries — check: block P when VIX < X:")
    # Already have vix_bear_threshold = 15.0 in params. Are there residual VIX<15 P stops?
    very_low_vix_p = [t for t in oos_stops if t.entry_vix < 15 and t.side == "P"]
    print(f"  OOS P stops with VIX < 15.0: {len(very_low_vix_p)}")
    for t in very_low_vix_p:
        print(f"    {t.entry_time_et.date()} VIX={t.entry_vix:.2f} tier={quality_tier(t)}")

    print("\n[8] Summary of best blocking opportunity:")
    # Find the pattern with most negative OOS P&L that might have near-zero IS impact
    # The key: TRENDLINE tier is where most losses concentrate
    tl_oos = [t for t in oos_stops if quality_tier(t) == "TRENDLINE"]
    tl_is_stops = [t for t in base_is if quality_tier(t) == "TRENDLINE" and is_premium_stop(t)]
    tl_is_wins  = [t for t in base_is if quality_tier(t) == "TRENDLINE" and not is_premium_stop(t)]
    print(f"  TRENDLINE tier OOS stops: n={len(tl_oos)} total={sum(t.dollar_pnl for t in tl_oos):+.0f}")
    print(f"  TRENDLINE tier IS stops:  n={len(tl_is_stops)} total={sum(t.dollar_pnl for t in tl_is_stops):+.0f}")
    print(f"  TRENDLINE tier IS wins:   n={len(tl_is_wins)} total={sum(t.dollar_pnl for t in tl_is_wins):+.0f}")
    print(f"  → Blocking TRENDLINE IS net: {sum(t.dollar_pnl for t in tl_is_stops)+sum(t.dollar_pnl for t in tl_is_wins):+.0f}")

    result = {
        "oos_total": stats(base_oos),
        "oos_stops": stats(oos_stops),
        "oos_wins":  stats(oos_wins),
        "tier_breakdown": {
            tier: stats(ts) for tier, ts in sorted(tier_map.items())
        },
        "side_breakdown": {
            side: stats(ts) for side, ts in sorted(side_map.items())
        },
        "trade_log": [
            {
                "date": str(t.entry_time_et.date()),
                "time": t.entry_time_et.strftime("%H:%M"),
                "side": t.side,
                "tier": quality_tier(t),
                "vix": round(t.entry_vix, 2),
                "pnl": round(t.dollar_pnl, 1),
                "triggers": sorted(t.triggers_fired or []),
            }
            for t in sorted(oos_stops, key=lambda x: x.entry_time_et)
        ],
    }

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("LOSER DISSECTION COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
