"""fleet_stale_signal_skip_extract.py -- FLEET-STALE-SIGNAL-SKIPS-STRUCTURE-STOP verify
(2026-09-03, Sonnet, read-only).

Verifies the queue claim: `automation/state/fleet/fleet_live.py:938` (the STRUCTURE-STOP
comment block) skips a tick's structure-stop check whenever the shared-signal feed is older
than SIGNAL_MAX_AGE_SEC (420s) -- `_load_signal` returns `sig_err = "signal_stale_{age}s"`,
`usable_signal` collapses to None, and `_closed_5m_close` (threaded into
`exit_actuator.manage_tick` as `last_closed_5m_close`) becomes None, which
`exit_manager.plan_exit_actions` treats as "skip the structure_stop branch only" (see
`fleet_live.py` line ~940 comment + `exit_manager.py` line ~520-534: the branch is gated on
`state.stop_mode == "structure"`; premium/catastrophe stop (a2), time stop (b), and
ribbon-flip-back (c) all still run on the same tick, unconditionally of
`last_closed_5m_close`).

This module is READ-ONLY: it parses `automation/state/fleet/<arm>/decisions.jsonl` (each row
already carries `row["signal_status"] = sig_err or "ok"`, fleet_live.py:824) and
`analysis/trades-enriched.jsonl`, and answers three questions per arm:
  1. how many ticks in a date window recorded `signal_status` starting with "signal_stale_"
     (the exact branch named in the queue item), split by whether that tick's position was
     open (`flat: false`) at the time;
  2. the age distribution of those stale ticks (parsed from the status string, seconds);
  3. for every `exit_reason == "structure_stop"` row in trades-enriched.jsonl for that arm in
     the window, whether the exit was preceded (same arm, same day, before exit_ts) by >= 1
     stale-with-open-position tick -- i.e. whether the skip plausibly delayed that exit.

A separate, distinct signal_status class -- "signal_unreadable: ..." (missing/corrupt
shared-signal.json, NOT a staleness condition; `_load_signal` line ~114/118) -- produces the
identical downstream effect (`usable_signal=None` -> structure check skipped) but is a
DIFFERENT root cause than the queue item's SIGNAL_MAX_AGE_SEC claim. This module counts it
separately (never conflated into the "stale" counts) so a reader can see both without the
report overstating the specifically-named branch's frequency.

No writes, no network, no OPRA, no replay. Guarded by
backtest/tests/test_fleet_stale_signal_skip_extract.py (synthetic fixture rows -- the real
decisions.jsonl files contain zero in-window stale hits, so the fixture is what actually
exercises the open-position / join logic).
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO_ROOT / "automation" / "state" / "fleet"
TRADES_ENRICHED = REPO_ROOT / "analysis" / "trades-enriched.jsonl"

_STALE_RE = re.compile(r"^signal_stale_(\d+)s$")


def parse_stale_age_sec(signal_status: str | None) -> int | None:
    """Return the staleness age in seconds if `signal_status` is the SIGNAL_MAX_AGE_SEC
    branch's string ("signal_stale_{age}s"), else None (covers "ok", "no_signal_file",
    "signal_unreadable: ...", and anything else)."""
    if not isinstance(signal_status, str):
        return None
    m = _STALE_RE.match(signal_status)
    return int(m.group(1)) if m else None


def is_unreadable(signal_status: str | None) -> bool:
    return isinstance(signal_status, str) and signal_status.startswith("signal_unreadable")


def _date_of(ts_et: str | None) -> str | None:
    if not isinstance(ts_et, str) or len(ts_et) < 10:
        return None
    return ts_et[:10]


def load_decisions(path: Path) -> Iterator[dict[str, Any]]:
    """Yield rows from a fleet arm's decisions.jsonl, skipping any line that fails to
    parse (append-only log; a torn last line is a known, harmless tail-write race --
    never abort the whole read over one bad line)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def classify_arm_window(
    rows: Iterable[dict[str, Any]], start_date: str, end_date: str
) -> dict[str, Any]:
    """Per-day tick classification for one arm within [start_date, end_date] (inclusive,
    'YYYY-MM-DD' strings). Returns per-day counts plus the stale-tick age list and the raw
    stale-with-open-position ticks (needed by the join step)."""
    per_day: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total_ticks": 0,
            "stale_ticks": 0,
            "stale_with_open_position": 0,
            "unreadable_ticks": 0,
            "unreadable_with_open_position": 0,
        }
    )
    stale_ages: list[int] = []
    stale_open_ticks: list[dict[str, Any]] = []  # for the join step

    for row in rows:
        d = _date_of(row.get("ts_et"))
        if d is None or not (start_date <= d <= end_date):
            continue
        status = row.get("signal_status")
        flat = row.get("flat")
        position_open = flat is False  # explicit: missing/None flat is NOT treated as open
        bucket = per_day[d]
        bucket["total_ticks"] += 1

        age = parse_stale_age_sec(status)
        if age is not None:
            bucket["stale_ticks"] += 1
            stale_ages.append(age)
            if position_open:
                bucket["stale_with_open_position"] += 1
                stale_open_ticks.append({"date": d, "ts_et": row.get("ts_et"), "age_sec": age})
        elif is_unreadable(status):
            bucket["unreadable_ticks"] += 1
            if position_open:
                bucket["unreadable_with_open_position"] += 1

    return {
        "per_day": {d: dict(v) for d, v in sorted(per_day.items())},
        "stale_age_sec_all": stale_ages,
        "stale_with_open_position_ticks": stale_open_ticks,
    }


def join_structure_stop_exits(
    trades_rows: Iterable[dict[str, Any]],
    arm: str,
    start_date: str,
    end_date: str,
    stale_open_ticks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """For every structure_stop exit on `arm` in the window, check whether it was preceded
    (same day, tick ts_et < exit_ts_et) by >= 1 stale-with-open-position tick. Returns one
    record per structure_stop exit with `preceded_by_stale_skip` and, if True, the matching
    tick(s) and the elapsed delay in minutes vs the earliest such tick that day."""
    by_day = defaultdict(list)
    for t in stale_open_ticks:
        by_day[t["date"]].append(t["ts_et"])

    results = []
    for row in trades_rows:
        if row.get("arm") != arm or row.get("exit_reason") != "structure_stop":
            continue
        d = row.get("date")
        if d is None or not (start_date <= d <= end_date):
            continue
        exit_ts = row.get("exit_ts_et")
        preceding = sorted(ts for ts in by_day.get(d, []) if exit_ts and ts < exit_ts)
        rec = {
            "date": d,
            "symbol": row.get("symbol"),
            "exit_ts_et": exit_ts,
            "pnl_dollars": row.get("pnl_dollars"),
            "preceded_by_stale_skip": bool(preceding),
        }
        if preceding:
            rec["preceding_stale_ticks"] = preceding
            rec["earliest_preceding_stale_tick"] = preceding[0]
        results.append(rec)
    return results


def load_trades_enriched(path: Path) -> list[dict[str, Any]]:
    """trades-enriched.jsonl line 1 is a `_meta` summary row, not a trade -- skip it."""
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if i == 0 and "_meta" in d:
                continue
            rows.append(d)
    return rows


def run(arms: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    trades = load_trades_enriched(TRADES_ENRICHED)
    out: dict[str, Any] = {"window": [start_date, end_date], "arms": {}}
    for arm in arms:
        path = FLEET_DIR / arm / "decisions.jsonl"
        cls = classify_arm_window(load_decisions(path), start_date, end_date)
        joins = join_structure_stop_exits(
            trades, arm, start_date, end_date, cls["stale_with_open_position_ticks"]
        )
        total_stale_open = sum(
            v["stale_with_open_position"] for v in cls["per_day"].values()
        )
        total_unreadable_open = sum(
            v["unreadable_with_open_position"] for v in cls["per_day"].values()
        )
        delayed = [j for j in joins if j["preceded_by_stale_skip"]]
        out["arms"][arm] = {
            "decisions_path": str(path.relative_to(REPO_ROOT)),
            "per_day": cls["per_day"],
            "stale_age_sec_all": cls["stale_age_sec_all"],
            "total_stale_with_open_position": total_stale_open,
            "total_unreadable_with_open_position_DISTINCT_MECHANISM": total_unreadable_open,
            "structure_stop_exits_in_window": joins,
            "structure_stop_exits_delayed_by_stale_skip": delayed,
            "classification": (
                "FIRED-DELAYED-EXITS"
                if delayed
                else ("FIRED-NO-HARM" if total_stale_open else "NEVER-FIRED")
            ),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", nargs="+", default=["safe-1", "safe-3", "risky-1", "risky-3"])
    ap.add_argument("--start", default="2026-08-25")
    ap.add_argument("--end", default="2026-09-02")
    args = ap.parse_args()
    result = run(args.arms, args.start, args.end)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
