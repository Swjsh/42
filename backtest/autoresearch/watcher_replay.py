"""Watcher replay — runs all watchers over historical bars to populate observation history.

Use cases:
  1. Bootstrap: replay last 30 days of bars to build watcher observation baseline
  2. Sunday research: re-grade open observations now that future bars exist
  3. New watcher rollout: replay a new watcher over 60 days to validate it produces signal

Usage:
    pythonw.exe -m autoresearch.watcher_replay --start 2026-04-01 --end 2026-05-09
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))  # needed for crypto.lib.chart_patterns (HS/DB/FBW/momentum_accel watchers)

from autoresearch import runner as ar_runner
from lib.filters import BarContext, vol_baseline_20bar, range_baseline_20bar, LevelState
from lib.ribbon import compute_ribbon
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import run_all_watchers, log_observation, grade_observation, OBS_LOG, SUMMARY


def replay_window(start: dt.date, end: dt.date) -> dict:
    spy_full, vix_full = ar_runner.load_data(start, end)
    import pandas as pd
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    level_states = {}
    ribbon_history = []
    last_seen_date = None

    n_signals = 0
    counter = Counter()

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if start is not None and bar_date < start:
            continue
        if end is not None and bar_date > end:
            continue

        if last_seen_date is not None and bar_date != last_seen_date:
            ribbon_history = []
            level_states = {}
        last_seen_date = bar_date

        # Need ribbon warmup
        if idx < 60:
            continue

        ribbon_state = None
        try:
            r = ribbon_df.iloc[idx]
            from lib.ribbon import RibbonState
            ribbon_state = RibbonState(
                fast=float(r["fast"]),
                pivot=float(r["pivot"]),
                slow=float(r["slow"]),
                stack=str(r["stack"]),
                spread_cents=float(r["spread_cents"]),
            )
        except Exception:
            continue

        ribbon_history.append(ribbon_state)
        if len(ribbon_history) > 10:
            ribbon_history = ribbon_history[-10:]

        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        # 2026-05-16 L40 fix: 3-bar VIX lookback (15-min trend) to match watcher_live.py
        _vix_prior_idx = max(0, idx - 3)
        vix_prior = float(vix_aligned.iloc[_vix_prior_idx]) if _vix_prior_idx < len(vix_aligned) else vix_now

        full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
        level_set = _detect_from_history(full_history, bar_date)
        _update_level_states(level_states, level_set.active, bar, idx)
        htf_stack = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time.to_pydatetime(),
            bar=bar,
            prior_bars=rth.iloc[:idx + 1],  # slice up to current bar — pattern detectors use .tail()
            ribbon_now=ribbon_state,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline,
            levels_active=level_set.active,
            multi_day_levels=level_set.multi_day,
            htf_15m_stack=htf_stack,
            level_states=level_states,
        )

        # Build day_bars (today only) for ORB + PIN-FADE
        day_bars = rth[rth["timestamp_et"].dt.date == bar_date].reset_index(drop=True)
        bar_idx_in_day = (day_bars["timestamp_et"] == bar_time).idxmax() if not day_bars.empty else 0

        signals = run_all_watchers(bar, day_bars, bar_idx_in_day, vol_baseline, ctx, vix_now)
        for s in signals:
            log_observation(s, bar_time)
            counter[(s.watcher_name, s.confidence)] += 1
            n_signals += 1

    summary = {
        "replay_window": f"{start} to {end}",
        "completed_at": dt.datetime.now().isoformat(),
        "total_signals": n_signals,
        "by_watcher_confidence": {f"{w}__{c}": n for (w, c), n in counter.items()},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default=None,
                        help="Start date YYYY-MM-DD (default: 30 days ago)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if args.start:
        start = dt.date.fromisoformat(args.start)
    else:
        start = dt.date.today() - dt.timedelta(days=30)
    if args.end:
        end = dt.date.fromisoformat(args.end)
    else:
        end = dt.date.today()

    print(f"Replaying watchers {start} to {end}...")
    summary = replay_window(start, end)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
