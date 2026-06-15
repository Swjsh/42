"""v36_orb_narrow_or_gate — ORB_NARROW_OR_GATE (or_range < 2.00) regression gate.

Background:
  2026-05-21: ORB_NARROW_OR_GATE promoted to PROMISING after:
    - Walk-forward PASS (OOS/IS Sharpe ratio = 1.149, gate >= 0.50)
    - Regime scan: LONG_OR_LT2.00 → N=143, WR=88.1%, P&L=+$4,597
    - Q2-2026 concentration reduced: 85% (LONG_ALL) → 46% (NARROW_OR)
    - Positive quarters: 4/6 (LONG_ALL) → 5/6 (NARROW_OR)
    - Real-fills: covered via #5 (all J-adjacent cases are narrow)

  Gate logic (wired into orb_watcher.py 2026-05-21):
    compute_opening_range() returns None when or_range >= MAX_OR_RANGE (2.00).
    Wide ORBs never advance past NEUTRAL — the state machine has no OR data to act on.
    Only narrow ORBs (or_range < 2.00) produce WAITING_RETEST → RETEST_HELD signals.

  VIX gate was tested and FAILED: VIX>=20 is the wrong direction.
  Q2-2026 ORB signals (133 obs, all profitable) had VIX < 20.
  VIX>=20 removes profits, keeps losses (WR=34%, P&L=-$620).
  The correct discriminator is OR-range, not VIX.

  Evidence:
    analysis/backtests/orb-regime-scan/results.json
    analysis/backtests/orb-narrow-or-walkforward/results.json
    strategy/candidates/_LEADERBOARD.md (#4 ORB_NARROW_OR_GATE)

Offline tests (6 total):

  T1  or_range=1.50, direction="long" → PASSES gate (narrow long)
  T2  or_range=2.10, direction="long" → BLOCKED gate (wide long, over threshold)
  T3  or_range=2.00, direction="long" → BLOCKED gate (exactly at boundary; gate is strict <)
  T4  or_range=1.99, direction="long" → PASSES gate (just under threshold)
  T5  or_range=0.51, direction="long" → PASSES gate (minimum valid OR range)
  T6  or_range=3.50, direction="long" → BLOCKED gate (very wide OR; news-driven range)

Live tests (audit mode):
  Scan watcher-observations.jsonl for orb_watcher direction=long observations.
  Split by or_range < 2.00 vs >= 2.00.
  Report WR + P&L for each bucket. pass=True always (evidence audit, not a blocking gate).

Modes:
  offline  6 deterministic gate boundary tests. All 6 must PASS.
  live     Audit: WR split by narrow vs wide. pass=True always (informational).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

OR_RANGE_MAX: float = 2.00   # gate threshold — must match orb_narrow_or_walkforward.py


# ---------------------------------------------------------------------------
# Gate predicate (mirrors the proposed watcher addition)
# ---------------------------------------------------------------------------

def _passes_narrow_or_gate(direction: str, or_range: float) -> bool:
    """Return True if a long ORB signal passes the narrow-OR gate."""
    return direction == "long" and or_range < OR_RANGE_MAX


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    cases = [
        ("T1", 1.50, "long",  True,  "narrow long — well under threshold"),
        ("T2", 2.10, "long",  False, "wide long — over threshold"),
        ("T3", 2.00, "long",  False, "exactly at boundary — gate is strict <"),
        ("T4", 1.99, "long",  True,  "just under threshold"),
        ("T5", 0.51, "long",  True,  "minimum valid OR (MIN_RANGE_DOLLARS=0.50)"),
        ("T6", 3.50, "long",  False, "very wide OR — news/gap driven, blocked"),
    ]

    results = []
    for label, or_range, direction, expected, desc in cases:
        actual = _passes_narrow_or_gate(direction, or_range)
        ok = actual == expected
        detail = f"gate={actual} expected={expected} (or_range={or_range} direction={direction})"
        results.append({"test": label, "desc": desc, "pass": ok, "detail": detail})
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}: {desc}")
        if not ok:
            print(f"         {detail}")

    all_pass = all(r["pass"] for r in results)
    return {
        "mode": "offline",
        "pass": all_pass,
        "passed": sum(1 for r in results if r["pass"]),
        "total": len(results),
        "or_range_max": OR_RANGE_MAX,
        "tests": results,
    }


# ---------------------------------------------------------------------------
# Live tests (audit mode)
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {
            "mode": "live",
            "pass": True,
            "note": "watcher-observations.jsonl not found (no data yet)",
            "narrow_n": 0, "narrow_wr": None, "narrow_pnl": None,
            "wide_n": 0, "wide_wr": None, "wide_pnl": None,
            "total_orb_long_n": 0,
        }

    narrow: list[float] = []
    wide: list[float] = []

    with obs_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("watcher_name") != "orb_watcher":
                continue
            if row.get("direction") != "long":
                continue
            pnl = row.get("would_be_pnl_dollars")
            if pnl is None:
                continue
            meta = row.get("metadata") or {}
            or_range = meta.get("or_range", 9999.0)
            if or_range < OR_RANGE_MAX:
                narrow.append(float(pnl))
            else:
                wide.append(float(pnl))

    def _stats(pnls: list[float]) -> dict:
        if not pnls:
            return {"n": 0, "wr": None, "pnl": None}
        wins = sum(1 for p in pnls if p > 0)
        return {
            "n": len(pnls),
            "wr": round(wins / len(pnls), 4),
            "pnl": round(sum(pnls), 2),
        }

    ns = _stats(narrow)
    ws = _stats(wide)
    total = len(narrow) + len(wide)

    print(f"  [AUDIT] orb_watcher long obs: total={total}")
    print(f"          narrow (or_range<{OR_RANGE_MAX}): n={ns['n']} WR={ns['wr']:.1%} P&L={ns['pnl']:+.0f}" if ns["n"] else f"          narrow (or_range<{OR_RANGE_MAX}): n=0 (no data)")
    print(f"          wide   (or_range>={OR_RANGE_MAX}): n={ws['n']} WR={ws['wr']:.1%} P&L={ws['pnl']:+.0f}" if ws["n"] else f"          wide   (or_range>={OR_RANGE_MAX}): n=0 (no data)")

    return {
        "mode": "live",
        "pass": True,
        "note": "audit only — pass=True regardless of split (evidence check, gate wired 2026-05-21)",
        "or_range_max": OR_RANGE_MAX,
        "narrow_n": ns["n"],
        "narrow_wr": ns["wr"],
        "narrow_pnl": ns["pnl"],
        "wide_n": ws["n"],
        "wide_wr": ws["wr"],
        "wide_pnl": ws["pnl"],
        "total_orb_long_n": total,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=["offline", "live"], default="offline")
    args = parser.parse_args()

    print(f"\n[v36] ORB_NARROW_OR_GATE (or_range<{OR_RANGE_MAX}) — mode={args.mode}")
    result = run_live() if args.mode == "live" else run_offline()

    status = "PASS" if result["pass"] else "FAIL"
    if args.mode == "offline":
        print(f"\n  [{status}] {result['passed']}/{result['total']} tests passed")
    else:
        print(f"\n  [{status}] audit complete (total long obs={result['total_orb_long_n']})")
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
