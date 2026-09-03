"""tick_freshness_audit.py -- READ-ONLY detector for TICK-FRESHNESS-VALIDATION-2026-08-20
(automation/overnight/queue.md).

WHAT THIS PROVES: whether the "tick validation lacks a timestamp-freshness check" gap
gamma_manager flagged (T-OPEN-TICK-STALE-QUOTE-2026-08-20, 71 duplicate escalations,
generic reason string, no attached evidence) ever actually bites in the real ledger.

INVESTIGATION FINDING (this fire, verified against current code -- not assumed):
  1. A genuine TIMESTAMP-based freshness measurement already exists and is logged on
     EVERY row: setup/scripts/heartbeat_core.py::_trigger_bar_stale (dict form, ~line
     1478) writes `bar_freshness: {checked, bar_et, age_min, prior_session, stale}` onto
     every core-decisions.jsonl row via the `"bar_freshness": _trigger_bar_stale(bc)`
     call at ~line 1718. Threshold: TRIGGER_BAR_MAX_AGE_MIN = 20.0 (~4 bars).
  2. That measurement is DELIBERATELY NOT wired into the entry gate -- heartbeat_core.py's
     own `_is_blind` docstring (~line 1538) says so explicitly: "Freshness IS now
     genuinely measured and logged on every row (`bar_freshness`...). Turning that
     measurement into a BLOCK is a live behaviour change with real blast radius, so it
     needs OP-11 evidence and an injected clock ... Queue: T-OPEN-TICK-STALE-QUOTE-2026-
     08-20 stays open for that decision." -- i.e. this exact queue item is the tracked
     decision point for whether bar_freshness.stale should become a veto.
  3. A SEPARATE, already-gating guard exists and DOES block entries on a stale sight:
     `_sight_staleness_check` / SIGHT_STALENESS_MAX_DIVERGENCE_USD ($1.00) cross-checks
     the trigger bar's price against a live tick-level quote (Alpaca latest-trade) at the
     moment of an actual entry attempt, and emits SKIP_STALE_SIGHT on divergence. This is
     PRICE-divergence based, not TIME-based, and is thoroughly tested
     (backtest/tests/test_sight_staleness_guard.py, ~30 cases). It does not, however,
     validate the freshness of the live tick-level quote ITSELF (Alpaca's trade
     timestamp `t` field is never read -- only the price `p`).
  4. The quantitative claims in the incident's own "validation" report
     (analysis/manager/2026-08-23-0233-...md: "$-1,569 scar", "09:27 bar used at
     09:30:00.123") are FLAGGED FABRICATED by this repo's own worker_output_verify.py
     ([!DANGER] QUARANTINED banner, "names files/commits that do not exist") -- there is
     no real incident evidence behind those numbers.

heartbeat_core.py, filters.py, risk_gate.py etc. are FROZEN for this session (cannot wire
bar_freshness into a gate here). This script is the read-only instrument that answers
"does the measured gap (bar_freshness.age_min > 2 bars, same-session) ever actually occur
in the live ledger" so that decision can be made with real numbers instead of a fabricated
narrative. Bundle-item spec for turning it into a gate is recorded in queue.md alongside
this item's closure note.

Run: backtest/.venv/Scripts/python.exe setup/scripts/tick_freshness_audit.py
     backtest/.venv/Scripts/python.exe setup/scripts/tick_freshness_audit.py --sessions 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

BAR_MINUTES = 5.0          # the engine's bar size (5m ribbon/trigger bars)
BARS_THRESHOLD = 2         # "> 2 bars" per the queue item's own freshness rule
AGE_MIN_THRESHOLD = BAR_MINUTES * BARS_THRESHOLD  # 10.0 minutes


def _iter_rows(path: Path):
    """Yield parsed JSON rows, skipping any malformed line (append-only ledger, never
    raise on one bad line -- same discipline as loop_state_refresh.derive_ticks)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    yield json.loads(ln)
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError as exc:
        print(f"tick_freshness_audit: cannot read {path} ({exc})", file=sys.stderr)


def audit(path: Path = CORE_DECISIONS, n_sessions: int = 5) -> dict:
    """Group rows by session date (rows carry a `date` field; fall back to ts_et[:10]),
    take the LAST n_sessions distinct dates present in the file, and for each count rows
    whose bar_freshness age exceeds BARS_THRESHOLD bars WITHIN THE SAME SESSION
    (prior_session rows are a separate, already-gated case -- _stale_trigger_bar already
    blocks those at the entry gate; counting them here would double-count a covered gap).
    """
    by_date: dict[str, list[dict]] = {}
    for row in _iter_rows(path):
        date = row.get("date") or str(row.get("ts_et", ""))[:10]
        if not date:
            continue
        by_date.setdefault(date, []).append(row)

    dates = sorted(by_date.keys())[-n_sessions:]
    sessions = []
    for date in dates:
        rows = by_date[date]
        n_ticks = len(rows)
        n_checked = 0
        n_stale_same_session = 0
        n_prior_session = 0
        worst_age_min = 0.0
        worst_row = None
        for row in rows:
            bf = row.get("bar_freshness")
            if not isinstance(bf, dict) or not bf.get("checked"):
                continue
            n_checked += 1
            if bf.get("prior_session"):
                n_prior_session += 1
                continue  # already covered by the existing _stale_trigger_bar entry gate
            age_min = bf.get("age_min")
            if not isinstance(age_min, (int, float)):
                continue
            if age_min > AGE_MIN_THRESHOLD:
                n_stale_same_session += 1
                if age_min > worst_age_min:
                    worst_age_min = age_min
                    worst_row = {"ts_et": row.get("ts_et"), "account": row.get("account"),
                                 "action": row.get("action"), "bar_et": bf.get("bar_et"),
                                 "age_min": age_min}
        sessions.append({
            "date": date, "n_ticks": n_ticks, "n_checked": n_checked,
            "n_prior_session_stale": n_prior_session,
            "n_same_session_stale_gt_2bars": n_stale_same_session,
            "worst_same_session_gap": worst_row,
        })
    total_gap_ticks = sum(s["n_same_session_stale_gt_2bars"] for s in sessions)
    return {
        "threshold_bars": BARS_THRESHOLD, "threshold_minutes": AGE_MIN_THRESHOLD,
        "n_sessions_scanned": len(sessions), "sessions": sessions,
        "total_same_session_stale_ticks": total_gap_ticks,
        "verdict": ("GAP OBSERVED -- same-session bar age exceeded 2 bars at least once"
                    if total_gap_ticks else
                    "NO GAP OBSERVED in this window -- same-session bar age never exceeded "
                    "2 bars (prior-session staleness is separately gated already)"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=int, default=5,
                    help="number of most-recent sessions to scan (default 5)")
    ap.add_argument("--path", type=Path, default=CORE_DECISIONS)
    args = ap.parse_args()

    result = audit(args.path, args.sessions)
    print(f"tick_freshness_audit: {result['n_sessions_scanned']} sessions scanned, "
          f"threshold=>{result['threshold_bars']} bars (>{result['threshold_minutes']:.0f}m)")
    for s in result["sessions"]:
        flag = "  <-- GAP" if s["n_same_session_stale_gt_2bars"] else ""
        print(f"  {s['date']}: n_ticks={s['n_ticks']:4d} checked={s['n_checked']:4d} "
              f"prior_session_stale={s['n_prior_session_stale']:3d} "
              f"same_session_gt_2bars={s['n_same_session_stale_gt_2bars']:3d}{flag}")
        if s["worst_same_session_gap"]:
            w = s["worst_same_session_gap"]
            print(f"      worst: {w['ts_et']} {w['account']} action={w['action']} "
                  f"bar_et={w['bar_et']} age_min={w['age_min']:.2f}")
    print(f"TOTAL same-session >2-bar ticks across window: {result['total_same_session_stale_ticks']}")
    print(f"VERDICT: {result['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
