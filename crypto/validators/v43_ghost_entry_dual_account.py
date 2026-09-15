"""v43_ghost_entry_dual_account — ENTER_* action audit for BOTH safe and aggressive accounts.

Background (evidence):
  2026-05-21 10:35 ET: order f0456743 filled (3×SPY735P @ $0.69, aggressive account).
  decisions.jsonl contained an ENTER record with a valid symbol, but
  current-position-bold.json remained null all day. loop-state.json showed
  writes_today=1 / ticks_today=0 (only premarket init). EOD flatten caught 3
  unaccounted contracts at $0.01 (incremental loss ~$162 above mechanical stop).

  v26_ghost_entry_detection already covers Mode A/B/C for the SAFE account
  (automation/state/decisions.jsonl). This validator extends coverage to:

  (a) Both accounts: safe (automation/state/decisions.jsonl) and aggressive
      (automation/state/aggressive/decisions.jsonl).
  (b) ENTER_* prefix matching: heartbeat may emit action="ENTER_BEAR",
      "ENTER_BULL", "ENTER_LEG2", etc. v26 only checks exact "ENTER".
      These ENTER_* variants are equally dangerous ghost-entry candidates.
  (c) Position-write confirmation.

  REPOINTED 2026-09-15 (HQ-POSITION-TRUTH, matches v26_ghost_entry_detection's
  same-day repoint): automation/state/current-position.json,
  automation/state/aggressive/current-position-bold.json, AND
  automation/state/decisions.jsonl / aggressive/decisions.jsonl are ALL dead --
  nothing has written any of them since the LLM heartbeat retired 2026-06-25.
  Evidence (this session): safe decisions.jsonl = 63 records / aggressive =
  46 records, both frozen at 2026-06-25 ticks; live run came back GREEN with
  ghost_candidates=0 not because both accounts are healthy today but because
  the position-write check compared two files that stopped changing on the
  same day, so "no discrepancy" was guaranteed regardless of what happens now.

  Position-write confirmation now compares LIVE sources instead: today's
  automation/state/fills-ledger.jsonl buy/sell fills (still written every
  trading day, keyed by fleet arm id: "safe-2" for the safe account, "bold-2"
  for the aggressive account) netted per symbol, against
  automation/state/fleet/<arm>/exit-state.json (engine's live open-position
  truth, read via setup/scripts/live_positions.read_open_positions). A symbol
  with net-open buy fills today and no exit-state.json entry (or an
  unreadable exit-state.json — LivePositionsError is a ghost candidate too,
  never coerced to "flat") is a state-write-failure ghost candidate. The
  ENTER_*-symbol-ghost check (Mode A extension, (b) above) still reads
  decisions.jsonl and remains historical-only for the same reason v26's Mode A
  does — it never depended on the position file.

Modes:
  offline  10 deterministic tests covering ENTER_* prefix matching, dual-account
           separation, and position-write confirmation logic.
  live     Audit-only: scan both decisions.jsonl files for ENTER_* actions and
           verify the corresponding position files are non-null. ghost_count
           reported; all_pass=True always (surface-only, no gym block).
  both     offline then live.

Offline coverage:
  ENTER_* prefix matching:
    T01: action="ENTER" -> qualifies as ENTER_* (exact match is a prefix)
    T02: action="ENTER_BEAR" -> qualifies as ENTER_*
    T03: action="ENTER_BULL" -> qualifies as ENTER_*
    T04: action="ENTER_LEG2" -> qualifies as ENTER_*
    T05: action="HOLD" -> does NOT qualify
    T06: action="EXIT_STOP" -> does NOT qualify

  Position-write check (repointed 2026-09-15, fills-ledger.jsonl vs exit-state.json):
    T07: net-open buy fill today, exit-state.json has no entry -> ghost candidate flagged
    T08: net-open buy fill today, exit-state.json HAS the symbol -> NOT flagged
    T09: buy fill offset by same-day sell fill (net qty <= 0) -> NOT flagged (closed)
    T10: empty fills list -> no ghost candidates, no crash
    T11: exit-state.json unreadable -> net-open buy fill flagged as unknown-state
         ghost (fail-loud, never coerced to "flat")

Live coverage:
  For safe account (automation/state/decisions.jsonl for Mode-A symbol-ghost
                    scan [historical-only, frozen 2026-06-25] + fills-ledger.jsonl
                    arm="safe-2" + fleet/safe-2/exit-state.json for the live
                    position-write check):
    - Count ENTER_* actions (exact "ENTER" or "ENTER_" prefix) in decisions.jsonl
    - Detect any ENTER_* with missing/null symbol (Mode A extension, historical)
    - Net today's safe-2 buy/sell fills per symbol; flag any net-open symbol
      absent from fleet/safe-2/exit-state.json
  For aggressive account (automation/state/aggressive/decisions.jsonl for Mode-A
                          + fills-ledger.jsonl arm="bold-2" + fleet/bold-2/exit-state.json):
    - Same checks as safe
  Reports: safe_ghost_count, aggressive_ghost_count, total_enter_star_count.
  all_pass = True always (audit-only — never blocks gym).

Exit code:
  0 — all offline tests PASS (or live-only run)
  1 — any offline test FAIL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from setup.scripts.live_positions import (  # noqa: E402
    LivePositionsError,
    read_open_positions,
)
from setup.scripts.et_clock import et_today_str  # noqa: E402

# Safe account paths (decisions.jsonl retained for the historical Mode-A
# symbol-ghost scan only — frozen since 2026-06-25, see module docstring)
_SAFE_DECISIONS    = _ROOT / "automation" / "state" / "decisions.jsonl"
_SAFE_ARM          = "safe-2"

# Aggressive account paths
_AGG_DECISIONS     = _ROOT / "automation" / "state" / "aggressive" / "decisions.jsonl"
_AGG_ARM           = "bold-2"

# Live broker-fill truth, shared by both accounts (filtered by "arm" field)
_FILLS_LEDGER_PATH = _ROOT / "automation" / "state" / "fills-ledger.jsonl"


# ---------------------------------------------------------------------------
# Core detection helpers
# ---------------------------------------------------------------------------

def is_enter_star(action: str) -> bool:
    """Return True if action is "ENTER" or starts with "ENTER_".

    v26 checks exact "ENTER" only. This function extends coverage to any
    ENTER_* variant (ENTER_BEAR, ENTER_BULL, ENTER_LEG2, etc.).
    """
    return action == "ENTER" or action.startswith("ENTER_")


def load_jsonl(path: Path) -> tuple[list[dict], int]:
    """Load a JSONL file; return (records, parse_error_count)."""
    if not path.exists():
        return [], 0
    records: list[dict] = []
    errors = 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                errors += 1
    return records, errors


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


def detect_ghost_enter_stars(
    decisions: list[dict],
    fills: list[dict],
    arm: str,
    engine_open_symbols: set[str] | None,
    engine_read_error: str | None = None,
    date_et: str | None = None,
) -> dict:
    """Scan decisions for ENTER_* symbol-ghosts (Mode A, historical) and
    fills-ledger.jsonl for state-write-failure ghosts (Mode B, repointed
    2026-09-15 — see module docstring "REPOINTED" note).

    Returns a summary dict with:
      enter_star_count: total ENTER_* actions in decisions.jsonl (historical)
      symbol_ghost_count: ENTER_* with missing/null/empty symbol (Mode A, historical)
      state_write_failures: net-open buy fills today with no matching
                            exit-state.json entry for `arm` (Mode B, live)
      details: list of flagged records
    """
    enter_star_records = [d for d in decisions if is_enter_star(d.get("action", ""))]

    # Mode A (historical): ENTER_* with no symbol, from frozen decisions.jsonl
    symbol_ghosts = [
        r for r in enter_star_records
        if not r.get("symbol")  # None, "", or missing
    ]

    # Mode B (live, repointed): net-open buy fills today vs exit-state.json
    net = net_open_qty_by_symbol(fills, arm, date_et=date_et)
    net_open_symbols = {sym: q for sym, q in net.items() if q > 0}

    state_write_failures: list[dict] = []
    for sym, qty in sorted(net_open_symbols.items()):
        if engine_open_symbols is None:
            state_write_failures.append({
                "symbol": sym, "arm": arm, "net_qty": qty,
                "kind": "exit_state_unreadable", "detail": engine_read_error,
            })
        elif sym not in engine_open_symbols:
            state_write_failures.append({
                "symbol": sym, "arm": arm, "net_qty": qty,
                "kind": "state_write_failure",
            })

    details = (
        [{"kind": "mode_a_no_symbol", "action": r.get("action"), "tick": r.get("tick"), "timestamp": r.get("timestamp")} for r in symbol_ghosts]
        + [{"kind": f.get("kind", "mode_b_state_write"), "arm": f.get("arm"), "symbol": f.get("symbol"), "net_qty": f.get("net_qty"), "detail": f.get("detail")} for f in state_write_failures]
    )

    return {
        "enter_star_count": len(enter_star_records),
        "symbol_ghost_count": len(symbol_ghosts),
        "state_write_failure_count": len(state_write_failures),
        "total_ghost_candidates": len(symbol_ghosts) + len(state_write_failures),
        "details": details,
    }


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """10 deterministic tests for ENTER_* prefix matching and position-write check."""
    results: list[dict] = []

    def assert_test(name: str, got: bool, note: str) -> None:
        passed = bool(got)
        results.append({"name": name, "passed": passed, "note": note})
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name:<50} {note}")

    # --- ENTER_* prefix matching ---

    assert_test(
        "T01_exact_ENTER_qualifies",
        is_enter_star("ENTER"),
        "action=ENTER -> is_enter_star=True",
    )
    assert_test(
        "T02_ENTER_BEAR_qualifies",
        is_enter_star("ENTER_BEAR"),
        "action=ENTER_BEAR -> is_enter_star=True",
    )
    assert_test(
        "T03_ENTER_BULL_qualifies",
        is_enter_star("ENTER_BULL"),
        "action=ENTER_BULL -> is_enter_star=True",
    )
    assert_test(
        "T04_ENTER_LEG2_qualifies",
        is_enter_star("ENTER_LEG2"),
        "action=ENTER_LEG2 -> is_enter_star=True",
    )
    assert_test(
        "T05_HOLD_does_not_qualify",
        not is_enter_star("HOLD"),
        "action=HOLD -> is_enter_star=False",
    )
    assert_test(
        "T06_EXIT_STOP_does_not_qualify",
        not is_enter_star("EXIT_STOP"),
        "action=EXIT_STOP -> is_enter_star=False",
    )

    # --- Position-write confirmation ---

    # T07: net-open buy fill today, no exit-state.json entry -> ghost candidate
    buy_fill_t7 = {
        "arm": "bold-2", "symbol": "SPY260521P00735000", "side": "buy",
        "qty": 5.0, "is_option": True, "date_et": "2026-05-21",
    }
    r7 = detect_ghost_enter_stars(
        [], [buy_fill_t7], "bold-2", engine_open_symbols=set(), date_et="2026-05-21"
    )
    assert_test(
        "T07_enter_star_no_exit_pos_null_flagged",
        r7["state_write_failure_count"] == 1,
        f"buy fill + no exit-state entry -> state_write_failures={r7['state_write_failure_count']} (expected 1)",
    )

    # T08: net-open buy fill today, exit-state.json HAS the symbol -> NOT flagged
    buy_fill_t8 = {
        "arm": "bold-2", "symbol": "SPY260522C00740000", "side": "buy",
        "qty": 5.0, "is_option": True, "date_et": "2026-05-22",
    }
    r8 = detect_ghost_enter_stars(
        [], [buy_fill_t8], "bold-2",
        engine_open_symbols={"SPY260522C00740000"}, date_et="2026-05-22",
    )
    assert_test(
        "T08_enter_star_position_open_not_flagged",
        r8["state_write_failure_count"] == 0,
        f"buy fill + exit-state entry present -> state_write_failures={r8['state_write_failure_count']} (expected 0)",
    )

    # T09: buy fill offset by a same-day sell fill (net qty <= 0) -> NOT flagged
    buy_fill_t9 = {
        "arm": "bold-2", "symbol": "SPY260523C00741000", "side": "buy",
        "qty": 5.0, "is_option": True, "date_et": "2026-05-23",
    }
    sell_fill_t9 = {
        "arm": "bold-2", "symbol": "SPY260523C00741000", "side": "sell",
        "qty": 5.0, "is_option": True, "date_et": "2026-05-23",
    }
    r9 = detect_ghost_enter_stars(
        [], [buy_fill_t9, sell_fill_t9], "bold-2",
        engine_open_symbols=set(), date_et="2026-05-23",
    )
    assert_test(
        "T09_enter_with_exit_not_flagged",
        r9["state_write_failure_count"] == 0,
        f"buy+sell nets to flat -> state_write_failures={r9['state_write_failure_count']} (expected 0; properly closed)",
    )

    # T10: empty decisions/fills lists -> no ghost candidates, no crash
    r10 = detect_ghost_enter_stars([], [], "bold-2", engine_open_symbols=set())
    assert_test(
        "T10_empty_decisions_no_crash",
        r10["enter_star_count"] == 0 and r10["total_ghost_candidates"] == 0,
        f"empty inputs -> enter_star_count={r10['enter_star_count']} ghost_candidates={r10['total_ghost_candidates']} (both 0)",
    )

    # T11: exit-state.json unreadable -> net-open buy fill flagged as
    # unknown-state ghost, never silently coerced to "flat"
    r11 = detect_ghost_enter_stars(
        [], [buy_fill_t7], "bold-2", engine_open_symbols=None,
        engine_read_error="exit-state file missing for arm 'bold-2'", date_et="2026-05-21",
    )
    assert_test(
        "T11_unreadable_exit_state_fails_loud",
        r11["state_write_failure_count"] == 1
        and r11["details"][-1]["kind"] == "exit_state_unreadable",
        f"exit-state unreadable + net-open buy fill -> state_write_failures={r11['state_write_failure_count']} (expected 1, fail-loud)",
    )

    # T12: a different arm's fill is never attributed to this arm
    r12 = detect_ghost_enter_stars(
        [], [{**buy_fill_t7, "arm": "safe-2"}], "bold-2",
        engine_open_symbols=set(), date_et="2026-05-21",
    )
    assert_test(
        "T12_other_arm_fill_not_attributed",
        r12["state_write_failure_count"] == 0,
        f"other-arm fill -> state_write_failures={r12['state_write_failure_count']} (expected 0; arm filter respected)",
    )

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    return {
        "mode": "offline",
        "tests": results,
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def _audit_account(
    decisions_path: Path,
    arm: str,
    fills: list[dict],
    date_et: str,
    label: str,
) -> dict:
    """Audit one account: Mode A (historical, decisions.jsonl) + Mode B (live,
    fills-ledger.jsonl vs fleet/<arm>/exit-state.json)."""
    decisions, parse_errors = load_jsonl(decisions_path)

    engine_open_symbols: set[str] | None
    engine_read_error: str | None = None
    try:
        engine_open_symbols = {p["symbol"] for p in read_open_positions(arm)}
    except LivePositionsError as e:
        engine_open_symbols = None
        engine_read_error = str(e)

    result = detect_ghost_enter_stars(
        decisions, fills, arm, engine_open_symbols,
        engine_read_error=engine_read_error, date_et=date_et,
    )

    print(
        f"  [AUDIT] {label} (arm={arm}): decisions={len(decisions)} enter_star={result['enter_star_count']} "
        f"ghost_candidates={result['total_ghost_candidates']} "
        f"engine_read_error={engine_read_error!r} parse_errors={parse_errors}"
    )
    if result["details"]:
        for d in result["details"][:5]:
            if d["kind"] == "mode_a_no_symbol":
                print(f"    [MODE_A_NO_SYMBOL] action={d.get('action')!r} tick={d.get('tick')} ts={d.get('timestamp')}")
            else:
                print(f"    [{d['kind'].upper()}] arm={d.get('arm')!r} symbol={d.get('symbol')!r} net_qty={d.get('net_qty')}")

    return {
        "label": label,
        "arm": arm,
        "found": bool(decisions) or bool(fills),
        "total_decisions": len(decisions),
        "parse_errors": parse_errors,
        "enter_star_count": result["enter_star_count"],
        "symbol_ghost_count": result["symbol_ghost_count"],
        "state_write_failure_count": result["state_write_failure_count"],
        "total_ghost_candidates": result["total_ghost_candidates"],
        "engine_read_error": engine_read_error,
        "details": result["details"][:10],  # cap to first 10 for scorecard size
    }


def run_live() -> dict:
    """Audit-only: Mode A (historical decisions.jsonl symbol-ghost scan) +
    Mode B (live fills-ledger.jsonl vs exit-state.json state-write-failure
    check) for both accounts.

    all_pass = True always. Ghost candidates surface as evidence but do not
    block the gym — the fix belongs in the heartbeat write path, not here.
    """
    print("\n[v43] GHOST_ENTRY_DUAL_ACCOUNT live audit")

    today_et = et_today_str()
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

    safe_result = _audit_account(_SAFE_DECISIONS, _SAFE_ARM, fills, today_et, "safe")
    agg_result  = _audit_account(_AGG_DECISIONS,  _AGG_ARM,  fills, today_et, "aggressive")

    total_enter_star = safe_result["enter_star_count"] + agg_result["enter_star_count"]
    total_ghosts = safe_result["total_ghost_candidates"] + agg_result["total_ghost_candidates"]

    if total_ghosts == 0:
        verdict = "GREEN"
    elif total_ghosts == 1:
        verdict = "YELLOW"
    else:
        verdict = "RED"

    print(
        f"\n  COMBINED: total_enter_star={total_enter_star} "
        f"ghost_candidates={total_ghosts}  verdict={verdict}"
    )
    if total_ghosts > 0:
        print(
            f"  NOTE: {total_ghosts} ghost candidate(s) — either a frozen ENTER_* "
            f"symbol-ghost (historical, decisions.jsonl pre-2026-06-25) or a "
            f"today's broker fill with no matching exit-state.json entry (live). "
            f"Foot-gun: option expiring at $0.01 vs mechanical stop (L76 pattern). "
            f"Fix belongs in heartbeat write path (state-write gate), not this validator."
        )
    else:
        print("  NOTE: No ghost candidates found in either account (historical or live).")

    return {
        "mode": "live",
        "all_pass": True,  # audit-only — never blocks gym
        "verdict": verdict,
        "date_et": today_et,
        "fills_parse_errors": fills_parse_errors,
        "safe": safe_result,
        "aggressive": agg_result,
        "total_enter_star_count": total_enter_star,
        "total_ghost_candidates": total_ghosts,
        "note": (
            f"Dual-account ghost audit (Mode A historical + Mode B live, repointed 2026-09-15). "
            f"safe_ghosts={safe_result['total_ghost_candidates']} "
            f"agg_ghosts={agg_result['total_ghost_candidates']} "
            f"verdict={verdict}. all_pass=True (audit-only)."
        ),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["offline", "live", "both"],
        default="offline",
        help="offline=ENTER_* logic tests; live=dual-account audit; both=all",
    )
    args = parser.parse_args(argv)

    print(f"\n[v43] GHOST_ENTRY_DUAL_ACCOUNT — mode={args.mode}")

    rc = 0
    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} tests passed")
        if not result["all_pass"]:
            rc = 1

    if args.mode in ("live", "both"):
        print()
        run_live()

    return rc


if __name__ == "__main__":
    sys.exit(main())
