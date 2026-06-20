"""v17_entry_gate_timing — verify the 09:35 ET entry gate + R2 bar-age guard.

Mirrors `automation/state/params.json` (v15.1):
  entry_no_trade_before_et: 09:35
  entry_no_trade_after_et:  15:00
  entry_no_trade_window_et: null (mid-day blackout REMOVED v15.1)

Plus the R2 closed-bar guard from
`markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md`: a trigger bar must be closed
(bar_open + 5min <= now) before its trigger is acted on.

Offline tests (T1-T12):
  T1  09:32 ET   -> reject (before_open)
  T2  09:34:59   -> reject (before_open)
  T3  09:35:00   -> accept (boundary inclusive)
  T4  09:36:00   -> accept
  T5  10:30:00   -> accept (mid-morning)
  T6  14:30:00   -> accept (v15.1 no mid-day blackout)
  T7  14:59:59   -> accept (last second before cutoff)
  T8  15:00:00   -> reject (after_close, boundary exclusive)
  T9  15:30:00   -> reject (well past cutoff)
  T10 R2 guard — 09:55 bar at 09:59:30 ET -> reject (bar_in_progress)
  T11 R2 guard — 09:55 bar at 10:00:00 ET -> accept (bar closed)
  T12 Legacy v14 with mid-day window 14:00-15:00 -> 14:30 rejects (regression check)

Live mode: pull current ET, compute gate decision against v15.1 thresholds.
Foot-gun this prevents: entry fires before 09:35 ET or past 15:00 ET; closed-bar
guard misfires on an in-progress bar.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.entry_gate import check_entry_gate


def run_offline() -> dict:
    results = []

    # T1: 09:32 ET — before the 09:35 cutoff
    d = check_entry_gate("09:32")
    results.append(("T1_09_32_before_open", not d.passed and d.reason == "before_open",
                    f"passed={d.passed} reason={d.reason}"))

    # T2: 09:34:59 — one second before boundary
    d = check_entry_gate("09:34:59")
    results.append(("T2_09_34_59_before_open", not d.passed and d.reason == "before_open",
                    f"passed={d.passed} reason={d.reason}"))

    # T3: 09:35:00 — boundary inclusive
    d = check_entry_gate("09:35:00")
    results.append(("T3_09_35_boundary_inclusive", d.passed and d.reason == "ok",
                    f"passed={d.passed} reason={d.reason}"))

    # T4: 09:36 — one minute past boundary
    d = check_entry_gate("09:36")
    results.append(("T4_09_36_accept", d.passed and d.reason == "ok",
                    f"passed={d.passed} reason={d.reason}"))

    # T5: 10:30 — mid-morning
    d = check_entry_gate("10:30")
    results.append(("T5_10_30_accept", d.passed and d.reason == "ok",
                    f"passed={d.passed} reason={d.reason}"))

    # T6: 14:30 — mid-day window. v15.1 REMOVED the blackout, so this MUST pass
    d = check_entry_gate("14:30")
    results.append(("T6_14_30_no_blackout_v15_1", d.passed and d.reason == "ok",
                    f"passed={d.passed} reason={d.reason}"))

    # T7: 14:59:59 — last legal second
    d = check_entry_gate("14:59:59")
    results.append(("T7_14_59_59_last_legal", d.passed and d.reason == "ok",
                    f"passed={d.passed} reason={d.reason}"))

    # T8: 15:00 — boundary exclusive (theta-cutoff per v15.1)
    d = check_entry_gate("15:00")
    results.append(("T8_15_00_boundary_exclusive", not d.passed and d.reason == "after_close",
                    f"passed={d.passed} reason={d.reason}"))

    # T9: 15:30 — well past cutoff
    d = check_entry_gate("15:30")
    results.append(("T9_15_30_after_close", not d.passed and d.reason == "after_close",
                    f"passed={d.passed} reason={d.reason}"))

    # T10: R2 guard — 09:55 bar (closes 10:00) checked at 09:59:30 -> in progress
    bar_open = datetime(2026, 5, 14, 9, 55, 0)
    now = datetime(2026, 5, 14, 9, 59, 30)
    d = check_entry_gate(now, trigger_bar_open_et=bar_open)
    results.append(("T10_R2_bar_in_progress",
                    not d.passed and d.reason == "bar_in_progress",
                    f"passed={d.passed} reason={d.reason} bar_close={d.bar_close_et}"))

    # T11: R2 guard — same bar checked at exactly 10:00:00 -> closed
    now_closed = datetime(2026, 5, 14, 10, 0, 0)
    d = check_entry_gate(now_closed, trigger_bar_open_et=bar_open)
    results.append(("T11_R2_bar_closed_at_boundary",
                    d.passed and d.reason == "ok",
                    f"passed={d.passed} reason={d.reason} bar_close={d.bar_close_et}"))

    # T12: regression — legacy v14 with mid-day blackout 14:00-15:00 -> 14:30 REJECTS
    d = check_entry_gate("14:30", entry_no_trade_window_et=("14:00", "15:00"))
    results.append(("T12_legacy_v14_midday_blackout",
                    not d.passed and d.reason == "midday_blackout",
                    f"passed={d.passed} reason={d.reason}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:90]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """Pull current ET and report gate verdict. No-network; uses local clock.

    Live mode is informational: it always passes (the gate logic itself is
    deterministic config). The "pass" here means the function executed without
    raising; the verdict is in `decision`.
    """
    try:
        from zoneinfo import ZoneInfo
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        now_et_naive = now_et.replace(tzinfo=None)
    except Exception:
        # Fallback: assume UTC-4 (DST). Slightly wrong in winter, fine for diagnostic.
        now_et_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=4)

    d = check_entry_gate(now_et_naive)
    return {
        "mode": "live",
        "now_et": now_et_naive.isoformat(),
        "decision": {
            "passed": d.passed,
            "reason": d.reason,
            "now_et_time": d.now_et_time.isoformat(),
        },
        "pass": True,  # live mode just exercises the code path; verdict is the decision content
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:35s} {t['note']}")

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        live = sc["live"]
        print(f"\n=== LIVE === now_et={live['now_et']}")
        print(f"  decision: passed={live['decision']['passed']} reason={live['decision']['reason']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    all_ok = True
    if "offline" in sc and not sc["offline"]["all_pass"]:
        all_ok = False
    if "live" in sc and not sc["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
