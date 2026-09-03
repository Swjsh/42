"""fleet_signal_unreadable_extract.py -- FLEET-SIGNAL-UNREADABLE-WITH-POSITION verify
(2026-09-03, Sonnet, read-only).

Sibling of `fleet_stale_signal_skip_extract.py` (copied, not imported/edited -- that module
is the trading-adjacent SIGNAL_MAX_AGE_SEC staleness class; this one is the DISTINCT
`signal_unreadable: ...` class -- `automation/state/fleet/fleet_live.py:118` -- a JSON parse
failure on `automation/state/fleet/shared-signal.json`, not an age check).

Verifies the queue claim FLEET-SIGNAL-UNREADABLE-WITH-POSITION: on some ticks
`_load_signal()` (fleet_live.py:112-119) fails to parse shared-signal.json, collapsing
`usable_signal` to None and therefore `last_closed_5m_close` to None for that tick --
`exit_manager.plan_exit_actions` skips ONLY the `stop_mode == "structure"` branch on such a
tick (verified: `exit_manager.py:535-539`, `_structure_stop_hit` is the sole consumer of
`last_closed_5m_close`; catastrophe/premium stop, time stop, and ribbon-flip-back are
unconditional of it). This module answers, per arm, in a date window:

  1. how many ticks recorded `signal_status` starting with "signal_unreadable" and whether
     a position was open at that tick (`flat is False`, exact exit_pass symbol/qty/premium
     carried in the row);
  2. the DISTINCT exception-text strings recorded (root-cause fingerprint);
  3. for each unreadable-with-open-position tick, the IMMEDIATELY PRECEDING and FOLLOWING
     READABLE tick's `last_closed_5m_close` for the same symbol -- if unchanged across the
     unreadable gap, the skip could not have altered the structure-stop outcome that tick
     (the readable neighbor saw the identical stale confirmed-bar value and also did not
     fire), which is the key discriminator between "cosmetic gap" and "real missed check";
  4. for every `exit_reason == "structure_stop"` row in trades-enriched.jsonl for that arm
     in the window, whether it was preceded (same day, before exit_ts) by >= 1
     unreadable-with-open-position tick, and if so, the $ and minutes between the first
     such tick and the actual exit fill vs. the option's cached 1-min bar price at the
     first missed tick (backtest/data/highres/<OCC>_1m_<date>.csv), when that file exists.

No writes, no network, no OPRA, no replay. READ-ONLY on automation/state/fleet/*/decisions.jsonl,
analysis/trades-enriched.jsonl, and backtest/data/highres/*.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO_ROOT / "automation" / "state" / "fleet"
TRADES_ENRICHED = REPO_ROOT / "analysis" / "trades-enriched.jsonl"
HIGHRES_DIR = REPO_ROOT / "backtest" / "data" / "highres"


def is_unreadable(signal_status: str | None) -> bool:
    return isinstance(signal_status, str) and signal_status.startswith("signal_unreadable")


def _date_of(ts_et: str | None) -> str | None:
    if not isinstance(ts_et, str) or len(ts_et) < 10:
        return None
    return ts_et[:10]


def load_decisions(path: Path) -> list[dict[str, Any]]:
    """List (not generator, so callers can index neighbors) of every parseable row in a
    fleet arm's decisions.jsonl, in file order. A torn last line is a known, harmless
    tail-write race -- skip it, never abort the whole read."""
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


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


def _exit_pass_entry(row: dict[str, Any], symbol: str | None = None) -> dict[str, Any] | None:
    ep = row.get("exit_pass") or []
    if not ep:
        return None
    if symbol is None:
        return ep[0]
    for e in ep:
        if e.get("symbol") == symbol:
            return e
    return None


def classify_arm_window(
    rows: list[dict[str, Any]], start_date: str, end_date: str
) -> dict[str, Any]:
    """Per-day tick classification for one arm within [start_date, end_date] (inclusive).
    Also resolves, for every unreadable-with-open-position tick, the nearest READABLE
    neighbor row (prev + next, by file order -- decisions.jsonl is append-only chronological)
    carrying the SAME symbol, so the caller can compare last_closed_5m_close across the gap."""
    per_day: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total_ticks": 0, "unreadable_ticks": 0, "unreadable_with_open_position": 0}
    )
    exception_texts: Counter[str] = Counter()
    unreadable_open_ticks: list[dict[str, Any]] = []

    # Index of every row's position in `rows` restricted to the window, so we can walk
    # neighbors irrespective of the window filter applied to the outer loop.
    for i, row in enumerate(rows):
        d = _date_of(row.get("ts_et"))
        if d is None or not (start_date <= d <= end_date):
            continue
        status = row.get("signal_status")
        flat = row.get("flat")
        position_open = flat is False
        bucket = per_day[d]
        bucket["total_ticks"] += 1

        if not is_unreadable(status):
            continue
        bucket["unreadable_ticks"] += 1
        exception_texts[status] += 1
        if not position_open:
            continue
        bucket["unreadable_with_open_position"] += 1

        ep = _exit_pass_entry(row)
        symbol = ep.get("symbol") if ep else None
        lc5_this = ep.get("last_closed_5m_close") if ep else None
        trigger_level = ep.get("trigger_level") if ep else None
        stop_mode = ep.get("stop_mode") if ep else None

        prev_readable = None
        for j in range(i - 1, -1, -1):
            pj = rows[j]
            if _date_of(pj.get("ts_et")) != d:
                break
            pep = _exit_pass_entry(pj, symbol)
            if pep is not None and not is_unreadable(pj.get("signal_status")):
                prev_readable = {"ts_et": pj.get("ts_et"),
                                  "last_closed_5m_close": pep.get("last_closed_5m_close")}
                break
        next_readable = None
        for j in range(i + 1, len(rows)):
            nj = rows[j]
            if _date_of(nj.get("ts_et")) != d:
                break
            nep = _exit_pass_entry(nj, symbol)
            if nep is not None and not is_unreadable(nj.get("signal_status")):
                next_readable = {"ts_et": nj.get("ts_et"),
                                  "last_closed_5m_close": nep.get("last_closed_5m_close")}
                break

        lc5_unchanged_vs_next = (
            next_readable is not None
            and next_readable["last_closed_5m_close"] == lc5_this
        )
        unreadable_open_ticks.append({
            "date": d, "ts_et": row.get("ts_et"), "symbol": symbol,
            "stop_mode": stop_mode, "trigger_level": trigger_level,
            "last_closed_5m_close_this_tick": lc5_this,
            "prev_readable": prev_readable, "next_readable": next_readable,
            "lc5_unchanged_vs_next_readable": lc5_unchanged_vs_next,
        })

    return {
        "per_day": {d: dict(v) for d, v in sorted(per_day.items())},
        "exception_texts": dict(exception_texts),
        "unreadable_open_ticks": unreadable_open_ticks,
    }


def join_structure_stop_exits(
    trades_rows: Iterable[dict[str, Any]],
    arm: str,
    start_date: str,
    end_date: str,
    unreadable_open_ticks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """For every structure_stop exit on `arm` in the window, check whether it was preceded
    (same day, tick ts_et < exit_ts_et, SAME symbol) by >= 1 unreadable-with-open-position
    tick. Quantifies delay two ways: (a) minutes from the earliest such preceding tick to
    the actual exit_ts, (b) the option's cached 1-min bar price at that earliest tick's
    minute vs. the row's own recorded exit pnl_dollars, when the highres CSV exists."""
    by_day_symbol = defaultdict(list)
    for t in unreadable_open_ticks:
        by_day_symbol[(t["date"], t["symbol"])].append(t)

    results = []
    for row in trades_rows:
        if row.get("arm") != arm or row.get("exit_reason") != "structure_stop":
            continue
        d = row.get("date") or _date_of(row.get("exit_ts_et"))
        if d is None or not (start_date <= d <= end_date):
            continue
        symbol = row.get("symbol")
        exit_ts = row.get("exit_ts_et")
        entry_ts = row.get("entry_ts_et")
        candidates = sorted(
            (t for t in by_day_symbol.get((d, symbol), [])
             if exit_ts and t["ts_et"] < exit_ts
             and (entry_ts is None or t["ts_et"] >= entry_ts)),
            key=lambda t: t["ts_et"],
        )
        rec = {
            "date": d, "symbol": symbol, "entry_ts_et": entry_ts, "exit_ts_et": exit_ts,
            "pnl_dollars": row.get("pnl_dollars"),
            "preceded_by_unreadable_open_tick": bool(candidates),
        }
        if candidates:
            first = candidates[0]
            rec["first_preceding_unreadable_tick"] = first["ts_et"]
            rec["first_tick_lc5_unchanged_vs_next_readable"] = first["lc5_unchanged_vs_next_readable"]
            rec["n_preceding_unreadable_ticks"] = len(candidates)
            bar = _option_bar_at(symbol, d, first["ts_et"])
            if bar is not None:
                rec["option_1m_bar_at_first_missed_tick"] = bar
        results.append(rec)
    return results


def _option_bar_at(symbol: str | None, date: str, ts_et: str) -> dict[str, Any] | None:
    """Return the cached 1-min option bar (open/high/low/close) whose minute matches ts_et,
    if backtest/data/highres/<symbol>_1m_<date>.csv exists. None (not an error) when the
    file is absent -- highres caching does not cover every contract/date."""
    if not symbol:
        return None
    path = HIGHRES_DIR / f"{symbol}_1m_{date}.csv"
    if not path.exists():
        return None
    minute = ts_et[:16]  # "YYYY-MM-DDTHH:MM"
    minute_sp = minute.replace("T", " ")
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("timestamp_et", "").startswith(minute_sp):
                return {"timestamp_et": row["timestamp_et"], "open": row["open"],
                        "high": row["high"], "low": row["low"], "close": row["close"]}
    return None


def run(arms: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    trades = load_trades_enriched(TRADES_ENRICHED)
    out: dict[str, Any] = {"window": [start_date, end_date], "arms": {}}
    for arm in arms:
        path = FLEET_DIR / arm / "decisions.jsonl"
        rows = load_decisions(path)
        cls = classify_arm_window(rows, start_date, end_date)
        joins = join_structure_stop_exits(
            trades, arm, start_date, end_date, cls["unreadable_open_ticks"]
        )
        total_unreadable_open = sum(
            v["unreadable_with_open_position"] for v in cls["per_day"].values()
        )
        total_unreadable = sum(v["unreadable_ticks"] for v in cls["per_day"].values())
        delayed = [j for j in joins if j["preceded_by_unreadable_open_tick"]]
        real_delay = [j for j in delayed if not j.get("first_tick_lc5_unchanged_vs_next_readable", False)]
        out["arms"][arm] = {
            "decisions_path": str(path.relative_to(REPO_ROOT)),
            "per_day": cls["per_day"],
            "exception_texts": cls["exception_texts"],
            "total_unreadable_ticks": total_unreadable,
            "total_unreadable_with_open_position": total_unreadable_open,
            "unreadable_open_ticks_detail": cls["unreadable_open_ticks"],
            "structure_stop_exits_in_window": joins,
            "structure_stop_exits_preceded_by_unreadable_tick": delayed,
            "structure_stop_exits_with_plausible_real_delay": real_delay,
            "classification": (
                "REAL-DELAY-CANDIDATE" if real_delay
                else ("COINCIDENT-NO-DELAY" if delayed
                      else ("FIRED-NO-STRUCTURE-STOP-HIT" if total_unreadable_open
                            else "NEVER-FIRED"))
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
