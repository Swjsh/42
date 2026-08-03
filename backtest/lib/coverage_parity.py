"""Strike-axis coverage-parity guard (C7: silent success is failure).

Filed from OPTION-CACHE-ITM-COVERAGE-GAP (found 2026-08-02 while re-verifying
ribbon_ride_strike_exit_ab.py's strike axis: the 5-min OPRA option-bar disk
cache has a coverage gap that widens monotonically with distance from OTM-2 --
0/250 signals missing bars at OTM-2, 1/250 at OTM-1, 6/250 at ATM, 19/250 at
ITM-2 on the ribbon_ride 250-signal cohort (analysis/recommendations/
ribbon-ride-strike-exit-ab-1min-coverage-matched-2026-08-02.json). Real OPRA
illiquidity on far-ITM 0DTE strikes, not a fetch-script bug (expand_opra_cache.py
already requests a symmetric +/-5 strike window every day -- Alpaca genuinely
returns fewer bars for the strikes traders touch less).

Every strike-axis study already DISCLOSES ``n_no_local_bars`` per cell (see
``ribbon_ride_strike_exit_ab.py#build_cell``) -- but disclosure alone is not a
gate: nothing stops a caller from comparing two cells whose underlying
populations are silently different sizes and calling the delta a strike edge.
This module is the reusable, $0, pure-Python assertion that closes that gap:
any strike-axis comparison must call ``check_coverage_parity`` and respect
``parity_ok`` before treating a cross-strike delta as trustworthy.

Usage:
    from lib.coverage_parity import check_coverage_parity
    result = check_coverage_parity([
        {"cell_id": "OTM-2", "n_no_local_bars": 0, "n_total_attempted": 250},
        {"cell_id": "ITM-2", "n_no_local_bars": 19, "n_total_attempted": 250},
    ])
    result["parity_ok"]  # False -- 7.6pp missing-rate spread > default 5.0pp
"""

from __future__ import annotations

DEFAULT_MAX_DELTA_PP = 5.0  # percentage points; tune via max_delta_pp kwarg


def missing_rate(n_no_local_bars: int, n_total_attempted: int) -> float | None:
    """Fraction of attempted signals with no local OPRA bars, as a percentage.

    Returns None (not 0.0) when n_total_attempted is 0 -- an empty cell is
    "no evidence", not "perfect coverage", and callers must not silently
    treat a None as passing.
    """
    if n_total_attempted <= 0:
        return None
    return 100.0 * n_no_local_bars / n_total_attempted


def check_coverage_parity(
    cells: list[dict],
    max_delta_pp: float = DEFAULT_MAX_DELTA_PP,
) -> dict:
    """Assert per-cell OPRA-bar coverage is comparable before trusting a
    strike-axis (or any other cross-cell) comparison.

    ``cells``: list of dicts, each needs ``cell_id``, ``n_no_local_bars``,
    ``n_total_attempted`` (== n_no_local_bars + matched-trade n).

    Returns a dict: {parity_ok, max_delta_pp, observed_delta_pp, rates: {cell_id: pct|None},
    reason}. ``parity_ok`` is False if any cell has no evidence (rate is None)
    OR the max-min spread across cells exceeds max_delta_pp. Fails CLOSED
    (parity_ok=False) on missing/malformed input rather than raising -- a
    caller that forgets to pass n_total_attempted must not get a silent pass.
    """
    if not cells or len(cells) < 2:
        return {
            "parity_ok": False,
            "max_delta_pp": max_delta_pp,
            "observed_delta_pp": None,
            "rates": {},
            "reason": "fewer than 2 cells supplied -- nothing to compare",
        }

    rates: dict[str, float | None] = {}
    for c in cells:
        cid = c.get("cell_id", "<unknown>")
        rates[cid] = missing_rate(
            c.get("n_no_local_bars", 0) or 0,
            c.get("n_total_attempted", 0) or 0,
        )

    if any(r is None for r in rates.values()):
        missing = [cid for cid, r in rates.items() if r is None]
        return {
            "parity_ok": False,
            "max_delta_pp": max_delta_pp,
            "observed_delta_pp": None,
            "rates": rates,
            "reason": f"no-evidence cell(s) (n_total_attempted<=0): {missing}",
        }

    numeric = [r for r in rates.values() if r is not None]
    delta = round(max(numeric) - min(numeric), 3)
    ok = delta <= max_delta_pp
    return {
        "parity_ok": ok,
        "max_delta_pp": max_delta_pp,
        "observed_delta_pp": delta,
        "rates": {cid: round(r, 3) for cid, r in rates.items()},
        "reason": (
            "coverage comparable across cells"
            if ok
            else f"missing-rate spread {delta}pp exceeds {max_delta_pp}pp "
                 f"-- strike-axis delta is NOT trustworthy without a coverage-matched re-run"
        ),
    }
