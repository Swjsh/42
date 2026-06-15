"""SHOTGUN_SCALPER-specific grader — single-exit doctrine, no runner.

The standard `grade_observation` in `lib/watchers/runner.py` assumes the
TP1+RUNNER+BE-stop framework. SHOTGUN_SCALPER's doctrine is explicitly the
opposite: single full-position exit at the target level, no runner. Grading
SHOTGUN observations with the runner model produces nonsense numbers (-$482
across 37 obs with 0 runner_hits) because the runner exit target is never set.

This grader re-walks SHOTGUN observations with the correct exit ladder:
  1. SPY hits ``target_level`` (= ``tp1_price`` in the observation row)
     → full exit, P&L = (target − entry) × direction × 100
  2. SPY hits ``stop_chart`` (= ``stop_price``)
     → full exit, P&L = (stop − entry) × direction × 100
  3. Time stop fires (default 12 min from entry)
     → exit at bar close at that time
  4. End-of-day cutoff at 15:50 ET
     → exit at bar close

Per SHOTGUN doctrine (strategy/playbook/SHOTGUN_SCALPER.md):
  - No runner. No TP1 partial exit.
  - Chandelier ladder ratchets the stop up after +25/+50/+75% premium gain.
    Approximated here in SPY-price terms by ratcheting `stop_chart` to
    progressively tighter levels as price moves favorably.

Writes back to `automation/state/watcher-observations.jsonl` overwriting
the `would_be_outcome` / `would_be_pnl_dollars` fields ONLY on rows where
``watcher_name == "shotgun_scalper_watcher"``. Other watchers are left
unchanged.

CLI::

    python -m autoresearch.shotgun_grader
    python -m autoresearch.shotgun_grader --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("shotgun_grader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as ar_runner  # noqa: E402

OBS_LOG = ROOT / "automation" / "state" / "watcher-observations.jsonl"
SUMMARY = ROOT / "automation" / "state" / "shotgun-grader-summary.json"

TIME_STOP_MIN = 12
EOD_CUTOFF_HOUR = 15
EOD_CUTOFF_MIN = 50

# Chandelier ladder thresholds (favor distance in SPY $)
# At +25c favor, ratchet stop to break-even.
# At +50c favor, ratchet stop to +20c profit lock.
# At +75c favor, ratchet stop to +40c profit lock.
CHANDELIER_LADDER = [
    (0.25, 0.00),   # arm at +25c favor → stop at entry
    (0.50, 0.20),   # at +50c favor → stop +20c past entry
    (0.75, 0.40),   # at +75c favor → stop +40c past entry
]


def _normalize_ts(ts_raw) -> "pd.Timestamp":
    import pandas as pd
    ts = pd.to_datetime(ts_raw)
    if ts.tz is not None:
        return ts.tz_convert("America/New_York").tz_localize(None)
    return ts


def grade_shotgun_single_exit(obs: dict, future_bars) -> dict:
    """Score a SHOTGUN observation with single-exit doctrine.

    Mutates `obs` in place: sets `would_be_outcome` and `would_be_pnl_dollars`.
    """
    import pandas as pd

    direction = obs.get("direction")
    entry = float(obs.get("entry_price"))
    stop = float(obs.get("stop_price"))
    target = float(obs.get("tp1_price"))
    if direction not in ("long", "short"):
        return obs
    if future_bars is None or future_bars.empty:
        return obs

    entry_ts = _normalize_ts(obs.get("bar_timestamp_et"))
    time_stop_at = entry_ts + dt.timedelta(minutes=TIME_STOP_MIN)
    eod_at = entry_ts.replace(hour=EOD_CUTOFF_HOUR, minute=EOD_CUTOFF_MIN, second=0, microsecond=0)
    final_at = min(time_stop_at, eod_at)

    chandelier_step = 0  # which rung we've moved to
    cur_stop = stop

    outcome = "open"
    exit_price = entry  # default if we time out exactly at entry
    exit_reason = "time_stop"

    for _, b in future_bars.iterrows():
        bar_ts = b["timestamp_et"]
        if bar_ts > final_at:
            # Use this bar's open as exit price (next-bar fill proxy)
            exit_price = float(b["open"])
            outcome = "time_stop"
            exit_reason = "time_stop"
            break

        high = float(b["high"])
        low = float(b["low"])

        if direction == "long":
            favor = high - entry
            # ratchet chandelier
            while chandelier_step < len(CHANDELIER_LADDER):
                threshold, lock_offset = CHANDELIER_LADDER[chandelier_step]
                if favor >= threshold:
                    new_stop = entry + lock_offset
                    if new_stop > cur_stop:
                        cur_stop = new_stop
                    chandelier_step += 1
                else:
                    break
            # stop check (low <= cur_stop)
            if low <= cur_stop:
                exit_price = cur_stop
                outcome = "stopped" if chandelier_step == 0 else "chandelier_lock"
                exit_reason = "stop"
                break
            # target check
            if high >= target:
                exit_price = target
                outcome = "target_hit"
                exit_reason = "target"
                break
        else:  # short
            favor = entry - low
            while chandelier_step < len(CHANDELIER_LADDER):
                threshold, lock_offset = CHANDELIER_LADDER[chandelier_step]
                if favor >= threshold:
                    new_stop = entry - lock_offset
                    if new_stop < cur_stop:
                        cur_stop = new_stop
                    chandelier_step += 1
                else:
                    break
            if high >= cur_stop:
                exit_price = cur_stop
                outcome = "stopped" if chandelier_step == 0 else "chandelier_lock"
                exit_reason = "stop"
                break
            if low <= target:
                exit_price = target
                outcome = "target_hit"
                exit_reason = "target"
                break
    else:
        # No exit fired — close at the last bar's close
        last = future_bars.iloc[-1]
        exit_price = float(last["close"])
        outcome = "open_at_eod"
        exit_reason = "eod_close"

    if direction == "long":
        pnl = (exit_price - entry) * 100
    else:
        pnl = (entry - exit_price) * 100

    obs["would_be_outcome"] = outcome
    obs["would_be_pnl_dollars"] = round(pnl, 2)
    obs["_shotgun_exit_reason"] = exit_reason
    obs["_shotgun_exit_price"] = round(exit_price, 4)
    obs["_shotgun_graded_at"] = dt.datetime.now().isoformat(timespec="seconds")
    return obs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without overwriting observations file")
    args = parser.parse_args()

    if not OBS_LOG.exists():
        logger.info("no observations file")
        return 0

    import pandas as pd

    rows = []
    for line in OBS_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    if not rows:
        logger.info("no observations parsed")
        return 0

    sg_rows = [r for r in rows if r.get("watcher_name") == "shotgun_scalper_watcher"]
    logger.info("grading %d SHOTGUN observations (of %d total)", len(sg_rows), len(rows))

    if not sg_rows:
        return 0

    by_date = defaultdict(list)
    for r in sg_rows:
        d = dt.date.fromisoformat(r["bar_timestamp_et"][:10])
        by_date[d].append(r)

    for d, day_rows in by_date.items():
        try:
            # Use end=d (same day) so rolling daily-append files are found for
            # the most-recent session.  0DTE shotgun trades close intraday, so
            # same-day bars are sufficient for grading.  (load_data(d, d+1)
            # would require a file covering tomorrow, which doesn't exist yet.)
            spy, _ = ar_runner.load_data(d, d)
            ts = pd.to_datetime(spy["timestamp_et"])
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
            spy["timestamp_et"] = ts
        except Exception as e:
            logger.error("could not load %s: %s", d, e)
            continue

        for r in day_rows:
            entry_ts = _normalize_ts(r["bar_timestamp_et"])
            future = spy[spy["timestamp_et"] > entry_ts]
            cutoff = entry_ts + pd.Timedelta(hours=4)
            future = future[future["timestamp_et"] <= cutoff]
            grade_shotgun_single_exit(r, future)

    # Recompute summary
    # L67: deduplicate by bar_timestamp_et[:16] before computing summary stats.
    # The 3-min heartbeat vs 5-min bar overlap causes duplicate observations
    # for the same bar, inflating WR/N by ~4.5×.
    _seen: set = set()
    sg_deduped = []
    for _r in sg_rows:
        _key = _r.get("bar_timestamp_et", "")[:16]
        if _key not in _seen:
            _seen.add(_key)
            sg_deduped.append(_r)
    logger.info("dedup: %d raw shotgun rows -> %d unique bars", len(sg_rows), len(sg_deduped))

    outcomes = Counter()
    pnl_total = 0.0
    pnl_by_tier = defaultdict(float)
    n_by_tier = defaultdict(int)
    # TBR vol_ratio split (2026-05-24): split TRENDLINE_BREAK_RETEST by vol >= 1.5x avg
    tbr_vol_pnl: dict[str, float] = {"hi": 0.0, "lo": 0.0}
    tbr_vol_n: dict[str, int] = {"hi": 0, "lo": 0}
    TBR_VOL_THRESH = 1.5
    for r in sg_deduped:
        outcome = r.get("would_be_outcome", "ungraded") or "ungraded"
        outcomes[outcome] += 1
        pnl = r.get("would_be_pnl_dollars") or 0
        try:
            pnl_total += float(pnl)
            tier = r.get("setup_name", "?")
            pnl_by_tier[tier] += float(pnl)
            n_by_tier[tier] += 1
            if tier == "TRENDLINE_BREAK_RETEST":
                vr = float(r.get("metadata", {}).get("vol_ratio") or r.get("vol_ratio") or 0)
                bucket = "hi" if vr >= TBR_VOL_THRESH else "lo"
                tbr_vol_pnl[bucket] += float(pnl)
                tbr_vol_n[bucket] += 1
        except Exception:
            pass

    tbr_vol_split = {
        f"TBR_vol_ge_{TBR_VOL_THRESH}": {
            "n": tbr_vol_n["hi"],
            "pnl": round(tbr_vol_pnl["hi"], 2),
            "expectancy": round(tbr_vol_pnl["hi"] / max(1, tbr_vol_n["hi"]), 2),
        },
        f"TBR_vol_lt_{TBR_VOL_THRESH}": {
            "n": tbr_vol_n["lo"],
            "pnl": round(tbr_vol_pnl["lo"], 2),
            "expectancy": round(tbr_vol_pnl["lo"] / max(1, tbr_vol_n["lo"]), 2),
        },
    }

    summary = {
        "graded_at": dt.datetime.now().isoformat(timespec="seconds"),
        "strategy": "shotgun_scalper",
        "n_observations_raw": len(sg_rows),
        "n_observations": len(sg_deduped),
        "outcomes": dict(outcomes),
        "total_would_be_pnl_dollars": round(pnl_total, 2),
        "n_winners": outcomes.get("target_hit", 0) + outcomes.get("chandelier_lock", 0),
        "n_losers": outcomes.get("stopped", 0),
        "win_rate": round(
            (outcomes.get("target_hit", 0) + outcomes.get("chandelier_lock", 0))
            / max(1, len(sg_deduped)),
            3,
        ),
        "expectancy_per_obs": round(pnl_total / max(1, len(sg_deduped)), 2),
        "pnl_by_tier": {k: round(v, 2) for k, v in pnl_by_tier.items()},
        "n_by_tier": dict(n_by_tier),
        "tbr_vol_ratio_split": tbr_vol_split,
    }

    if not args.dry_run:
        with OBS_LOG.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")
        SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        logger.info("observations updated; summary at %s", SUMMARY)

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
