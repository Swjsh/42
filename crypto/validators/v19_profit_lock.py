"""v19_profit_lock — verify chandelier trailing profit-lock + HWM ratcheting.

Mirrors backtest/lib/simulator_real.py profit-lock block.
Production source (params.json v15.1):
  v15_profit_lock_mode:           "trailing"
  v15_profit_lock_threshold_pct:  0.05   (arm at +5%)
  v15_profit_lock_trail_pct:      0.20   (chandelier 20% off HWM)
  v15_profit_lock_stop_offset_pct: 0.0   (when armed, floor = entry)

Offline tests (T1-T10):
  T1  Entry $1.00, run to +4.99% ($1.0499) -> NOT armed
  T2  Entry $1.00, run to +5.00% ($1.05)  -> ARMED, stop_floor at $1.00 (BE)
  T3  After arm, HWM ratchets up -> trail floor follows HWM * (1 - 0.20)
  T4  After arm, retracement -> stop_floor monotonic (doesn't decrease)
  T5  After 20% retrace off HWM -> stop_triggered fires
  T6  Premium oscillates above HWM -> HWM only goes up
  T7  Initial stop ($0.92 = entry -8%) preserved when not armed
  T8  At arm, if entry * (1+offset) < existing stop, stop is NOT lowered
  T9  Trailing-mode arms at +5% then trails: entry $1, peak $1.50,
      stop_floor = max(1.00, 1.50*0.80) = 1.20
  T10 'fixed' mode: arms, stop floor stays at entry+offset regardless of HWM moves

Live mode: no live trade exists; we just confirm the module imports + run offline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.profit_lock import (
    ProfitLockState,
    initial_state,
    stop_triggered,
    tick,
)


def run_offline() -> dict:
    results = []

    # T1: entry $1.00, premium reaches $1.0499 (+4.99%) -> NOT armed
    s = initial_state(entry_premium=1.00, initial_stop_premium=0.92,
                      threshold_pct=0.05, stop_offset_pct=0.0,
                      mode="trailing", trail_pct=0.20)
    s = tick(s, 1.0499)
    results.append(("T1_just_under_threshold_not_armed",
                    s.armed is False and abs(s.stop_floor - 0.92) < 1e-9,
                    f"armed={s.armed} stop_floor={s.stop_floor}"))

    # T2: hits exactly +5% -> ARMED, stop_floor at $1.00 (BE since stop_offset=0)
    # And since mode='trailing', stop_floor also = max(1.00, 1.05*0.80=0.84) = 1.00
    s = initial_state(1.00, 0.92, 0.05, 0.0, "trailing", 0.20)
    s = tick(s, 1.05)
    results.append(("T2_at_threshold_arms_to_BE",
                    s.armed is True and abs(s.stop_floor - 1.00) < 1e-9,
                    f"armed={s.armed} stop_floor={s.stop_floor}"))

    # T3: HWM ratchets. entry $1, premium runs $1.05 -> $1.20 -> $1.50.
    # After tick to 1.50: HWM=1.50, trail=1.50*0.80=1.20, stop_floor=max(1.00,1.20)=1.20
    s = initial_state(1.00, 0.92, 0.05, 0.0, "trailing", 0.20)
    s = tick(s, 1.05)
    s = tick(s, 1.20)
    s = tick(s, 1.50)
    results.append(("T3_hwm_ratchet_trails_at_20pct_off",
                    abs(s.hwm - 1.50) < 1e-9 and abs(s.stop_floor - 1.20) < 1e-9,
                    f"hwm={s.hwm} stop_floor={s.stop_floor}"))

    # T4: retracement after HWM. After s above (stop_floor=1.20, HWM=1.50),
    # tick to 1.30 -> HWM unchanged (1.50), trail=1.20, stop_floor still 1.20 (monotonic)
    s = tick(s, 1.30)
    results.append(("T4_retracement_stop_floor_monotonic",
                    abs(s.hwm - 1.50) < 1e-9 and abs(s.stop_floor - 1.20) < 1e-9,
                    f"hwm={s.hwm} stop_floor={s.stop_floor}"))

    # T5: 20% retrace off HWM -> stop triggers at exactly 1.20
    triggered = stop_triggered(s, 1.20)
    triggered_below = stop_triggered(s, 1.19)
    triggered_above = stop_triggered(s, 1.21)
    results.append(("T5_stop_trigger_boundary",
                    triggered is True and triggered_below is True and triggered_above is False,
                    f"at_floor={triggered} below={triggered_below} above={triggered_above}"))

    # T6: HWM only goes up. Premium oscillates 1.05 -> 1.50 -> 1.10 -> 1.40 -> 1.20
    # HWM should stay at 1.50 throughout.
    s = initial_state(1.00, 0.92, 0.05, 0.0, "trailing", 0.20)
    for p in [1.05, 1.50, 1.10, 1.40, 1.20]:
        s = tick(s, p)
    results.append(("T6_hwm_only_goes_up",
                    abs(s.hwm - 1.50) < 1e-9,
                    f"hwm={s.hwm} after oscillation"))

    # T7: Initial stop ($0.92) preserved when not armed
    s = initial_state(1.00, 0.92, 0.05, 0.0, "trailing", 0.20)
    s = tick(s, 1.02)  # +2%, below 5% threshold
    s = tick(s, 1.03)
    s = tick(s, 0.95)  # drops back
    results.append(("T7_unarmed_stop_floor_preserved",
                    s.armed is False and abs(s.stop_floor - 0.92) < 1e-9,
                    f"armed={s.armed} stop_floor={s.stop_floor}"))

    # T8: Edge case — arm-floor below existing initial stop. If entry_premium=1.00,
    # initial_stop=1.10 (very tight, above entry — pathological), arm at 1.05,
    # stop_offset=0.0 -> arm_floor = 1.00 which is BELOW initial 1.10.
    # Implementation must NOT lower the stop_floor.
    s = initial_state(1.00, 1.10, 0.05, 0.0, "trailing", 0.20)
    s = tick(s, 1.05)
    # armed=True, arm_floor=1.00, BUT stop_floor must stay at 1.10 (no lowering)
    # AND trailing: hwm=1.05, trail=1.05*0.80=0.84, max(1.00, 0.84)=1.00, still below 1.10
    results.append(("T8_arm_does_not_lower_stop",
                    s.armed is True and abs(s.stop_floor - 1.10) < 1e-9,
                    f"armed={s.armed} stop_floor={s.stop_floor}"))

    # T9: explicit reference scenario from docstring.
    # entry=$1, peak $1.50, expected stop_floor=$1.20 in trailing mode
    s = initial_state(1.00, 0.50, 0.05, 0.0, "trailing", 0.20)
    s = tick(s, 1.10)  # arms, stop_floor moves to max(0.50, 1.00)=1.00 + trail 0.88 -> 1.00
    s = tick(s, 1.50)  # trail = 1.20, stop_floor = max(1.00, 1.20) = 1.20
    results.append(("T9_trailing_classic_scenario",
                    abs(s.stop_floor - 1.20) < 1e-9 and abs(s.hwm - 1.50) < 1e-9,
                    f"hwm={s.hwm} stop_floor={s.stop_floor}"))

    # T10: 'fixed' mode — arms, then HWM moves further but stop floor doesn't trail
    s = initial_state(1.00, 0.92, 0.05, 0.0, mode="fixed", trail_pct=0.20)
    s = tick(s, 1.05)  # arms at 1.05, stop_floor = max(0.92, 1.00) = 1.00
    s = tick(s, 1.50)  # 'fixed' mode: stop_floor STAYS at 1.00, doesn't trail
    results.append(("T10_fixed_mode_does_not_trail",
                    s.armed is True and abs(s.stop_floor - 1.00) < 1e-9 and abs(s.hwm - 1.50) < 1e-9,
                    f"armed={s.armed} stop_floor={s.stop_floor} hwm={s.hwm}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:90]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """No-op: profit-lock has no live mode. Pass on successful module import + offline run."""
    return {"mode": "live", "pass": True,
            "note": "profit-lock is a pure state machine — no live data dependency"}


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
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:45s} {t['note']}")

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        print(f"\n=== LIVE === {sc['live']['note']}")

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
