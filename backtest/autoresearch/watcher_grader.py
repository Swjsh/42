"""Watcher grader — fills in would_be_outcome on past observations.

Reads watcher-observations.jsonl, finds rows with would_be_outcome=null,
fetches future bars after entry, simulates the would-be trade outcome,
writes back to the file.

Run via Gamma_WatcherGrader scheduled task hourly (during market hours)
or daily (post-market for Sunday batch).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as ar_runner
from lib.watchers.runner import grade_observation, OBS_LOG, SUMMARY


def main() -> int:
    if not OBS_LOG.exists():
        print("no observations to grade")
        return 0

    rows = []
    for line in OBS_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    if not rows:
        print("no observations parsed")
        return 0

    # Find ungraded rows, excluding shotgun_scalper (handled by shotgun_grader.py
    # which uses single-exit doctrine instead of the TP1+runner 50/50 split).
    _SHOTGUN_WATCHER = "shotgun_scalper_watcher"
    ungraded = [
        r for r in rows
        if r.get("would_be_outcome") is None
        and r.get("watcher_name") != _SHOTGUN_WATCHER
    ]
    n_shotgun_skipped = sum(
        1 for r in rows
        if r.get("would_be_outcome") is None and r.get("watcher_name") == _SHOTGUN_WATCHER
    )
    if n_shotgun_skipped:
        print(f"skipping {n_shotgun_skipped} shotgun_scalper_watcher rows "
              f"(use shotgun_grader.py for correct single-exit doctrine)")
    if not ungraded:
        print(f"all non-shotgun observations already graded")
        return 0

    print(f"grading {len(ungraded)} of {len(rows)} observations (excluding shotgun)...")

    # Group by date for efficient bar loading
    from collections import defaultdict
    import pandas as pd
    by_date = defaultdict(list)
    for r in ungraded:
        d = dt.date.fromisoformat(r["bar_timestamp_et"][:10])
        by_date[d].append(r)

    for d, day_rows in by_date.items():
        # Load bars for this day.  We use end=d (same day) so that the
        # auto-discovery in load_data can find rolling daily-append files
        # (e.g. spy_5m_2026-05-08_2026-05-20.csv) when grading the most-
        # recent session.  Using end=d+1 would require a file covering the
        # *next* day, which doesn't exist for today's session.  All watcher
        # observations are 0DTE (intraday only), so same-day bars are enough.
        try:
            spy, _ = ar_runner.load_data(d, d)
            # Normalize to tz-naive (CLAUDE.md L31: concat / mixed tz collisions
            # in observations vs spy timestamps. SHOTGUN obs come from a code
            # path that wrote bar_timestamp_et as tz-aware ISO strings like
            # "2026-04-15T11:20:00-04:00"; ORB/BULL came tz-naive. Coerce both
            # ends to tz-naive ET so the > / <= comparisons work uniformly.)
            ts = pd.to_datetime(spy["timestamp_et"])
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
            spy["timestamp_et"] = ts
        except Exception as e:
            print(f"  could not load {d}: {e}")
            continue

        for r in day_rows:
            entry_ts_raw = pd.to_datetime(r["bar_timestamp_et"])
            # Normalize entry_ts to tz-naive ET to match `spy`. Tz-aware
            # observations (SHOTGUN obs are tz-aware) would otherwise raise
            # "Invalid comparison between dtype=datetime64[ns, ...] and Timestamp".
            if entry_ts_raw.tz is not None:
                entry_ts = entry_ts_raw.tz_convert("America/New_York").tz_localize(None)
            else:
                entry_ts = entry_ts_raw
            future = spy[spy["timestamp_et"] > entry_ts]
            # Limit to same day + 4 hours after (for short-term watchers)
            cutoff = entry_ts + pd.Timedelta(hours=4)
            future = future[future["timestamp_et"] <= cutoff]
            grade_observation(r, future)

    # Rewrite the file with graded rows
    with OBS_LOG.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")

    # Update summary
    # L67: deduplicate by (bar_timestamp_et[:16], watcher_name) before computing
    # summary stats.  The 3-min heartbeat vs 5-min bar overlap causes duplicate
    # observations for the same bar, inflating WR/N by ~4.5×.
    from collections import Counter
    _seen_bar_keys: set = set()
    _rows_deduped = []
    for _r in rows:
        _key = ((_r.get("bar_timestamp_et") or "")[:16], _r.get("watcher_name", ""))
        if _key not in _seen_bar_keys:
            _seen_bar_keys.add(_key)
            _rows_deduped.append(_r)
    dedup_rows = _rows_deduped  # use for summary only; raw `rows` still written to disk

    outcomes = Counter()
    pnl_by_watcher = defaultdict(float)
    for r in dedup_rows:
        outcome = r.get("would_be_outcome", "open") or "open"
        outcomes[(r["watcher_name"], outcome)] += 1
        pnl = r.get("would_be_pnl_dollars") or 0
        pnl_by_watcher[r["watcher_name"]] += pnl

    summary = {
        "graded_at": dt.datetime.now().isoformat(),
        "total_observations": len(rows),
        "total_unique_bars": len(dedup_rows),
        "outcomes_by_watcher": {f"{w}__{o}": n for (w, o), n in outcomes.items()},
        "would_be_pnl_by_watcher": {w: round(p, 2) for w, p in pnl_by_watcher.items()},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
