"""v20_strike_selection — verify per-tier OTM/ITM strike math.

Mirrors params.json#v15_strike_offset_per_tier (Bold) + params_safe.json (Safe).
Canonical formula (heartbeat.md L254):
  BEAR puts:  strike = round(spot) + offset   (positive=ITM, negative=OTM)
  BULL calls: strike = round(spot) - offset   (mirror)

Offline tests (T1-T12) — spot=740 throughout for human-checkable math:
  T1  Bold $1,000   bull call -> OTM-3 -> strike 743 (740 - (-3))
  T2  Bold $1,000   bear put  -> OTM-3 -> strike 737 (740 + (-3))
  T3  Bold $5,000   bull call -> OTM-2 -> strike 742
  T4  Bold $9,000   bear put  -> OTM-2 -> strike 738
  T5  Bold $15,000  bull call -> OTM-1 -> strike 741
  T6  Bold $24,000  bear put  -> OTM-1 -> strike 739
  T7  Bold $50,000  bull call -> ITM-2 -> strike 738 (740 - 2)
  T8  Bold $50,000  bear put  -> ITM-2 -> strike 742 (740 + 2)
  T9  Boundary $2,000 -> upper-tier ($2K-$10K) per tier semantics [emin, emax)
  T10 Boundary $25,000 -> ITM-2 tier (inclusive lower bound)
  T11 Safe $1,000 bull call -> ATM -> strike 740
  T12 Moneyness sanity: every Bold-computed strike correctly classified ITM/OTM/ATM
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.strike_selection import (
    V15_BOLD_TIERS,
    V15_SAFE_TIERS,
    moneyness,
    pick_strike,
    pick_tier,
)


def run_offline() -> dict:
    results = []
    spot = 740.0

    # T1: Bold $1K bull call -> OTM-3 -> 743
    s = pick_strike(spot, 1_000, "C", V15_BOLD_TIERS)
    results.append(("T1_bold_1k_bull_OTM3",
                    s == 743, f"strike={s} expected=743"))

    # T2: Bold $1K bear put -> OTM-3 -> 737
    s = pick_strike(spot, 1_000, "P", V15_BOLD_TIERS)
    results.append(("T2_bold_1k_bear_OTM3",
                    s == 737, f"strike={s} expected=737"))

    # T3: Bold $5K bull call -> OTM-2 -> 742
    s = pick_strike(spot, 5_000, "C", V15_BOLD_TIERS)
    results.append(("T3_bold_5k_bull_OTM2",
                    s == 742, f"strike={s} expected=742"))

    # T4: Bold $9K bear put -> OTM-2 -> 738
    s = pick_strike(spot, 9_000, "P", V15_BOLD_TIERS)
    results.append(("T4_bold_9k_bear_OTM2",
                    s == 738, f"strike={s} expected=738"))

    # T5: Bold $15K bull call -> OTM-1 -> 741
    s = pick_strike(spot, 15_000, "C", V15_BOLD_TIERS)
    results.append(("T5_bold_15k_bull_OTM1",
                    s == 741, f"strike={s} expected=741"))

    # T6: Bold $24K bear put -> OTM-1 -> 739
    s = pick_strike(spot, 24_000, "P", V15_BOLD_TIERS)
    results.append(("T6_bold_24k_bear_OTM1",
                    s == 739, f"strike={s} expected=739"))

    # T7: Bold $50K bull call -> ITM-2 -> 738
    s = pick_strike(spot, 50_000, "C", V15_BOLD_TIERS)
    results.append(("T7_bold_50k_bull_ITM2",
                    s == 738, f"strike={s} expected=738"))

    # T8: Bold $50K bear put -> ITM-2 -> 742
    s = pick_strike(spot, 50_000, "P", V15_BOLD_TIERS)
    results.append(("T8_bold_50k_bear_ITM2",
                    s == 742, f"strike={s} expected=742"))

    # T9: Boundary $2000 -> $2K-$10K tier per [emin, emax) semantics
    t = pick_tier(2_000, V15_BOLD_TIERS)
    results.append(("T9_boundary_2k_inclusive_lower",
                    t.equity_min == 2_000 and t.strike_offset == -2,
                    f"tier=({t.equity_min},{t.equity_max}) offset={t.strike_offset}"))

    # T10: Boundary $25K -> ITM-2 tier inclusive on lower bound
    t = pick_tier(25_000, V15_BOLD_TIERS)
    results.append(("T10_boundary_25k_ITM2_tier",
                    t.equity_min == 25_000 and t.strike_offset == +2,
                    f"tier=({t.equity_min},{t.equity_max}) offset={t.strike_offset}"))

    # T11: Safe $1K bull call -> ATM -> 740
    s = pick_strike(spot, 1_000, "C", V15_SAFE_TIERS)
    results.append(("T11_safe_1k_bull_ATM",
                    s == 740, f"strike={s} expected=740"))

    # T12: Moneyness sanity invariant for all Bold tiers
    cases = [
        (1_000, "C", "OTM"), (1_000, "P", "OTM"),
        (5_000, "C", "OTM"), (5_000, "P", "OTM"),
        (15_000, "C", "OTM"), (15_000, "P", "OTM"),
        (50_000, "C", "ITM"), (50_000, "P", "ITM"),
    ]
    bad = []
    for eq, side, expected in cases:
        strike = pick_strike(spot, eq, side, V15_BOLD_TIERS)
        m = moneyness(strike, spot, side)
        if m != expected:
            bad.append(f"eq={eq} side={side} strike={strike} got={m} want={expected}")
    results.append(("T12_moneyness_sanity_invariant",
                    len(bad) == 0, "all OK" if not bad else f"failures: {bad}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:90]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """No-op live: strike selection is config-driven math, no live data needed."""
    return {"mode": "live", "pass": True,
            "note": "strike-selection is pure config math — no live data needed"}


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
