"""Backfill replay for 4 watchers added 2026-05-20 that were not in the prior full replay.

Writes to a SEPARATE file (watcher-replay-backfill-2026-05-20.jsonl) to avoid
contaminating watcher-observations.jsonl with duplicates of already-replayed watchers.

Target watchers (all have 0 observations in the main log as of 2026-05-20):
  - HEAD_AND_SHOULDERS_BEAR      (hs_watcher.py)
  - DOUBLE_BOTTOM_BASE_QUIET     (double_bottom_base_quiet_watcher.py)
  - DOUBLE_BOTTOM_MORNING_LOW_VOL(double_bottom_morning_low_vol_watcher.py)
  - MOMENTUM_ACCELERATION_HIGHVOL(momentum_acceleration_highvol_watcher.py)

Also captures hs_near_named_level_watcher which was added at the same time.

Usage:
    python backtest/autoresearch/watcher_replay_new_watchers.py --start 2025-01-01 --end 2026-05-15
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))  # needed for crypto.lib.chart_patterns (HS/DB/FBW/momentum_accel watchers)

# ── Redirect OBS_LOG + SUMMARY before any other imports ──────────────────────
import lib.watchers.runner as _watcher_runner

_BACKFILL_LOG = ROOT / "automation" / "state" / "watcher-replay-backfill-2026-05-20.jsonl"
_BACKFILL_SUMMARY = ROOT / "automation" / "state" / "watcher-replay-backfill-2026-05-20-summary.json"

_watcher_runner.OBS_LOG = _BACKFILL_LOG
_watcher_runner.SUMMARY = _BACKFILL_SUMMARY

# Clear the backfill log on each run (fresh start)
_BACKFILL_LOG.parent.mkdir(parents=True, exist_ok=True)
_BACKFILL_LOG.write_text("", encoding="utf-8")

# ── Now import the replay infrastructure ────────────────────────────────────
from autoresearch import runner as ar_runner
from lib.filters import BarContext, vol_baseline_20bar, range_baseline_20bar
from lib.ribbon import compute_ribbon
from lib.levels import _detect_from_history
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks, _update_level_states
from lib.watchers.runner import run_all_watchers, log_observation

# ── Only collect signals for the NEW watchers ────────────────────────────────
_NEW_WATCHER_SETUP_NAMES = frozenset({
    "HEAD_AND_SHOULDERS_BEAR",
    "DOUBLE_BOTTOM_BASE_QUIET",
    "DOUBLE_BOTTOM_MORNING_LOW_VOL",
    "MOMENTUM_ACCELERATION_HIGHVOL",
    "HEAD_AND_SHOULDERS_NEAR_NAMED",  # hs_near_named_level_watcher
    "FAILED_BREAKDOWN_WICK_MORNING_MID",  # fbw_morning_mid_watcher added 2026-05-20
})


def replay_new_watchers(start: dt.date, end: dt.date, skip_levels: bool = False) -> dict:
    """skip_levels=True skips _detect_from_history per-bar (O(n²) call). Safe because none of the
    target watchers (FBW, HS_BEAR, DB_BASE_QUIET, DB_MORNING, MOMENTUM_ACCEL) use ctx.levels_active.
    HS_NEAR_NAMED does use levels but is WATCH_FRAGILE — will get 0 signals with skip_levels=True."""
    print(f"[watcher_replay_new_watchers] Loading data {start} to {end}... (skip_levels={skip_levels})")
    spy_full, vix_full = ar_runner.load_data(start, end)
    import pandas as pd
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    print(f"  RTH bars: {len(rth)}")

    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    level_states = {}
    ribbon_history = []
    last_seen_date = None

    n_signals = 0
    counter: Counter = Counter()
    days_processed = 0
    last_reported_date = None

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
            days_processed += 1
            if days_processed % 50 == 0:
                print(f"  ...processed {days_processed} days, {n_signals} new signals so far")

        last_seen_date = bar_date

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
        _vix_prior_idx = max(0, idx - 3)
        vix_prior = float(vix_aligned.iloc[_vix_prior_idx]) if _vix_prior_idx < len(vix_aligned) else vix_now

        if skip_levels:
            # Skip O(n²) level detection — FBW/HS_BEAR/DB/MOMENTUM don't use levels_active.
            # HS_NEAR_NAMED will get 0 signals (it requires ctx.levels_active).
            levels_active_list: list = []
            multi_day_levels_list: list = []
        else:
            full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
            level_set = _detect_from_history(full_history, bar_date)
            _update_level_states(level_states, level_set.active, bar, idx)
            levels_active_list = level_set.active
            multi_day_levels_list = level_set.multi_day
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
            levels_active=levels_active_list,
            multi_day_levels=multi_day_levels_list,
            htf_15m_stack=htf_stack,
            level_states=level_states,
        )

        day_bars = rth[rth["timestamp_et"].dt.date == bar_date].reset_index(drop=True)
        bar_idx_in_day = (day_bars["timestamp_et"] == bar_time).idxmax() if not day_bars.empty else 0

        all_signals = run_all_watchers(bar, day_bars, bar_idx_in_day, vol_baseline, ctx, vix_now)

        for s in all_signals:
            if s.setup_name not in _NEW_WATCHER_SETUP_NAMES:
                continue
            log_observation(s, bar_time)
            counter[(s.watcher_name, s.setup_name, s.confidence)] += 1
            n_signals += 1

    summary = {
        "target_watchers": sorted(_NEW_WATCHER_SETUP_NAMES),
        "replay_window": f"{start} to {end}",
        "completed_at": dt.datetime.now().isoformat(),
        "total_signals": n_signals,
        "days_processed": days_processed,
        "by_watcher_setup_confidence": {
            f"{w}_{s}__{c}": n for (w, s, c), n in sorted(counter.items())
        },
        "by_setup": {
            sname: sum(n for (_, s, _), n in counter.items() if s == sname)
            for sname in _NEW_WATCHER_SETUP_NAMES
        },
        "output_file": str(_BACKFILL_LOG),
    }
    _BACKFILL_SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=str, default="2025-01-01")
    parser.add_argument("--end",   type=str, default="2026-05-15")
    parser.add_argument("--skip-levels", action="store_true",
                        help="Skip _detect_from_history per bar (100x faster). "
                             "HS_NEAR_NAMED gets 0 signals. All other targets unaffected.")
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end   = dt.date.fromisoformat(args.end)

    summary = replay_new_watchers(start, end, skip_levels=args.skip_levels)
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE — new-watcher signal counts:")
    print(json.dumps(summary["by_setup"], indent=2))
    print(f"\nTotal new signals: {summary['total_signals']}")
    print(f"Full summary: {_BACKFILL_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
