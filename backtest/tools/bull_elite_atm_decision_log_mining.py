"""bull_elite_atm_decision_log_mining.py -- SECOND, independent evidence source for the
block_elite_bull ATM/SS-B requalification (2026-07-22 pre-reg).

bull_gate_atm_ssb_requalification.py's run_backtest-based detection only evaluates gates at
5-min bar closes (n=9 added-cohort at ATM over 2026-05-21..07-17) -- it structurally UNDER-
COUNTS relative to the live engine, which ticks every ~1 minute and can re-fire the same signal
multiple times before the bar closes, or catch timing the 5-min replay misses. This script
mines the LIVE decision log directly (automation/state/core-decisions.jsonl, account=='safe',
action=='SKIP_ELITE_BULL_LEVEL_RECLAIM') -- the SAME method backtest/tools/
block_elite_bull_ssb_revalidation.py used on 2026-07-10 (which got n=28 at OTM-2) -- changed to
ATM strike (offset 0) and re-walked through the live exit_manager at the SS-B/RIBBON_RIDE shape.

100% LOCAL CACHE, NO BROKER IMPORTS: unlike the 2026-07-10 original (which fell back to a live
Alpaca OPRA fetch via exit_shape_parity_study.fetch_option_bars for uncached contracts), this
script ONLY reads automation/state/core-decisions.jsonl (already on disk) and
backtest/data/options/*.csv (already-cached). Any event whose option contract isn't cached
locally is DROPPED and counted in n_missing_bars -- never imputed, never fetched live.

Window bound: core-decisions.jsonl's earliest row is 2026-06-25 (the log did not exist before
that) through 2026-07-17 (backtest/data/options/ cache ceiling) -- narrower than the backtest-
detection script's 2026-05-21 start, disclosed explicitly in the output, not silently widened.

Rail-4 CLEAR: analysis only, no trading-path writes, no commits, no network/broker reads.
Run: backtest/.venv/Scripts/python.exe backtest/tools/bull_elite_atm_decision_log_mining.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

import tw8_level_context as lc                      # noqa: E402  (pure-local: lib.levels/lib.filters only)
from lib.filters import detect_level_reclaim         # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import strategies as strat_mod                       # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = REPO / "analysis" / "recommendations" / "bull-elite-atm-decision-log-mining-2026-07-22.json"

MINING_END = dt.date(2026, 7, 17)      # bounded by local option-bar cache coverage
LEVEL_HISTORY_START = dt.date(2026, 5, 19)
DEDUPE_GAP_MINUTES = 5
QTY_ELITE = 10                         # orchestrator.py:1178-1184 quality-tier sizing (ELITE=10)
TIME_STOP_ET = dt.time(15, 50)
STRIKE_OFFSET_ATM = 0

RIBBON_RIDE_SHAPE = strat_mod.RIBBON_RIDE.exit.to_dict()


# ------------------------------------------------------------------------------------------ #
# DECISION-LOG I/O + event dedupe (same pure logic as block_elite_bull_ssb_revalidation.py)
# ------------------------------------------------------------------------------------------ #
def load_core_decisions() -> list[dict]:
    rows = []
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def rows_in_window(rows: list[dict], account: str, start: dt.date, end: dt.date) -> list[dict]:
    out = []
    for r in rows:
        ts = r.get("ts_et")
        if not ts or r.get("account") != account:
            continue
        try:
            d = dt.date.fromisoformat(ts[:10])
        except ValueError:
            continue
        if start <= d <= end:
            out.append(r)
    return out


def dedupe_into_events(rows: list[dict], gap_minutes: int = DEDUPE_GAP_MINUTES) -> list[dict]:
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: r["ts_et"])
    groups: list[list[dict]] = [[ordered[0]]]
    for prev, row in zip(ordered, ordered[1:]):
        prev_ts = dt.datetime.fromisoformat(prev["ts_et"])
        this_ts = dt.datetime.fromisoformat(row["ts_et"])
        gap_min = (this_ts - prev_ts).total_seconds() / 60.0
        if gap_min <= gap_minutes:
            groups[-1].append(row)
        else:
            groups.append([row])
    return [{"entry_row": grp[0], "n_ticks": len(grp), "first_ts": grp[0]["ts_et"]} for grp in groups]


def is_possible_stale_echo(entry_row: dict, other_account_rows: list[dict]) -> tuple[bool, str]:
    ts = dt.datetime.fromisoformat(entry_row["ts_et"])
    for other in other_account_rows:
        other_ts_str = other.get("ts_et")
        if not other_ts_str:
            continue
        other_ts = dt.datetime.fromisoformat(other_ts_str)
        if abs((other_ts - ts).total_seconds()) <= 90 and other.get("action") == "SKIP_STALE_TRIGGER":
            return True, f"cross-account SKIP_STALE_TRIGGER at {other_ts_str}"
    return False, ""


def is_open_adjacent(entry_row: dict) -> bool:
    ts = dt.datetime.fromisoformat(entry_row["ts_et"])
    t = ts.time()
    return dt.time(9, 35) <= t < dt.time(9, 41)


def mine_events(all_rows: list[dict], start: dt.date, end: dt.date) -> tuple[list[dict], dict]:
    safe_rows = rows_in_window(all_rows, "safe", start, end)
    elite_rows = [r for r in safe_rows if r.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"]
    events = dedupe_into_events(elite_rows, DEDUPE_GAP_MINUTES)
    bold_rows = rows_in_window(all_rows, "bold", start, end)
    kept, excluded, flagged = [], [], []
    for ev in events:
        stale, reason = is_possible_stale_echo(ev["entry_row"], bold_rows)
        if stale:
            excluded.append({**ev, "exclusion_reason": reason})
            continue
        if is_open_adjacent(ev["entry_row"]):
            ev = {**ev, "elevated_stale_risk": True}
            flagged.append(ev)
        kept.append(ev)
    stats = {
        "n_raw_ticks": len(elite_rows), "n_events_total": len(events),
        "n_excluded_stale_echo": len(excluded), "n_flagged_open_adjacent": len(flagged),
        "n_kept": len(kept),
    }
    return kept, stats


# ------------------------------------------------------------------------------------------ #
# TRIGGER-LEVEL RECOVERY (local only)
# ------------------------------------------------------------------------------------------ #
_level_cache: dict = {}
_spy_full_cache: Optional[pd.DataFrame] = None


def _spy_full() -> pd.DataFrame:
    global _spy_full_cache
    if _spy_full_cache is None:
        _spy_full_cache = lc.load_spy_full(LEVEL_HISTORY_START, MINING_END)
    return _spy_full_cache


def recover_trigger_level(entry_row: dict) -> tuple[Optional[float], str]:
    logged = entry_row.get("trigger_level_exact")
    if logged is not None:
        return float(logged), "logged"
    ts_et = dt.datetime.fromisoformat(entry_row["ts_et"])
    date = ts_et.date()
    spy_full = _spy_full()
    level_set = lc.frozen_level_set_for_date(spy_full, date, _level_cache)
    if level_set is None:
        return None, "no_level_set"
    day_bars = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] <= ts_et)].tail(3)
    for idx in list(day_bars.index)[::-1]:
        bar = spy_full.loc[idx]
        lvl = detect_level_reclaim(bar, level_set.active)
        if lvl is not None:
            return lvl, "recovered_exact_match"
    return None, "no_trigger_bar_found"


# ------------------------------------------------------------------------------------------ #
# ENTRY PREMIUM (LOCAL CACHE ONLY) + EXIT RE-WALK
# ------------------------------------------------------------------------------------------ #
def prepare_and_requalify(entry_row: dict, elevated_stale_risk: bool) -> Optional[dict]:
    ts_et = dt.datetime.fromisoformat(entry_row["ts_et"])
    date = ts_et.date()
    spy_spot = entry_row.get("spy")
    if spy_spot is None:
        return None
    strike = int(round(float(spy_spot))) + STRIKE_OFFSET_ATM
    trigger_level, level_status = recover_trigger_level(entry_row)
    symbol = option_symbol(date, strike, "C")
    opt_df = load_contract_bars(symbol)
    if opt_df is None or opt_df.empty:
        return None
    ts_col = pd.to_datetime(opt_df["timestamp_et"])
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    opt_df = opt_df.assign(timestamp_et=ts_col)
    after = opt_df[opt_df["timestamp_et"] >= ts_et]
    if after.empty:
        return None
    entry_premium = float(after.iloc[0]["open"])
    if entry_premium <= 0:
        return None

    spy_full = _spy_full()
    five_min = spy_full[spy_full["date"] == date]
    if five_min.empty:
        return None

    res = walk_exit_manager(
        symbol=symbol, side="C", entry_time_et=ts_et, entry_premium=entry_premium,
        qty=QTY_ELITE, exit_shape=RIBBON_RIDE_SHAPE, structure_stop_enabled=True,
        trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=five_min,
    )
    structure_fired = any(leg.stage == "structure_stop" for leg in res.legs)
    return {
        "date": date.isoformat(), "entry_ts_et": ts_et.isoformat(), "strike": strike,
        "entry_premium": round(entry_premium, 4), "trigger_level": trigger_level,
        "trigger_level_status": level_status, "pnl": res.dollar_pnl,
        "exit_reason": res.exit_reason, "structure_fired": structure_fired,
        "elevated_stale_risk": elevated_stale_risk,
    }


# ------------------------------------------------------------------------------------------ #
# STATS (same shape as bull_gate_atm_ssb_requalification.py, kept independent/duplicated --
# small pure functions, not worth a shared-module refactor mid-task)
# ------------------------------------------------------------------------------------------ #
def drop_top1(pnls: list[float]) -> tuple[float, bool]:
    if not pnls:
        return 0.0, False
    winners = [p for p in pnls if p > 0]
    if not winners:
        total = sum(pnls)
        return round(total, 2), total > 0
    remainder = sum(pnls) - max(winners)
    return round(remainder, 2), remainder > 0


def half_split_stability(replays: list[dict]) -> dict:
    if not replays:
        return {"first_half_pnl": 0.0, "second_half_pnl": 0.0, "both_negative": False, "n_first": 0, "n_second": 0}
    ordered = sorted(replays, key=lambda r: r["entry_ts_et"])
    mid = len(ordered) // 2
    first = ordered[:mid] if mid > 0 else ordered[:1]
    second = ordered[mid:] if mid > 0 else ordered[1:]
    first_pnl = round(sum(r["pnl"] for r in first), 2)
    second_pnl = round(sum(r["pnl"] for r in second), 2)
    return {"first_half_pnl": first_pnl, "second_half_pnl": second_pnl,
            "n_first": len(first), "n_second": len(second),
            "both_negative": first_pnl < 0 and second_pnl < 0}


def cohort_stats(replays: list[dict], n_missing: int) -> dict:
    pnls = [r["pnl"] for r in replays]
    n = len(pnls)
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    remainder, remainder_pos = drop_top1(pnls)
    by_day: dict = {}
    for r in replays:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["pnl"], 2)
    top3 = sorted(by_day.values(), reverse=True)[:3]
    top3_pct = round(sum(top3) / total * 100.0, 1) if total else None
    n_structure_fired = sum(1 for r in replays if r.get("structure_fired"))
    return {
        "n": n, "n_missing_bars": n_missing,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "total_pnl": total, "expectancy_per_trade": round(total / n, 2) if n else 0.0,
        "drop_top1_remainder": remainder, "drop_top1_positive": remainder_pos,
        "top3_day_pct_of_net": top3_pct, "n_structure_fired": n_structure_fired,
        "half_split": half_split_stability(replays),
        "by_day_pnl": by_day,
        "trades": sorted(replays, key=lambda r: r["entry_ts_et"]),
    }


N_FLOOR = 20


def grade(stats: dict) -> dict:
    n = stats["n"]
    if n < N_FLOOR:
        return {"verdict": "RETEST-INSUFFICIENT-N", "n": n, "n_floor": N_FLOOR}
    cond_total_pos = stats["total_pnl"] > 0
    cond_stable = not stats["half_split"]["both_negative"]
    cond_drop_top1 = stats["drop_top1_positive"]
    all_pass = cond_total_pos and cond_stable and cond_drop_top1
    return {"verdict": "RETIRE" if all_pass else "KEEP", "n": n, "n_floor": N_FLOOR,
            "condition_total_positive": cond_total_pos,
            "condition_half_split_not_both_negative": cond_stable,
            "condition_drop_top1_positive": cond_drop_top1}


def main() -> int:
    start = dt.date.fromisoformat(
        min(json.loads(l)["ts_et"] for l in CORE_DECISIONS.open(encoding="utf-8") if l.strip())[:10]
    )
    print(f"[bull-elite-mining] core-decisions.jsonl earliest row: {start}", flush=True)
    all_rows = load_core_decisions()
    kept, mining_stats = mine_events(all_rows, start, MINING_END)
    print(f"[bull-elite-mining] mining stats: {mining_stats}", flush=True)

    replays, missing = [], 0
    for ev in kept:
        r = prepare_and_requalify(ev["entry_row"], ev.get("elevated_stale_risk", False))
        if r is None:
            missing += 1
        else:
            replays.append(r)
    print(f"[bull-elite-mining] prepared={len(replays)} missing_bars={missing}", flush=True)

    stats = cohort_stats(replays, missing)
    stats_conservative = cohort_stats(
        [r for r in replays if not r.get("elevated_stale_risk")], missing)
    g = grade(stats)

    out = {
        "_doc": "block_elite_bull ATM/SS-B requalification via LIVE decision-log mining "
                "(2nd independent evidence source alongside bull_gate_atm_ssb_requalification.py's "
                "backtest-detection cohort). 100% local cache, no broker imports, no live fetch.",
        "generated_at": dt.datetime.now().isoformat(),
        "window": [start.isoformat(), MINING_END.isoformat()],
        "window_caveat": "Narrower than the backtest-detection script's 2026-05-21 start -- "
                          "core-decisions.jsonl did not exist before its first row.",
        "strike_offset": STRIKE_OFFSET_ATM,
        "mining_stats": mining_stats,
        "n_missing_bars": missing,
        "cohort": stats,
        "cohort_excluding_open_adjacent_flagged": stats_conservative,
        "grade": g,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[bull-elite-mining] wrote {OUT_JSON}", flush=True)
    print(f"[bull-elite-mining] n={stats['n']} total=${stats['total_pnl']} verdict={g['verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
