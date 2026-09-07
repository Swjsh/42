"""
H4 prerequisite kill-check: does the dealer-gamma regime (spot vs. zero-gamma
flip level) actually VARY across the banked journal/gex-archive/*-cboe.json
sessions? H4 (markdown/trading-knowledge/microstructure-informed-flow.md §4)
asks whether gamma regime adds predictive info beyond order flow -- that
question is only testable if both regimes (spot-above-flip and
spot-below-flip) occur often enough on this archive to give contrast.

This script does NOT test H4 itself. It only computes net GEX / flip level
per day and reports whether the regime varies enough to make H4 testable.

SIGN CONVENTION (stated once, used everywhere below):
  GEX_contract = gamma * open_interest * 100 * spot^2 * 0.01
  signed POSITIVE for calls, NEGATIVE for puts.
  Rationale: dealers are modeled as long calls / short puts from customer
  flow, so positive net GEX means dealers are long gamma in aggregate
  (dealer hedging dampens moves); negative net GEX means dealers are short
  gamma (dealer hedging amplifies moves). This is the standard SqueezeMetrics/
  Cboe-style convention. Every GEX number in this script's output uses this
  convention consistently -- flip the sign here and every downstream number
  flips, so this comment is the single source of truth for it.

Data is CBOE-native gamma (has_native_gamma: true per file) -- gamma is used
as-is, not derived from BS. gamma==0.0 and/or missing/absent open_interest
are handled explicitly and counted, never silently dropped.

Zero-gamma flip: net GEX is re-evaluated on a grid of hypothetical spot
prices (actual spot * [0.90 .. 1.10] in 0.25% steps), holding each
contract's gamma fixed (first-order approximation -- gamma itself would
change with spot in reality, this is not modeled). The flip is the spot
value where the grid crosses zero (linear interpolation between the two
bracketing grid points). If no sign change occurs across the whole grid,
flip is recorded as null -- never fabricated by extrapolation.

$0 cost: pure stdlib Python, no network, no LLM calls.
"""

from __future__ import annotations

import glob
import json
import os
import statistics
from typing import Optional

ARCHIVE_GLOB = os.path.join(
    os.path.dirname(__file__), "..", "..", "journal", "gex-archive", "*-cboe.json"
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "analysis",
    "recommendations",
    "h4-gex-regime-series.json",
)

SIGN_CONVENTION = (
    "GEX_contract = gamma * open_interest * 100 * spot^2 * 0.01; "
    "+1 for calls, -1 for puts (dealers modeled long calls / short puts). "
    "Positive net GEX = dealers net long gamma (stabilizing); "
    "negative net GEX = dealers net short gamma (destabilizing)."
)

# grid for zero-gamma flip search: spot * (1 + pct) for pct in this range
GRID_LO_PCT = -0.10
GRID_HI_PCT = 0.10
GRID_STEP_PCT = 0.0025  # 0.25%


def contract_gex(gamma: float, oi: float, spot: float, right: str) -> float:
    sign = 1.0 if right == "C" else -1.0 if right == "P" else 0.0
    return sign * gamma * oi * 100.0 * (spot ** 2) * 0.01


def compute_net_gex_at_spot(contracts: list[dict], spot: float) -> float:
    """Sum GEX across contracts at a hypothetical spot, holding gamma fixed."""
    total = 0.0
    for c in contracts:
        gamma = c.get("gamma")
        oi = c.get("open_interest")
        right = c.get("right")
        if gamma is None or oi is None or right not in ("C", "P"):
            continue
        total += contract_gex(gamma, oi, spot, right)
    return total


def find_zero_gamma_flip(contracts: list[dict], spot: float) -> Optional[float]:
    """
    Grid-search for the spot price where net GEX crosses zero, holding each
    contract's gamma fixed (first-order approx). Returns None if no sign
    change is found anywhere in the grid -- never extrapolated/fabricated.

    STRUCTURAL NOTE (verified empirically on this archive, see
    h4-gex-regime-series.json summary.flip_method_diagnostic): with gamma
    and OI held fixed per contract, net_gex(hypothetical_spot) reduces to
    spot^2 * K where K = sum(sign * gamma * OI) * 100 * 0.01 is a CONSTANT
    independent of the hypothetical spot. Since spot^2 > 0 everywhere on the
    grid, sign(net_gex) == sign(K) for every grid point -- a crossing is
    mathematically impossible under this frozen-gamma method, regardless of
    the underlying data. This is not a data/coverage problem; it is a
    structural degeneracy of the "hold gamma fixed" approximation as
    specified. A real flip calculation would need gamma to vary with
    hypothetical spot (e.g. re-derived from BS per strike), which was
    explicitly out of scope here. Reported honestly rather than silently
    producing a number.
    """
    n_steps = int(round((GRID_HI_PCT - GRID_LO_PCT) / GRID_STEP_PCT))
    grid_spots = [spot * (1.0 + GRID_LO_PCT + i * GRID_STEP_PCT) for i in range(n_steps + 1)]
    grid_vals = [compute_net_gex_at_spot(contracts, s) for s in grid_spots]

    for i in range(len(grid_vals) - 1):
        v0, v1 = grid_vals[i], grid_vals[i + 1]
        if v0 == 0.0:
            return grid_spots[i]
        if (v0 < 0.0) != (v1 < 0.0):
            # linear interpolation for the crossing point
            s0, s1 = grid_spots[i], grid_spots[i + 1]
            frac = v0 / (v0 - v1)
            return s0 + frac * (s1 - s0)
    return None


def analyze_symbol(sym_data: dict, symbol_name: str) -> dict:
    spot = sym_data.get("spot")
    contracts = sym_data.get("contracts", [])

    n_total = len(contracts)
    n_used = 0
    n_dropped_missing_gamma = 0
    n_dropped_missing_oi = 0
    n_dropped_bad_right = 0
    n_zero_gamma_rows = 0

    call_gex = 0.0
    put_gex = 0.0

    for c in contracts:
        gamma = c.get("gamma")
        oi = c.get("open_interest")
        right = c.get("right")

        if right not in ("C", "P"):
            n_dropped_bad_right += 1
            continue
        if gamma is None:
            n_dropped_missing_gamma += 1
            continue
        if oi is None:
            n_dropped_missing_oi += 1
            continue

        if gamma == 0.0:
            n_zero_gamma_rows += 1

        g = contract_gex(gamma, oi, spot, right)
        n_used += 1
        if right == "C":
            call_gex += g
        else:
            put_gex += g

    net_gex = call_gex + put_gex
    flip = find_zero_gamma_flip(contracts, spot) if spot else None

    spot_vs_flip = None
    norm_dist = None
    if flip is not None and spot:
        spot_vs_flip = "above" if spot > flip else ("below" if spot < flip else "at")
        norm_dist = (spot - flip) / spot

    return {
        "symbol": symbol_name,
        "spot": spot,
        "n_contracts_total": n_total,
        "n_contracts_used": n_used,
        "n_dropped_missing_gamma": n_dropped_missing_gamma,
        "n_dropped_missing_oi": n_dropped_missing_oi,
        "n_dropped_bad_right": n_dropped_bad_right,
        "n_zero_gamma_rows": n_zero_gamma_rows,
        "call_gex": call_gex,
        "put_gex": put_gex,
        "net_gex": net_gex,
        "zero_gamma_flip": flip,
        "spot_vs_flip": spot_vs_flip,
        "normalized_distance": norm_dist,
    }


def main() -> None:
    files = sorted(glob.glob(ARCHIVE_GLOB))
    if not files:
        raise SystemExit(f"No archive files found matching {ARCHIVE_GLOB}")

    per_date = []
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        session_date = data.get("session_date")
        by_symbol = data.get("by_symbol", {})

        entry = {"session_date": session_date, "source_file": os.path.basename(path)}

        if "SPY" in by_symbol:
            entry["SPY"] = analyze_symbol(by_symbol["SPY"], "SPY")
        else:
            entry["SPY"] = None

        if "_SPX" in by_symbol:
            entry["_SPX"] = analyze_symbol(by_symbol["_SPX"], "_SPX")
        else:
            entry["_SPX"] = None

        per_date.append(entry)

    # summary, computed off SPY (primary symbol)
    spy_entries = [e["SPY"] for e in per_date if e["SPY"] is not None]
    n_days = len(spy_entries)

    n_flip_unavailable = sum(1 for e in spy_entries if e["zero_gamma_flip"] is None)
    with_flip = [e for e in spy_entries if e["zero_gamma_flip"] is not None]

    n_above = sum(1 for e in with_flip if e["spot_vs_flip"] == "above")
    n_below = sum(1 for e in with_flip if e["spot_vs_flip"] == "below")
    n_at = sum(1 for e in with_flip if e["spot_vs_flip"] == "at")

    net_gex_vals = [e["net_gex"] for e in spy_entries]
    norm_dist_vals = [e["normalized_distance"] for e in with_flip]

    def minmedmax(vals):
        if not vals:
            return {"min": None, "median": None, "max": None}
        return {"min": min(vals), "median": statistics.median(vals), "max": max(vals)}

    n_minority = min(n_above, n_below) if with_flip else 0
    testable = n_minority >= 10

    flip_method_diagnostic = (
        "Zero-gamma flip could not be computed for ANY day (0/{} SPY sessions). "
        "This is a STRUCTURAL degeneracy, not a data-coverage problem: with "
        "gamma and OI held fixed per contract (as specified), net_gex(spot) "
        "reduces to spot^2 * K for a constant K, and spot^2 > 0 everywhere on "
        "the +/-10% grid, so sign(net_gex) cannot change -- a crossing is "
        "mathematically impossible under this method regardless of what the "
        "archive data says. Verified empirically: net_gex on 2026-06-22 SPY "
        "at spot*0.90 = -5.45e9, at spot*1.10 = -8.14e9 (same sign, roughly "
        "spot^2-scaled, as the degeneracy predicts). A genuine flip level "
        "requires per-strike gamma to vary with hypothetical spot (e.g. "
        "re-derived via Black-Scholes at each grid point), which the spec's "
        "'hold gamma fixed' instruction explicitly excludes. Net GEX and its "
        "sign (regime: dealers net long vs. net short gamma at the OBSERVED "
        "spot) are still valid and reported below; only the flip/normalized- "
        "distance fields are unusable from this method."
    ).format(n_days)

    # Fallback regime split that does NOT suffer the flip degeneracy: sign of
    # net GEX at the OBSERVED spot (dealers net long vs. net short gamma).
    # This is a real, non-fabricated contrast computed directly from the data.
    n_net_positive = sum(1 for v in net_gex_vals if v > 0)
    n_net_negative = sum(1 for v in net_gex_vals if v < 0)
    n_net_zero = sum(1 for v in net_gex_vals if v == 0)
    n_minority_net_sign = min(n_net_positive, n_net_negative) if net_gex_vals else 0
    testable_by_net_sign = n_minority_net_sign >= 10

    summary = {
        "n_days": n_days,
        "n_days_flip_available": len(with_flip),
        "n_days_flip_unavailable": n_flip_unavailable,
        "n_days_spot_above_flip": n_above,
        "n_days_spot_below_flip": n_below,
        "n_days_spot_at_flip": n_at,
        "fraction_above": (n_above / len(with_flip)) if with_flip else None,
        "fraction_below": (n_below / len(with_flip)) if with_flip else None,
        "net_gex": minmedmax(net_gex_vals),
        "normalized_distance": minmedmax(norm_dist_vals),
        "minority_side_count": n_minority,
        "h4_testable_threshold": 10,
        "h4_testable": testable,
        "flip_method_diagnostic": flip_method_diagnostic,
        "net_gex_sign_regime": {
            "note": (
                "Fallback regime split using sign of net GEX at the observed "
                "spot (dealers net long vs. net short gamma). Computed directly "
                "from archive data -- does NOT depend on the broken flip method "
                "above. Not what the spec's spot_vs_flip field asks for, but the "
                "closest honest substitute for judging regime variation."
            ),
            "n_days_net_gex_positive": n_net_positive,
            "n_days_net_gex_negative": n_net_negative,
            "n_days_net_gex_zero": n_net_zero,
            "minority_side_count": n_minority_net_sign,
            "h4_testable_by_this_measure": testable_by_net_sign,
        },
        "verdict": (
            f"Zero-gamma flip (as specified, gamma held fixed) is STRUCTURALLY "
            f"UNCOMPUTABLE -- 0/{n_days} days produced a crossing, and this is "
            f"mathematically guaranteed regardless of data (see "
            f"flip_method_diagnostic). The spot-vs-flip contrast the spec asked "
            f"for cannot be evaluated by this method. "
            f"Fallback: net-GEX-sign regime (dealers net long vs. short gamma) "
            f"IS computable from this data and shows real variation -- "
            f"{n_net_positive} days positive (dealer long gamma) vs. "
            f"{n_net_negative} days negative (dealer short gamma) out of {n_days}, "
            f"minority side = {n_minority_net_sign} days "
            f"({'>= ' if testable_by_net_sign else '< '}10 threshold), so H4 "
            f"{'IS' if testable_by_net_sign else 'is NOT'} testable using net-GEX-"
            f"sign as the regime label. The flip-level version of H4 cannot be "
            f"answered from this archive without a non-degenerate flip method "
            f"(e.g. BS-repriced gamma per grid point), which was out of scope here."
        ),
    }

    output = {
        "sign_convention": SIGN_CONVENTION,
        "grid_search": {
            "range_pct": [GRID_LO_PCT, GRID_HI_PCT],
            "step_pct": GRID_STEP_PCT,
            "note": "gamma held fixed across grid (first-order approx, not re-derived from BS)",
        },
        "per_date": per_date,
        "summary": summary,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    # compact stdout table
    print(f"{'date':<12} {'spot':>9} {'flip':>9} {'vs_flip':>8} {'norm_dist':>10} {'net_gex':>16} {'used/total':>11}")
    for e in per_date:
        s = e["SPY"]
        if s is None:
            print(f"{e['session_date']:<12} (no SPY data)")
            continue
        flip_str = f"{s['zero_gamma_flip']:.2f}" if s["zero_gamma_flip"] is not None else "null"
        nd_str = f"{s['normalized_distance']:.4f}" if s["normalized_distance"] is not None else "null"
        print(
            f"{e['session_date']:<12} {s['spot']:>9.2f} {flip_str:>9} "
            f"{str(s['spot_vs_flip']):>8} {nd_str:>10} {s['net_gex']:>16,.0f} "
            f"{s['n_contracts_used']}/{s['n_contracts_total']:>7}"
        )

    print()
    print("=" * 78)
    print(f"n_days:                {summary['n_days']}")
    print(f"flip available/unavail: {summary['n_days_flip_available']} / {summary['n_days_flip_unavailable']}")
    print(f"spot ABOVE flip:       {summary['n_days_spot_above_flip']}")
    print(f"spot BELOW flip:       {summary['n_days_spot_below_flip']}")
    print(f"spot AT flip:          {summary['n_days_spot_at_flip']}")
    print(f"minority side count:   {summary['minority_side_count']} (threshold: 10)")
    print(f"H4 TESTABLE (flip method):     {summary['h4_testable']}")
    nsr = summary["net_gex_sign_regime"]
    print(f"net_gex positive/negative/zero: {nsr['n_days_net_gex_positive']} / {nsr['n_days_net_gex_negative']} / {nsr['n_days_net_gex_zero']}")
    print(f"H4 TESTABLE (net-gex-sign fallback): {nsr['h4_testable_by_this_measure']}")
    print("-" * 78)
    print(summary["verdict"])
    print("=" * 78)
    print(f"Output written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
