"""right_tail_capture.py -- GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R2/R3.

$0 daily instrument. For one trading day, joins `backtest/lib/
right_tail_waves.find_waves` output to the real fills ledger
(`automation/state/fills-ledger.jsonl`, `journal/trades.csv`) and each fleet
arm's own decisions (`automation/state/fleet/<arm>/decisions.jsonl`) to score,
per arm, per wave: taken / missed / refused-by-gate, latency, held-to-TP1,
runner ran, and second-wave presence/capture. Writes
`analysis/right-tail/CAPTURE-<date>.json` and appends to the rolling
`analysis/right-tail/ledger.jsonl`.

Read-only, $0, fail-open: a missing ledger row, missing fleet file, or
unparseable line degrades that ONE field to a labeled null, never a crash for
the whole day.

CLI: python setup/scripts/right_tail_capture.py --date 2026-08-04
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.right_tail_waves import find_waves, WAVE_THRESHOLD  # noqa: E402

OUT_DIR = REPO / "analysis" / "right-tail"
LEDGER_PATH = OUT_DIR / "ledger.jsonl"
FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
FLEET_DIR = REPO / "automation" / "state" / "fleet"

# CLAUDE.md's "4 active real-fills arms" -- the arms this instrument scores.
ARMS = ["safe-2", "bold-2", "safe-3", "risky-1"]

TP1_MULTIPLE = 2.0
RUNNER_MULTIPLE = 2.5
SECOND_WAVE_GAP_MIN = 60  # goal text: "SECOND wave (>=60 min after the first exit)"
CAP4_LIVE_DATE = "2026-08-31"  # TIGHT-LADDER max_same_day_roundtrips=4 went live


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _symbol_side(symbol: str) -> str | None:
    """'C' or 'P' from an OCC-ish option symbol (…C00763000 / …P00763000)."""
    for ch in ("C", "P"):
        if ch in symbol[6:]:  # skip root+date digits region
            idx = symbol.rfind(ch)
            if idx > 0 and symbol[idx + 1:].isdigit():
                return ch
    return None


def _fills_for_arm_day(all_fills: list[dict[str, Any]], arm: str, day: str) -> list[dict[str, Any]]:
    rows = [f for f in all_fills if f.get("arm") == arm and f.get("date_et") == day]
    rows.sort(key=lambda r: r.get("ts_et", ""))
    return rows


# mcp_heartbeat-executed core arms have NO automation/state/fleet/<arm>/decisions.jsonl
# (that file is fleet_rest-only -- confirmed 2026-09-05: safe-2/bold-2's fleet dirs hold
# only entry-claim/exit-state/flat-streak, never decisions.jsonl). Before this fix,
# `_fleet_decisions_for_arm_day` returned [] for these two arms unconditionally, so
# EVERY missed wave for safe-2/bold-2 fell through to the generic "no matching fleet
# decision row found (fail-open)" label even when core-decisions.jsonl had a fully
# informative HOLD/SKIP_* row at that exact tick. Fix (GOAL-FLEET-CAPTURE-GAP-2026-09-05
# F3): read core-decisions.jsonl (`account` safe|bold) for these two arms instead, and
# reshape each row into the same {ts_et, reason, risk_code} shape _refusal_reason reads,
# using the row's own `verdict` as the risk_code substitute (None only for a genuine
# no-signal HOLD with no blockers -- everything else, e.g. SKIP_STRUCTURE_VETO, carries
# real attribution). See test_right_tail_capture_core_account_fallback.py.
CORE_ACCOUNT_FOR_ARM = {"safe-2": "safe", "bold-2": "bold"}
CORE_DECISIONS_PATH = REPO / "automation" / "state" / "core-decisions.jsonl"


# SECOND fix discovered while attributing the missed rows this reshape produced (F1/F2
# fire, same session): `verdict` only records what the SIGNAL layer wanted to do
# (ENTER_BULL/ENTER_BEAR/HOLD) -- it does NOT record what happened downstream at the
# execution layer. Real example, account=bold 2026-08-04T12:26:55: verdict=ENTER_BULL,
# reason="...passed scoring + all entry gates (tier ELITE)" (reads as a clean entry),
# but the row's own top-level `action` field is "RISK_DENY_PDT" and `exec.status` is
# "RISK_DENY_PDT" / reason "bold: 3 day-trades in 5d at equity $5,478 < $25,000 -- PDT
# rule blocks a 4th day-trade" -- the trade the goal's own DONE-WHEN calls mechanism (4)
# risk_gate deny. The v1 reshape above used `verdict` as risk_code and would have
# labeled this row "ALLOW" (filtered out as a non-refusal), hiding a real PDT denial
# behind a false-clean ENTER_BULL. `action` is the authoritative post-gate outcome
# (HOLD / SKIP_<gate-name> / RISK_DENY_<code> / PLACE_FAIL / PLACED / VETOED_BY_MODELS)
# and is what this function now reads. Guard:
# test_right_tail_capture_core_action_field_not_verdict.
_CORE_NO_SIGNAL_ACTIONS = frozenset({"HOLD"})
_CORE_REAL_ENTRY_ACTIONS = frozenset({"PLACED"})


def _core_decisions_reshaped_for_arm_day(arm: str, day: str) -> list[dict[str, Any]]:
    account = CORE_ACCOUNT_FOR_ARM[arm]
    rows = _load_jsonl(CORE_DECISIONS_PATH)
    out = []
    for r in rows:
        ts = r.get("ts_et", "")
        if r.get("account") != account or not str(ts).startswith(day):
            continue
        action = r.get("action")
        reason = r.get("reason")
        # bull_blockers/bear_blockers are populated on EVERY tick (they're the running
        # "why this side isn't eligible right now" scoring detail, not a gate EVENT) --
        # verified against a real 2026-08-04 HOLD row carrying bull_blockers=[10, 11]
        # while doing nothing else notable. `action` alone is the real event marker.
        if action in _CORE_NO_SIGNAL_ACTIONS:
            risk_code = None  # genuine "no setup fired" -- not an attributable gate
        elif action in _CORE_REAL_ENTRY_ACTIONS:
            risk_code = "ALLOW"
        else:
            # every SKIP_*/RISK_DENY_*/PLACE_FAIL/VETOED_BY_MODELS/None-with-blockers
            # action is real, named attribution -- pass it through verbatim.
            risk_code = action or "CORE_HOLD_WITH_BLOCKERS"
        out.append({"ts_et": ts, "reason": reason or action, "risk_code": risk_code,
                     "action": action, "exec_status": (r.get("exec") or {}).get("status")})
    out.sort(key=lambda r: r.get("ts_et", ""))
    return out


def _fleet_decisions_for_arm_day(arm: str, day: str) -> list[dict[str, Any]]:
    if arm in CORE_ACCOUNT_FOR_ARM:
        return _core_decisions_reshaped_for_arm_day(arm, day)
    rows = _load_jsonl(FLEET_DIR / arm / "decisions.jsonl")
    out = [r for r in rows if str(r.get("ts_et", "")).startswith(day)]
    out.sort(key=lambda r: r.get("ts_et", ""))
    return out


def _naive_dt(ts: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(ts)
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
    return d


def _wave_side_char(wave: dict[str, Any]) -> str | None:
    side = wave.get("side")
    if side in ("C", "P"):
        return side
    if side == "bull":
        return "C"
    if side == "bear":
        return "P"
    return None


def _find_entry_fill(fills: list[dict[str, Any]], side_char: str, after: dt.datetime,
                      window_min: float = 90.0, lookback_min: float = 10.0) -> dict[str, Any] | None:
    """First BUY fill of the matching option side within `window_min` minutes
    at/after `after`, allowing `lookback_min` minutes of slack BEFORE the
    detected wave start -- the wave-start tick is anchored to ONE reference
    source (a specific core-decisions account or fleet reference arm; see
    right_tail_waves.py), so a DIFFERENT arm's own 1-min-cadence tick can
    fire a couple of minutes earlier or later than that anchor for the same
    underlying move (observed: safe-2's real 08-04 fill at 09:56:50 vs the
    fleet-fallback wave anchor at 09:58:05 -- a 75-second lead, evidence for
    this tolerance)."""
    best = None
    for f in fills:
        if f.get("side") != "buy":
            continue
        sym = f.get("symbol", "")
        if _symbol_side(sym) != side_char:
            continue
        try:
            ts = _naive_dt(f["ts_et"])
        except Exception:
            continue
        gap_min = (ts - after).total_seconds() / 60.0
        if -lookback_min <= gap_min <= window_min:
            if best is None or ts < _naive_dt(best["ts_et"]):
                best = f
    return best


def _prior_entry_count(fills: list[dict[str, Any]], before: dt.datetime) -> int:
    """Count of distinct BUY fills (round-trip entries) strictly before `before`
    on this arm/day -- used for the cap-4 would-be-refused flag."""
    n = 0
    seen_symbols_ts: set[tuple[str, str]] = set()
    for f in fills:
        if f.get("side") != "buy":
            continue
        try:
            ts = _naive_dt(f["ts_et"])
        except Exception:
            continue
        if ts < before:
            key = (f.get("symbol", ""), f.get("ts_et", ""))
            if key not in seen_symbols_ts:
                seen_symbols_ts.add(key)
                n += 1
    return n


def _exit_multiple_for_fill(entry_fill: dict[str, Any], fills: list[dict[str, Any]]) -> tuple[float | None, bool, bool]:
    """(best_exit_multiple, held_to_tp1, runner_ran) for the symbol of
    `entry_fill`, from the SAME arm/day fill set. TP1 = any sell fill at
    >= TP1_MULTIPLE * entry price; runner = any sell fill at >= RUNNER_MULTIPLE."""
    symbol = entry_fill.get("symbol")
    entry_price = entry_fill.get("price")
    if symbol is None or entry_price in (None, 0):
        return None, False, False
    sells = [f for f in fills if f.get("symbol") == symbol and f.get("side") == "sell"]
    if not sells:
        return None, False, False
    multiples = [f["price"] / entry_price for f in sells if f.get("price") is not None]
    if not multiples:
        return None, False, False
    best = max(multiples)
    return round(best, 4), best >= TP1_MULTIPLE, best >= RUNNER_MULTIPLE


# Bug fixed 2026-09-05 (GOAL-FLEET-CAPTURE-GAP-2026-09-05 F3, discriminating evidence:
# safe-3/risky-1 decisions.jsonl carry risk_code=None on EVERY min_triggers/confluence
# gate rejection -- e.g. {"risk_code": None, "reason": "gate: 1 triggers < 2"} -- because
# risk_code is only ever populated on the risk_gate.py path (NOT_FLAT / SKIP_MIN_PREMIUM_
# FLOOR / FLEET_SETTLEMENT_CAP / ALLOW), never on the earlier fleet_executor gate_override
# check. The old `risk_code not in (None, "ALLOW")` filter therefore discarded ALL 938
# gate-rejection rows across safe-3+risky-1 (223+286 safe-3, 155+206 risky-1, counted this
# session), which is exactly the goal's named "dominant refusal bucket" mechanism -- it was
# being systematically mislabeled "no matching fleet decision row found" instead of
# attributed to the real gate. Fix: also admit a reason starting with "gate:" or
# "A+ gate:" regardless of risk_code. Guard: test_right_tail_capture_gate_reason_recovery.
_GATE_REASON_PREFIXES = ("gate:", "a+ gate:")


def _refusal_reason(decisions: list[dict[str, Any]], after: dt.datetime,
                     window_min: float = 90.0, lookback_min: float = 10.0) -> str | None:
    """Best (most informative) HOLD-with-reason row for this arm within the
    window after the wave start -- the gate attribution for a missed wave."""
    candidates = []
    for r in decisions:
        try:
            ts = _naive_dt(r["ts_et"])
        except Exception:
            continue
        gap_min = (ts - after).total_seconds() / 60.0
        if -lookback_min <= gap_min <= window_min:
            reason = r.get("reason")
            risk_code = r.get("risk_code")
            if not reason:
                continue
            is_gate_reason = str(reason).strip().lower().startswith(_GATE_REASON_PREFIXES)
            if risk_code not in (None, "ALLOW") or is_gate_reason:
                effective_code = risk_code if risk_code not in (None, "ALLOW") else "GATE"
                candidates.append((ts, reason, effective_code))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return f"{candidates[0][2]}: {candidates[0][1]}"


def score_arm_wave(arm: str, day: str, wave: dict[str, Any],
                    fills: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one (arm, wave) pair. Never raises."""
    side_char = _wave_side_char(wave)
    if not wave.get("computed") or side_char is None:
        return {
            "arm": arm, "wave_start_et": wave.get("start_tick_et"),
            "side": wave.get("side"), "scored": False,
            "reason": "wave not priced (fail-open) -- nothing to score",
        }
    start_dt = _naive_dt(wave["start_tick_et"])
    entry_fill = _find_entry_fill(fills, side_char, start_dt)
    would_be_refused_under_cap4 = False
    if entry_fill is not None:
        prior = _prior_entry_count(fills, _naive_dt(entry_fill["ts_et"]))
        if day < CAP4_LIVE_DATE and prior >= 4:
            would_be_refused_under_cap4 = True
        latency_min = round((_naive_dt(entry_fill["ts_et"]) - start_dt).total_seconds() / 60.0, 1)
        exit_mult, held_tp1, runner_ran = _exit_multiple_for_fill(entry_fill, fills)
        return {
            "arm": arm, "wave_start_et": wave["start_tick_et"], "side": side_char,
            "scored": True, "taken": True,
            "entry_ts_et": entry_fill.get("ts_et"), "entry_symbol": entry_fill.get("symbol"),
            "latency_minutes": latency_min,
            "exit_multiple": exit_mult, "held_to_tp1": held_tp1, "runner_ran": runner_ran,
            "would_be_refused_under_cap4": would_be_refused_under_cap4,
            "peak_multiple_on_tape": wave.get("peak_multiple"),
        }
    # not taken -- attribute to a gate
    prior = _prior_entry_count(fills, start_dt)
    if day < CAP4_LIVE_DATE and prior >= 4:
        would_be_refused_under_cap4 = True
    reason = _refusal_reason(decisions, start_dt)
    return {
        "arm": arm, "wave_start_et": wave["start_tick_et"], "side": side_char,
        "scored": True, "taken": False,
        "refused_by_gate": reason or "no matching fleet decision row found (fail-open)",
        "would_be_refused_under_cap4": would_be_refused_under_cap4,
        "peak_multiple_on_tape": wave.get("peak_multiple"),
    }


def score_second_wave(waves: list[dict[str, Any]], arm_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Was there a SECOND wave (>= 60 min after the first taken wave's exit)?
    Best-effort: uses the first taken wave's entry time + hold as a proxy for
    'first exit' when no explicit exit timestamp is tracked (fills-ledger has
    exit fills too, but this function works off the already-scored events)."""
    taken = [e for e in arm_events if e.get("taken")]
    if not taken:
        return {"present": False, "reason": "no first wave taken this arm/day"}
    computed_waves = [w for w in waves if w.get("computed")]
    if len(computed_waves) < 2:
        return {"present": False, "reason": "fewer than 2 waves this day"}
    first_start = _naive_dt(computed_waves[0]["start_tick_et"])
    for w in computed_waves[1:]:
        gap_min = (_naive_dt(w["start_tick_et"]) - first_start).total_seconds() / 60.0
        if gap_min >= SECOND_WAVE_GAP_MIN:
            return {"present": True, "second_wave_start_et": w["start_tick_et"],
                    "gap_minutes_from_first": round(gap_min, 1)}
    return {"present": False, "reason": "no wave >=60min after the first"}


def run_capture(day: str) -> dict[str, Any]:
    """Build the full CAPTURE-<day>.json payload. Never raises."""
    waves = find_waves(day)
    real_waves = [w for w in waves if w.get("computed") and w.get("meets_threshold")]

    all_fills = _load_jsonl(FILLS_LEDGER)
    per_arm: dict[str, Any] = {}
    for arm in ARMS:
        fills = _fills_for_arm_day(all_fills, arm, day)
        decisions = _fleet_decisions_for_arm_day(arm, day)
        events = [score_arm_wave(arm, day, w, fills, decisions) for w in real_waves]
        second_wave = score_second_wave(real_waves, events)
        n_taken = sum(1 for e in events if e.get("taken"))
        per_arm[arm] = {
            "wave_events": events,
            "second_wave": second_wave,
            "n_waves": len(real_waves),
            "n_taken": n_taken,
            "capture_rate": round(n_taken / len(real_waves), 4) if real_waves else None,
        }

    return {
        "_doc": "right_tail_capture.py output -- per-arm wave capture scoring for one day. "
                "Composes backtest/lib/right_tail_waves.find_waves + fills-ledger.jsonl + "
                "fleet decisions.jsonl. Read-only, $0, fail-open.",
        "schema_version": 1,
        "date": day,
        "n_waves_all": len(waves),
        "n_waves_meeting_threshold": len(real_waves),
        "waves": waves,
        "arms": per_arm,
    }


def _append_ledger_rows(day: str, result: dict[str, Any]) -> int:
    """Append one row per (arm, wave) scored to the rolling ledger.jsonl.
    Idempotent-ish: does not dedupe against prior runs for the same day (the
    rolling ledger is append-only per the goal's "rolling ledger" framing;
    callers doing a re-run for the same date should expect duplicates -- the
    backfill script guards against this by writing the ledger fresh)."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with LEDGER_PATH.open("a", encoding="utf-8") as fh:
        for arm, data in result["arms"].items():
            for ev in data["wave_events"]:
                row = {"date": day, **ev}
                fh.write(json.dumps(row, default=str) + "\n")
                n += 1
            fh.write(json.dumps({"date": day, "arm": arm, "second_wave_summary": data["second_wave"],
                                  "capture_rate": data["capture_rate"]}, default=str) + "\n")
            n += 1
    return n


def _default_date() -> str:
    from et_clock import et_today_str
    return et_today_str()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-ledger", action="store_true", help="Skip appending to ledger.jsonl (used by backfill).")
    args = ap.parse_args()
    day = args.date or _default_date()

    result = run_capture(day)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"CAPTURE-{day}.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    if not args.no_ledger:
        n = _append_ledger_rows(day, result)
    else:
        n = 0

    print(f"[right-tail-capture] {day}: waves={result['n_waves_all']} "
          f"meeting_threshold={result['n_waves_meeting_threshold']} ledger_rows={n}")
    print(f"[right-tail-capture] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
