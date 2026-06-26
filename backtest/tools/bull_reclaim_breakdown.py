"""BULLISH_RECLAIM_RIDE_THE_RIBBON breakdown (task 0c0aff49).

Perform Stage-1 backtest, break down performance by time-of-day and VIX buckets.
Find sub-segments with WR>30% and P&L > baseline.

NOTE: BULLISH_RECLAIM stays DRAFT per CLAUDE.md until J has 3 live wins on it.
This IS analysis only — no auto-ratify, no production param changes.
Results go to analysis/recommendations/bull_reclaim_breakdown.json.
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
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "bull_reclaim_breakdown.json"
IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}

# Bullish config from SAFE_BASE with bullish enabled and not blocking
BULL_BASE = dict(
    use_real_fills=True, strike_offset=-2,
    premium_stop_pct_bear=-0.10, premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5, f9_vol_mult=0.7,
    min_triggers_bear=1, min_triggers_bull=2,
    no_trade_before=dt.time(9, 35), no_trade_window=(dt.time(11, 30), dt.time(12, 0)),
    block_level_rejection=True, block_conf_lvl_rec_afternoon=True,
    midday_trendline_gate=True,
    # NOTE: NOT blocking elite bull here — we WANT to see bull trades
    block_elite_bull=False,
    time_stop_minutes_before_close=20, per_trade_risk_cap_pct=0.3, enable_bullish=True,
    params_overrides={"vix_bear_threshold": 17.3, "vix_bull_hard_cap": 18.0},
)


def naive(ts):
    return ts.replace(tzinfo=None) if ts.tzinfo else ts


def time_bucket(t) -> str:
    et = naive(t.entry_time_et)
    tod = et.hour * 60 + et.minute
    if tod < 10 * 60:
        return "09:35-10:00"
    elif tod < 11 * 60:
        return "10:00-11:00"
    elif tod < 12 * 60:
        return "11:00-12:00"
    elif tod < 13 * 60:
        return "12:00-13:00"
    elif tod < 14 * 60:
        return "13:00-14:00"
    elif tod < 15 * 60:
        return "14:00-15:00"
    return "15:00-15:55"


def vix_bucket(t) -> str:
    v = getattr(t, "entry_vix", None)
    if v is None:
        return "unknown"
    if v < 15:
        return "vix<15"
    elif v < 17:
        return "vix_15-17"
    elif v < 20:
        return "vix_17-20"
    elif v < 25:
        return "vix_20-25"
    return "vix_25+"


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
    print("BULLISH_RECLAIM_RIDE_THE_RIBBON BREAKDOWN (0c0aff49)")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)
    is_days = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]
    print(f"IS: {len(is_days)} days")

    print("\nRunning IS (block_elite_bull=False to see all bull trades)...")
    r_is = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **BULL_BASE)

    all_trades = r_is.trades
    bull_trades = [t for t in all_trades if getattr(t, "side", "").upper() in ("C", "CALL", "BULL")]
    bear_trades = [t for t in all_trades if getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")]

    print(f"\nAll IS trades: {len(all_trades)}")
    print(f"Bull (CALL) trades: {len(bull_trades)}")
    print(f"Bear (PUT) trades: {len(bear_trades)}")

    if not bull_trades:
        print("\nNO BULL TRADES FOUND — enable_bullish may not be generating BULLISH_RECLAIM setups")
        print("Checking setup names...")
        for t in all_trades[:5]:
            print(f"  setup={getattr(t, 'setup', 'N/A')} side={getattr(t, 'side', 'N/A')}")
        out = {"task": "0c0aff49-bull-reclaim-breakdown", "bull_trades": 0,
               "note": "No BULLISH_RECLAIM trades found in IS window",
               "verdict": "NO_SETUPS_FOUND"}
        OUT_PATH.parent.mkdir(exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        return

    bull_pnls = [t.dollar_pnl for t in bull_trades]
    print(f"\nBull overall: WR={sum(p>0 for p in bull_pnls)/len(bull_pnls):.1%} "
          f"avg={sum(bull_pnls)/len(bull_pnls):+.1f} total={sum(bull_pnls):+.0f}")

    print("\n--- BULL BY TIME OF DAY ---")
    tod_rows = bucket_report(bull_trades, time_bucket)
    for b in tod_rows:
        print(f"  {b['bucket']}: n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f} total={b['total']:+.0f}")

    print("\n--- BULL BY VIX ---")
    vix_rows = bucket_report(bull_trades, vix_bucket)
    for b in vix_rows:
        print(f"  {b['bucket']:15s}: n={b['n']:3d} WR={b['wr']:.1%} avg={b['avg']:+.1f} total={b['total']:+.0f}")

    print("\n--- BEAR (context) ---")
    bear_pnls = [t.dollar_pnl for t in bear_trades]
    if bear_pnls:
        print(f"  overall: n={len(bear_pnls)} WR={sum(p>0 for p in bear_pnls)/len(bear_pnls):.1%} "
              f"avg={sum(bear_pnls)/len(bear_pnls):+.1f} total={sum(bear_pnls):+.0f}")

    # Sub-segments WR > 30% and positive total
    good_segs = [(b, "time") for b in tod_rows if b.get("wr", 0) > 0.30 and b["total"] > 0 and b["n"] >= 5]
    good_segs += [(b, "vix") for b in vix_rows if b.get("wr", 0) > 0.30 and b["total"] > 0 and b["n"] >= 5]

    print(f"\n--- PROMISING SUB-SEGMENTS (WR>30%, total>0, n>=5) ---")
    if good_segs:
        for b, dim in sorted(good_segs, key=lambda x: -x[0]["wr"]):
            print(f"  [{dim}] {b['bucket']}: n={b['n']} WR={b['wr']:.1%} avg={b['avg']:+.1f}")
    else:
        print("  None — bull reclaim has poor WR across all sub-segments")

    out = {
        "task": "0c0aff49-bull-reclaim-breakdown",
        "bull_n": len(bull_trades),
        "bull_wr": round(sum(p > 0 for p in bull_pnls) / len(bull_pnls), 3),
        "bull_avg": round(sum(bull_pnls) / len(bull_pnls), 1),
        "bull_total": round(sum(bull_pnls), 1),
        "tod_breakdown": tod_rows,
        "vix_breakdown": vix_rows,
        "promising_segments": [{"bucket": b["bucket"], "dim": dim, "n": b["n"],
                                 "wr": b["wr"], "avg": b["avg"]} for b, dim in good_segs],
        "note": ("BULLISH_RECLAIM stays DRAFT per CLAUDE.md until J has 3 live wins. "
                 "This IS analysis is for sub-segment identification only."),
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
