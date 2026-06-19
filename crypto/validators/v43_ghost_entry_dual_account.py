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
  (c) Position-write confirmation: after any ENTER_* tick the corresponding
      current-position-bold.json (aggressive) or current-position.json (safe)
      must be non-null. If position file shows null/flat after the last ENTER_*,
      it is a ghost candidate.

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

  Position-write check:
    T07: last ENTER_* in ledger, position file null -> ghost candidate flagged
    T08: last ENTER_* in ledger, position file has status="open" -> NOT flagged
    T09: last ENTER_* + subsequent EXIT_* in ledger, position null -> NOT flagged
         (position was properly managed — EXIT closed it)
    T10: empty decisions list -> no ghost candidates, no crash

Live coverage:
  For safe account (automation/state/decisions.jsonl +
                    automation/state/current-position.json):
    - Count ENTER_* actions (exact "ENTER" or "ENTER_" prefix)
    - Detect any ENTER_* with missing/null symbol (Mode A extension)
    - If last ENTER_* has no subsequent EXIT_* and position file is null -> flag
  For aggressive account (automation/state/aggressive/decisions.jsonl +
                          automation/state/aggressive/current-position-bold.json):
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

# Safe account paths
_SAFE_DECISIONS    = _ROOT / "automation" / "state" / "decisions.jsonl"
_SAFE_POSITION     = _ROOT / "automation" / "state" / "current-position.json"

# Aggressive account paths
_AGG_DECISIONS     = _ROOT / "automation" / "state" / "aggressive" / "decisions.jsonl"
_AGG_POSITION      = _ROOT / "automation" / "state" / "aggressive" / "current-position-bold.json"


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


def load_position(path: Path) -> dict | None:
    """Load current-position JSON; return None on missing/malformed."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def detect_ghost_enter_stars(
    decisions: list[dict],
    position: dict | None,
) -> dict:
    """Scan decisions for ENTER_* ghost candidates.

    Returns a summary dict with:
      enter_star_count: total ENTER_* actions in ledger
      symbol_ghost_count: ENTER_* with missing/null/empty symbol (Mode A extension)
      state_write_failures: ENTER_* records with valid symbol, no subsequent EXIT_*,
                            and position file showing null/flat (Mode B extension)
      details: list of flagged records
    """
    enter_star_records = [d for d in decisions if is_enter_star(d.get("action", ""))]

    # Mode A extension: ENTER_* with no symbol
    symbol_ghosts = [
        r for r in enter_star_records
        if not r.get("symbol")  # None, "", or missing
    ]

    # Build set of exited symbols from any EXIT_* action
    exited_symbols: set[str] = set()
    for rec in decisions:
        action = rec.get("action", "")
        if action.startswith("EXIT") and rec.get("symbol"):
            exited_symbols.add(rec["symbol"])

    # Mode B extension: ENTER_* with valid symbol, no EXIT_*, position null
    pos_status = None
    pos_symbol = None
    if isinstance(position, dict):
        pos_status = position.get("status")
        pos_symbol = position.get("symbol")

    position_null = (pos_status is None or str(pos_status).lower() in ("null", "none", "flat", ""))
    if pos_symbol:
        position_null = False  # position has an active symbol — not null

    state_write_failures = []
    for rec in enter_star_records:
        sym = rec.get("symbol")
        if not sym:
            continue  # already in symbol_ghosts (Mode A)
        if sym in exited_symbols:
            continue  # properly closed
        if position_null:
            state_write_failures.append(rec)

    details = (
        [{"kind": "mode_a_no_symbol", "action": r.get("action"), "tick": r.get("tick"), "timestamp": r.get("timestamp")} for r in symbol_ghosts]
        + [{"kind": "mode_b_state_write", "action": r.get("action"), "symbol": r.get("symbol"), "tick": r.get("tick"), "timestamp": r.get("timestamp")} for r in state_write_failures]
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

    # T07: last ENTER_BEAR in ledger, no EXIT, position null -> ghost candidate
    decisions_t7 = [
        {"action": "HOLD", "timestamp": "2026-05-21T14:00:00Z", "tick": 5},
        {"action": "ENTER_BEAR", "timestamp": "2026-05-21T14:35:00Z", "tick": 11,
         "symbol": "SPY260521P00735000", "entry_price": 0.69},
    ]
    pos_null = {"status": None}
    r7 = detect_ghost_enter_stars(decisions_t7, pos_null)
    assert_test(
        "T07_enter_star_no_exit_pos_null_flagged",
        r7["state_write_failure_count"] == 1,
        f"ENTER_BEAR + pos_null + no EXIT -> state_write_failures={r7['state_write_failure_count']} (expected 1)",
    )

    # T08: ENTER_BULL, position shows status=open -> NOT flagged
    decisions_t8 = [
        {"action": "ENTER_BULL", "timestamp": "2026-05-22T10:30:00Z", "tick": 8,
         "symbol": "SPY260522C00740000", "entry_price": 1.10},
    ]
    pos_open = {"status": "open", "symbol": "SPY260522C00740000"}
    r8 = detect_ghost_enter_stars(decisions_t8, pos_open)
    assert_test(
        "T08_enter_star_position_open_not_flagged",
        r8["state_write_failure_count"] == 0,
        f"ENTER_BULL + pos_open -> state_write_failures={r8['state_write_failure_count']} (expected 0)",
    )

    # T09: ENTER + subsequent EXIT_TP1 + position null -> NOT flagged (properly managed)
    decisions_t9 = [
        {"action": "ENTER", "timestamp": "2026-05-23T10:00:00Z", "tick": 6,
         "symbol": "SPY260523C00741000", "entry_price": 0.80},
        {"action": "EXIT_TP1", "timestamp": "2026-05-23T11:00:00Z", "tick": 20,
         "symbol": "SPY260523C00741000", "exit_price": 1.10},
    ]
    pos_null2 = {"status": None}
    r9 = detect_ghost_enter_stars(decisions_t9, pos_null2)
    assert_test(
        "T09_enter_with_exit_not_flagged",
        r9["state_write_failure_count"] == 0,
        f"ENTER + EXIT_TP1 -> state_write_failures={r9['state_write_failure_count']} (expected 0; properly closed)",
    )

    # T10: empty decisions list -> no ghost candidates, no crash
    r10 = detect_ghost_enter_stars([], None)
    assert_test(
        "T10_empty_decisions_no_crash",
        r10["enter_star_count"] == 0 and r10["total_ghost_candidates"] == 0,
        f"empty decisions -> enter_star_count={r10['enter_star_count']} ghost_candidates={r10['total_ghost_candidates']} (both 0)",
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
    position_path: Path,
    label: str,
) -> dict:
    """Audit one account for ENTER_* ghost candidates."""
    decisions, parse_errors = load_jsonl(decisions_path)
    position = load_position(position_path)

    if not decisions:
        note = f"{label}: no decisions found at {decisions_path}"
        print(f"  [SKIP] {note}")
        return {
            "label": label,
            "found": False,
            "enter_star_count": 0,
            "total_ghost_candidates": 0,
            "details": [],
            "note": note,
        }

    result = detect_ghost_enter_stars(decisions, position)

    pos_status = position.get("status") if isinstance(position, dict) else None
    print(
        f"  [AUDIT] {label}: decisions={len(decisions)} enter_star={result['enter_star_count']} "
        f"ghost_candidates={result['total_ghost_candidates']} "
        f"pos_status={pos_status!r} parse_errors={parse_errors}"
    )
    if result["details"]:
        for d in result["details"][:5]:
            print(
                f"    [{d['kind'].upper()}] action={d.get('action')!r} "
                f"symbol={d.get('symbol')!r} tick={d.get('tick')} ts={d.get('timestamp')}"
            )

    return {
        "label": label,
        "found": True,
        "total_decisions": len(decisions),
        "parse_errors": parse_errors,
        "enter_star_count": result["enter_star_count"],
        "symbol_ghost_count": result["symbol_ghost_count"],
        "state_write_failure_count": result["state_write_failure_count"],
        "total_ghost_candidates": result["total_ghost_candidates"],
        "position_status": pos_status,
        "details": result["details"][:10],  # cap to first 10 for scorecard size
    }


def run_live() -> dict:
    """Audit-only: scan both account decisions ledgers for ENTER_* ghost candidates.

    all_pass = True always. Historical ghost events surface as evidence but
    do not block the gym (they are unfixable retroactively — the fix is in
    the heartbeat write path, not the validator).
    """
    print("\n[v43] GHOST_ENTRY_DUAL_ACCOUNT live audit")

    safe_result   = _audit_account(_SAFE_DECISIONS, _SAFE_POSITION,   "safe")
    agg_result    = _audit_account(_AGG_DECISIONS,  _AGG_POSITION,    "aggressive")

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
            f"  NOTE: {total_ghosts} ghost candidate(s) — "
            f"ENTER_* with no subsequent EXIT_* and position null. "
            f"Foot-gun: option expiring at $0.01 vs mechanical stop (L76 pattern). "
            f"Fix belongs in heartbeat write path (state-write gate), not this validator."
        )
    else:
        print("  NOTE: No ENTER_* ghost candidates found in either account ledger.")

    return {
        "mode": "live",
        "all_pass": True,  # audit-only — never blocks gym
        "verdict": verdict,
        "safe": safe_result,
        "aggressive": agg_result,
        "total_enter_star_count": total_enter_star,
        "total_ghost_candidates": total_ghosts,
        "note": (
            f"Dual-account ENTER_* ghost audit. "
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
