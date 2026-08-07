"""Adversarial LENS-3 recompute for the SSR battery scorecards.

Standalone: NO imports from backtest/futures/ssr/* or backtest/futures/battery.py.
Recomputes every Family A cell's n/wr/total_net/mean_net/IS-OOS split from the
EMBEDDED trade rows in analysis/recommendations/futures-ssr-smoke.json (and spot
checks Family B from futures-ssr-regime.json), and diffs against the reported
cell-level fields. Also checks: FDR family size (24/8), alpha=0.05 BH-FDR
semantics reimplemented independently, OOS cut dates honored per-trade,
commission+slippage magnitudes vs GC/ES/NQ instrument specs, B&H null
presence, drop_top3 math, halves math, with/without-exhibit-day arithmetic,
duplicate-entry-timestamp detection, overlapping-position detection (same
instrument), and signal-frequency (C27) sanity.

Run:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_ssr_lens3_recompute.py -v -s
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[2]
SMOKE_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-smoke.json"
REGIME_JSON = _REPO / "analysis" / "recommendations" / "futures-ssr-regime.json"

# Instrument specs, re-declared HERE from scratch (not imported) so this check
# is independent of ssr_instruments.py / instruments.py.
SPECS = {
    "GC": {"point_value": 100.0, "tick_size": 0.1, "round_turn_usd": 6.00},
    "ES": {"point_value": 50.0, "tick_size": 0.25, "round_turn_usd": 4.00},
    "NQ": {"point_value": 20.0, "tick_size": 0.25, "round_turn_usd": 4.00},
}


def _load(path: Path) -> dict:
    assert path.exists(), f"missing scorecard: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _independent_stats(nets: list[float]) -> dict:
    n = len(nets)
    if n == 0:
        return {"n": 0, "wr": None, "total": 0.0, "mean": None}
    arr = np.asarray(nets, dtype=float)
    return {"n": n, "wr": round(float((arr > 0).mean()), 4),
            "total": round(float(arr.sum()), 2), "mean": round(float(arr.mean()), 2)}


def _independent_bh_fdr(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Reimplemented BH step-up from scratch (no import of battery.py)."""
    m = len(pvalues)
    if m == 0:
        return []
    idx_sorted = sorted(range(m), key=lambda i: pvalues[i])
    survive = [False] * m
    thresh_rank = 0
    for rank, idx in enumerate(idx_sorted, start=1):
        p = pvalues[idx]
        if p <= (rank / m) * alpha:
            thresh_rank = rank
    for rank, idx in enumerate(idx_sorted, start=1):
        if rank <= thresh_rank:
            survive[idx] = True
    return survive


# ---------------------------------------------------------------------------
# Family A (smoke)
# ---------------------------------------------------------------------------

def test_family_a_cell_count_matches_prereg():
    d = _load(SMOKE_JSON)
    assert d["n_cells"] == 24, f"pre-reg is 24 cells (3 symbols x 2 dirs x 4 combos), got {d['n_cells']}"
    assert len(d["cells"]) == 24


def test_family_a_recompute_n_wr_total_mean_per_cell():
    d = _load(SMOKE_JSON)
    mismatches = []
    for c in d["cells"]:
        nets = [t["net"] for t in c["trades"]]
        recomputed = _independent_stats(nets)
        for field, rkey in (("n", "n"), ("wr", "wr"), ("total_net", "total"), ("mean_net", "mean")):
            reported = c[field]
            recomp = recomputed[rkey]
            if reported != recomp:
                mismatches.append((c["symbol"], c["direction"], c["combo"], field, reported, recomp))
    assert not mismatches, f"recompute mismatches: {mismatches}"


def test_family_a_recompute_is_oos_split():
    d = _load(SMOKE_JSON)
    oos_cut = dt.date.fromisoformat(d["oos_cut"])
    mismatches = []
    for c in d["cells"]:
        is_nets = [t["net"] for t in c["trades"] if dt.date.fromisoformat(t["date"]) < oos_cut]
        oos_nets = [t["net"] for t in c["trades"] if dt.date.fromisoformat(t["date"]) >= oos_cut]
        is_recomp = _independent_stats(is_nets)
        oos_recomp = _independent_stats(oos_nets)
        for field in ("n", "wr", "total", "mean"):
            if c["is"][field] != is_recomp[field]:
                mismatches.append(("IS", c["symbol"], c["direction"], c["combo"], field,
                                    c["is"][field], is_recomp[field]))
            if c["oos"][field] != oos_recomp[field]:
                mismatches.append(("OOS", c["symbol"], c["direction"], c["combo"], field,
                                    c["oos"][field], oos_recomp[field]))
    assert not mismatches, f"IS/OOS split mismatches: {mismatches}"


def test_family_a_no_duplicate_entry_timestamps_per_cell():
    """Two trades with the identical ts_entry_et inside ONE cell would mean a
    duplicated trade (same signal counted twice)."""
    d = _load(SMOKE_JSON)
    dupes = []
    for c in d["cells"]:
        ts_list = [t["ts_entry_et"] for t in c["trades"]]
        if len(ts_list) != len(set(ts_list)):
            seen = set()
            for ts in ts_list:
                if ts in seen:
                    dupes.append((c["symbol"], c["direction"], c["combo"], ts))
                seen.add(ts)
    assert not dupes, f"duplicated entry timestamps found: {dupes}"


def test_family_a_no_overlapping_positions_within_cell():
    """Within one (symbol,direction,combo) cell there is one position at a
    time per DESIGN.md sec.3 concurrency rule -- verify entries are
    monotonically non-decreasing in time and (best-effort, since exit ts
    isn't stored) that no two entries share the exact same bar."""
    d = _load(SMOKE_JSON)
    problems = []
    for c in d["cells"]:
        entries = sorted(t["ts_entry_et"] for t in c["trades"])
        raw = [t["ts_entry_et"] for t in c["trades"]]
        if raw != entries:
            problems.append((c["symbol"], c["direction"], c["combo"], "not time-ordered"))
    assert not problems, f"ordering problems (possible overlap / out-of-order trades): {problems}"


def test_family_a_commission_slippage_magnitude_gc():
    """Spot-check net vs gross for GC cells: net should equal gross minus
    (commission + slippage), and the per-trade cost should be in a sane band
    around round_turn(6.00) + 1-tick-per-side slippage * qty(3) * point_value(100).
    tick 0.1 => 1 tick slippage per side * 2 sides * 3 qty * $100/pt * 0.1 = $60
    round_turn_usd * qty = 6.00 * 3 = $18
    total expected friction per trade ~= $78 (only true if qty=3 uniformly and
    tp1_fraction doesn't change contract count mid-trade -- DESIGN.md sec.3 says
    qty=3, tp1_fraction=2/3, so total commission legs still cover 3 contracts
    exiting across 2 fills; slippage similarly 1 tick per fill side). We assert
    the observed cost band is *reasonable* (not exact, since partial-fill
    slippage differs at TP1 vs stop vs runner), not a single fixed number.
    """
    d = _load(SMOKE_JSON)
    costs = []
    for c in d["cells"]:
        if c["symbol"] != "GC=F":
            continue
        for t in c["trades"]:
            cost = t["gross"] - t["net"]
            costs.append(cost)
    assert costs, "no GC trades found to check"
    arr = np.asarray(costs)
    # Friction should always be strictly positive (commission+slippage never
    # negative) and bounded well below any single trade's typical R (few
    # hundred to few thousand $ on 3 contracts) -- catches a sign-flip or a
    # units bug (e.g. reporting slippage in points not dollars).
    assert (arr > 0).all(), f"found non-positive friction (gross-net<=0) on {int((arr<=0).sum())} GC trades"
    assert arr.min() >= 15.0, f"suspiciously low GC friction, min={arr.min()} (expect >= ~$18 round-turn alone)"
    assert arr.max() <= 500.0, f"suspiciously high GC friction, max={arr.max()} (expect low hundreds at most)"


def test_family_a_beats_bh_flag_consistent_with_totals():
    d = _load(SMOKE_JSON)
    mismatches = []
    for c in d["cells"]:
        expected = c["total_net"] > c["buy_and_hold_total"]
        if bool(c["beats_bh"]) != expected:
            mismatches.append((c["symbol"], c["direction"], c["combo"],
                                c["total_net"], c["buy_and_hold_total"], c["beats_bh"]))
    assert not mismatches, f"beats_bh flag inconsistent with total_net vs buy_and_hold_total: {mismatches}"


def test_family_a_drop_top3_math():
    d = _load(SMOKE_JSON)
    mismatches = []
    for c in d["cells"]:
        nets = [t["net"] for t in c["trades"]]
        if len(nets) <= 3:
            expected = 0.0
        else:
            expected = round(float(sum(sorted(nets, reverse=True)[3:])), 2)
        if c["drop_top3_net"] != expected:
            mismatches.append((c["symbol"], c["direction"], c["combo"], c["drop_top3_net"], expected))
    assert not mismatches, f"drop_top3_net mismatches: {mismatches}"


def test_family_a_halves_stability_math():
    d = _load(SMOKE_JSON)
    mismatches = []
    for c in d["cells"]:
        sorted_trades = sorted(c["trades"], key=lambda t: t["date"])
        mid = len(sorted_trades) // 2
        exp_first = round(sum(t["net"] for t in sorted_trades[:mid]), 2)
        exp_second = round(sum(t["net"] for t in sorted_trades[mid:]), 2)
        h = c["halves_stability"]
        if h["first_half_total"] != exp_first or h["second_half_total"] != exp_second:
            mismatches.append((c["symbol"], c["direction"], c["combo"],
                                h["first_half_total"], exp_first, h["second_half_total"], exp_second))
        if h["first_half_n"] != mid or h["second_half_n"] != len(sorted_trades) - mid:
            mismatches.append(("n-split", c["symbol"], c["direction"], c["combo"],
                                h["first_half_n"], mid, h["second_half_n"], len(sorted_trades) - mid))
    assert not mismatches, f"halves_stability mismatches: {mismatches}"


def test_family_a_headline_with_without_exhibit_day_arithmetic():
    d = _load(SMOKE_JSON)
    headline = d["headline_with_without_exhibit_2026_08_07"]
    assert headline is not None, "Family A must have the headline split (DESIGN.md sec.2)"
    exhibit_date = "2026-08-07"
    with_total = 0.0
    without_total = 0.0
    n_exhibit = 0
    for c in d["cells"]:
        for t in c["trades"]:
            with_total += t["net"]
            if t["date"] == exhibit_date:
                n_exhibit += 1
            else:
                without_total += t["net"]
    assert round(with_total, 2) == headline["with_2026_08_07"], (
        f"WITH total recompute mismatch: {round(with_total,2)} vs reported {headline['with_2026_08_07']}")
    assert round(without_total, 2) == headline["without_2026_08_07"], (
        f"WITHOUT total recompute mismatch: {round(without_total,2)} vs reported {headline['without_2026_08_07']}")
    assert n_exhibit == headline["n_trades_on_2026_08_07"], (
        f"exhibit-day trade count mismatch: {n_exhibit} vs reported {headline['n_trades_on_2026_08_07']}")
    # sanity: with_total - without_total should equal the sum of exhibit-day nets
    exhibit_sum = sum(t["net"] for c in d["cells"] for t in c["trades"] if t["date"] == exhibit_date)
    assert abs((with_total - without_total) - exhibit_sum) < 0.02, (
        "with-without delta does not equal exhibit-day net sum")


def test_family_a_bh_fdr_family_size_and_alpha_reimplemented():
    d = _load(SMOKE_JSON)
    assert d["alpha"] == 0.05
    eligible = [c for c in d["cells"] if not c["null_unavailable"] and c["null"]["p_value"] is not None]
    assert len(eligible) == d["n_bh_fdr_eligible"]
    pvals = [c["null"]["p_value"] for c in eligible]
    survivors = _independent_bh_fdr(pvals, alpha=0.05)
    reported_survivors = [c["fdr_survivor"] for c in eligible]
    assert survivors == reported_survivors, (
        f"independent BH-FDR reimplementation disagrees with reported fdr_survivor flags:\n"
        f"recomputed={survivors}\nreported={reported_survivors}")
    n_recomputed_survivors = sum(1 for c in d["cells"] if _independent_bh_fdr(
        [x["null"]["p_value"] for x in eligible], 0.05)[eligible.index(c)] if c in eligible)
    assert d["n_clearing_cells"] == sum(1 for c in d["cells"] if c["clears"])


def test_family_a_clears_gate_reimplemented_per_cell():
    """Reimplement the DESIGN.md sec.5 ladder from scratch per cell and diff
    against the reported `clears` boolean -- this is the single field the
    verdict hinges on."""
    d = _load(SMOKE_JSON)
    mismatches = []
    for c in d["cells"]:
        oos_n = c["oos"]["n"]
        oos_mean = c["oos"]["mean"]
        expected = bool(
            oos_n >= d["min_oos_n"] and oos_mean is not None and oos_mean > 0
            and c["fdr_survivor"] and c["beats_bh"] and c["drop_top3_net"] > 0
        )
        if expected != c["clears"]:
            mismatches.append((c["symbol"], c["direction"], c["combo"], expected, c["clears"]))
    assert not mismatches, f"clears-gate reimplementation mismatches: {mismatches}"
    assert d["n_clearing_cells"] == sum(1 for c in d["cells"] if c["clears"]) == 0
    assert d["verdict"] == "KILL"


def test_family_a_signal_frequency_c27_sanity():
    """C27: any (symbol,combo,direction) firing signals on >80% of the ~60
    trading days in the smoke window is a noise-not-signal smell. Approximate
    trading-day count from distinct trade dates union across ALL cells of
    that symbol (a lower bound on the true days-in-window, since not every
    day fires a signal) -- if even this lower-bound check trips 80%, that's
    a genuine finding worth flagging."""
    d = _load(SMOKE_JSON)
    provenance = d["data_provenance"]
    for c in d["cells"]:
        n_days = len({t["date"] for t in c["trades"]})
        # can't know exact total trading days per-symbol without re-fetching bars;
        # use the disclosed rows/interval as an upper bound proxy instead: 60d
        # smoke window, and flag only if a cell's distinct-day count alone
        # exceeds 48 (80% of 60) -- a hard trip regardless of exact denominator.
        assert n_days <= 48, (
            f"{c['symbol']} {c['direction']} {c['combo']}: fired on {n_days} distinct days, "
            f"exceeds 80% of the 60-day smoke window on a raw trade-date-count basis alone")


# ---------------------------------------------------------------------------
# Family B (regime) -- spot check, per LENS-3 scope ("also spot check Family B")
# ---------------------------------------------------------------------------

def test_family_b_cell_count_matches_prereg():
    d = _load(REGIME_JSON)
    assert d["n_cells"] == 8, f"pre-reg is 8 cells (1 symbol x 2 dirs x 4 combos), got {d['n_cells']}"


def test_family_b_best_cell_recompute():
    """The integrator's claimed best-by-OOS-mean Family B cell: GC=F short
    0.5/0.1, oos_n=35, oos_mean=852.50. Recompute directly from its trades."""
    d = _load(REGIME_JSON)
    target = None
    for c in d["cells"]:
        if (c["symbol"] == "GC=F" and c["direction"] == "short"
                and c["combo"]["zone_atr_mult"] == 0.5 and c["combo"]["sweep_atr_mult"] == 0.1):
            target = c
            break
    assert target is not None, "could not find GC=F short 0.5/0.1 cell in Family B"
    oos_cut = dt.date.fromisoformat(d["oos_cut"])
    oos_nets = [t["net"] for t in target["trades"] if dt.date.fromisoformat(t["date"]) >= oos_cut]
    recomp = _independent_stats(oos_nets)
    assert recomp["n"] == target["oos"]["n"] == 35, f"oos_n mismatch: recomputed {recomp['n']} vs claimed 35 vs stored {target['oos']['n']}"
    assert recomp["mean"] == target["oos"]["mean"], f"oos_mean mismatch: recomputed {recomp['mean']} vs stored {target['oos']['mean']}"
    assert abs(target["oos"]["mean"] - 852.50) < 0.01, f"stored oos_mean {target['oos']['mean']} != claimed 852.50"


def test_family_b_min_p_value_claim():
    d = _load(REGIME_JSON)
    pvals = [c["null"]["p_value"] for c in d["cells"] if c["null"]["p_value"] is not None]
    assert pvals, "no p-values found in Family B"
    assert round(min(pvals), 4) == 0.0505, f"min p-value recomputed as {min(pvals)}, integrator claimed 0.0505"


def test_family_b_fdr_survivors_zero():
    d = _load(REGIME_JSON)
    survivors = sum(1 for c in d["cells"] if c.get("fdr_survivor"))
    assert survivors == 0
    assert d["n_clearing_cells"] == 0
    assert d["verdict"] == "KILL"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
