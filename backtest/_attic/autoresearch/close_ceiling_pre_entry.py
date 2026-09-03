"""
CLOSE-CEILING PATTERN PRE-ENTRY ANALYSIS (2026-06-17)

L59: N≥3 consecutive bars with wick >= level AND close < level = distribution pattern.
"Before any level-break trade, run detect_close_ceiling on the prior 5-10 bars."

QUESTION: In the backtest, do trades with N≥3 close-ceiling pre-entry pattern produce
worse outcomes than trades without? If the pattern discriminates, a future gate may help.

METHOD: For each trade in Safe IS + OOS:
  1. Get rejection_level (the named level that triggered the trade)
  2. Look at the 10 bars IMMEDIATELY BEFORE entry_time_et in the 5-min SPY data
  3. Count consecutive bars where: high >= level AND close < level (wick-test without close-above)
  4. If max consecutive run >= N_MIN (3): flag as CLOSE_CEILING_DETECTED
  5. Group: ceiling vs no-ceiling; compare avg pnl, stop rate

NOTE: This is a BEAR-entry analysis (rejection_level = resistance for BEAR, support for BULL).
For BULL entries (side=="C"), close-ceiling = n bars with low <= level AND close > level.

Security: read-only, no Alpaca calls, no production writes.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

SAFE_KW = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)
SAFE_OVR = {"vix_bull_max": 18.0}

N_MIN = 3            # consecutive wick-tests needed to flag distribution
LOOKBACK_BARS = 10   # bars to check before entry


def _detect_close_ceiling_bear(bars_before, level, n_min=N_MIN):
    """BEAR: ceiling = resistance. Flag if N consecutive bars have high>=level AND close<level."""
    max_run = 0
    current = 0
    for _, row in bars_before.iterrows():
        if row["high"] >= level and row["close"] < level:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run >= n_min, max_run


def _detect_close_floor_bull(bars_before, level, n_min=N_MIN):
    """BULL: floor = support. Flag if N consecutive bars have low<=level AND close>level."""
    max_run = 0
    current = 0
    for _, row in bars_before.iterrows():
        if row["low"] <= level and row["close"] > level:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run >= n_min, max_run


def _exit_group(t):
    r = t.exit_reason.value if t.exit_reason else "UNKNOWN"
    if "RUNNER_TIME" in r or "RUNNER_RIBBON" in r or "RUNNER_TARGET" in r:
        return "TP1+runner"
    if "STOP" in r:
        return "STOP"
    return r


def _classify(t):
    trig = set(t.triggers_fired)
    has_conf = "confluence" in trig
    has_rec = "level_reclaim" in trig
    has_rej = "level_rejection" in trig
    if has_conf and has_rec:
        return "conf+lvl_rec"
    if has_conf and has_rej:
        return "conf+lvl_rej"
    if has_conf:
        return "conf_other"
    if has_rec:
        return "lvl_rec_only"
    if has_rej:
        return "lvl_rej_only"
    return "trendline/other"


def _analyze(trades, spy_df, label, n_min=N_MIN, lookback=LOOKBACK_BARS):
    """Compute close-ceiling pattern for each trade and compare outcomes."""
    # Build SPY 5-min time index for lookback — strip timezone so comparisons work
    spy_df = spy_df.copy()
    spy_df["ts"] = pd.to_datetime(spy_df["timestamp_et"]).apply(lambda x: x.replace(tzinfo=None))
    spy_df = spy_df.sort_values("ts").reset_index(drop=True)

    ceiling_trades = []
    no_ceiling_trades = []
    ceiling_runs = []

    for t in trades:
        level = t.rejection_level
        if not level:
            no_ceiling_trades.append(t)
            continue

        # Get entry time as timezone-naive
        entry_ts = t.entry_time_et
        if getattr(entry_ts, "tzinfo", None):
            entry_ts = entry_ts.replace(tzinfo=None)

        # Find bars before entry
        before = spy_df[spy_df["ts"] < entry_ts].tail(lookback)

        if len(before) < 2:
            no_ceiling_trades.append(t)
            continue

        if t.side == "P":  # bear entry: look for ceiling pattern at resistance
            detected, max_run = _detect_close_ceiling_bear(before, level, n_min)
        else:  # bull entry: look for floor pattern at support
            detected, max_run = _detect_close_floor_bull(before, level, n_min)

        ceiling_runs.append(max_run)
        if detected:
            ceiling_trades.append((t, max_run))
        else:
            no_ceiling_trades.append(t)

    print(f"\n{'='*72}")
    print(f"  {label}: n={len(trades)} | N_MIN={n_min} | lookback={lookback}")
    print(f"{'='*72}")

    def _stats(group, label_g):
        if not group:
            print(f"  {label_g}: n=0")
            return None
        pnl = sum(t.dollar_pnl for t in group)
        avg = pnl / len(group)
        stop_n = sum(1 for t in group if _exit_group(t) == "STOP")
        runner_n = sum(1 for t in group if _exit_group(t) == "TP1+runner")
        print(f"  {label_g}: n={len(group)} pnl={pnl:+,.0f} avg={avg:+.0f} stop%={100*stop_n/len(group):.1f}% runner%={100*runner_n/len(group):.1f}%")
        return {"n": len(group), "pnl": round(pnl, 2), "avg": round(avg, 2),
                "stop_rate": round(stop_n/len(group), 3), "runner_rate": round(runner_n/len(group), 3)}

    ceiling_only = [t for t, _ in ceiling_trades]
    ceiling_stats = _stats(ceiling_only, f"  close-ceiling DETECTED (run>={n_min})")
    no_ceiling_stats = _stats(no_ceiling_trades, f"  no close-ceiling")

    # Per-trigger-class breakdown for ceiling trades
    if ceiling_trades:
        print(f"\n  Ceiling-detected trades by trigger class:")
        by_cls = collections.defaultdict(list)
        for t, run in ceiling_trades:
            by_cls[_classify(t)].append((t, run))
        for cls in sorted(by_cls.keys(), key=lambda c: -sum(t.dollar_pnl for t, _ in by_cls[c])):
            items = by_cls[cls]
            pnl = sum(t.dollar_pnl for t, _ in items)
            avg_run = sum(r for _, r in items) / len(items)
            print(f"    {cls}: n={len(items)} avg=${pnl/len(items):.0f} avg_run={avg_run:.1f}")

    # Distribution of max_run values
    if ceiling_runs:
        from collections import Counter
        run_dist = Counter(min(r, 8) for r in ceiling_runs)
        print(f"\n  Max-run distribution (capped at 8): {dict(sorted(run_dist.items()))}")

    return {
        "n": len(trades),
        "ceiling_detected": ceiling_stats,
        "no_ceiling": {"n": len(no_ceiling_trades), **({} if not no_ceiling_trades else
                        {"pnl": round(sum(t.dollar_pnl for t in no_ceiling_trades), 2),
                         "avg": round(sum(t.dollar_pnl for t in no_ceiling_trades)/len(no_ceiling_trades), 2)})},
    }


if __name__ == "__main__":
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\nRunning Safe IS (verify: expect n=130)...")
    r_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                        params_overrides=dict(SAFE_OVR), **SAFE_KW)
    is_pnl = sum(t.dollar_pnl for t in r_is.trades)
    print(f"IS: n={len(r_is.trades)} pnl={is_pnl:+,.0f}")

    print("Running Safe OOS...")
    r_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                         params_overrides=dict(SAFE_OVR), **SAFE_KW)
    oos_pnl = sum(t.dollar_pnl for t in r_oos.trades)
    print(f"OOS: n={len(r_oos.trades)} pnl={oos_pnl:+,.0f}")

    is_result = _analyze(r_is.trades, spy_df, "IS (2025-01-02 to 2026-05-07)")
    oos_result = _analyze(r_oos.trades, spy_df, "OOS (2026-05-08 to 2026-06-16)")

    # Sweep N_MIN: does the pattern change with different thresholds?
    # Use tz-naive ts for N_MIN sweep comparison too
    spy_ts_naive = pd.to_datetime(spy_df["timestamp_et"]).apply(lambda x: x.replace(tzinfo=None))
    print(f"\n  === N_MIN SWEEP (IS only) ===")
    sweep_results = {}
    for n in [2, 3, 4, 5]:
        ceiling = [t for t in r_is.trades if t.side == "P" and t.rejection_level and _detect_close_ceiling_bear(
            spy_df[spy_ts_naive < (
                t.entry_time_et.replace(tzinfo=None) if getattr(t.entry_time_et, "tzinfo", None) else t.entry_time_et
            )].tail(LOOKBACK_BARS), t.rejection_level, n)[0]]
        no_c = [t for t in r_is.trades if t not in ceiling]
        pnl_c = sum(t.dollar_pnl for t in ceiling)
        pnl_no = sum(t.dollar_pnl for t in no_c)
        avg_c = f"{pnl_c/len(ceiling):.0f}" if ceiling else "n/a"
        avg_no = f"{pnl_no/len(no_c):.0f}" if no_c else "n/a"
        print(f"    N_MIN={n}: ceiling n={len(ceiling)} avg={avg_c} | no_ceiling n={len(no_c)} avg={avg_no}")
        sweep_results[n] = {"ceiling_n": len(ceiling), "ceiling_avg": round(pnl_c/len(ceiling), 2) if ceiling else 0}

    out = {
        "study": "close-ceiling pre-entry pattern analysis (L59)",
        "date": "2026-06-17",
        "n_min": N_MIN,
        "lookback_bars": LOOKBACK_BARS,
        "is": is_result,
        "oos": oos_result,
        "n_min_sweep": sweep_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "close_ceiling_pre_entry.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")
