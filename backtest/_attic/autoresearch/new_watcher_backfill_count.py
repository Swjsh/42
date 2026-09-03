"""Count 16-month historical fires for the 3 new watchers shipped 2026-05-20.

Writes ONLY to analysis/watcher-backfill-2026-05-20.json — does NOT touch
automation/state/watcher-observations.jsonl (the live log) to avoid duplicate
contamination of old watcher entries.

NOTE: levels_active=[] (NOT_NEAR_NAMED filter SKIPPED) — same as real-fills scripts.
Reproducing the full BarContext level pipeline would require per-bar _detect_from_history
which (a) is O(N^2) slow and (b) over-filters using ALL detected levels as ★2, killing
almost every signal. The count here is the "without NOT_NEAR_NAMED" upper bound; the
full-filter count would be somewhat lower.

Usage:
    python backtest/autoresearch/new_watcher_backfill_count.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))  # needed for crypto.lib.chart_patterns

from autoresearch import runner as ar_runner
from lib.filters import BarContext, vol_baseline_20bar, range_baseline_20bar
from lib.ribbon import compute_ribbon, RibbonState
from lib.orchestrator import _align_vix_to_spy, _precompute_htf_15m_stacks
from lib.watchers.double_bottom_base_quiet_watcher import detect_db_base_quiet_setup
from lib.watchers.double_bottom_morning_low_vol_watcher import detect_db_morning_low_vol_setup
from lib.watchers.momentum_acceleration_highvol_watcher import detect_momentum_accel_highvol_setup

import pandas as pd

START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)

_NEW_WATCHERS = [
    ("DOUBLE_BOTTOM_BASE_QUIET",       detect_db_base_quiet_setup),
    ("DOUBLE_BOTTOM_MORNING",          detect_db_morning_low_vol_setup),
    ("MOMENTUM_ACCELERATION_HIGHVOL",  detect_momentum_accel_highvol_setup),
]


def run() -> dict:
    print(f"Loading data {START} to {END}...")
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)

    print(f"RTH bars: {len(rth)}")

    ribbon_df  = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks  = _precompute_htf_15m_stacks(rth)

    ribbon_history: list = []
    last_seen_date: dt.date | None = None

    counter: Counter = Counter()
    by_month: dict   = defaultdict(lambda: defaultdict(int))
    total = 0

    print("Scanning...")
    for idx in range(len(rth)):
        bar      = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = pd.Timestamp(bar_time).date()

        if bar_date < START or bar_date > END:
            continue
        if last_seen_date is not None and bar_date != last_seen_date:
            ribbon_history = []
        last_seen_date = bar_date

        if idx < 60:
            continue

        try:
            r = ribbon_df.iloc[idx]
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

        vol_baseline   = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now        = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior      = float(vix_aligned.iloc[max(0, idx - 3)]) if idx >= 3 else vix_now
        htf_stack      = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time.to_pydatetime(),
            bar=bar,
            prior_bars=rth.iloc[:idx],   # bars BEFORE current bar
            ribbon_now=ribbon_state,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline,
            # levels_active=[] intentionally — NOT_NEAR_NAMED filter skipped
            # (reproducing per-bar level detection is O(N^2) and over-filters)
            levels_active=[],
            multi_day_levels={},
            htf_15m_stack=htf_stack,
            level_states={},
        )

        for name, fn in _NEW_WATCHERS:
            try:
                sig = fn(ctx)
            except Exception:
                sig = None
            if sig is not None:
                counter[(name, sig.confidence)] += 1
                by_month[name][bar_date.strftime("%Y-%m")] += 1
                total += 1

        if idx % 2000 == 0:
            print(f"  bar {idx}/{len(rth)}  signals_so_far={total}")

    out = {
        "run_date": dt.date.today().isoformat(),
        "window": f"{START} to {END}",
        "total_signals": total,
        "by_watcher_confidence": {f"{w}__{c}": n for (w, c), n in counter.items()},
        "by_watcher_month": {k: dict(v) for k, v in by_month.items()},
        "notes": (
            "Count-only replay — does NOT write to watcher-observations.jsonl. "
            "NOT_NEAR_NAMED filter skipped (levels_active=[]) — count is the "
            "without-filter upper bound, consistent with real-fills scripts."
        ),
    }
    out_path = ROOT / "analysis" / "watcher-backfill-2026-05-20.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote: {out_path}")
    return out


if __name__ == "__main__":
    result = run()
    for k, v in result["by_watcher_confidence"].items():
        print(f"  {k}: {v}")
    print(f"\nTotal: {result['total_signals']}")
