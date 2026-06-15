"""v21_kill_switch — verify daily-loss circuit breaker math + LATCHING behavior.

Production source-of-truth:
  params_safe.json#daily_loss_kill_switch_pct = 0.30 (Safe: -30%)
  params_bold.json#daily_loss_kill_switch_pct = 0.50 (Bold: -50%)

Critical foot-gun: kill switch must LATCH (once tripped, stays tripped for the
trading day even if equity recovers above the threshold). Mid-day oscillation
around the threshold must not produce un-trip events.

Offline tests (T1-T12):
  T1  Safe $1000 start, equity $701 (-29.9%) -> NOT tripped (just under)
  T2  Safe $1000 start, equity $700 (-30.0%) -> TRIPPED at boundary
  T3  Safe $1000 start, equity $699 (-30.1%) -> TRIPPED
  T4  Bold $1000 start, equity $501 -> NOT tripped (49.9%)
  T5  Bold $1000 start, equity $500 -> TRIPPED at 50% boundary
  T6  LATCHING: trip at $700, then recover to $850 -> STAYS tripped
  T7  LATCHING: trip, recover, drop again, recover -> STAYS tripped forever
  T8  Multiple ticks above threshold -> never trips
  T9  trading_allowed() flips False on trip, stays False on recovery
  T10 Independence: Safe trips doesn't affect Bold state (per-account isolation)
  T11 Defensive: zero/negative start_of_day_equity raises ValueError
  T12 Defensive: out-of-range threshold_pct raises ValueError
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.kill_switch import (
    KillSwitchState,
    initial_state,
    loss_pct,
    threshold_equity,
    tick,
    trading_allowed,
)


def run_offline() -> dict:
    results = []

    # T1: Safe $1000 start, equity $701 (-29.9%) -> NOT tripped
    s = initial_state("safe", 1_000.0, 0.30)
    s = tick(s, 701.0)
    results.append(("T1_safe_under_threshold_not_tripped",
                    s.tripped is False, f"tripped={s.tripped}"))

    # T2: Safe $1000 start, equity $700 (-30.0%) -> TRIPPED at boundary
    s = initial_state("safe", 1_000.0, 0.30)
    s = tick(s, 700.0)
    results.append(("T2_safe_at_threshold_boundary_tripped",
                    s.tripped is True and s.tripped_at_equity == 700.0,
                    f"tripped={s.tripped} at_equity={s.tripped_at_equity}"))

    # T3: Safe $1000, equity $699 (-30.1%) -> TRIPPED
    s = initial_state("safe", 1_000.0, 0.30)
    s = tick(s, 699.0)
    results.append(("T3_safe_past_threshold_tripped",
                    s.tripped is True, f"tripped={s.tripped}"))

    # T4: Bold $1000 start, equity $501 -> NOT tripped (49.9%)
    s = initial_state("bold", 1_000.0, 0.50)
    s = tick(s, 501.0)
    results.append(("T4_bold_under_threshold_not_tripped",
                    s.tripped is False, f"tripped={s.tripped}"))

    # T5: Bold $1000 start, equity $500 -> TRIPPED at 50% boundary
    s = initial_state("bold", 1_000.0, 0.50)
    s = tick(s, 500.0)
    results.append(("T5_bold_at_50pct_boundary_tripped",
                    s.tripped is True and s.tripped_at_equity == 500.0,
                    f"tripped={s.tripped} at_equity={s.tripped_at_equity}"))

    # T6: LATCHING — trip then recover
    # Safe $1000: tick $700 -> trip. Then tick $850 -> stays tripped.
    s = initial_state("safe", 1_000.0, 0.30)
    s = tick(s, 700.0)
    assert s.tripped
    s = tick(s, 850.0)
    results.append(("T6_latching_trip_then_recover_stays_tripped",
                    s.tripped is True and s.tripped_at_equity == 700.0,
                    f"tripped={s.tripped} at_equity={s.tripped_at_equity}"))

    # T7: LATCHING — oscillation pattern.
    # Safe $1000: ticks [900, 700 (TRIP), 850, 750, 950, 700, 920]. Must stay tripped.
    s = initial_state("safe", 1_000.0, 0.30)
    sequence = [900.0, 700.0, 850.0, 750.0, 950.0, 700.0, 920.0]
    for e in sequence:
        s = tick(s, e)
    results.append(("T7_latching_oscillation_stays_tripped",
                    s.tripped is True and s.tripped_at_equity == 700.0
                    and s.min_equity_seen == 700.0,
                    f"tripped={s.tripped} min_seen={s.min_equity_seen}"))

    # T8: Multiple ticks above threshold -> never trips
    s = initial_state("safe", 1_000.0, 0.30)
    for e in [1_000.0, 950.0, 900.0, 800.0, 720.0, 750.0, 800.0]:
        s = tick(s, e)
    # min_seen $720 which is above $700 floor -> never tripped
    results.append(("T8_above_threshold_never_trips",
                    s.tripped is False and s.min_equity_seen == 720.0,
                    f"tripped={s.tripped} min_seen={s.min_equity_seen}"))

    # T9: trading_allowed() semantics
    s = initial_state("safe", 1_000.0, 0.30)
    ok_before = trading_allowed(s)
    s = tick(s, 700.0)
    ok_after_trip = trading_allowed(s)
    s = tick(s, 900.0)
    ok_after_recover = trading_allowed(s)
    results.append(("T9_trading_allowed_flips_and_stays_false",
                    ok_before is True and ok_after_trip is False and ok_after_recover is False,
                    f"before={ok_before} after_trip={ok_after_trip} after_recover={ok_after_recover}"))

    # T10: Per-account isolation — Safe trips does NOT affect Bold
    safe = initial_state("safe", 1_000.0, 0.30)
    bold = initial_state("bold", 1_000.0, 0.50)
    safe = tick(safe, 700.0)  # trips safe
    bold = tick(bold, 700.0)  # 30% loss < 50% bold threshold
    results.append(("T10_account_isolation_safe_trip_no_affect_on_bold",
                    safe.tripped is True and bold.tripped is False,
                    f"safe.tripped={safe.tripped} bold.tripped={bold.tripped}"))

    # T11: Defensive — zero/negative start_of_day_equity
    try:
        initial_state("safe", 0.0, 0.30)
        t11_ok = False
    except ValueError:
        t11_ok = True
    try:
        initial_state("safe", -100.0, 0.30)
        t11_ok = t11_ok and False
    except ValueError:
        pass
    results.append(("T11_defensive_invalid_start_equity_raises",
                    t11_ok, "ValueError raised on zero/negative" if t11_ok else "defense missing"))

    # T12: Defensive — out-of-range threshold_pct
    try:
        initial_state("safe", 1_000.0, 0.0)
        t12a = False
    except ValueError:
        t12a = True
    try:
        initial_state("safe", 1_000.0, 1.0)
        t12b = False
    except ValueError:
        t12b = True
    try:
        initial_state("safe", 1_000.0, -0.1)
        t12c = False
    except ValueError:
        t12c = True
    results.append(("T12_defensive_invalid_threshold_pct_raises",
                    t12a and t12b and t12c,
                    f"a={t12a} b={t12b} c={t12c}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:90]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """No-op live: kill-switch is pure math + ledger state."""
    return {"mode": "live", "pass": True,
            "note": "kill-switch is pure state machine — no live data dependency"}


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
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:55s} {t['note']}")

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
