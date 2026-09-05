"""gate_net_cost_inventory.py -- GOAL-GATE-NET-COST-2026-09-05 N1.

Inventories every ENTER-eligible tick refused by a named gate, 2026-08-01..today,
deduped to WAVES (reuses backtest/lib/right_tail_waves.WAVE_GAP_MINUTES episode-grouping
logic -- same-side refusal ticks within 30 minutes of each other collapse into one wave).

Sources (read-only, per goal OPERATING RULES -- no new backtest grid):
  - automation/state/core-decisions.jsonl `verdict`/`action` for the 7 core-named gates
    (SKIP_STRUCTURE_VETO, SKIP_LATE_ENTRY, SKIP_STALE_TRIGGER,
    SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY, SKIP_MIN_PREMIUM_FLOOR, RISK_DENY_SETTLEMENT
    (settlement cap), NOT_FLAT).
  - analysis/recommendations/fleet-gate-leak-ledger.jsonl `cohort=="bypass"` rows for the
    2 fleet gate_override gates (min_triggers / require_confluence_or_sequence), keyed by
    `gate_param_key`.

Filter 8 / filter 10 (bear/bull min_triggers volume-multiplier blockers) are NOT counted
here as discrete refusal waves: those blocker codes fire on the large majority of every
tick regardless of whether the tick was otherwise ENTER-eligible (verified this session:
bull_blockers code 10 fires on 4288/6068 core-decisions rows since 2026-08-01, bear code 8
on 5896/6068) -- isolating "ENTER-eligible but for this blocker alone" requires replaying
backtest/lib/filters.py's full per-side gate stack (score + every other blocker) at each
tick, not a blocker-code tally. Reported honestly as UNDERPOWERED/NOT COMPUTED rather than
force-fit into a wave count -- see the .md's explicit note.

Cross-check: every (date, wave_start_et) key in
analysis/right-tail/capture-gap-join-2026-09-05.json's 46 rows must appear in this script's
wave set (goal DONE-WHEN "strict subset by wave id").

CLI: python setup/scripts/gate_net_cost_inventory.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
GATE_LEAK_LEDGER = REPO / "analysis" / "recommendations" / "fleet-gate-leak-ledger.jsonl"
CAPTURE_GAP_JOIN = REPO / "analysis" / "right-tail" / "capture-gap-join-2026-09-05.json"
OUT_PATH = REPO / "analysis" / "gate-net-cost" / "refusals-2026-09-05.json"

WINDOW_START = "2026-08-01"
FROZEN_START = "2026-08-31"
WAVE_GAP_MINUTES = 30  # matches backtest/lib/right_tail_waves.WAVE_GAP_MINUTES

# Core-named gates from the goal's DONE-WHEN, matched against core-decisions.jsonl's own
# `verdict` (== `action` for every refusal row observed this session).
CORE_GATE_VERDICTS = {
    "SKIP_STRUCTURE_VETO": "SKIP_STRUCTURE_VETO",
    "SKIP_LATE_ENTRY": "SKIP_LATE_ENTRY",
    "SKIP_STALE_TRIGGER": "SKIP_STALE_TRIGGER",
    "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY": "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY",
    "SKIP_MIN_PREMIUM_FLOOR": "SKIP_MIN_PREMIUM_FLOOR",
    "settlement_cap": "RISK_DENY_SETTLEMENT",
    "NOT_FLAT": "NOT_FLAT",
}

FLEET_GATE_PARAM_KEYS = {"min_triggers", "require_confluence_or_sequence"}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _row_ts(row: dict[str, Any]) -> dt.datetime | None:
    ts = row.get("ts_et") or row.get("trigger_bar_et")
    if not ts:
        return None
    try:
        s = ts.replace("Z", "")
        if "+" in s[10:]:
            s = s[: s.index("+", 10)]
        return dt.datetime.fromisoformat(s.replace("T", " ") if " " not in s and "T" in s else s.split("+")[0].replace("T", " ") if False else s.replace("T", " "))
    except Exception:
        try:
            return dt.datetime.fromisoformat(ts[:19])
        except Exception:
            return None


def _row_day(row: dict[str, Any]) -> str | None:
    d = row.get("date")
    if d:
        return d
    ts = row.get("ts_et") or row.get("trigger_bar_et")
    if ts:
        return ts[:10]
    return None


def _side_from_row(row: dict[str, Any]) -> str | None:
    verdict = row.get("verdict") or ""
    action = row.get("action") or ""
    for tag in (verdict, action):
        pass
    # No explicit side on a SKIP row in every case -- infer from which blockers side fired,
    # falling back to the `side` field if present.
    if row.get("side") in ("C", "P", "BULL", "BEAR"):
        s = row["side"]
        return "C" if s in ("C", "BULL") else "P"
    return None


def _group_waves(ticks: list[tuple[dt.datetime, dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    """Same-gate, same-day episode grouping: consecutive ticks within
    WAVE_GAP_MINUTES collapse into one wave (mirrors right_tail_waves._group_into_waves,
    side-agnostic here since a single named gate's refusal ticks on one day are already a
    homogeneous population)."""
    ticks = sorted(ticks, key=lambda t: t[0])
    groups: list[list[dict[str, Any]]] = []
    last_ts: dt.datetime | None = None
    for ts, row in ticks:
        if groups and last_ts is not None and (ts - last_ts).total_seconds() / 60.0 <= WAVE_GAP_MINUTES:
            groups[-1].append(row)
        else:
            groups.append([row])
        last_ts = ts
    return groups


def inventory_core_gates() -> dict[str, Any]:
    rows = _load_jsonl(CORE_DECISIONS)
    per_gate: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    n_rows_seen = 0
    for row in rows:
        day = _row_day(row)
        if not day or day < WINDOW_START:
            continue
        verdict = row.get("verdict")
        action = row.get("action")
        for gate_id, target_verdict in CORE_GATE_VERDICTS.items():
            if verdict == target_verdict or action == target_verdict:
                ts = _row_ts(row) or dt.datetime.fromisoformat(day + " 00:00:00")
                per_gate[gate_id][day].append((ts, row))
                n_rows_seen += 1

    result: dict[str, Any] = {}
    for gate_id, by_day in per_gate.items():
        waves = []
        for day, ticks in by_day.items():
            for group in _group_waves(ticks):
                start = group[0]
                waves.append({
                    "date": day,
                    "wave_start_et": start.get("ts_et") or start.get("trigger_bar_et"),
                    "account": start.get("account"),
                    "n_ticks_in_wave": len(group),
                    "in_frozen_window": day >= FROZEN_START,
                })
        result[gate_id] = {
            "source": "core-decisions.jsonl verdict",
            "n_refusal_rows": sum(len(v) for v in by_day.values()),
            "n_waves": len(waves),
            "n_waves_frozen_window": sum(1 for w in waves if w["in_frozen_window"]),
            "waves": waves,
        }
    return result


FLEET_DECISIONS_GLOB = list((REPO / "automation" / "state" / "fleet").glob("*/decisions.jsonl"))

# Reason-string prefixes -> gate id, discovered this session by tallying every fleet arm's
# decisions.jsonl `reason` field since 2026-08-01 (fleet_executor writes these, not a fixed
# code enum) -- min_triggers/require_confluence_or_sequence never appear as a `gate_param_key`
# in fleet-gate-leak-ledger.jsonl (that ledger only instruments the 4 non-selectivity gates:
# require_bearish_fill_bar, structure_veto_enabled, block_bull_1100_1200,
# block_conf_lvl_rec_afternoon), so this is the ONLY source for the two named
# gate_override keys.
FLEET_REASON_GATES = [
    ("require_confluence_or_sequence", "gate: requires confluence/sequence"),
    ("min_triggers", "gate: 1 triggers < 2"),
    ("NOT_FLAT", "risk_gate denied:"),  # ": position already open" suffix varies by acct
    ("settlement_cap", "fleet settlement gate:"),
    ("SKIP_MIN_PREMIUM_FLOOR", "< min_entry_premium floor"),
]


def inventory_fleet_decisions_reasons() -> dict[str, Any]:
    per_gate: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for fp in FLEET_DECISIONS_GLOB:
        arm = fp.parent.name
        for row in _load_jsonl(fp):
            day = _row_day(row)
            if not day or day < WINDOW_START:
                continue
            reason = row.get("reason") or ""
            ts_raw = row.get("ts_et") or row.get("tick_id") or row.get("core_tick_id")
            for gate_id, needle in FLEET_REASON_GATES:
                if needle in reason:
                    try:
                        ts = dt.datetime.fromisoformat(str(ts_raw)[:19].replace("T", " "))
                    except Exception:
                        continue
                    per_gate[f"{gate_id}__{arm}"][day].append((ts, {**row, "arm": arm}))
                    break

    result: dict[str, Any] = {}
    for key, by_day in per_gate.items():
        waves = []
        for day, ticks in by_day.items():
            for group in _group_waves(ticks):
                start = group[0]
                waves.append({
                    "date": day,
                    "wave_start_et": start.get("ts_et") or start.get("tick_id") or start.get("core_tick_id"),
                    "arm": start.get("arm"),
                    "reason_sample": start.get("reason"),
                    "n_ticks_in_wave": len(group),
                    "in_frozen_window": day >= FROZEN_START,
                })
        result[key] = {
            "source": "fleet/<arm>/decisions.jsonl reason string",
            "n_refusal_rows": sum(len(v) for v in by_day.values()),
            "n_waves": len(waves),
            "n_waves_frozen_window": sum(1 for w in waves if w["in_frozen_window"]),
            "waves": waves,
        }
    return result


def inventory_fleet_gate_override() -> dict[str, Any]:
    rows = _load_jsonl(GATE_LEAK_LEDGER)
    per_key: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("cohort") != "bypass":
            continue
        day = row.get("date_et")
        if not day or day < WINDOW_START:
            continue
        key = row.get("gate_param_key")
        if key not in FLEET_GATE_PARAM_KEYS:
            continue
        tick_id = row.get("core_tick_id") or ""
        try:
            ts = dt.datetime.fromisoformat(tick_id.replace("T", " ")[:19])
        except Exception:
            continue
        per_key[key][day].append((ts, row))

    result: dict[str, Any] = {}
    for key, by_day in per_key.items():
        waves = []
        for day, ticks in by_day.items():
            for group in _group_waves(ticks):
                start = group[0]
                waves.append({
                    "date": day,
                    "wave_start_et": start.get("core_tick_id"),
                    "arm": start.get("arm"),
                    "gate": start.get("gate"),
                    "direction": start.get("direction"),
                    "n_ticks_in_wave": len(group),
                    "in_frozen_window": day >= FROZEN_START,
                })
        result[key] = {
            "source": "fleet-gate-leak-ledger.jsonl cohort=bypass",
            "n_refusal_rows": sum(len(v) for v in by_day.values()),
            "n_waves": len(waves),
            "n_waves_frozen_window": sum(1 for w in waves if w["in_frozen_window"]),
            "waves": waves,
        }
    return result


def cross_check_subset(core_gates: dict, fleet_gates: dict) -> dict[str, Any]:
    """Goal DONE-WHEN: the right-tail 46-missed-pair attribution's wave ids must be a
    strict subset of this inventory's wave ids."""
    if not CAPTURE_GAP_JOIN.exists():
        return {"checked": False, "reason": "capture-gap-join file missing"}
    data = json.loads(CAPTURE_GAP_JOIN.read_text(encoding="utf-8"))
    gap_rows = data.get("rows", [])

    def _parse(ts: str) -> dt.datetime | None:
        try:
            return dt.datetime.fromisoformat(ts[:19].replace("T", " "))
        except Exception:
            return None

    my_ticks_by_day: dict[str, list[dt.datetime]] = defaultdict(list)
    for gd in list(core_gates.values()) + list(fleet_gates.values()):
        for w in gd["waves"]:
            ts = _parse(w["wave_start_et"] or "")
            if ts is not None:
                my_ticks_by_day[w["date"]].append(ts)

    gap_wave_ids = sorted({(r["date"], r["wave_start_et"]) for r in gap_rows})
    missing = []
    present = []
    for day, wid in gap_wave_ids:
        gap_ts = _parse(wid)
        candidates = my_ticks_by_day.get(day, [])
        hit = gap_ts is not None and any(
            abs((gap_ts - c).total_seconds()) / 60.0 <= WAVE_GAP_MINUTES for c in candidates
        )
        (present if hit else missing).append((day, wid))
    return {
        "checked": True,
        "method": ("time-window join: a gap-ledger wave id counts as PRESENT if any "
                   f"refusal tick this script found on the same date falls within "
                   f"{WAVE_GAP_MINUTES} minutes of it (matches right_tail_waves' own "
                   "WAVE_GAP_MINUTES episode-grouping tolerance, not exact-string match)."),
        "n_gap_rows": len(gap_rows),
        "n_gap_wave_ids": len(gap_wave_ids),
        "n_present_in_my_inventory": len(present),
        "n_missing": len(missing),
        "missing_sample": missing[:15],
        "strict_subset": len(missing) == 0,
    }


def main() -> int:
    core_gates = inventory_core_gates()
    fleet_gates = inventory_fleet_gate_override()
    fleet_reason_gates = inventory_fleet_decisions_reasons()
    cross_check = cross_check_subset(
        core_gates, {**fleet_gates, **fleet_reason_gates})

    out = {
        "_doc": __doc__,
        "window": {"start": WINDOW_START, "frozen_start": FROZEN_START},
        "core_gates": core_gates,
        "fleet_gate_override": fleet_gates,
        "fleet_decisions_reason_gates": fleet_reason_gates,
        "filter_8_filter_10": {
            "status": "NOT_COMPUTED",
            "reason": ("blocker codes 8 (bear vol-multiplier) and 10 (bull vol-multiplier) "
                       "fire on the large majority of ticks regardless of other-blocker "
                       "state (bull-10: 4288/6068 rows since 2026-08-01, bear-8: 5896/6068) "
                       "-- isolating 'ENTER-eligible but for this blocker alone' requires "
                       "replaying filters.py's full per-side gate stack at each tick, out "
                       "of scope for this pass. UNVERIFIED / not in this table."),
        },
        "cross_check_vs_capture_gap_46": cross_check,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    for gid, gd in {**core_gates, **fleet_gates, **fleet_reason_gates}.items():
        print(f"  {gid}: {gd['n_refusal_rows']} rows -> {gd['n_waves']} waves "
              f"({gd['n_waves_frozen_window']} in frozen window)")
    print("cross_check:", json.dumps(cross_check, indent=2)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
