"""SAFE BEARISH_REJECTION entry quality miner.

Post-hoc analysis: run IS baseline, then for each trade compute bar-level quality
metrics. Split WR and avg P&L by metric buckets to find discriminatory thresholds.

Metrics tested (per cook-queue task f4d9b0de):
  1. bearish_streak: # consecutive bearish (close<open) bars in 5 bars before entry
  2. prior_rejection: whether bar N-1 is a rejection bar (upper_wick >= 50% of range)
  3. vol_ratio: entry_bar_volume / 20-bar_avg_volume

If any metric gives WR >= 55% for top bucket vs overall 38.9%, propose as gate candidate.
Outputs gate candidates to analysis/recommendations/safe_entry_quality_gates.json
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
from lib.filters import _bar_geometry as bar_body_stats  # noqa
from sniper_matrix import norm_str         # noqa

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "safe_entry_quality_gates.json"
IS_CUTOFF = dt.date(2026, 2, 27)
MDATES    = {dt.date(2026,5,26), dt.date(2026,5,27), dt.date(2026,5,28), dt.date(2026,5,29)}
ANCHOR_WINNERS = {dt.date(2026,4,29), dt.date(2026,5,1), dt.date(2026,5,4)}

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


def _naive(ts):
    if hasattr(ts, "tzinfo") and ts.tzinfo:
        return ts.replace(tzinfo=None)
    return ts


def compute_bar_quality(trade, spy_df: pd.DataFrame) -> dict:
    """Compute quality metrics for a single trade's entry bar."""
    entry_dt = _naive(trade.entry_time_et)
    date_str = entry_dt.strftime("%Y-%m-%d")
    day_mask = spy_df["timestamp_et"].str[:10] == date_str
    day_bars = spy_df[day_mask].copy()
    day_bars = day_bars.sort_values("timestamp_et").reset_index(drop=True)

    entry_str = entry_dt.strftime("%Y-%m-%d %H:%M")
    # find index of entry bar (or nearest bar)
    match_mask = day_bars["timestamp_et"].str[:16] == entry_str
    matches = day_bars[match_mask]
    if matches.empty:
        return {}
    bar_idx = matches.index[0]
    if bar_idx < 5:
        return {}

    # compute 20-bar volume avg ending at bar_idx (excluding entry bar)
    vol_window = day_bars["volume"].iloc[max(0, bar_idx - 20): bar_idx]
    vol_avg = vol_window.mean() if len(vol_window) >= 5 else None
    entry_vol = float(day_bars["volume"].iloc[bar_idx])
    vol_ratio = round(entry_vol / vol_avg, 2) if vol_avg and vol_avg > 0 else None

    # bearish streak: count consecutive bearish bars ending AT bar_idx (including entry bar)
    streak = 0
    for i in range(bar_idx, max(bar_idx - 6, -1), -1):
        row = day_bars.iloc[i]
        if float(row["close"]) < float(row["open"]):
            streak += 1
        else:
            break

    # prior bar stats (bar N-1)
    prior_row = day_bars.iloc[bar_idx - 1]
    prior_stats = bar_body_stats(prior_row)
    prior_is_rejection = (
        prior_stats["is_red"]
        and prior_stats["upper_wick_pct"] >= 0.35  # bearish rejection: big upper wick
    )

    # entry bar stats
    entry_row = day_bars.iloc[bar_idx]
    entry_stats = bar_body_stats(entry_row)

    return {
        "bearish_streak": streak,
        "vol_ratio": vol_ratio,
        "prior_is_rejection": prior_is_rejection,
        "entry_body_pct": round(entry_stats.get("body_pct", 0), 3),
        "entry_upper_wick_pct": round(entry_stats.get("upper_wick_pct", 0), 3),
        "entry_is_red": entry_stats.get("is_red", False),
    }


def bucket_analysis(rows, metric_key, buckets):
    """Split a list of (metric_val, pnl) by bucket and report WR/avg/n."""
    result = []
    for label, lo, hi in buckets:
        subset = [(v, p) for v, p in rows if v is not None and lo <= v < hi]
        if not subset:
            result.append({"bucket": label, "n": 0, "wr": None, "avg": None, "total": None})
            continue
        pnls = [p for _, p in subset]
        result.append({
            "bucket": label,
            "lo": lo, "hi": hi,
            "n": len(pnls),
            "wr": round(sum(p > 0 for p in pnls) / len(pnls), 3),
            "avg": round(sum(pnls) / len(pnls), 1),
            "total": round(sum(pnls), 1),
        })
    return result


def main():
    print("=" * 70)
    print("SAFE ENTRY QUALITY MINER (f4d9b0de)")
    print("=" * 70)

    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    spy_df = norm_str(pd.read_csv(spy_path))
    vix_df = norm_str(pd.read_csv(vix_path))

    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    all_fill = sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})
    is_days = [d for d in all_fill if d < IS_CUTOFF and d not in MDATES]

    print(f"IS: {len(is_days)} days | Running baseline...")
    r_is = run_backtest(spy_df, vix_df, start_date=is_days[0], end_date=is_days[-1], **SAFE_BASE)
    bear_trades = [t for t in r_is.trades if getattr(t, "side", "").upper() in ("P", "PUT", "BEAR")]
    print(f"IS BEAR trades: {len(bear_trades)}")
    print(f"Overall WR: {sum(t.dollar_pnl > 0 for t in bear_trades) / len(bear_trades):.1%}")

    print("\nComputing per-trade quality metrics...")
    annotated = []
    for t in bear_trades:
        q = compute_bar_quality(t, spy_df)
        annotated.append({"trade": t, "q": q})
        if not q:
            print(f"  WARN: no bar data for {_naive(t.entry_time_et)}")

    valid = [(a["q"], a["trade"].dollar_pnl) for a in annotated if a["q"]]
    print(f"Annotated: {len(valid)} / {len(bear_trades)}")

    print("\n--- BEARISH_STREAK ---")
    streak_rows = [(q.get("bearish_streak"), pnl) for q, pnl in valid]
    streak_buckets = [
        ("streak_1", 1, 2),
        ("streak_2", 2, 3),
        ("streak_3+", 3, 99),
    ]
    streak_res = bucket_analysis(streak_rows, "bearish_streak", streak_buckets)
    for b in streak_res:
        print(f"  {b['bucket']}: n={b['n']} WR={b['wr']:.1%} avg={b['avg']:+.1f}" if b["n"] else f"  {b['bucket']}: n=0")

    print("\n--- VOLUME RATIO ---")
    vol_rows = [(q.get("vol_ratio"), pnl) for q, pnl in valid]
    vol_buckets = [
        ("vol<0.7", 0, 0.7),
        ("vol_0.7-1.0", 0.7, 1.0),
        ("vol_1.0-1.5", 1.0, 1.5),
        ("vol_1.5-2.0", 1.5, 2.0),
        ("vol_2.0+", 2.0, 99),
    ]
    vol_res = bucket_analysis(vol_rows, "vol_ratio", vol_buckets)
    for b in vol_res:
        print(f"  {b['bucket']}: n={b['n']} WR={b['wr']:.1%} avg={b['avg']:+.1f}" if b["n"] else f"  {b['bucket']}: n=0")

    print("\n--- PRIOR BAR REJECTION ---")
    prior_true  = [(1, pnl) for q, pnl in valid if q.get("prior_is_rejection")]
    prior_false = [(0, pnl) for q, pnl in valid if not q.get("prior_is_rejection")]
    for label, subset in [("prior_rejection=True", prior_true), ("prior_rejection=False", prior_false)]:
        if subset:
            pnls = [p for _, p in subset]
            print(f"  {label}: n={len(pnls)} WR={sum(p>0 for p in pnls)/len(pnls):.1%} "
                  f"avg={sum(pnls)/len(pnls):+.1f}")

    print("\n--- ENTRY BODY PCT (momentum strength) ---")
    body_rows = [(q.get("entry_body_pct"), pnl) for q, pnl in valid]
    body_buckets = [
        ("body<0.20", 0, 0.20),
        ("body_0.20-0.40", 0.20, 0.40),
        ("body_0.40-0.60", 0.40, 0.60),
        ("body_0.60+", 0.60, 1.01),
    ]
    body_res = bucket_analysis(body_rows, "entry_body_pct", body_buckets)
    for b in body_res:
        print(f"  {b['bucket']}: n={b['n']} WR={b['wr']:.1%} avg={b['avg']:+.1f}" if b["n"] else f"  {b['bucket']}: n=0")

    # Identify gate candidates (WR >= 55% and n >= 10)
    candidates = []
    for metric, buckets_res in [
        ("bearish_streak", streak_res), ("vol_ratio", vol_res), ("entry_body_pct", body_res)
    ]:
        for b in buckets_res:
            if b.get("wr") and b["wr"] >= 0.55 and b["n"] >= 10:
                candidates.append({"metric": metric, "bucket": b["bucket"],
                                   "n": b["n"], "wr": b["wr"], "avg": b["avg"]})

    # Prior rejection candidate
    if prior_true:
        pnls = [p for _, p in prior_true]
        wr = sum(p > 0 for p in pnls) / len(pnls)
        if wr >= 0.55 and len(pnls) >= 10:
            candidates.append({"metric": "prior_is_rejection", "bucket": "True",
                               "n": len(pnls), "wr": round(wr, 3), "avg": round(sum(pnls)/len(pnls), 1)})

    print("\n--- GATE CANDIDATES (WR >= 55%, n >= 10) ---")
    if candidates:
        for c in sorted(candidates, key=lambda x: -x["wr"]):
            print(f"  {c['metric']} [{c['bucket']}]: n={c['n']} WR={c['wr']:.1%} avg={c['avg']:+.1f}")
    else:
        print("  None found — no metric gives WR >= 55% with n >= 10")

    out = {
        "task": "f4d9b0de-entry-quality-miner",
        "is_days": len(is_days),
        "bear_trades_total": len(bear_trades),
        "annotated": len(valid),
        "overall_wr": round(sum(t.dollar_pnl > 0 for t in bear_trades) / len(bear_trades), 3),
        "bearish_streak": streak_res,
        "vol_ratio": vol_res,
        "entry_body_pct": body_res,
        "prior_rejection": {
            "True": {"n": len(prior_true), "wr": round(sum(p>0 for _,p in prior_true)/len(prior_true), 3) if prior_true else None},
            "False": {"n": len(prior_false), "wr": round(sum(p>0 for _,p in prior_false)/len(prior_false), 3) if prior_false else None},
        },
        "gate_candidates": candidates,
        "verdict": "GATE_CANDIDATES_FOUND" if candidates else "NO_GATE_CANDIDATES",
        "next_step": "For each gate candidate WR>=55%, n>=10: run IS/OOS A/B backtest via orchestrator gate parameter." if candidates else "No quality gate found in IS data. Baseline is well-calibrated on entry quality.",
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
