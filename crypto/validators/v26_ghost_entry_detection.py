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

  REPOINTED 2026-09-15 (HQ-POSITION-TRUTH): automation/state/current-position.json
  and automation/state/decisions.jsonl are BOTH dead — nothing has written either
  since the LLM heartbeat retired 2026-06-25 (decisions.jsonl is frozen at its last
  2026-06-25 tick; current-position.json parses to a permanent `{"status": null}`).
  Checking ENTER-without-EXIT in decisions.jsonl against current-position.json was
  therefore evaluating two dead files against each other — permanently degenerate.
  Evidence (this session, `python -c` run against live repo state): decisions.jsonl
  has 63 records, all dated 2026-06-25, exactly 1 ENTER (tick 9, 2026-05-19 in the
  payload, frozen); ghost_count=0 / state_write_failure_count=0 came back GREEN not
  because the system is healthy today but because the one frozen ENTER happens to
  have a matching frozen EXIT — the check cannot see anything that happened after
  2026-06-25 and never will again.

  Mode B now compares LIVE sources instead: automation/state/fills-ledger.jsonl
  (broker-confirmed buy/sell fills, still written every trading day — 1349 records,
  latest today 2026-09-15) netted per arm+symbol for TODAY, against
  automation/state/fleet/<arm>/exit-state.json (the engine's live open-position
  truth, read via setup/scripts/live_positions.read_open_positions — same source
  dashboard/lib/hq-positions-pure.ts and hq_market_correlate.py already use).
  Ghost = today's net-open buy fills for a symbol > 0 but exit-state.json has no
  entry for that symbol (or is unreadable — LivePositionsError is treated as an
  unknown-state ghost candidate too, never silently coerced to "flat", per that
  module's fail-loud contract).
  LIMITATION: if the EOD flatten closes a position (broker sell fill) before the
  gym re-reads exit-state.json, that trade's ghost signal self-resolves within the
  same day it ran (netting also runs sell fills, so a since-closed fill nets to 0).
  Use Mode C as a complementary check for the loop-level failure signature.

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

  MODE B (fills-ledger vs exit-state.json, see REPOINTED note above):
  - Net-open buy fill for a symbol today + no exit-state.json entry → ghost flagged
  - Net-open buy fill + matching exit-state.json entry → not flagged (engine tracked it)
  - Buy fill fully offset by a same-day sell fill (net qty <= 0) → not flagged (closed)
  - exit-state.json unreadable (LivePositionsError) + net-open buy fill → flagged as
    unknown-state ghost candidate (fail-loud, never coerced to "flat")

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

from setup.scripts.live_positions import (  # noqa: E402
    LivePositionsError,
    read_open_positions,
)
from setup.scripts.et_clock import et_today_str  # noqa: E402

_DECISIONS_PATH    = _ROOT / "automation" / "state" / "decisions.jsonl"
_FILLS_LEDGER_PATH = _ROOT / "automation" / "state" / "fills-ledger.jsonl"
_LOOP_STATE_PATH   = _ROOT / "automation" / "state" / "loop-state.json"

# v26 tracks the single legacy "safe" account, which is fleet arm safe-2
# (the mcp_heartbeat CONTROL — see automation/state/fleet/accounts.json).
_ARM = "safe-2"


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


def net_open_qty_by_symbol(
    fills: list[dict],
    arm: str,
    date_et: str | None = None,
) -> dict[str, float]:
    """Net today's (or `date_et`'s) option buy/sell fills for `arm` into
    per-symbol quantity. Positive == broker fills alone show a net-open long
    option position for that symbol on that day (buy qty minus sell qty).
    """
    net: dict[str, float] = {}
    for rec in fills:
        if not isinstance(rec, dict):
            continue
        if rec.get("arm") != arm:
            continue
        if not rec.get("is_option"):
            continue
        if date_et is not None and rec.get("date_et") != date_et:
            continue
        sym = rec.get("symbol")
        if not sym:
            continue
        qty = rec.get("qty") or 0
        side = str(rec.get("side") or "").lower()
        if side == "buy":
            net[sym] = net.get(sym, 0) + qty
        elif side == "sell":
            net[sym] = net.get(sym, 0) - qty
    return net


def detect_state_write_failure(
    fills: list[dict],
    arm: str,
    engine_open_symbols: set[str] | None,
    engine_read_error: str | None = None,
    date_et: str | None = None,
) -> list[dict]:
    """MODE B (repointed 2026-09-15): Detect broker fills invisible to the engine.

    The 2026-05-21 failure pattern generalized: a symbol filled at the broker
    (fills-ledger.jsonl) but the engine's live open-position truth
    (automation/state/fleet/<arm>/exit-state.json, read via
    setup/scripts/live_positions.read_open_positions) never recorded it.

    Detection logic:
    1. Net today's buy/sell fills for `arm` per symbol.
    2. A symbol with net-open qty > 0 is "broker shows this open".
    3. If that symbol has no entry in `engine_open_symbols` -> state-write
       failure: real position invisible to the engine's state.
    4. If `engine_open_symbols` is None (exit-state.json was unreadable --
       LivePositionsError), EVERY net-open symbol is flagged as an
       unknown-state ghost candidate. Fail-loud: an unreadable state file is
       never treated as evidence of "flat" (matches live_positions.py's own
       contract).

    Returns list of ghost-candidate dicts: {symbol, arm, net_qty, kind}.
    """
    net = net_open_qty_by_symbol(fills, arm, date_et=date_et)
    net_open_symbols = {sym: q for sym, q in net.items() if q > 0}
    if not net_open_symbols:
        return []

    failures: list[dict] = []
    for sym, qty in sorted(net_open_symbols.items()):
        if engine_open_symbols is None:
            failures.append({
                "symbol": sym, "arm": arm, "net_qty": qty,
                "kind": "exit_state_unreadable",
                "detail": engine_read_error,
            })
        elif sym not in engine_open_symbols:
            failures.append({
                "symbol": sym, "arm": arm, "net_qty": qty,
                "kind": "state_write_failure",
            })
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
    # MODE B: state-write-failure detection — repointed 2026-09-15 to
    # fills-ledger.jsonl (broker truth) vs exit-state.json (engine truth,
    # via live_positions.read_open_positions). See module docstring.
    # -----------------------------------------------------------------------

    # Retained for MODE C tests below (loop-state discrepancy still keys off
    # decisions.jsonl ENTER records — that check was never position-file-based).
    enter_no_exit = {
        "timestamp": "2026-05-21T14:35:00Z",
        "tick": 11,
        "action": "ENTER",
        "symbol": "SPY260521P00735000",
        "entry_price": 0.69,
    }

    # Scenario T8: buy fill today, no matching exit-state.json entry → should flag
    buy_fill = {
        "arm": "safe-2", "symbol": "SPY260521P00735000", "side": "buy",
        "qty": 3.0, "is_option": True, "date_et": "2026-05-21",
    }
    failures_t8 = detect_state_write_failure(
        [buy_fill], "safe-2", engine_open_symbols=set(), date_et="2026-05-21"
    )
    t8 = len(failures_t8) == 1 and failures_t8[0]["symbol"] == "SPY260521P00735000"
    results.append(("T8_state_write_failure_detected", t8,
                    f"failures={len(failures_t8)} expected=1 (broker fill, engine blind to it)"))

    # Scenario T9: buy fill fully offset by a same-day sell fill → should NOT flag
    sell_fill = {
        "arm": "safe-2", "symbol": "SPY260521P00735000", "side": "sell",
        "qty": 3.0, "is_option": True, "date_et": "2026-05-21",
    }
    failures_t9 = detect_state_write_failure(
        [buy_fill, sell_fill], "safe-2", engine_open_symbols=set(), date_et="2026-05-21"
    )
    t9 = len(failures_t9) == 0
    results.append(("T9_properly_closed_not_flagged", t9,
                    f"failures={len(failures_t9)} expected=0 (buy+sell nets to flat)"))

    # Scenario T10: buy fill + exit-state.json DOES have the symbol → should NOT flag
    failures_t10 = detect_state_write_failure(
        [buy_fill], "safe-2",
        engine_open_symbols={"SPY260521P00735000"}, date_et="2026-05-21",
    )
    t10 = len(failures_t10) == 0
    results.append(("T10_open_position_tracked_not_flagged", t10,
                    f"failures={len(failures_t10)} expected=0 (position properly in exit-state.json)"))

    # Scenario T11: exit-state.json unreadable (engine_open_symbols=None) →
    # net-open buy fill flagged as unknown-state ghost, not silently "flat"
    failures_t11 = detect_state_write_failure(
        [buy_fill], "safe-2", engine_open_symbols=None,
        engine_read_error="exit-state file missing for arm 'safe-2'", date_et="2026-05-21",
    )
    t11 = len(failures_t11) == 1 and failures_t11[0]["kind"] == "exit_state_unreadable"
    results.append(("T11_unreadable_exit_state_fails_loud", t11,
                    f"failures={len(failures_t11)} expected=1 (fail-loud, never coerced to flat)"))

    # Scenario T11b: different arm's fill is never attributed to this arm
    failures_t11b = detect_state_write_failure(
        [{**buy_fill, "arm": "bold-2"}], "safe-2",
        engine_open_symbols=set(), date_et="2026-05-21",
    )
    t11b = len(failures_t11b) == 0
    results.append(("T11b_other_arm_fill_not_attributed", t11b,
                    f"failures={len(failures_t11b)} expected=0 (arm filter respected)"))

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

    # MODE B (repointed 2026-09-15): fills-ledger.jsonl (broker truth, today)
    # vs exit-state.json (engine truth, via live_positions). decisions.jsonl
    # and current-position.json are both frozen at 2026-06-25 and are no
    # longer read here — see module docstring "REPOINTED" note.
    fills: list[dict] = []
    fills_parse_errors = 0
    if _FILLS_LEDGER_PATH.exists():
        with _FILLS_LEDGER_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed_fill = json.loads(line)
                    if isinstance(parsed_fill, dict):
                        fills.append(parsed_fill)
                except json.JSONDecodeError:
                    fills_parse_errors += 1

    today_et = et_today_str()
    engine_open_symbols: set[str] | None
    engine_read_error: str | None = None
    try:
        engine_open_symbols = {p["symbol"] for p in read_open_positions(_ARM)}
    except LivePositionsError as e:
        engine_open_symbols = None
        engine_read_error = str(e)

    state_write_failures = detect_state_write_failure(
        fills, _ARM, engine_open_symbols,
        engine_read_error=engine_read_error, date_et=today_et,
    )

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
            "kind": f.get("kind", "mode_b_state_write_failure"),
            "arm": f.get("arm"),
            "symbol": f.get("symbol"),
            "net_qty": f.get("net_qty"),
            "date_et": today_et,
            "note": (
                f.get("detail")
                or "Broker fill shows net-open qty today but exit-state.json has no entry for this symbol"
            ),
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
        "fills_parse_errors": fills_parse_errors,
        "arm": _ARM,
        "date_et": today_et,
        "engine_read_error": engine_read_error,
        "note": (
            f"Scanned {len(decisions)} FROZEN decisions.jsonl records (2026-06-25 and earlier; "
            f"{len(enter_records)} ENTER). ModeA ghosts={len(ghosts)} (symbol=None/empty, "
            f"historical-only — decisions.jsonl has not been written since 2026-06-25). "
            f"ModeB state-write-failures={len(state_write_failures)} "
            f"(arm={_ARM}, date={today_et}: broker fills-ledger.jsonl net-open buy fills with "
            f"no matching exit-state.json entry"
            + (f"; exit-state read error: {engine_read_error}" if engine_read_error else "")
            + "). "
            f"ModeC loop-state-discrepancy={loop_state_discrepancy} "
            f"(ticks_today=0 with frozen ENTER present, historical-only). "
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
