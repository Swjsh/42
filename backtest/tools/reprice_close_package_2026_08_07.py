"""reprice_close_package_2026_08_07.py -- ONE-COMMAND evening re-price addendum for
CLOSE-PACKAGE-2026-08-07 (analysis/deep-research/CLOSE-PACKAGE-2026-08-07.md sec E).

Today's (2026-08-07) 0DTE OPRA bars land ~16:21 ET (the 403 wall). Every intraday
number for today in the close package is EST (engine premium track / SPY bars). This
runner re-prices on REAL bars and prints CONFIRM/CORRECT lines, so nothing staged gets
applied on EST-only evidence.

Steps (all read-only except its own artifacts):
  1. ET gate: refuses before 16:21 ET (et_clock.py, never Bash TZ).
  2. postfix_gate_costing --start 2026-08-07 --end 2026-08-07
     -> real-OPRA refusal costing for today's sole-blocker cohorts (incl. bull f10/f7).
  3. feed_divergence_f10_f7 --date 2026-08-07  (full-day SIP re-run over the
     PARTIAL-DAY artifact committed intraday).
  4. Prints the bull filter10/filter7 sole-blocker cells (real OPRA) next to the
     lanes' EST artifacts when present (FRIDAY-REPLAY-2026-08-07.json); missing lane
     artifacts print SKIPPED, never silently pass (C7).

Usage (after 16:21 ET):
    backtest/.venv/Scripts/python.exe backtest/tools/reprice_close_package_2026_08_07.py
    # --force skips the clock gate (testing only; labeled in output)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
ET = ZoneInfo("America/New_York")
DATE = "2026-08-07"
COSTING_OUT = ROOT / "analysis" / "recommendations" / f"gate-postfix-costing-{DATE}.json"
EST_LANE_ARTIFACTS = [
    ROOT / "analysis" / "deep-research" / f"FRIDAY-REPLAY-{DATE}.json",
    ROOT / "analysis" / "recommendations" / f"f10-f7-today-est-walk-{DATE}.json",
    ROOT / "analysis" / "recommendations" / f"f10-f7-population-battery-{DATE}.smoke.json",
]


def _et_now() -> dt.datetime:
    """Read ET via et_clock.py (rig is Mountain; Bash TZ is broken here)."""
    r = subprocess.run([sys.executable, str(ROOT / "setup" / "scripts" / "et_clock.py")],
                       capture_output=True, text=True, timeout=30)
    first = (r.stdout or "").strip().splitlines()[0]  # "2026-08-07 12:01:24 Friday EDT"
    return dt.datetime.strptime(" ".join(first.split()[:2]),
                                "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)


def _run(label: str, cmd: list[str]) -> int:
    print(f"\n=== {label} ===\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="skip the 16:21 ET clock gate (testing only)")
    args = ap.parse_args()

    now = _et_now()
    print(f"[reprice] et_clock says: {now.isoformat()}")
    if not args.force:
        if now.date() != dt.date(2026, 8, 7):
            print(f"REFUSE: built for {DATE}, clock says {now.date()} "
                  "(--force to override for testing)")
            return 3
        if now.time() < dt.time(16, 21):
            print("REFUSE: before 16:21 ET -- today's 0DTE OPRA is behind the 403 "
                  "wall; EST cells cannot be re-priced yet. Re-run after 16:21.")
            return 3
    else:
        print("[reprice] --force: CLOCK GATE SKIPPED (testing mode, results may be "
              "partial/empty before 16:21)")

    py = sys.executable
    rc1 = _run("1/2 real-OPRA refusal costing (today only)",
               [py, str(ROOT / "backtest" / "tools" / "postfix_gate_costing.py"),
                "--start", DATE, "--end", DATE, "--out", str(COSTING_OUT)])
    rc2 = _run("2/2 full-day feed divergence re-run",
               [py, str(ROOT / "backtest" / "tools" / "feed_divergence_f10_f7.py"),
                "--date", DATE])

    print("\n=== CONFIRM/CORRECT: real-OPRA vs EST ===")
    if COSTING_OUT.exists():
        d = json.loads(COSTING_OUT.read_text(encoding="utf-8"))
        pb = d.get("part_b_filter_sole_blockers", {})
        hits = {k: v for k, v in pb.items()
                if k.startswith(("bull_filter10", "bull_filter7"))}
        if not hits:
            print("  bull filter10/filter7 sole-blocker cells: NONE in costing output "
                  "-- check verdict_counts_in_window before concluding zero cost (C7)")
        for k, v in hits.items():
            print(f"  REAL {k}: n={v.get('n')} events, total=${v.get('total_dollar')}, "
                  f"exp/tr=${v.get('exp_per_trade')}, sign={v.get('sign')}")
    else:
        print(f"  SKIPPED: {COSTING_OUT.name} missing (step 1 rc={rc1})")

    for p in EST_LANE_ARTIFACTS:
        if p.exists():
            print(f"  EST artifact present for manual diff: {p}")
        else:
            print(f"  SKIPPED: EST lane artifact absent: {p.name} "
                  "(lane did not land -- diff by hand from its committed successor)")

    ok = rc1 == 0 and rc2 == 0
    print(f"\n[reprice] DONE rc=({rc1},{rc2}) -- "
          + ("numbers above supersede every EST cell in the close package"
             if ok else "PARTIAL: a step failed, do NOT treat EST cells as confirmed"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
