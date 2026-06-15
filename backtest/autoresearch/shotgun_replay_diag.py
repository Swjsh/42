"""Diagnostic: re-run SHOTGUN_SCALPER detector across historical bars to verify
the Tier 3 bullish-bias fix produces bullish fires.

The original 37 historical observations were 29 short / 0 long. The Tier 3 fix
landed 2026-05-16 morning. This diag walks the same historical date range,
calls the FIXED detector, and prints direction distribution.

Does NOT write to watcher-observations.jsonl. Read-only diagnostic.

CLI::

    python -m autoresearch.shotgun_replay_diag --start 2026-04-15 --end 2026-05-12
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.eod_deep.missed_setups_scanner import _load_spy_bars  # noqa: E402


TIME_STOP_MIN = 12
EOD_CUTOFF_HOUR = 15
EOD_CUTOFF_MIN = 50
CHANDELIER_LADDER = [(0.25, 0.00), (0.50, 0.20), (0.75, 0.40)]


def _grade_single_fire(bar_idx, rth, entry, stop, target, direction):
    """Forward-walk bars after fire, compute single-exit P&L per SHOTGUN doctrine.

    Returns (pnl_in_dollars_per_share_times_100, outcome_label).
    """
    import datetime as dt2
    chandelier_step = 0
    cur_stop = stop
    exit_price = entry  # default
    outcome = "time_stop"

    entry_ts = rth.iloc[bar_idx]["timestamp_et"]
    time_stop_at = entry_ts + dt2.timedelta(minutes=TIME_STOP_MIN)
    eod_at = entry_ts.replace(hour=EOD_CUTOFF_HOUR, minute=EOD_CUTOFF_MIN, second=0, microsecond=0)
    final_at = min(time_stop_at, eod_at)

    for j in range(bar_idx + 1, len(rth)):
        b = rth.iloc[j]
        bar_ts = b["timestamp_et"]
        if bar_ts > final_at:
            exit_price = float(b["open"])
            outcome = "time_stop"
            break
        high = float(b["high"])
        low = float(b["low"])
        if direction == "long":
            favor = high - entry
            while chandelier_step < len(CHANDELIER_LADDER):
                threshold, lock_offset = CHANDELIER_LADDER[chandelier_step]
                if favor >= threshold:
                    new_stop = entry + lock_offset
                    if new_stop > cur_stop:
                        cur_stop = new_stop
                    chandelier_step += 1
                else:
                    break
            if low <= cur_stop:
                exit_price = cur_stop
                outcome = "stopped" if chandelier_step == 0 else "chandelier_lock"
                break
            if high >= target:
                exit_price = target
                outcome = "target_hit"
                break
        else:
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
                break
            if low <= target:
                exit_price = target
                outcome = "target_hit"
                break
    else:
        exit_price = float(rth.iloc[-1]["close"])
        outcome = "open_at_eod"

    if direction == "long":
        pnl = (exit_price - entry) * 100
    else:
        pnl = (entry - exit_price) * 100
    return pnl, outcome


def run_diag(start: dt.date, end: dt.date, grade: bool = False) -> dict:
    """Walk bars day-by-day, call FIXED detector, count tier+direction fires.

    If grade=True, also simulate single-exit forward-walk and compute P&L
    per fire using the SHOTGUN doctrine (target hit / chart stop / 12-min
    time stop / EOD cutoff). Aggregates by tier and direction.
    """
    from lib.watchers.shotgun_scalper_watcher import detect_shotgun_scalper_setup

    cur = start
    by_dir: Counter = Counter()
    by_tier_dir: Counter = Counter()
    fires_by_date: dict[str, list[dict]] = defaultdict(list)
    total_bars_seen = 0
    total_fires = 0
    pnl_by_tier_dir: dict[tuple[int, str], float] = defaultdict(float)
    n_by_tier_dir: dict[tuple[int, str], int] = defaultdict(int)
    outcomes_by_tier_dir: dict[tuple[int, str], Counter] = defaultdict(Counter)
    total_pnl = 0.0

    while cur <= end:
        # Skip weekends
        if cur.weekday() >= 5:
            cur += dt.timedelta(days=1)
            continue

        spy = _load_spy_bars(cur)
        if spy is None or spy.empty:
            cur += dt.timedelta(days=1)
            continue

        rth = spy[
            (spy["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy["timestamp_et"].dt.time < dt.time(16, 0))
        ].reset_index(drop=True)
        if rth.empty:
            cur += dt.timedelta(days=1)
            continue

        last_fire_idx = -1
        for i in range(len(rth)):
            total_bars_seen += 1
            if i <= last_fire_idx + 1:
                # tiny cooldown so we don't double-count same setup
                continue

            bar = rth.iloc[i]
            day_bars = rth.iloc[: i + 1]

            try:
                signal = detect_shotgun_scalper_setup(
                    bar=bar,
                    day_bars=day_bars,
                    bar_idx_in_day=i,
                    ribbon_state_dict=None,  # fall back to NEUTRAL
                    vix_now=None,
                )
            except Exception:
                continue

            if signal is None:
                continue

            total_fires += 1
            last_fire_idx = i
            tier = signal.metadata.get("tier")
            direction = signal.direction
            by_dir[direction] += 1
            by_tier_dir[(tier, direction)] += 1
            fire_record = {
                "time": bar["timestamp_et"].strftime("%H:%M"),
                "tier": tier,
                "direction": direction,
                "setup": signal.setup_name,
                "entry": signal.entry_price,
                "target": signal.tp1_price,
                "stop": signal.stop_price,
            }

            if grade:
                pnl, outcome = _grade_single_fire(
                    bar_idx=i,
                    rth=rth,
                    entry=signal.entry_price,
                    stop=signal.stop_price,
                    target=signal.tp1_price,
                    direction=signal.direction,
                )
                fire_record["pnl"] = round(pnl, 2)
                fire_record["outcome"] = outcome
                pnl_by_tier_dir[(tier, direction)] += pnl
                n_by_tier_dir[(tier, direction)] += 1
                outcomes_by_tier_dir[(tier, direction)][outcome] += 1
                total_pnl += pnl

            fires_by_date[cur.isoformat()].append(fire_record)

        cur += dt.timedelta(days=1)

    result = {
        "start": str(start),
        "end": str(end),
        "total_bars_seen": total_bars_seen,
        "total_fires": total_fires,
        "by_direction": dict(by_dir),
        "by_tier_direction": {f"T{t}_{d}": n for (t, d), n in by_tier_dir.items()},
        "fires_per_day": {d: len(v) for d, v in fires_by_date.items()},
        "sample_fires": dict(list(fires_by_date.items())[:5]),
    }
    if grade:
        result["total_pnl_dollars"] = round(total_pnl, 2)
        result["expectancy_per_fire"] = round(total_pnl / max(1, total_fires), 2)
        result["pnl_by_tier_direction"] = {
            f"T{t}_{d}": round(p, 2)
            for (t, d), p in pnl_by_tier_dir.items()
        }
        result["expectancy_by_tier_direction"] = {
            f"T{t}_{d}": round(pnl_by_tier_dir[(t, d)] / max(1, n), 2)
            for (t, d), n in n_by_tier_dir.items()
        }
        result["outcomes_by_tier_direction"] = {
            f"T{t}_{d}": dict(o)
            for (t, d), o in outcomes_by_tier_dir.items()
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default="2026-04-15")
    parser.add_argument("--end", type=str, default="2026-05-15")
    parser.add_argument("--grade", action="store_true",
                        help="also simulate single-exit P&L per fire")
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    result = run_diag(start, end, grade=args.grade)
    import json
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
