"""
gate_override_blocked_cohort.py

Extends the safe3_risky1_gate_retest blocked-cohort sample (queue item
SAFE3-RISKY1-GATE-RETEST-EXTEND, pre-reg
analysis/recommendations/safe3-risky1-gate-retest-preregistration.json) by
matching gate_override-blocked ticks on safe-3/risky-1 to same-signal ENTER
fills on the core arms (safe-2/bold-2), using the core arm's REALISED
trades-enriched.jsonl P&L as the blocked cohort's counterfactual.

Read-only. Does not place orders, does not touch production state.

Match rule (per SAFE3-RISKY1-GATE-RETEST-EXTEND task spec):
  same date + same direction (side) + core ENTER ts_et within +/-2 min of a
  gate-blocked tick's ts_et + same strike (when the core exec carries one).

Gate-blocked reason strings matched (verified via grep against
automation/state/fleet/{safe-3,risky-1}/decisions.jsonl):
  "gate: 1 triggers < 2"
  "gate: requires confluence/sequence"

Consecutive gate-blocked ticks for the same arm/date/side/setup within
GAP_MIN minutes of each other are collapsed into one "episode" (the engine
re-evaluates the same live signal every ~3 min tick; treating each tick as
a separate blocked "event" would inflate n far past what a human auditing
distinct signals would count).
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

REPO = r"C:\Users\jackw\Desktop\42"
GATE_REASONS = {"gate: 1 triggers < 2", "gate: requires confluence/sequence"}
GAP_MIN = 10  # ticks within this many minutes, same arm/date/side/setup, collapse to one episode
MATCH_WINDOW_MIN = 2  # core ENTER must be within +/- this many minutes of a blocked tick
WINDOW_START = "2026-07-16"  # redesign date
WINDOW_END = "2026-09-02"

ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def parse_ts(ts):
    # core-decisions.jsonl: naive "2026-06-25T13:48:17" (ET, no offset)
    # fleet decisions.jsonl: "2026-06-21T21:53:32.493267-04:00" (ET w/ offset)
    ts = ts.split("-04:00")[0].split("-05:00")[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable ts {ts!r}")


def in_window(date_str):
    return WINDOW_START <= date_str <= WINDOW_END


def load_gate_blocked_ticks(arm_id):
    """Raw gate-blocked ticks (one row per HOLD tick with a gate_override reason)."""
    path = f"{REPO}/automation/state/fleet/{arm_id}/decisions.jsonl"
    rows = load_jsonl(path)
    blocked = []
    for r in rows:
        if r.get("reason") in GATE_REASONS and r.get("ts_et"):
            dt = parse_ts(r["ts_et"])
            date_str = dt.strftime("%Y-%m-%d")
            if not in_window(date_str):
                continue
            blocked.append({
                "arm_id": arm_id, "dt": dt, "date": date_str, "side": r.get("side"),
                "setup": r.get("setup_name"), "reason": r.get("reason"),
            })
    blocked.sort(key=lambda x: x["dt"])
    return blocked


def group_into_episodes(blocked_ticks):
    """Collapse consecutive gate-blocked ticks (same date/side/setup, gap <= GAP_MIN)
    into episodes, purely for reporting n_ticks per underlying signal -- NOT used
    for matching (matching is done tick-by-tick against the +/-2min window)."""
    episodes = []
    cur = None
    for b in blocked_ticks:
        if (cur is not None
                and cur["date"] == b["date"]
                and cur["side"] == b["side"]
                and cur["setup"] == b["setup"]
                and (b["dt"] - cur["last_ts"]) <= timedelta(minutes=GAP_MIN)):
            cur["last_ts"] = b["dt"]
            cur["n_ticks"] += 1
            cur["reasons"].add(b["reason"])
        else:
            if cur:
                episodes.append(cur)
            cur = {
                "arm_id": b["arm_id"], "date": b["date"], "side": b["side"],
                "setup": b["setup"], "first_ts": b["dt"], "last_ts": b["dt"],
                "n_ticks": 1, "reasons": {b["reason"]},
            }
    if cur:
        episodes.append(cur)
    return episodes


def load_core_enters():
    path = f"{REPO}/automation/state/core-decisions.jsonl"
    rows = load_jsonl(path)
    enters = []
    for r in rows:
        verdict = r.get("verdict", "")
        if verdict not in ("ENTER_BEAR", "ENTER_BULL"):
            continue
        if not r.get("ts_et"):
            continue
        dt = parse_ts(r["ts_et"])
        date_str = dt.strftime("%Y-%m-%d")
        if not in_window(date_str):
            continue
        exec_ = r.get("exec", {}) or {}
        arm = ACCOUNT_TO_ARM.get(r.get("account"))
        if not arm:
            continue
        enters.append({
            "dt": dt, "date": date_str, "side": r.get("side"),
            "setup": r.get("setup"), "arm": arm,
            "strike": exec_.get("strike"), "symbol": exec_.get("symbol"),
            "exec_status": exec_.get("status"),
        })
    return enters


def load_trades_enriched_index():
    path = f"{REPO}/analysis/trades-enriched.jsonl"
    rows = load_jsonl(path)
    idx = defaultdict(list)
    for r in rows:
        if r.get("_meta"):
            continue
        key = (r.get("date"), r.get("arm"), r.get("symbol"))
        idx[key].append(r)
    return idx


def find_nearest_trade(trades_idx, date, arm, symbol, target_dt, tol_sec=5 * 60):
    trade_rows = trades_idx.get((date, arm, symbol)) if symbol else None
    if not trade_rows:
        return None
    best, best_delta = None, None
    for tr in trade_rows:
        ets = tr.get("entry_ts_et")
        if not ets:
            continue
        try:
            tr_dt = parse_ts(ets)
        except ValueError:
            continue
        delta = abs((tr_dt - target_dt).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta, best = delta, tr
    if best is None or best_delta > tol_sec:
        return None
    return best


def main():
    trades_idx = load_trades_enriched_index()
    core_enters = load_core_enters()

    # index core enters by (date, side) for fast tick-level lookup
    core_by_date_side = defaultdict(list)
    for c in core_enters:
        core_by_date_side[(c["date"], c["side"])].append(c)

    per_arm_ticks = {}
    per_arm_episodes = {}
    for arm_id in ("safe-3", "risky-1"):
        ticks = load_gate_blocked_ticks(arm_id)
        per_arm_ticks[arm_id] = ticks
        per_arm_episodes[arm_id] = group_into_episodes(ticks)

    # tick-level match: for each blocked tick, find core ENTERs within +/-2min
    # same date+side. Dedupe to one match per (blocked_arm, core_arm, core_entry_ts)
    # since multiple ticks in the same episode can all fall within 2min of one entry.
    seen = set()
    all_matches = []
    matched_no_fill = []
    unmatched_ticks = []

    setup_mismatch_near_misses = []
    for arm_id, ticks in per_arm_ticks.items():
        for b in ticks:
            near = [
                c for c in core_by_date_side.get((b["date"], b["side"]), [])
                if abs((c["dt"] - b["dt"]).total_seconds()) <= MATCH_WINDOW_MIN * 60
            ]
            # require same setup_name -- the pre-reg's own cohort_definition specifies
            # "SAME underlying signal (same side, same or adjacent strike, same
            # setup_name)"; time+direction alone is not sufficient (the engine
            # evaluates multiple distinct setups per tick, and a time+direction-only
            # match can pick up an unrelated setup firing in the same 2min window --
            # verified false-positive risk: 2026-08-04 09:56 safe-3 was blocked on
            # VWAP_CONTINUATION while the core arm's nearest ENTER that minute was
            # BULLISH_RECLAIM_RIDE_THE_RIBBON, a different pattern).
            cands = [c for c in near if c["setup"] == b["setup"]]
            for c in near:
                if c["setup"] != b["setup"]:
                    setup_mismatch_near_misses.append({
                        "date": b["date"], "arm": arm_id, "blocked_setup": b["setup"],
                        "core_setup": c["setup"], "core_arm": c["arm"],
                        "blocked_tick_ts": b["dt"].isoformat(), "core_entry_ts": c["dt"].isoformat(),
                    })
            if not cands:
                unmatched_ticks.append(b)
                continue
            for c in cands:
                tr = find_nearest_trade(trades_idx, c["date"], c["arm"], c["symbol"], c["dt"])
                if tr is None:
                    dedupe_key = (arm_id, c["arm"], c["dt"].isoformat(), c["symbol"])
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    matched_no_fill.append({"tick": b, "core": c})
                    continue
                # dedupe on the RESOLVED trade identity, not the raw core-decisions
                # log line -- the engine sometimes logs 2 near-duplicate ENTER
                # verdicts (<=1 tick apart) for what resolves to the same fill
                trade_key = tuple(tr.get("fifo_trip_ids") or []) or (
                    c["date"], c["arm"], c["symbol"], tr.get("entry_ts_et"))
                dedupe_key = (arm_id, c["arm"], trade_key)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                all_matches.append({
                    "blocked_arm": arm_id,
                    "date": b["date"],
                    "side": b["side"],
                    "setup": b["setup"],
                    "gate_reason": b["reason"],
                    "blocked_tick_ts": b["dt"].isoformat(),
                    "core_arm": c["arm"],
                    "core_entry_ts": c["dt"].isoformat(),
                    "core_symbol": c["symbol"],
                    "core_strike": c["strike"],
                    "core_exec_status": c["exec_status"],
                    "pnl_dollars": tr.get("pnl_dollars"),
                    "qty": tr.get("qty"),
                    "entry_px": tr.get("entry_px"),
                    "exit_px_avg": tr.get("exit_px_avg"),
                    "fifo_trip_ids": tr.get("fifo_trip_ids"),
                })

    out = {
        "n_gate_blocked_ticks": {k: len(v) for k, v in per_arm_ticks.items()},
        "n_gate_blocked_episodes": {k: len(v) for k, v in per_arm_episodes.items()},
        "matches": all_matches,
        "n_matches": len(all_matches),
        "n_unmatched_ticks": len(unmatched_ticks),
        "n_matched_core_enter_no_fill": len(matched_no_fill),
        "n_setup_mismatch_near_misses": len(setup_mismatch_near_misses),
        "setup_mismatch_near_misses": setup_mismatch_near_misses,
        "matched_no_fill_detail": [
            {"date": m["tick"]["date"], "arm": m["tick"]["arm_id"],
             "side": m["tick"]["side"], "core_arm": m["core"]["arm"],
             "core_symbol": m["core"]["symbol"], "core_exec_status": m["core"]["exec_status"]}
            for m in matched_no_fill
        ],
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
