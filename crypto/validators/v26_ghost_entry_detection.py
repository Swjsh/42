"""v26_ghost_entry_detection — regression gate for heartbeat ghost entries.

Background:
  THREE distinct ghost-entry failure modes exist:

  MODE A — "symbol-ghost" (5/19 pattern): heartbeat logged ENTER but Alpaca
  confirmed zero orders placed. The ENTER decision record has symbol=None/empty,
  indicating tool-call truncation before mcp__alpaca__place_option_order executed.

  MODE B — "state-write-failure" (5/21 pattern): order f0456743 DID fill at
  10:35 ET (3×SPY735P @ $0.69, confirmed in Alpaca). BUT loop-state.json showed
  writes_today=1 / ticks_today=0 (only premarket init), and current-position.json
  remained null all day. The heartbeat thought it was flat and never managed the
  position. EOD flatten safety net closed 3 contracts at $0.01.
  This pattern = ENTER with valid symbol, no matching EXIT, and current-position
  showing null. The position was real but the state write failed.
  LIMITATION: if the EOD flatten ran and wrote an EXIT record, the Mode B check
  is masked (ENTER + EXIT + null appears like a properly-closed position). Use
  Mode C as a complementary check.

  MODE C — "loop-state-discrepancy" (5/21 pattern, complement to Mode B):
  loop-state.json shows ticks_today==0 (heartbeat never incremented tick counter)
  but decisions.jsonl contains at least one ENTER record with a valid symbol.
  Implies the state write loop failed partway through the ENTER tick. This check
  is NOT masked by EOD flatten because ticks_today is an independent counter.

  All three modes are dangerous. Mode A = phantom position in state. Mode B/C =
  real position invisible to state machine.

Modes:
  offline  Synthetic fixture covering MODE A, MODE B, and MODE C patterns.
  live     Reads decisions.jsonl + current-position.json + loop-state.json.
           Returns verdicts for all three ghost-type checks.

Offline coverage:
  MODE A:
  - Ghost ENTER: symbol=None → flagged
  - Ghost ENTER: symbol="" (empty) → flagged
  - Real ENTER: symbol="SPY260519C00738000" → not flagged
  - Non-ENTER records → never flagged

  MODE B:
  - ENTER(symbol set) + no EXIT + current_position=None → state-write-failure flagged
  - ENTER(symbol set) + matching EXIT + current_position=None → not flagged (properly closed)
  - ENTER(symbol set) + no EXIT + current_position has symbol → not flagged (position tracked)

  MODE C:
  - ENTER(symbol set) + loop_state.ticks_today==0 → discrepancy flagged
  - ENTER(symbol set) + loop_state.ticks_today==5 → not flagged (ticks ran normally)
  - No ENTER records + loop_state.ticks_today==0 → not flagged (no order placed, flat is valid)

Live coverage:
  pass=True in audit mode (historical events don't block gym).

Exit code:
  0  all tests pass
  1  any offline test fails
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_DECISIONS_PATH    = _ROOT / "automation" / "state" / "decisions.jsonl"
_CURRENT_POS_PATH  = _ROOT / "automation" / "state" / "current-position.json"
_LOOP_STATE_PATH   = _ROOT / "automation" / "state" / "loop-state.json"


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def detect_ghost_entries(decisions: list[dict]) -> list[dict]:
    """MODE A: Return ENTER records where symbol is None, absent, or empty string.

    A ghost entry is an ENTER decision that has no associated order symbol —
    meaning the Alpaca order was never confirmed after the entry reasoning fired.

    Args:
        decisions: list of decision dicts (as parsed from decisions.jsonl)

    Returns:
        Subset of decisions where action == "ENTER" AND
        (symbol is None OR symbol missing OR symbol == "")
    """
    ghosts = []
    for rec in decisions:
        action = rec.get("action", "")
        if action != "ENTER":
            continue
        symbol = rec.get("symbol")
        if symbol is None or symbol == "":
            ghosts.append(rec)
    return ghosts


def detect_state_write_failure(
    decisions: list[dict],
    current_position: dict | None,
) -> list[dict]:
    """MODE B: Detect orders that filled but state was never written.

    The 2026-05-21 failure pattern: order DID fill (symbol in decisions.jsonl)
    but loop-state.json / current-position.json were never updated. Heartbeat
    treated the session as flat all day; EOD flatten caught 3 unaccounted
    contracts at $0.01.

    Detection logic:
    1. Find ENTER records with a valid symbol (order was placed).
    2. Check whether a corresponding EXIT record exists for that symbol
       (EXIT records have action containing "EXIT" and the same symbol).
    3. If no EXIT found AND current-position status is None/null → state-write
       failure: real position invisible to the state machine.

    Returns list of ENTER records that match the state-write-failure pattern.
    """
    # Collect symbols with confirmed EXIT records
    exited_symbols: set[str] = set()
    for rec in decisions:
        action = rec.get("action", "")
        if "EXIT" in action.upper():
            sym = rec.get("symbol")
            if sym:
                exited_symbols.add(sym)

    # Check current position status (None/null = flat per state file)
    pos_symbol = None
    if isinstance(current_position, dict):
        pos_symbol = current_position.get("symbol") or current_position.get("status")

    failures = []
    for rec in decisions:
        if rec.get("action", "") != "ENTER":
            continue
        sym = rec.get("symbol")
        if not sym:
            continue  # MODE A ghost, already detected by detect_ghost_entries
        if sym in exited_symbols:
            continue  # Position properly closed — no failure
        # ENTER with valid symbol + no EXIT + state shows flat
        if pos_symbol is None or pos_symbol == "null":
            failures.append(rec)
    return failures


def detect_loop_state_discrepancy(
    decisions: list[dict],
    loop_state: dict | None,
) -> bool:
    """MODE C: Detect when loop-state.json shows zero trading ticks but ENTER exists.

    The 2026-05-21 root-cause signature: loop-state.json had writes_today=1 /
    ticks_today=0 (only premarket init ran) even though an ENTER with a valid
    symbol was present in decisions.jsonl. This means the state-write loop
    failed partway through the ENTER tick — the order was placed but the tick
    counter never incremented.

    This check is NOT masked by EOD flatten because ticks_today is incremented
    by the heartbeat loop independently of any EXIT records in decisions.jsonl.

    Args:
        decisions: list of decision dicts
        loop_state: parsed loop-state.json dict, or None if file is missing

    Returns:
        True if discrepancy detected (ticks_today==0 AND valid ENTER exists),
        False otherwise. Also returns False if loop_state is None (no data).
    """
    if loop_state is None:
        return False  # no loop-state data, cannot detect

    ticks_today = loop_state.get("ticks_today", None)
    if ticks_today is None or ticks_today != 0:
        return False  # ticks ran normally, no discrepancy

    # ticks_today == 0: check if any ENTER with valid symbol exists
    for rec in decisions:
        if rec.get("action") == "ENTER" and rec.get("symbol"):
            return True  # ENTER placed an order but no ticks counted = discrepancy
    return False


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Offline: detect ghost entries in synthetic fixture.

    Evidence basis: 2026-05-19 10:03 ET HB#11 logged ENTER_BEAR in tick-audit
    output (heartbeat-tick-audit-2026-05-19.csv row tick_id=11) but Alpaca
    confirmed zero orders placed. The live decisions.jsonl shows a real ENTER
    at 14:06 ET (tick 31) with symbol=SPY260519C00738000 — the ghost was the
    10:03 tick that never reached tool-call stage.
    """
    results: list[tuple[str, bool, str]] = []

    # --- Scenario 1: ghost ENTER — no symbol (the 5/19 10:03 ET foot-gun pattern)
    ghost = {
        "timestamp": "2026-05-19T15:03:02Z",
        "tick": 11,
        "action": "ENTER",
        "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "symbol": None,
        "entry_price": None,
    }

    # --- Scenario 2: real ENTER — has symbol (the 5/19 14:06 ET confirmed entry)
    real_enter = {
        "timestamp": "2026-05-19T18:06:21Z",
        "tick": 31,
        "action": "ENTER",
        "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "symbol": "SPY260519C00738000",
        "entry_price": 0.44,
    }

    # --- Scenario 3: empty-string symbol → also a ghost
    ghost_empty = {
        "timestamp": "2026-05-19T19:00:00Z",
        "tick": 40,
        "action": "ENTER",
        "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "symbol": "",
        "entry_price": None,
    }

    # --- Scenario 4: non-ENTER records should never be flagged
    hold = {"timestamp": "2026-05-19T14:00:00Z", "tick": 20, "action": "HOLD"}
    exit_stop = {
        "timestamp": "2026-05-19T18:20:17Z",
        "tick": 32,
        "action": "EXIT_STOP",
        "symbol": "SPY260519C00738000",
        "exit_price": 0.32,
    }

    decisions_all = [ghost, real_enter, ghost_empty, hold, exit_stop]
    ghosts = detect_ghost_entries(decisions_all)

    # T1: exactly 2 ghosts found (null symbol + empty symbol)
    t1 = len(ghosts) == 2
    results.append(("T1_ghost_count_is_2", t1, f"ghosts={len(ghosts)} expected=2"))

    # T2: the null-symbol ghost is present
    null_ghost = [g for g in ghosts if g.get("symbol") is None]
    t2 = len(null_ghost) == 1
    results.append(("T2_null_symbol_ghost_flagged", t2,
                    f"null-symbol ghosts={len(null_ghost)}"))

    # T3: the empty-string ghost is present
    empty_ghost = [g for g in ghosts if g.get("symbol") == ""]
    t3 = len(empty_ghost) == 1
    results.append(("T3_empty_symbol_ghost_flagged", t3,
                    f"empty-symbol ghosts={len(empty_ghost)}"))

    # T4: real ENTER with symbol is NOT a ghost
    real_enters = [g for g in ghosts if g.get("symbol") == "SPY260519C00738000"]
    t4 = len(real_enters) == 0
    results.append(("T4_real_enter_not_flagged", t4,
                    f"real-ENTER in ghosts={len(real_enters)} (must be 0)"))

    # T5: HOLD and EXIT_STOP are never flagged
    non_enter = [g for g in ghosts if g.get("action") != "ENTER"]
    t5 = len(non_enter) == 0
    results.append(("T5_non_enter_not_flagged", t5,
                    f"non-ENTER in ghosts={len(non_enter)} (must be 0)"))

    # T6: single-ghost fixture (just the null-symbol ghost)
    ghosts_single = detect_ghost_entries([ghost])
    t6 = len(ghosts_single) == 1 and ghosts_single[0]["tick"] == 11
    results.append(("T6_single_ghost_fixture", t6,
                    f"single fixture ghosts={len(ghosts_single)} tick={ghosts_single[0].get('tick') if ghosts_single else 'n/a'}"))

    # T7: empty input yields no ghosts
    t7 = detect_ghost_entries([]) == []
    results.append(("T7_empty_input_no_ghosts", t7, "empty list yields []"))

    # -----------------------------------------------------------------------
    # MODE B: state-write-failure detection (2026-05-21 pattern)
    # -----------------------------------------------------------------------

    # Scenario T8: ENTER with valid symbol, no EXIT, position null → should flag
    enter_no_exit = {
        "timestamp": "2026-05-21T14:35:00Z",
        "tick": 11,
        "action": "ENTER",
        "symbol": "SPY260521P00735000",
        "entry_price": 0.69,
    }
    current_pos_null = {"status": None}  # position state shows flat
    failures_t8 = detect_state_write_failure([enter_no_exit, hold, exit_stop], current_pos_null)
    t8 = len(failures_t8) == 1 and failures_t8[0]["symbol"] == "SPY260521P00735000"
    results.append(("T8_state_write_failure_detected", t8,
                    f"failures={len(failures_t8)} expected=1 (5/21 pattern)"))

    # Scenario T9: ENTER + matching EXIT + position null → should NOT flag
    exit_matching = {
        "timestamp": "2026-05-21T15:50:00Z",
        "tick": 45,
        "action": "EXIT_TP1",
        "symbol": "SPY260521P00735000",
        "exit_price": 1.00,
    }
    failures_t9 = detect_state_write_failure(
        [enter_no_exit, exit_matching], current_pos_null
    )
    t9 = len(failures_t9) == 0
    results.append(("T9_properly_closed_not_flagged", t9,
                    f"failures={len(failures_t9)} expected=0 (ENTER+EXIT = properly closed)"))

    # Scenario T10: ENTER + no EXIT + position IS tracked → should NOT flag
    current_pos_has_symbol = {"status": "open", "symbol": "SPY260521P00735000"}
    failures_t10 = detect_state_write_failure([enter_no_exit, hold], current_pos_has_symbol)
    t10 = len(failures_t10) == 0
    results.append(("T10_open_position_tracked_not_flagged", t10,
                    f"failures={len(failures_t10)} expected=0 (position properly in state)"))

    # Scenario T11: MODE A ghost (symbol=None) should NOT be double-counted by Mode B
    failures_t11 = detect_state_write_failure([ghost, ghost_empty], current_pos_null)
    t11 = len(failures_t11) == 0
    results.append(("T11_modeA_ghost_not_modeB_false_positive", t11,
                    f"failures={len(failures_t11)} expected=0 (no-symbol entries skip ModeB)"))

    # -----------------------------------------------------------------------
    # MODE C: loop-state discrepancy (5/21 root-cause: ticks_today=0 + ENTER)
    # -----------------------------------------------------------------------

    # Scenario T12: ticks_today==0 AND valid ENTER → discrepancy flagged
    loop_state_zero = {"writes_today": 1, "ticks_today": 0}
    t12 = detect_loop_state_discrepancy([enter_no_exit], loop_state_zero) is True
    results.append(("T12_zero_ticks_with_enter_flagged", t12,
                    "ticks_today=0 + valid ENTER -> discrepancy=True (5/21 pattern)"))

    # Scenario T13: ticks_today==5 AND valid ENTER → NOT flagged (ticks ran normally)
    loop_state_five = {"writes_today": 6, "ticks_today": 5}
    t13 = detect_loop_state_discrepancy([enter_no_exit], loop_state_five) is False
    results.append(("T13_normal_ticks_not_flagged", t13,
                    "ticks_today=5 + valid ENTER -> discrepancy=False (normal session)"))

    # Scenario T14: ticks_today==0 + NO valid ENTER → NOT flagged (flat day is valid)
    no_enter_decisions = [hold, {"action": "HOLD"}, {"action": "SKIP_BEARISH_G5"}]
    t14 = detect_loop_state_discrepancy(no_enter_decisions, loop_state_zero) is False
    results.append(("T14_zero_ticks_no_enter_not_flagged", t14,
                    "ticks_today=0 + no ENTER -> discrepancy=False (flat day is valid)"))

    # Scenario T15: loop_state is None → returns False gracefully
    t15 = detect_loop_state_discrepancy([enter_no_exit], None) is False
    results.append(("T15_none_loop_state_no_crash", t15,
                    "loop_state=None -> False (no data, no crash)"))

    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note} for n, p, note in results],
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

def run_live() -> dict:
    """Live: scan decisions.jsonl for ghost entries.

    Reads the real decisions.jsonl and checks all ENTER records for missing
    or null symbol fields. Returns GREEN if 0 ghosts, YELLOW if 1, RED if >1.

    This is an audit-reporting mode: pass=True regardless of ghost count,
    so gym overall_pass is not blocked by historical ghost events.
    """
    if not _DECISIONS_PATH.exists():
        return {
            "mode": "live",
            "pass": True,
            "verdict": "GREEN",
            "note": f"decisions.jsonl not found at {_DECISIONS_PATH} — no data to audit",
            "ghost_count": 0,
            "enter_count": 0,
        }

    decisions: list[dict] = []
    parse_errors = 0
    with _DECISIONS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    decisions.append(parsed)
                # non-dict JSON values (strings, arrays) are skipped silently
            except json.JSONDecodeError:
                parse_errors += 1

    enter_records = [d for d in decisions if d.get("action") == "ENTER"]
    ghosts = detect_ghost_entries(decisions)

    # MODE B: state-write-failure check — read current-position.json
    current_pos: dict | None = None
    if _CURRENT_POS_PATH.exists():
        try:
            with _CURRENT_POS_PATH.open(encoding="utf-8") as fh:
                raw_pos = json.load(fh)
                current_pos = raw_pos if isinstance(raw_pos, dict) else None
        except Exception:
            current_pos = None

    state_write_failures = detect_state_write_failure(decisions, current_pos)

    # MODE C: loop-state discrepancy check
    loop_state: dict | None = None
    if _LOOP_STATE_PATH.exists():
        try:
            with _LOOP_STATE_PATH.open(encoding="utf-8") as fh:
                raw_ls = json.load(fh)
                loop_state = raw_ls if isinstance(raw_ls, dict) else None
        except Exception:
            loop_state = None

    loop_state_discrepancy = detect_loop_state_discrepancy(decisions, loop_state)

    # Combined verdict: worst of MODE A + MODE B + MODE C
    total_issues = len(ghosts) + len(state_write_failures) + (1 if loop_state_discrepancy else 0)
    if total_issues == 0:
        verdict = "GREEN"
    elif total_issues == 1:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    ghost_summary = [
        {
            "kind": "mode_a_symbol_ghost",
            "timestamp": g.get("timestamp"),
            "tick": g.get("tick"),
            "setup_name": g.get("setup_name"),
            "symbol": g.get("symbol"),
        }
        for g in ghosts
    ]
    swf_summary = [
        {
            "kind": "mode_b_state_write_failure",
            "timestamp": f.get("timestamp"),
            "tick": f.get("tick"),
            "setup_name": f.get("setup_name"),
            "symbol": f.get("symbol"),
            "note": "Order confirmed (symbol set) but no EXIT recorded and current-position is null",
        }
        for f in state_write_failures
    ]

    ls_issue: list[dict] = []
    if loop_state_discrepancy:
        ticks = loop_state.get("ticks_today", "?") if loop_state else "?"
        ls_issue = [{
            "kind": "mode_c_loop_state_discrepancy",
            "ticks_today": ticks,
            "enter_count": len(enter_records),
            "note": (
                f"loop-state.json ticks_today={ticks} but {len(enter_records)} ENTER record(s) "
                f"exist — state write loop failed partway through ENTER tick (5/21 pattern)"
            ),
        }]

    return {
        "mode": "live",
        "pass": True,   # audit mode — presence of historical issues is evidence, not a gym block
        "verdict": verdict,
        "total_decisions": len(decisions),
        "enter_count": len(enter_records),
        "ghost_count": len(ghosts),
        "state_write_failure_count": len(state_write_failures),
        "loop_state_discrepancy": loop_state_discrepancy,
        "issues": ghost_summary + swf_summary + ls_issue,
        "parse_errors": parse_errors,
        "note": (
            f"Scanned {len(decisions)} decisions ({len(enter_records)} ENTER records). "
            f"ModeA ghosts={len(ghosts)} (symbol=None/empty). "
            f"ModeB state-write-failures={len(state_write_failures)} "
            f"(order filled, no EXIT, position null). "
            f"ModeC loop-state-discrepancy={loop_state_discrepancy} "
            f"(ticks_today=0 with ENTER present — not masked by EOD flatten). "
            f"Verdict={verdict}. pass=True (audit mode)."
        ),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc: dict = {}
    exit_code = 0

    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        r = sc["offline"]
        print(f"=== OFFLINE === {r['passed']}/{r['total']} pass  all_pass={r['all_pass']}")
        for t in r["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:<50} {t['note']}")
        if not r["all_pass"]:
            exit_code = 1

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        r = sc["live"]
        print(f"\n=== LIVE === verdict={r['verdict']}  "
              f"modeA_ghosts={r['ghost_count']}  "
              f"modeB_swf={r.get('state_write_failure_count', 0)}  "
              f"modeC_ls_discrepancy={r.get('loop_state_discrepancy', False)}  "
              f"enter_count={r['enter_count']}  pass={r['pass']}")
        for issue in r.get("issues", []):
            kind = issue.get("kind", "?")
            print(f"  [{kind.upper()}]  tick={issue.get('tick')}  "
                  f"ts={issue.get('timestamp')}  setup={issue.get('setup_name')}  "
                  f"symbol={issue.get('symbol')!r}")
            if issue.get("note"):
                print(f"    note: {issue['note']}")
        print(f"  {r['note']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
