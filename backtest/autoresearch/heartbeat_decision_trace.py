"""Heartbeat decision trace -- per-tick filter walk diagnostic.

For a given (date, tick_id), find the matching decisions.jsonl entry AND
heartbeat-{date}.log line, then walk filter 1-11 and explain WHY each
passed/failed using the recorded state.

This is a pure DIAGNOSTIC skill (NO healing). It explains the decision
by parameterizing against `automation/state/params.json` (canonical
filter thresholds) and the recorded tick state.

USAGE:
    python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --tick 27
    python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --time 14:24
    python -m autoresearch.heartbeat_decision_trace --date 2026-05-14 --last  # most recent tick on that date

OUTPUTS:
    stdout: per-filter PASS/FAIL table + final action explanation
    automation/state/heartbeat-decision-trace-{date}-tick{N}.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DECISIONS_PATH = ROOT / "automation" / "state" / "decisions.jsonl"
PARAMS_PATH    = ROOT / "automation" / "state" / "params.json"
LOGS_DIR       = ROOT / "automation" / "state" / "logs"
OUTPUT_DIR     = ROOT / "automation" / "state"

# Filter-by-filter explanation framework. Mirrors heartbeat.md filter list.
# Each filter is (name, applies_to, eval_fn) where eval_fn returns (passed, reason).
@dataclass
class FilterResult:
    n: int
    name: str
    direction: str  # "bear", "bull", "both"
    passed: bool | None  # None if not applicable
    reason: str


def parse_decisions_jsonl() -> list[dict]:
    """decisions.jsonl is pretty-printed JSON objects; parse with brace-depth tracking."""
    if not DECISIONS_PATH.exists():
        return []
    text = DECISIONS_PATH.read_text(encoding="utf-8", errors="ignore")
    entries: list[dict] = []
    buf, depth = "", 0
    for ch in text:
        buf += ch
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and buf.strip():
                try:
                    entries.append(json.loads(buf.strip()))
                except json.JSONDecodeError:
                    pass
                buf = ""
    return entries


def find_tick(entries: list[dict], date: str, tick_id: int | None,
              time_et: str | None, last: bool) -> dict | None:
    matches = [e for e in entries if e.get("date") == date]
    if not matches:
        return None
    if last:
        return matches[-1]
    if tick_id is not None:
        for e in matches:
            if e.get("tick_id") == tick_id:
                return e
        return None
    if time_et is not None:
        for e in matches:
            if e.get("time_et") == time_et:
                return e
        return None
    return matches[-1]


def evaluate_filters(tick: dict, params: dict) -> list[FilterResult]:
    """Walk filter 1-11 against the tick's recorded state.

    Filter list (per heartbeat.md v15.1 doctrine):
      1: Time gate (entry window [09:35, 15:00) ET; outside = blocked)
      2: News blackout (high-severity event ±5min)
      3: Position-already-open (skip new entries)
      4: Daily kill-switch (-50% account loss)
      5: PDT day-trade count (under $25K = max 3 / rolling 5)
      6: Per-trade risk cap
      7: Ribbon spread (must be >= ribbon_min_spread_cents)
      8: VIX gate (8a: bull-side; 8b: bear-side)
      9: Volume multiplier (must be >= filter_9_vol_multiplier x 20-bar avg)
     10: Trigger threshold (bear >= 1, bull >= 2; level_tied required)
     11: Asymmetric direction selector (BEAR vs BULL based on stack + score)
    """
    results: list[FilterResult] = []
    time_et = tick.get("time_et", "??:??")
    bull_score = tick.get("bull_score", 0)
    bear_score = tick.get("bear_score", 0)
    spy = tick.get("spy")
    vix = tick.get("vix")
    vix_dir = tick.get("vix_dir", "")
    ribbon_stack = tick.get("ribbon_stack", "")
    ribbon_cents = tick.get("ribbon_spread_cents", 0)
    htf_stack = tick.get("htf_15m_stack")
    pos_open = bool(tick.get("position_status") not in (None, "null", "none", ""))
    filter_state = tick.get("filter_state") or {}
    bear_blocked = set(filter_state.get("bear_blocked") or [])
    bull_blocked = set(filter_state.get("bull_blocked") or [])

    no_trade_before = params.get("entry_no_trade_before_et", "09:35")
    no_trade_after  = params.get("entry_no_trade_after_et", "15:00")
    nt_window       = params.get("entry_no_trade_window_et")  # may be None
    ribbon_min      = params.get("ribbon_min_spread_cents", 30)
    vol_mult_min    = params.get("filter_9_vol_multiplier", 0.7)
    bear_trig_min   = params.get("filter_10_min_triggers_bear", 1)
    bull_trig_min   = params.get("filter_10_min_triggers_bull", 2)
    vix_bull_max    = params.get("vix_entry_thresholds", {}).get("bull_max_exclusive_or_falling", 17.20)
    vix_bear_min    = params.get("vix_entry_thresholds", {}).get("bear_min_exclusive_and_rising", 17.30)
    vix_bull_cap    = params.get("vix_entry_thresholds", {}).get("bull_hard_cap", 22.00)

    # ---- Filter 1: Time gate ----
    in_window = no_trade_before <= time_et < no_trade_after
    in_blackout = False
    if nt_window and isinstance(nt_window, list) and len(nt_window) == 2:
        in_blackout = nt_window[0] <= time_et < nt_window[1]
    f1_pass = in_window and not in_blackout
    f1_reason = (f"time_et={time_et} in entry window [{no_trade_before},{no_trade_after}) "
                 + (f"AND blackout {nt_window} active" if in_blackout else "AND no blackout active")
                 + (" -> PASS" if f1_pass else " -> BLOCK"))
    results.append(FilterResult(1, "Time gate", "both", f1_pass, f1_reason))

    # ---- Filter 2: News blackout ----
    # Cannot fully reconstruct without news.json snapshot at tick time.
    # Use the recorded reason field as a hint.
    reason_str = (tick.get("reason") or "").lower()
    f2_block_hint = "news" in reason_str or "blackout" in reason_str
    f2_pass = not f2_block_hint
    results.append(FilterResult(2, "News blackout", "both", f2_pass,
        "blocked by news (reason mentions news)" if f2_block_hint else "no news blackout indicated in reason field"))

    # ---- Filter 3: Position-already-open (only blocks NEW entries) ----
    f3_pass = not pos_open
    results.append(FilterResult(3, "Position-already-open", "both", f3_pass,
        "position open -> new entries blocked" if pos_open else "no position open -> new entries allowed"))

    # ---- Filter 4: Daily kill-switch ----
    # Recorded as PAUSED action / kill_switch_active flag -- best effort detect from action.
    action = tick.get("action") or ""
    f4_pass = action != "PAUSED"
    results.append(FilterResult(4, "Daily kill-switch", "both", f4_pass,
        "PAUSED action recorded -- kill-switch active" if not f4_pass else "no kill-switch indicator"))

    # ---- Filter 5: PDT day-trade count ----
    # Cannot reconstruct from tick alone -- best effort: assume PASS unless reason mentions PDT.
    f5_block_hint = "pdt" in reason_str or "day-trade" in reason_str
    results.append(FilterResult(5, "PDT day-trade count", "both", not f5_block_hint,
        "PDT block detected in reason" if f5_block_hint else "no PDT issue indicated"))

    # ---- Filter 6: Per-trade risk cap ----
    # Sizing-time check; ticks where size>cap rarely emit a separate filter id.
    results.append(FilterResult(6, "Per-trade risk cap", "both", True, "evaluated at sizing time -- assumed PASS"))

    # ---- Filter 7: Ribbon spread ----
    f7_pass = ribbon_cents is not None and ribbon_cents >= ribbon_min
    results.append(FilterResult(7, "Ribbon spread", "both", f7_pass,
        f"ribbon={ribbon_cents}c {'>=' if f7_pass else '<'} min={ribbon_min}c"))

    # ---- Filter 8a: VIX bull-side ----
    if vix is not None:
        vix_falling = vix_dir in ("falling", "fall")
        f8a_pass = (vix < vix_bull_max) or vix_falling
        # Also blocked if vix >= bull_hard_cap
        if vix >= vix_bull_cap:
            f8a_pass = False
        results.append(FilterResult(8, "VIX gate (bull)", "bull", f8a_pass,
            f"vix={vix} dir={vix_dir} -> "
            + ("PASS" if f8a_pass else f"BLOCK (need vix < {vix_bull_max} OR falling AND vix < {vix_bull_cap})")))

        # ---- Filter 8b: VIX bear-side ----
        vix_rising = vix_dir in ("rising", "rise")
        f8b_pass = (vix > vix_bear_min) and vix_rising
        results.append(FilterResult(8, "VIX gate (bear)", "bear", f8b_pass,
            f"vix={vix} dir={vix_dir} -> "
            + ("PASS" if f8b_pass else f"BLOCK (need vix > {vix_bear_min} AND rising)")))
    else:
        results.append(FilterResult(8, "VIX gate", "both", None, "no vix recorded -- skipped"))

    # ---- Filter 9: Volume multiplier ----
    # Not directly recorded per-tick; use blocker-list as proxy.
    f9_bear = 9 not in bear_blocked
    f9_bull = 9 not in bull_blocked
    if 9 in bear_blocked and 9 in bull_blocked:
        f9_pass = False
        f9_reason = f"vol < {vol_mult_min}x 20-bar avg -> blocked both directions"
    elif 9 in bear_blocked:
        f9_pass = False
        f9_reason = f"vol blocked bear only"
    elif 9 in bull_blocked:
        f9_pass = False
        f9_reason = f"vol blocked bull only"
    else:
        f9_pass = True
        f9_reason = f"vol >= {vol_mult_min}x 20-bar avg (no F9 in blocked list)"
    results.append(FilterResult(9, "Volume multiplier", "both", f9_pass, f9_reason))

    # ---- Filter 10: Trigger threshold ----
    f10_bear_pass = bear_score >= bear_trig_min and 10 not in bear_blocked
    f10_bull_pass = bull_score >= bull_trig_min and 10 not in bull_blocked
    results.append(FilterResult(10, "Trigger threshold (bear)", "bear", f10_bear_pass,
        f"bear_score={bear_score} {'>=' if f10_bear_pass else '<'} min={bear_trig_min} "
        + ("(level_tied required)" if params.get("filter_10_level_tied_required") else "")))
    results.append(FilterResult(10, "Trigger threshold (bull)", "bull", f10_bull_pass,
        f"bull_score={bull_score} {'>=' if f10_bull_pass else '<'} min={bull_trig_min} "
        + ("(level_tied required)" if params.get("filter_10_level_tied_required") else "")))

    # ---- Filter 11: Asymmetric direction selector ----
    bull_side_clean = all(r.passed in (True, None) for r in results if r.direction in ("both", "bull") and r.n != 11)
    bear_side_clean = all(r.passed in (True, None) for r in results if r.direction in ("both", "bear") and r.n != 11)
    if bull_side_clean and not bear_side_clean:
        f11 = "BULL eligible"
    elif bear_side_clean and not bull_side_clean:
        f11 = "BEAR eligible"
    elif bull_side_clean and bear_side_clean:
        f11 = "BOTH eligible - direction selector by ribbon stack=" + ribbon_stack
    else:
        f11 = "neither side clean - HOLD"
    results.append(FilterResult(11, "Direction selector", "both", bull_side_clean or bear_side_clean, f11))

    return results


def render_table(results: list[FilterResult]) -> str:
    lines = []
    lines.append(f"{'#':>3} {'name':<28} {'dir':<5} {'verdict':<8} reason")
    lines.append("-" * 110)
    for r in results:
        if r.passed is True:
            verdict = "PASS"
        elif r.passed is False:
            verdict = "BLOCK"
        else:
            verdict = "N/A"
        lines.append(f"{r.n:>3} {r.name:<28} {r.direction:<5} {verdict:<8} {r.reason}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--tick", type=int, help="tick_id (e.g. 27)")
    parser.add_argument("--time", help="time_et (e.g. 14:24)")
    parser.add_argument("--last", action="store_true", help="last tick on that date")
    parser.add_argument("--output-dir", help="override output dir")
    args = parser.parse_args()

    if not (args.tick or args.time or args.last):
        print("ERROR: provide --tick OR --time OR --last", file=sys.stderr)
        return 2

    if not PARAMS_PATH.exists():
        print(f"ERROR: params.json missing at {PARAMS_PATH}", file=sys.stderr)
        return 2
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))

    entries = parse_decisions_jsonl()
    if not entries:
        print(f"ERROR: no decisions parsed from {DECISIONS_PATH}", file=sys.stderr)
        return 2

    tick = find_tick(entries, args.date, args.tick, args.time, args.last)
    if tick is None:
        print(f"ERROR: no tick found for date={args.date} tick={args.tick} time={args.time} last={args.last}", file=sys.stderr)
        return 2

    results = evaluate_filters(tick, params)

    print(f"=== heartbeat-decision-trace {args.date} tick_id={tick.get('tick_id')} time_et={tick.get('time_et')} ===")
    print(f"action: {tick.get('action')}")
    print(f"recorded reason: {tick.get('reason')}")
    print(f"spy={tick.get('spy')} vix={tick.get('vix')} ({tick.get('vix_dir')}) "
          f"ribbon={tick.get('ribbon_spread_cents')}c {tick.get('ribbon_stack')} "
          f"bear={tick.get('bear_score')}/10 bull={tick.get('bull_score')}/11 htf={tick.get('htf_15m_stack')}")
    print()
    print(render_table(results))
    print()

    # Final summary
    bull_blocks = [r for r in results if r.direction in ("both", "bull") and r.passed is False]
    bear_blocks = [r for r in results if r.direction in ("both", "bear") and r.passed is False]
    print(f"BULL-side blocking filters: {[(r.n, r.name) for r in bull_blocks]}")
    print(f"BEAR-side blocking filters: {[(r.n, r.name) for r in bear_blocks]}")

    out_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    out_path = out_dir / f"heartbeat-decision-trace-{args.date}-tick{tick.get('tick_id')}.json"
    payload = {
        "skill": "heartbeat-decision-trace",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": args.date,
        "tick_id": tick.get("tick_id"),
        "time_et": tick.get("time_et"),
        "recorded_action": tick.get("action"),
        "recorded_reason": tick.get("reason"),
        "params_rule_version": params.get("rule_version"),
        "filter_results": [r.__dict__ for r in results],
        "bull_blockers": [(r.n, r.name) for r in bull_blocks],
        "bear_blockers": [(r.n, r.name) for r in bear_blocks],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
