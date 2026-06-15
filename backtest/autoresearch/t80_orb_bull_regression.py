"""T80 — ORB + BULL fire-rate regression diagnostic.

Hypothesis (from T48 follow-up doc):
  - 4/23 -> 5/07: ORB fired 6/day, BULL fired 1-6/day, V14E 2-5/day
  - 5/08 -> 5/12: ORB 0/day, BULL 0/day, V14E 2/day
  - 5/13 -> 5/14: ALL ZERO

This script BYPASSES the medium-confidence filter at runner.py L98+L104 and
captures EVERY raw detect_orb_break / detect_bullish_setup return value across
5/13 + 5/14 RTH bars. If the watchers return LOW or HIGH consistently, the
filter is too strict for the current regime. If they return None, the
detectors broke.

Production-safe: reads files only, calls detect functions directly, does NOT
modify runner.py or watcher_live.py.

Output:
    docs/T80-ORB-BULL-REGRESSION.md
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

from lib.ribbon import compute_ribbon, RibbonState
from lib.levels import _detect_from_history
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext
from lib.watchers.orb_watcher import detect_orb_break, _orb_state
from lib.watchers.bullish_watcher import detect_bullish_setup


def main():
    master_csv = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-12.csv"
    today_csv = REPO / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-14.csv"
    m = pd.read_csv(master_csv)
    m["timestamp_et"] = pd.to_datetime(m["timestamp_et"])
    if m["timestamp_et"].dt.tz is not None:
        m["timestamp_et"] = m["timestamp_et"].dt.tz_localize(None)
    t = pd.read_csv(today_csv)
    t["timestamp_et"] = pd.to_datetime(t["timestamp_et"])
    if t["timestamp_et"].dt.tz is not None:
        t["timestamp_et"] = t["timestamp_et"].dt.tz_localize(None)
    full = pd.concat([m, t], ignore_index=True).drop_duplicates(
        subset=["timestamp_et"], keep="last"
    ).sort_values("timestamp_et").reset_index(drop=True)
    full["date"] = full["timestamp_et"].dt.date
    rth = full[
        (full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    rth = rth[rth["volume"] > 0].reset_index(drop=True)

    # Pre-compute ribbon over full rth
    ribbon_df = compute_ribbon(rth["close"])

    # Test dates: include 5/05 (working day, baseline) + 5/08 (regression
    # boundary) + 5/13 + 5/14 (silent days)
    test_dates = [
        dt.date(2026, 5, 5),
        dt.date(2026, 5, 7),
        dt.date(2026, 5, 8),
        dt.date(2026, 5, 12),
        dt.date(2026, 5, 13),
        dt.date(2026, 5, 14),
    ]

    print(f"Loaded {len(rth):,} RTH bars across history")
    print(f"Testing {len(test_dates)} dates: {[str(d) for d in test_dates]}")
    print()

    results: dict = {}

    for test_date in test_dates:
        # Per-day reset of ORB state (matches production behavior — runner
        # builds new state per date_str)
        for k in list(_orb_state.keys()):
            del _orb_state[k]

        day_bars = rth[rth["timestamp_et"].dt.date == test_date].reset_index(drop=True)
        if day_bars.empty:
            results[str(test_date)] = {"error": "no bars"}
            print(f"=== {test_date}: no bars ===")
            continue

        orb_returns = []
        bull_returns = []

        for bar_idx_in_day in range(len(day_bars)):
            bar = day_bars.iloc[bar_idx_in_day]
            # Find this bar's idx in full rth (for ribbon + vol baseline + levels)
            full_ix = rth.index[rth["timestamp_et"] == bar["timestamp_et"]]
            if len(full_ix) == 0:
                continue
            full_idx = int(full_ix[0])

            # Build context for bullish_watcher (needs full BarContext)
            r = ribbon_df.iloc[full_idx]
            ribbon_state = RibbonState(
                fast=float(r["fast"]),
                pivot=float(r["pivot"]),
                slow=float(r["slow"]),
                stack=str(r["stack"]),
                spread_cents=float(r["spread_cents"]),
            )
            ribbon_history = []
            for i in range(max(0, full_idx - 5), full_idx + 1):
                rh = ribbon_df.iloc[i]
                ribbon_history.append(
                    RibbonState(
                        fast=float(rh["fast"]),
                        pivot=float(rh["pivot"]),
                        slow=float(rh["slow"]),
                        stack=str(rh["stack"]),
                        spread_cents=float(rh["spread_cents"]),
                    )
                )
            vol_baseline = vol_baseline_20bar(rth, full_idx)
            full_hist = full[full["timestamp_et"] <= bar["timestamp_et"]]
            level_set = _detect_from_history(full_hist, test_date)

            ctx = BarContext(
                bar_idx=full_idx,
                timestamp_et=bar["timestamp_et"].to_pydatetime(),
                bar=bar,
                prior_bars=rth,
                ribbon_now=ribbon_state,
                ribbon_history=ribbon_history,
                vix_now=17.8,
                vix_prior=17.9,
                vol_baseline_20=vol_baseline,
                range_baseline_20=range_baseline_20bar(rth, full_idx),
                levels_active=level_set.active,
                multi_day_levels=level_set.multi_day,
                htf_15m_stack=None,
                level_states={},
            )

            # Call ORB
            try:
                orb_sig = detect_orb_break(bar, day_bars, bar_idx_in_day, vol_baseline)
                if orb_sig is not None:
                    orb_returns.append({
                        "time": bar["timestamp_et"].strftime("%H:%M"),
                        "confidence": orb_sig.confidence,
                        "setup": orb_sig.setup_name,
                        "direction": orb_sig.direction,
                        "reason": orb_sig.reason[:120],
                    })
            except Exception as e:
                orb_returns.append({
                    "time": bar["timestamp_et"].strftime("%H:%M"),
                    "error": f"{type(e).__name__}: {e}",
                })

            # Call BULL
            try:
                bull_sig = detect_bullish_setup(ctx)
                if bull_sig is not None:
                    bull_returns.append({
                        "time": bar["timestamp_et"].strftime("%H:%M"),
                        "confidence": bull_sig.confidence,
                        "setup": bull_sig.setup_name,
                        "direction": bull_sig.direction,
                        "reason": bull_sig.reason[:120],
                    })
            except Exception as e:
                bull_returns.append({
                    "time": bar["timestamp_et"].strftime("%H:%M"),
                    "error": f"{type(e).__name__}: {e}",
                })

        orb_conf_count = Counter(r.get("confidence", "ERROR") for r in orb_returns)
        bull_conf_count = Counter(r.get("confidence", "ERROR") for r in bull_returns)

        results[str(test_date)] = {
            "n_bars": len(day_bars),
            "orb_total": len(orb_returns),
            "orb_by_confidence": dict(orb_conf_count),
            "orb_samples": orb_returns[:5],
            "bull_total": len(bull_returns),
            "bull_by_confidence": dict(bull_conf_count),
            "bull_samples": bull_returns[:5],
        }

        print(f"=== {test_date} ({len(day_bars)} bars) ===")
        print(f"  ORB: total={len(orb_returns)} by_conf={dict(orb_conf_count)}")
        if orb_returns:
            for r in orb_returns[:3]:
                if "confidence" in r:
                    print(f"    {r['time']}: {r['confidence']} {r['setup']} {r['direction']}: {r['reason'][:80]}")
                else:
                    print(f"    {r['time']}: ERROR {r.get('error', '?')}")
        print(f"  BULL: total={len(bull_returns)} by_conf={dict(bull_conf_count)}")
        if bull_returns:
            for r in bull_returns[:3]:
                if "confidence" in r:
                    print(f"    {r['time']}: {r['confidence']} {r['setup']} {r['direction']}: {r['reason'][:80]}")
                else:
                    print(f"    {r['time']}: ERROR {r.get('error', '?')}")
        print()

    # Save raw results JSON
    out_json = REPO / "automation" / "state" / "t80-orb-bull-diag.json"
    out_json.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
