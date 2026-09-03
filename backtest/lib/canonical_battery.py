"""canonical_battery.py -- single source of truth for the G-battery pattern
(G_mean / G_oos / G_drop3 / G_bhfdr / G_n) that adjudicates gate-revalidation and
knob-flip decisions across this project.

FILED AS: queue.md BATTERY-LOGIC-DUPLICATED-ACROSS-TOOLS (LOW, 2026-08-30).

WHAT THIS FOLD ACTUALLY FOUND (2026-09-03 audit, before writing this file): the queue
item's premise -- "reimplemented inline, independently, in at least
backtest/autoresearch/daily_premium_budget_battery.py,
backtest/tools/gate_revalidation_structure_veto_extended_2026_08_23.py, and
backtest/tools/gate_revalidation_bearish_fill_bar_wholebook_2026_08_30.py" -- does NOT
hold on inspection:

  - gate_revalidation_structure_veto_extended_2026_08_23.py,
    gate_revalidation_bearish_fill_bar_extended_2026_08_23.py, and
    gate_revalidation_bearish_fill_bar_wholebook_2026_08_30.py all already
    `import gate_revalidation_ab as grab` and call `grab.g_battery` / `grab.bh_fdr` /
    `grab.one_sample_p` / `grab.is_oos_split` VERBATIM -- their own docstrings say so
    ("REUSES every pure function from gate_revalidation_ab.py UNCHANGED ... via direct
    import"). There was already exactly ONE implementation of the G-battery gate
    functions before this fold: `backtest/tools/gate_revalidation_ab.py`. Nothing was
    diverging.
  - backtest/autoresearch/daily_premium_budget_battery.py does NOT implement the
    G-battery at all. Its gates are `oos_positive` / `wf_median_ge_0.70` /
    `sub_window_stable` / `anchor_no_regression` -- the DIFFERENT, separately-named
    "OP-11 battery" pattern (CLAUDE.md OP-11: "Auto-ratify requires: OOS_positive AND
    WF >= 0.70 AND sub_window_stable AND anchor_no_regression"). It has zero G_mean /
    G_oos / G_drop3 / G_bhfdr / G_n gates and does not call bh_fdr/one_sample_p/
    drop_top_n anywhere. The queue item's filer conflated two different named battery
    patterns that happen to share the word "battery".

So the REAL (and much smaller) risk this fold closes is architectural, not a live
divergence: the one true G-battery implementation lived inside a `backtest/tools/`
*script* (gate_revalidation_ab.py, a one-off runner with its own `main()`), reached by
every downstream file via a `sys.path` + `import gate_revalidation_ab as grab` hack.
That is exactly the shape that invites a FUTURE new tool file to copy-paste instead of
import (there is no `backtest/lib/` module to import from). This file is that module:
the six pure functions are relocated here verbatim (byte-identical math, see the
regression test), and `gate_revalidation_ab.py` now imports them from here instead of
defining them -- so `grab.g_battery` etc. keep working unchanged for every existing
caller with ZERO caller-file edits.

`run_g_battery()` is a NEW convenience entry point (nothing currently calls it) for a
future caller that already has a flat `list[float]` of daily/per-trade deltas rather
than a list of trade-row dicts -- it wraps the same six functions with explicit,
documented defaults so a new caller does not have to re-derive them.

NOT the same helper as `backtest/lib/concentration.py::drop_top_n` -- that module
operates on `(date_iso_str, pnl)` record tuples and backs a DIFFERENT, lighter-weight
diagnostic (`gate_expiry_check.py`'s drop_top1/drop_top3 costing display), not the full
G-battery. Its own docstring already disclaims fold scope over this module's
`drop_top_n` ("gate_revalidation_ab.py's own drop_top_n is left untouched ... out of
this fold's scope"). Kept separate deliberately -- do not merge the two signatures.
"""
from __future__ import annotations

import math

# ============================================================ stats (relocated verbatim from
# backtest/tools/gate_revalidation_ab.py, itself ported from
# bull_gate_f5class_requal_2026_08_01.py:307 / shelf_hold_reclaim_study.py -- so p-values/BH
# remain directly comparable to that lineage) ==================================================
def one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 1.0
    tstat = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(tstat) / (2 ** 0.5))))))


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= (rank + 1) / m * q:
            max_k = rank
    sig = [False] * m
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


def drop_top_n(pnls: list[float], n_drop: int = 3) -> tuple[float, int]:
    """Total minus the sum of the (up to n_drop) largest WINNING trades. Only ever drops
    actual winners (pnl > 0) -- generalizes drop_best (which drops exactly 1 winner,
    bull_gate_atm_ssb_requalification's drop_top1 semantics) from 1 to N. An all-losing
    cohort's drop_topN equals its raw total (nothing to drop). Returns (value, n_dropped).

    Operates on a plain list[float] -- NOT the same call shape as
    backtest/lib/concentration.py::drop_top_n, which takes (date, pnl) record tuples for a
    different, lighter-weight instrument. Byte-identical arithmetic, different signature;
    kept separate on purpose (see module docstring)."""
    if not pnls:
        return 0.0, 0
    winners = sorted([p for p in pnls if p > 0], reverse=True)
    k = min(n_drop, len(winners))
    dropped_sum = sum(winners[:k])
    return round(sum(pnls) - dropped_sum, 2), k


def cohort_metrics(ok_rows: list[dict]) -> dict:
    pnls = [r["pnl"] for r in ok_rows]
    n = len(pnls)
    if n == 0:
        return {"n": 0}
    total = round(sum(pnls), 2)
    mean = round(total / n, 2)
    wins = sum(1 for p in pnls if p > 0)
    dtop3, k_dropped = drop_top_n(pnls, 3)
    return {
        "n": n, "total": total, "mean": mean, "wr_pct": round(100 * wins / n, 1),
        "drop_top3": dtop3, "n_dropped_for_drop_top3": k_dropped,
        "best": round(max(pnls), 2), "worst": round(min(pnls), 2),
    }


def is_oos_split(ok_rows_chrono: list[dict]) -> tuple[list[dict], list[dict]]:
    mid = len(ok_rows_chrono) // 2
    return ok_rows_chrono[:mid], ok_rows_chrono[mid:]


def g_battery(cohort: dict, oos_metrics: dict, pval: float, bh_pass: bool) -> dict:
    n = cohort.get("n", 0)
    g_mean = bool(n) and cohort.get("mean", 0) > 0
    g_oos = bool(oos_metrics.get("n", 0)) and oos_metrics.get("mean", -1) > 0
    g_drop3 = bool(n) and cohort.get("drop_top3", -1) > 0
    g_bhfdr = bool(bh_pass)
    g_n = n >= 15
    gates = {"G_mean": g_mean, "G_oos": g_oos, "G_drop3": g_drop3, "G_bhfdr": g_bhfdr, "G_n": g_n}
    if all(gates.values()):
        verdict = "UNBLOCK-ELIGIBLE"
    elif g_mean and g_oos and g_drop3 and g_bhfdr and not g_n:
        verdict = "UNDERPOWERED"
    else:
        verdict = "NOT-UNBLOCK-ELIGIBLE"
    return {"gates": gates, "verdict": verdict, "pval": round(pval, 4)}


# ============================================================ aggregate convenience entry
# point -- NOT called by any existing producer (every current caller already has trade-row
# dicts and orchestrates the six functions above itself, often across a multi-cell BH-FDR
# family). This exists for a FUTURE caller that only has a flat list of per-trade/per-day
# deltas. Defaults below are pinned to what 100% of the four existing G-battery producers
# (gate_revalidation_ab.py's own main() + the 3 files that import it) use today -- see
# test_canonical_battery.py::test_defaults_match_existing_caller_majority. =====================
def run_g_battery(
    daily_deltas: list[float],
    *,
    drop_n: int = 3,
    alpha: float = 0.10,
    oos_fraction: float = 0.5,
    n_floor: int = 15,
) -> dict:
    """Single-cohort, single-cell G-battery over a flat list[float] of per-trade (or
    per-day) P&L deltas. `oos_fraction` must be 0.5 -- the existing is_oos_split's exact
    floor-division 50/50 chronological split is the only behavior this wrapper reproduces;
    a non-0.5 value raises rather than silently drifting from every existing caller's
    methodology. `drop_n`/`alpha`/`n_floor` are free (they thread straight through to
    drop_top_n / bh_fdr / the g_n floor) but default to the value every current producer
    passes, so a caller that wants a DIFFERENT threshold must say so explicitly."""
    if oos_fraction != 0.5:
        raise ValueError(
            "run_g_battery only supports oos_fraction=0.5 (the existing is_oos_split "
            "chronological 50/50 split) -- no caller uses anything else; a different split "
            "needs its own reviewed methodology, not a silent parameter drift."
        )
    rows = [{"pnl": p} for p in daily_deltas]
    cohort = cohort_metrics(rows)
    if drop_n != 3:
        # cohort_metrics hardcodes drop_top_n(pnls, 3); honor a non-default drop_n explicitly
        # rather than silently ignoring it.
        dtop, k = drop_top_n(daily_deltas, drop_n)
        cohort = {**cohort, "drop_top3": dtop, "n_dropped_for_drop_top3": k}
    is_rows, oos_rows = is_oos_split(rows)
    oos_metrics = cohort_metrics(oos_rows)
    pval = one_sample_p(daily_deltas)
    bh_sig = bh_fdr([pval], q=alpha)
    battery = g_battery(cohort, oos_metrics, pval, bh_sig[0] if bh_sig else False)
    if n_floor != 15:
        n = cohort.get("n", 0)
        g_n = n >= n_floor
        gates = {**battery["gates"], "G_n": g_n}
        if all(gates.values()):
            verdict = "UNBLOCK-ELIGIBLE"
        elif gates["G_mean"] and gates["G_oos"] and gates["G_drop3"] and gates["G_bhfdr"] and not g_n:
            verdict = "UNDERPOWERED"
        else:
            verdict = "NOT-UNBLOCK-ELIGIBLE"
        battery = {**battery, "gates": gates, "verdict": verdict}
    return {
        "cohort": cohort,
        "is_half": cohort_metrics(is_rows),
        "oos_half": oos_metrics,
        "one_sample_p": round(pval, 4),
        "bh_fdr_significant": bool(bh_sig[0]) if bh_sig else False,
        "g_battery": battery,
    }


# ============================================================ equal-count sub-window buckets --
# NEW 2026-09-03, queue.md GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS
# (FORWARD-ONLY: never applied retroactively to an already-frozen prereg). Doctrine + threshold
# in markdown/research/BACKTESTING-PLAYBOOK.md #4.5. =============================================
def equal_count_buckets(
    deltas_in_time_order: list[float], n_buckets: int = 4
) -> list[tuple[int, int]]:
    """Split a chronologically-ordered list of CHANGED-trade deltas into `n_buckets`
    equal-count buckets. Returns [(start, end), ...] half-open index ranges into
    `deltas_in_time_order` (deltas_in_time_order[start:end] is one bucket) -- it does not
    slice the input itself, so the caller can apply the same boundaries to a parallel list
    of trade-row dicts.

    G4-style FIXED CALENDAR sub-windows (2025H1/H2/2026Q1/Q2...) can starve a low-fire-rate
    knob permanently: worked example `analysis/recommendations/
    tp1-r50-readjudication-2026-08-23.json` (R_tp100_f50, 20.4% fire rate) has 2025H1 and
    2026Q1 stuck at n_changed=4 each in both the original and a forward-extended run, so
    only 2 of 4 calendar windows can EVER qualify (>=5-changed floor). Equal-count buckets
    fix this by construction: every bucket gets floor(n/n_buckets) or ceil(n/n_buckets)
    changed trades, so if the total clears n_buckets * floor, every bucket clears it too --
    no bucket can be calendar-starved. Any remainder (n % n_buckets) goes to the LAST
    buckets, so a forward-only data extension only ever grows buckets going forward in
    time, consistent with the FORWARD-ONLY constraint.

    `deltas_in_time_order` must already be filtered to CHANGED trades only and sorted
    oldest-first -- this function does not filter or sort."""
    if n_buckets < 1:
        raise ValueError("n_buckets must be >= 1")
    n = len(deltas_in_time_order)
    base, remainder = divmod(n, n_buckets)
    boundaries: list[tuple[int, int]] = []
    start = 0
    for i in range(n_buckets):
        size = base + (1 if i >= n_buckets - remainder else 0)
        end = start + size
        boundaries.append((start, end))
        start = end
    return boundaries
