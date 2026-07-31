"""min_entry_premium_blocked_replay_2026_07_31 -- what would the fleet's floor-blocked
signals have paid, 2026-07-28..2026-07-31?

MISSION (J, 2026-07-31 post-close): the 12:19 ET 11/11 bull setup at level 743.25 was taken
by risky-3 (SPY260731C00746000 @ $0.33, WON) but refused for safe-3/risky-1 because their
own (further-OTM) strike priced at $0.15 -- below params.json's min_entry_premium=0.30 floor.
Forensics found risky-1 alone logged 15 of 16 named-setup ticks today dying on this exact
floor. Treat the floor as a suspect gate: provenance-audit it, and if the data shows it is
costing real money for no protective reason, kill it; if it is protecting against a real
mechanism, find the REAL lever instead of touching the floor.

PROVENANCE VERDICT (read before the numbers): the floor is NOT an unvalidated invented lock.
It shipped 2026-07-09 (STOP-B disposition) on T2 (mechanism: sub-$0.20 fills are ~2-tick
stops, ~42% spread proxy -- the stop reads spread noise, not price) + T3 (full population
n=157, control $22.91 -> $36.62/tr at the floor) + this scorecard's own T5 anchor
(entry-1+control -$72.5 vs control -$757.1, floor dropped 63 toxic positions from the 79-
position anchor population). It was independently re-audited and marked KEEP in
markdown/audits/GATE-PROVENANCE-CENSUS-2026-07-09.md ("0 gates found with zero provenance").
Guard: backtest/tests/test_min_entry_premium_floor.py (10/10 green, RED-proofed both lanes).

REAL MECHANISM FOUND (2026-07-31 investigation, this file): the floor itself is fine. What
changed is WHICH strike the fleet's 3 non-core arms (safe-3, risky-1, risky-3) pick.
fleet_executor._tiers_for_arm defaults any non-"safe"-prefixed arm id (and safe-3 via an
explicit params_patch.strike_tier_table="bold") to strike_selection.V15_BOLD_TIERS -- OTM-2
($2K-10K equity) / OTM-3 (<$2K equity) -- NOT the ATM-at-low-equity V15_BOLD_CORE_TIERS table
that core Bold's heartbeat_core.py was repointed to on 2026-07-17 (J: "wire Bold to ATM"),
which cleared the SAME floor 97.95% of the time vs OTM-3's 34% (bold-strike-axis-2026-07-15
.json). This was ALREADY DIAGNOSED on 2026-07-10 (accounts.json probe_arm._doc AMENDMENT 1:
"the fleet's own far-OTM/bold sizing tiers price their natural 0DTE contracts under the $0.30
floor... 18 of 31 arm-events on 07-10 alone") -- today's 58 floor-hits are the SAME mechanism,
not a new one, three weeks later, still unresolved for the fleet lane specifically.

METHOD: real OPRA 5-min option bars (Alpaca `/v1beta1/options/bars`), fill = OPEN of the
first option bar at/after the decision tick (today_blocked_replay_2026_07_29.py's convention
-- "next available print", the same approximation the live marketable-limit path uses).
Walked through the REAL live exit_manager decision core
(backtest/lib/exit_manager_walk.walk_exit_manager), never simulator_real (2026-07-09
sim-parity scar). Each cell uses the ARM'S OWN registered exit shape (RIBBON_RIDE base +
that arm's accounts.json params_patch.exit_patch overlay, mirroring fleet_executor.
_exit_shape_dict) and the qty actually logged for that arm at that tick. trigger_level is
backfilled from any arm's real ENTER_* row at the EXACT same decision tick (several clusters
share a tick with an arm that DID clear the floor); where no arm entered at that tick, no
trigger_level exists anywhere in the record, and the walk runs in "premium" stop-mode by
exit_manager.ExitState.from_entry's own documented inertness contract (missing trigger_level
=> premium mode, byte-identical fallback, not a fabricated level) -- disclosed per-cell.

PRE-REGISTRATION (before running the walk): see this file's sibling scorecard
analysis/recommendations/min-entry-premium-2026-07-31.json's `pre_registration` block,
written and timestamped (setup/scripts/et_clock.py) BEFORE this script was executed.

ANALYSIS ONLY. No live file touched, no order placed, no params.json edit. n = 25 arm x
signal-instance cells across 4 trading days = SMALL, disclosed not padded -- exactly the same
disclosure discipline as today_blocked_replay_2026_07_29.py's n=5.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from backtest.lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import strategies  # noqa: E402
import fleet_executor as fx  # noqa: E402

ET = "America/New_York"
DATES = {"2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"}

PATHS = {
    "safe-3": REPO / "automation" / "state" / "fleet" / "safe-3" / "decisions.jsonl",
    "risky-1": REPO / "automation" / "state" / "fleet" / "risky-1" / "decisions.jsonl",
    "risky-3": REPO / "automation" / "state" / "fleet" / "risky-3" / "decisions.jsonl",
}
CORE_PATH = REPO / "automation" / "state" / "core-decisions.jsonl"

ARM_CONFIG = {
    "safe-3": {"exit_patch": {"stop_mode": "structure", "profit_lock_mode": "trailing"}},
    "risky-1": {"exit_patch": {"tp1_premium_pct": 0.5, "stop_mode": "structure"}},
    "risky-3": {"exit_patch": {"stop_mode": "structure", "profit_lock_mode": "trailing",
                                "trail_pct": 0.20}},
}


def _creds() -> tuple[str, str]:
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def _get(url: str) -> dict:
    key, sec = _creds()
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _bars_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame([{"timestamp_et": b["t"], "open": b["o"], "high": b["h"],
                        "low": b["l"], "close": b["c"]} for b in rows])
    if df.empty:
        return df
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return df.sort_values("timestamp_et").reset_index(drop=True)


def option_symbol(day: str, side: str, strike: int) -> str:
    y, m, d = day.split("-")
    cp = "C" if side == "C" else "P"
    return f"SPY{y[2:]}{m}{d}{cp}{strike * 1000:08d}"


def fetch_option(day: str, side: str, strike: int) -> pd.DataFrame:
    sym = option_symbol(day, side, strike)
    url = (f"https://data.alpaca.markets/v1beta1/options/bars?symbols={sym}"
           f"&timeframe=5Min&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=200&sort=asc")
    d = _get(url)
    return _bars_df((d.get("bars") or {}).get(sym) or [])


def fetch_spy(day: str) -> pd.DataFrame:
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min"
           f"&start={day}T13:30:00Z&end={day}T20:05:00Z&limit=200&feed=iex&sort=asc")
    return _bars_df(_get(url).get("bars") or [])


def entry_premium(opt: pd.DataFrame, tick_et_str: str) -> float | None:
    t = pd.Timestamp(tick_et_str)
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    after = opt[opt["timestamp_et"] >= t]
    return float(after.iloc[0]["open"]) if len(after) else None


def load_clusters() -> list[dict]:
    """Re-derive the 25 arm x signal-instance clusters (same clustering the mission's
    forensics used: consecutive SKIP_MIN_PREMIUM_FLOOR rows, same (day,side,setup), gap
    <=15min = one instance) and backfill trigger_level from any arm's real ENTER_* row at
    the identical decision tick."""
    # pass 1: collect every real ENTER_* row (any lane) keyed by exact ts_et -> trigger_level
    trig_by_ts: dict[str, float] = {}
    all_paths = {**PATHS, "core": CORE_PATH}
    for _arm, p in all_paths.items():
        with open(p, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                ts = d.get("ts_et") or ""
                if ts[:10] not in DATES:
                    continue
                if d.get("action") in ("ENTER_BULL", "ENTER_BEAR") and d.get("trigger_level") is not None:
                    trig_by_ts[ts] = float(d["trigger_level"])

    clusters: list[dict] = []
    for arm, p in PATHS.items():
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                ts = d.get("ts_et") or ""
                if ts[:10] not in DATES:
                    continue
                if d.get("risk_code") == "SKIP_MIN_PREMIUM_FLOOR":
                    rows.append(d)
        rows.sort(key=lambda d: d["ts_et"])
        cur = None
        for d in rows:
            ts = dt.datetime.fromisoformat(d["ts_et"]).replace(tzinfo=None)
            key = (d["ts_et"][:10], d.get("side"), d.get("setup_name"))
            if (cur and cur["arm"] == arm and cur["day"] == key[0] and cur["side"] == key[1]
                    and cur["setup"] == key[2] and (ts - cur["last_ts"]).total_seconds() <= 900):
                cur["last_ts"] = ts
                cur["rows"].append(d)
            else:
                if cur:
                    clusters.append(cur)
                cur = {"arm": arm, "day": key[0], "side": key[1], "setup": key[2],
                       "first_ts": ts, "last_ts": ts, "rows": [d]}
        if cur:
            clusters.append(cur)

    for c in clusters:
        first = c["rows"][0]
        c["strike"] = first["strike"]
        c["qty"] = first.get("qty") or 3
        c["decision_premium"] = first["premium"]
        c["trigger_level"] = trig_by_ts.get(first["ts_et"])
    return clusters


def run_walk(arm: str, side: str, strike: int, day: str, entry: float, entry_ts: pd.Timestamp,
             trigger_level: float | None, qty: int, opt: pd.DataFrame, spy: pd.DataFrame):
    base = strategies.RIBBON_RIDE.exit.to_dict()
    patch = ARM_CONFIG[arm]["exit_patch"]
    shape = {**base, **patch}
    return walk_exit_manager(
        symbol=option_symbol(day, side, strike), side=side, entry_time_et=entry_ts,
        entry_premium=entry, qty=qty, exit_shape=shape, structure_stop_enabled=True,
        trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
        opt_df=opt, ribbon_tick_df=None, five_min_spy_df=spy), shape


def main() -> int:
    clusters = load_clusters()
    spy_cache: dict[str, pd.DataFrame] = {}
    out_cells = []
    for c in clusters:
        day = c["day"]
        if day not in spy_cache:
            spy_cache[day] = fetch_spy(day)
        spy = spy_cache[day]
        opt = fetch_option(day, c["side"], c["strike"])
        if opt.empty:
            out_cells.append({**{k: c[k] for k in ("arm", "day", "side", "setup", "strike", "qty",
                                                    "decision_premium", "trigger_level")},
                               "first_ts": str(c["first_ts"]), "excluded": "no_option_data"})
            continue
        entry_ts = c["first_ts"]
        entry = entry_premium(opt, str(entry_ts))
        if entry is None or entry <= 0:
            out_cells.append({**{k: c[k] for k in ("arm", "day", "side", "setup", "strike", "qty",
                                                    "decision_premium", "trigger_level")},
                               "first_ts": str(entry_ts), "excluded": "no_entry_print"})
            continue
        result, shape = run_walk(c["arm"], c["side"], c["strike"], day, entry, entry_ts,
                                  c["trigger_level"], c["qty"], opt, spy)
        cell = {
            "arm": c["arm"], "day": day, "side": c["side"], "setup": c["setup"],
            "strike": c["strike"], "qty": c["qty"],
            "decision_tick_premium": c["decision_premium"],
            "trigger_level": c["trigger_level"],
            "resolved_stop_mode": result.stop_mode,
            "first_ts": str(entry_ts),
            "entry_fill_premium": round(entry, 4),
            "n_floor_hit_ticks_this_cluster": len(c["rows"]),
            "pnl": round(result.dollar_pnl, 2),
            "exit_reason": result.exit_reason,
            "exit_time_et": str(result.exit_time_et),
            "resolved": result.resolved,
            "exit_shape": shape,
        }
        out_cells.append(cell)
        print(f"[{c['arm']:8s} {day} {c['side']} {c['strike']}] entry ${entry:.2f} "
              f"({len(c['rows'])} floor ticks) -> stop_mode={result.stop_mode} "
              f"pnl ${result.dollar_pnl:>8.2f}  {result.exit_reason}")

    valid = [x for x in out_cells if not x.get("excluded")]
    tot = sum(x["pnl"] for x in valid)
    wins = [x for x in valid if x["pnl"] > 0]
    n = len(valid)
    wr = (len(wins) / n) if n else None
    per_trade = (tot / n) if n else None
    drop_best = None
    if n > 1:
        best = max(x["pnl"] for x in valid)
        drop_best = (tot - best) / (n - 1)

    summary = {
        "n_cells": len(out_cells), "n_valid": n, "n_excluded": len(out_cells) - n,
        "total_pnl": round(tot, 2), "wr": round(wr, 4) if wr is not None else None,
        "expectancy_per_trade": round(per_trade, 2) if per_trade is not None else None,
        "expectancy_drop_best": round(drop_best, 2) if drop_best is not None else None,
        "by_arm": {},
    }
    for arm in PATHS:
        arm_cells = [x for x in valid if x["arm"] == arm]
        if not arm_cells:
            continue
        summary["by_arm"][arm] = {
            "n": len(arm_cells), "total": round(sum(x["pnl"] for x in arm_cells), 2),
            "wr": round(sum(1 for x in arm_cells if x["pnl"] > 0) / len(arm_cells), 4),
        }

    out = {"window": sorted(DATES), "cells": out_cells, "summary": summary}
    p = REPO / "analysis" / "recommendations" / "min-entry-premium-blocked-replay-2026-07-31.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {p}")
    print(f"\nSUMMARY: n={n} total=${tot:,.2f} WR={wr} exp/tr=${per_trade if per_trade else 0:,.2f} "
          f"drop_best=${drop_best if drop_best else 0:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
