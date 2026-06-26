"""SAFE account OOS loser dissection.

Mirrors agg_oos_loser_dissect.py for the SAFE account.
Goal: find any blockable sub-pattern where IS delta >= 0 AND OOS delta > 0.

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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_oos_loser_dissect.json"

IS_CUTOFF  = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

SAFE_PARAMS = dict(
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


def quality_tier(t):
    trig = set(t.triggers_fired or [])
    if ("confluence" in trig and "ribbon_flip" in trig) or len(trig) >= 3:
        return "SUPER"
    elif "confluence" in trig or "sequence_rejection" in trig or "sequence_reclaim" in trig:
        return "ELITE"
    elif "level_rejection" in trig or "level_reclaim" in trig:
        return "LEVEL"
    elif "trendline_rejection" in trig:
        return "TRENDLINE"
    return "BASE"


def is_pstop(t):
    return str(t.exit_reason).endswith("PREMIUM_STOP")


def stats(ts):
    if not ts:
        return {"n": 0, "wr": 0.0, "avg": 0.0, "total": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {
        "n": len(ts),
        "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
        "avg": round(sum(pnls) / len(ts), 1),
        "total": round(sum(pnls), 1),
    }


def try_block(label, pred, oos_stops, is_all):
    blocked_oos = [t for t in oos_stops if pred(t)]
    blocked_is  = [t for t in is_all if pred(t)]
    if not blocked_oos:
        return None
    oos_d = -sum(t.dollar_pnl for t in blocked_oos)
    is_d  = -sum(t.dollar_pnl for t in blocked_is)
    g1 = is_d >= 0
    g2 = oos_d > 0
    return {
        "label": label,
        "oos_stops_blocked": len(blocked_oos),
        "oos_delta": round(oos_d, 1),
        "is_stops_blocked": len(blocked_is),
        "is_delta": round(is_d, 1),
        "G1": g1, "G2": g2, "both": g1 and g2,
    }


def main():
    print("=" * 70)
    print("SAFE OOS LOSER DISSECTION")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days  = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES_SET]
    oos_days = [d for d in all_fill if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]

    print(f"IS: {len(is_days)} days | OOS: {len(oos_days)} days")
    print("Running SAFE baseline...")

    r_is  = run_backtest(spy_df, vix_df, start_date=is_days[0],  end_date=is_days[-1],  **SAFE_PARAMS)
    r_oos = run_backtest(spy_df, vix_df, start_date=oos_days[0], end_date=oos_days[-1], **SAFE_PARAMS)

    oos_stops = [t for t in r_oos.trades if is_pstop(t)]
    oos_wins  = [t for t in r_oos.trades if not is_pstop(t)]
    is_stops  = [t for t in r_is.trades  if is_pstop(t)]

    print(f"\nTotal OOS: {len(r_oos.trades)} | Premium stops: {len(oos_stops)} ({len(oos_stops)/len(r_oos.trades):.0%}) | Non-stops: {len(oos_wins)}")
    print()

    print("--- Full stop log ---")
    print(f"{'date':<10} {'T':<5} {'side':<4} {'tier':<10} {'vix':<6} {'pnl':>7}  triggers")
    for t in sorted(oos_stops, key=lambda x: x.entry_time_et):
        trig = "+".join(sorted(t.triggers_fired or []))[:60]
        print(f"{str(t.entry_time_et.date()):<10} {t.entry_time_et.strftime('%H:%M'):<5} "
              f"{t.side:<4} {quality_tier(t):<10} {t.entry_vix:<6.1f} {t.dollar_pnl:>+7.0f}  {trig}")
    print()

    print("--- By tier ---")
    tier_map = defaultdict(list)
    for t in oos_stops:
        tier_map[quality_tier(t)].append(t)
    for tier in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "BASE"]:
        ts = tier_map.get(tier, [])
        if ts:
            s  = stats(ts)
            is_ts = [t for t in is_stops if quality_tier(t) == tier]
            si = stats(is_ts)
            print(f"  {tier:<10} OOS n={s['n']:2} avg={s['avg']:+.0f} total={s['total']:+.0f} | "
                  f"IS n={si['n']:2} avg={si['avg']:+.0f} total={si['total']:+.0f}")
    print()

    print("--- By side ---")
    for side in ["P", "C"]:
        ts = [t for t in oos_stops if t.side == side]
        if ts:
            is_ts = [t for t in is_stops if t.side == side]
            s = stats(ts); si = stats(is_ts)
            print(f"  {side}: OOS n={s['n']:2} avg={s['avg']:+.0f} | IS n={si['n']:2} avg={si['avg']:+.0f} total={si['total']:+.0f}")
    print()

    print("--- By VIX bucket ---")
    for label, vlo, vhi in [("<15", 0, 15), ("[15-17.3)", 15, 17.3), ("[17.3-18)", 17.3, 18), ("[18-22)", 18, 22), ("[22+)", 22, 999)]:
        ts = [t for t in oos_stops if vlo <= t.entry_vix < vhi]
        if ts:
            is_ts = [t for t in is_stops if vlo <= t.entry_vix < vhi]
            s = stats(ts); si = stats(is_ts)
            print(f"  VIX {label:<10} OOS n={s['n']:2} avg={s['avg']:+.0f} | IS n={si['n']:2} avg={si['avg']:+.0f} total={si['total']:+.0f}")
    print()

    print("--- By time bucket ---")
    def hour_frac(t):
        return t.entry_time_et.hour + t.entry_time_et.minute / 60
    for label, h0, h1 in [("09:35-10:00", 9.58, 10), ("10:00-11:00", 10, 11), ("11:00-12:00", 11, 12),
                            ("12:00-14:00", 12, 14), ("14:00+", 14, 16)]:
        ts = [t for t in oos_stops if h0 <= hour_frac(t) < h1]
        if ts:
            is_ts = [t for t in is_stops if h0 <= hour_frac(t) < h1]
            s = stats(ts); si = stats(is_ts)
            print(f"  {label:<15} OOS n={s['n']:2} avg={s['avg']:+.0f} | IS n={si['n']:2} avg={si['avg']:+.0f} total={si['total']:+.0f}")
    print()

    print("--- Pattern block attempts (G1=IS_delta>=0, G2=OOS_delta>0) ---")
    patterns = [
        ("ALL premium stops",       lambda t: True),
        ("LEVEL tier stops",        lambda t: quality_tier(t) == "LEVEL"),
        ("TRENDLINE tier stops",    lambda t: quality_tier(t) == "TRENDLINE"),
        ("BASE tier stops",         lambda t: quality_tier(t) == "BASE"),
        ("ELITE tier stops",        lambda t: quality_tier(t) == "ELITE"),
        ("Bear (P) stops only",     lambda t: t.side == "P"),
        ("Bull (C) stops only",     lambda t: t.side == "C"),
        ("VIX < 15 stops",          lambda t: t.entry_vix < 15.0),
        ("VIX < 17.3 stops",        lambda t: t.entry_vix < 17.3),
        ("VIX >= 17.3 stops",       lambda t: t.entry_vix >= 17.3),
        ("LEVEL P stops",           lambda t: quality_tier(t) == "LEVEL" and t.side == "P"),
        ("LEVEL C stops",           lambda t: quality_tier(t) == "LEVEL" and t.side == "C"),
        ("BASE P stops",            lambda t: quality_tier(t) == "BASE" and t.side == "P"),
        ("TRENDLINE P stops",       lambda t: quality_tier(t) == "TRENDLINE" and t.side == "P"),
        ("Stops before 10:00",      lambda t: hour_frac(t) < 10),
        ("Stops after 14:00",       lambda t: hour_frac(t) >= 14),
        ("Stops 10:00-11:00",       lambda t: 10 <= hour_frac(t) < 11),
        ("LEVEL VIX < 15",          lambda t: quality_tier(t) == "LEVEL" and t.entry_vix < 15),
        ("LEVEL VIX >= 17.3",       lambda t: quality_tier(t) == "LEVEL" and t.entry_vix >= 17.3),
        ("TRENDLINE VIX < 17.3",    lambda t: quality_tier(t) == "TRENDLINE" and t.entry_vix < 17.3),
        ("BASE VIX < 15",           lambda t: quality_tier(t) == "BASE" and t.entry_vix < 15),
    ]

    block_results = []
    best_g2_only = None
    for label, pred in patterns:
        r = try_block(label, pred, oos_stops, r_is.trades)
        if r is None:
            continue
        flag = "** BOTH PASS **" if r["both"] else ""
        print(f"  {label:<35} OOS_D={r['oos_delta']:>+7.0f} IS_D={r['is_delta']:>+7.0f}  G1={'Y' if r['G1'] else 'N'} G2={'Y' if r['G2'] else 'N'} {flag}")
        block_results.append(r)
        if r["G2"] and (best_g2_only is None or r["oos_delta"] > best_g2_only["oos_delta"]):
            best_g2_only = r

    print()
    print("--- Winner log (non-stops) ---")
    def sort_key(t):
        ts = t.entry_time_et
        if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts
    for t in sorted(oos_wins, key=sort_key):
        trig = "+".join(sorted(t.triggers_fired or []))[:50]
        print(f"  {str(t.entry_time_et.date()):<10} {t.entry_time_et.strftime('%H:%M'):<5} "
              f"{t.side:<4} {quality_tier(t):<10} {t.entry_vix:<6.1f} {t.dollar_pnl:>+7.0f}  "
              f"{str(t.exit_reason).split('.')[-1]:<30}  {trig}")
    print()

    passing = [r for r in block_results if r["both"]]
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    if passing:
        best = max(passing, key=lambda r: r["oos_delta"])
        print(f"  CANDIDATE FOUND: {best['label']}")
        print(f"  OOS_delta={best['oos_delta']:+.0f}  IS_delta={best['is_delta']:+.0f}")
        print("  --> Full OP-22 gates require WF and SW checks — run dedicated sweep to confirm.")
    else:
        print("  REJECT - no sub-pattern passes both G1 (IS_delta>=0) AND G2 (OOS_delta>0).")
        if best_g2_only:
            print(f"  Best OOS-only: {best_g2_only['label']} OOS_D={best_g2_only['oos_delta']:+.0f} IS_D={best_g2_only['is_delta']:+.0f}")

    out = {
        "account": "SAFE",
        "run_date": "2026-06-18",
        "oos_total": len(r_oos.trades),
        "oos_stops": len(oos_stops),
        "oos_wins": len(oos_wins),
        "stop_pct": round(len(oos_stops) / len(r_oos.trades), 3),
        "block_attempts": block_results,
        "passing": passing,
        "verdict": "CANDIDATE" if passing else "REJECT",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")
    print("SAFE OOS LOSER DISSECTION COMPLETE.")


if __name__ == "__main__":
    raise SystemExit(main())
