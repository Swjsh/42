"""scorecard_guards.py -- shared structural guards for every A/B / counterfactual scorecard
(built 2026-08-27, AUDIT-CORRECTIONS-2026-08-27).

WHY THIS EXISTS: an adversarial audit tonight found LIVE CORRUPTION in
analysis/recommendations/premium_cost_cap_1200.json + 3 sibling scorecards + the
SEPT-TUNE-OVERLAP-MATRIX (commit 12f86c11) -- phantom merged-bucket positions up to $8,816
(true max is $1,880) -- and, separately, the audit's #1 STRUCTURAL recommendation: every
scorecard cell was missing four guard fields that would have made the corruption, and other
overfitting failure modes, visible BEFORE ratification instead of after. This module is the
one place those four guards live so every future scorecard gets them for $0 marginal cost
instead of re-deriving (and re-getting-wrong) the formulas per script, the same failure mode
that let the merged-bucket basis silently leak into 5 files (L160-style: prose control fails,
one tested function doesn't).

THE FOUR GUARDS (per rule/cell):

  (i)   DAY-LEVEL bootstrap CI + P(pnl<=0) / P(PF<=1.0) -- bootstrap by TRADING DAY, not by
        trade. Project Gamma's 5 real-fills arms trade ONE shared signal
        (automation/state/fleet/build_shared_signal.py; documented r=0.846/95.7% sign
        agreement in analysis/journal/calendar-data.json's correlation_disclosure) -- a
        trade-level bootstrap would treat 5 near-simultaneous correlated fills as 5
        independent draws and understate the true variance. Resampling whole DAYS (with
        replacement) preserves the within-day cross-arm correlation structure without
        needing to model it explicitly.

  (ii)  EX-BEST-DAY sign-flip check -- remove the single best day's pnl and see if the
        cell's sign flips. A "profitable" rule whose entire edge lives in one day is not
        evidence of a robust edge; auto_fail_sign_flips_ex_best_day=True is a hard fail
        signal regardless of what the other gates say.

  (iii) SIGNAL-CLUSTER count alongside raw fill count -- arms fire the same signal within
        single-digit seconds of each other (verified real-tape gaps, 2026-08-27: same-signal
        entries across arms land 1-70s apart; a genuinely separate re-trigger of the same
        strike lands minutes later). Reporting "n=20 blocked trades" when that's really ~6-8
        independent signal instances overstates the evidence 3x-5x.

  (iv)  BENJAMINI-HOCHBERG FDR (q=0.10) across every cell scanned in the SAME sweep, with the
        scanned-cell count disclosed. A sweep that tests several thresholds/rules and reports
        the best-looking one without a multiple-comparisons correction is exactly how the
        original September-tune sweep found "signal" in what a corrected re-run mostly
        rejects.

Stdlib only, deterministic (explicit seed, default 1337), $0 cost -- no numpy/pandas
required so this runs under the plain system python trades_enriched.py already requires
(no venv dependency), matching this repo's C7/C9/cost-discipline conventions.
"""
from __future__ import annotations

import math
import random
from typing import Optional

DEFAULT_SEED = 1337
DEFAULT_N_BOOT = 2000
DEFAULT_CI = 0.90


# --------------------------------------------------------------------------- #
# Guard (i): day-level bootstrap
# --------------------------------------------------------------------------- #

def day_level_bootstrap(
    day_trade_pnls: dict,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    ci_level: float = DEFAULT_CI,
) -> dict:
    """Block-bootstrap by TRADING DAY (never by trade -- see module docstring).

    Args:
        day_trade_pnls: {date_str: [trade_pnl, trade_pnl, ...]} -- every trade's pnl for
            that day, for the population/rule-delta being tested. An empty dict or a dict
            with fewer than 2 distinct days returns a degenerate result (n_days recorded,
            everything else None) -- a bootstrap over 0-1 days cannot estimate variance and
            must not fabricate a CI (C7: fail loud, don't fake precision).
        n_boot: number of resamples (default 2000 -- stable to 3 sig figs for CI bounds at
            typical Gamma sample sizes, $0 cost, sub-second on stdlib).
        seed: fixed seed -> the SAME scorecard input always reproduces the SAME CI (no
            silent day-to-day drift from an unseeded RNG masquerading as a "different"
            result).
        ci_level: central CI mass, e.g. 0.90 -> report the [5th, 95th] percentile band.

    Returns dict with:
        n_days, n_boot, seed,
        pnl_mean, pnl_ci_low, pnl_ci_high, p_pnl_le_0,
        pf_mean, pf_ci_low, pf_ci_high, p_pf_le_1 (None if every resample has zero gross
            loss -- PF undefined, never fabricated as inf),
    """
    dates = sorted(day_trade_pnls.keys())
    n_days = len(dates)
    result = {
        "n_days": n_days,
        "n_boot": n_boot,
        "seed": seed,
        "ci_level": ci_level,
        "pnl_mean": None, "pnl_ci_low": None, "pnl_ci_high": None, "p_pnl_le_0": None,
        "pf_mean": None, "pf_ci_low": None, "pf_ci_high": None, "p_pf_le_1": None,
        "insufficient_days": n_days < 2,
    }
    if n_days < 2:
        return result

    rng = random.Random(seed)
    day_lists = [day_trade_pnls[d] for d in dates]

    pnl_samples: list = []
    pf_samples: list = []
    for _ in range(n_boot):
        picks = [day_lists[rng.randrange(n_days)] for _ in range(n_days)]
        pooled = [p for day in picks for p in day]
        total = sum(pooled)
        pnl_samples.append(total)
        gp = sum(p for p in pooled if p > 0)
        gl = sum(p for p in pooled if p < 0)
        pf_samples.append((gp / abs(gl)) if gl < 0 else None)

    pnl_samples.sort()
    lo_idx = int((1 - ci_level) / 2 * n_boot)
    hi_idx = int((1 + ci_level) / 2 * n_boot) - 1
    hi_idx = min(hi_idx, n_boot - 1)
    result["pnl_mean"] = round(sum(pnl_samples) / n_boot, 2)
    result["pnl_ci_low"] = round(pnl_samples[lo_idx], 2)
    result["pnl_ci_high"] = round(pnl_samples[hi_idx], 2)
    result["p_pnl_le_0"] = round(sum(1 for p in pnl_samples if p <= 0) / n_boot, 4)

    pf_valid = sorted(p for p in pf_samples if p is not None)
    if pf_valid:
        n_valid = len(pf_valid)
        pf_lo_idx = int((1 - ci_level) / 2 * n_valid)
        pf_hi_idx = min(int((1 + ci_level) / 2 * n_valid) - 1, n_valid - 1)
        result["pf_mean"] = round(sum(pf_valid) / n_valid, 4)
        result["pf_ci_low"] = round(pf_valid[pf_lo_idx], 4)
        result["pf_ci_high"] = round(pf_valid[pf_hi_idx], 4)
        result["p_pf_le_1"] = round(sum(1 for p in pf_valid if p <= 1.0) / n_valid, 4)
        result["pf_undefined_resamples"] = n_boot - n_valid
    else:
        result["pf_undefined_resamples"] = n_boot

    return result


def bootstrap_pvalue(day_trade_pnls: dict, n_boot: int = DEFAULT_N_BOOT,
                      seed: int = DEFAULT_SEED) -> Optional[float]:
    """Convenience: just the one-sided empirical bootstrap p-value P(total_pnl<=0), for
    feeding into benjamini_hochberg across a sweep of cells. None if <2 days (can't test)."""
    boot = day_level_bootstrap(day_trade_pnls, n_boot=n_boot, seed=seed)
    return boot["p_pnl_le_0"]


# --------------------------------------------------------------------------- #
# Guard (ii): ex-best-day sign flip
# --------------------------------------------------------------------------- #

def _sign(x: float) -> int:
    if x > 1e-9:
        return 1
    if x < -1e-9:
        return -1
    return 0


def ex_best_day(day_pnls: dict) -> dict:
    """Remove the single best trading day's pnl and check whether the cell's sign flips.

    Args:
        day_pnls: {date_str: day_total_pnl} -- ALREADY summed per day (not per-trade lists;
            use day_level_bootstrap for the trade-level version).

    Returns dict with: total_pnl, best_day, best_day_pnl, ex_best_day_pnl,
        auto_fail_sign_flips_ex_best_day (bool -- TRUE = FAIL, the audit's required field
        name verbatim), n_days.

    A cell with 0-1 days has no "best day to remove" in any meaningful sense --
    auto_fail is reported False (nothing to flip) with best_day=None, never fabricated.
    """
    n_days = len(day_pnls)
    total = round(sum(day_pnls.values()), 2) if day_pnls else 0.0
    if n_days == 0:
        return {
            "total_pnl": 0.0, "best_day": None, "best_day_pnl": None,
            "ex_best_day_pnl": 0.0, "auto_fail_sign_flips_ex_best_day": False,
            "n_days": 0,
        }
    best_day = max(day_pnls, key=lambda d: day_pnls[d])
    best_day_pnl = round(day_pnls[best_day], 2)
    ex_best = round(total - best_day_pnl, 2)
    flips = _sign(total) != _sign(ex_best)
    return {
        "total_pnl": total,
        "best_day": best_day,
        "best_day_pnl": best_day_pnl,
        "ex_best_day_pnl": ex_best,
        "auto_fail_sign_flips_ex_best_day": flips,
        "n_days": n_days,
    }


# --------------------------------------------------------------------------- #
# Guard (iii): signal-cluster count
# --------------------------------------------------------------------------- #

def signal_cluster_n(
    entries: list,
    window_s: float = 60.0,
    date_key: str = "date",
    ts_key: str = "entry_ts_et",
    symbol_key: str = "sym",
) -> dict:
    """Collapse near-simultaneous same-signal entries across arms into ONE cluster.

    CLUSTERING RULE (stated + justified per the audit's requirement): two entries cluster
    together iff they share (date, symbol) -- same underlying option contract, i.e. the
    same signal instance's chosen strike -- AND their entry timestamps are within
    `window_s` seconds of each other, chained transitively (A-B within window and B-C
    within window clusters A/B/C together even if A-C exceeds window). Default
    window_s=60: real-tape entry-timestamp gaps for arms firing off ONE shared-signal
    instance land 1-70s apart (verified 2026-08-27 across multiple sample days); a
    SEPARATE re-trigger of the same strike (a genuinely new signal instance, not the
    same one propagating to more arms) lands 4-40+ minutes later in every observed case.
    60s comfortably absorbs execution-path latency variance across the 5 arms without
    merging genuinely distinct signal instances.

    Args:
        entries: list of dicts, each carrying at least date_key/ts_key/symbol_key.
        ts_key: ISO-8601 datetime string field (naive ET, e.g. trades-enriched.jsonl's
            entry_ts_et). Entries missing a parseable timestamp each become their OWN
            singleton cluster (never silently dropped or merged by guesswork -- C7).

    Returns dict: fill_n, signal_cluster_n, window_s, cluster_sizes (list of ints, one per
        cluster, descending -- lets a caller see e.g. "20 fills collapsed into 7 clusters,
        largest cluster n=5").
    """
    from datetime import datetime

    def _parse(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).rstrip("Z"))
        except ValueError:
            return None

    fill_n = len(entries)
    groups: dict = {}
    for e in entries:
        key = (e.get(date_key), e.get(symbol_key))
        groups.setdefault(key, []).append(e)

    cluster_sizes: list = []
    for key, group in groups.items():
        timed = [(e, _parse(e.get(ts_key))) for e in group]
        timed_ok = sorted((t for t in timed if t[1] is not None), key=lambda t: t[1])
        timed_bad = [t for t in timed if t[1] is None]

        cluster: list = []
        for e, ts in timed_ok:
            if not cluster:
                cluster = [(e, ts)]
                continue
            _, last_ts = cluster[-1]
            if (ts - last_ts).total_seconds() <= window_s:
                cluster.append((e, ts))
            else:
                cluster_sizes.append(len(cluster))
                cluster = [(e, ts)]
        if cluster:
            cluster_sizes.append(len(cluster))
        # entries with no parseable timestamp: each its own singleton cluster
        cluster_sizes.extend([1] * len(timed_bad))

    cluster_sizes.sort(reverse=True)
    return {
        "fill_n": fill_n,
        "signal_cluster_n": len(cluster_sizes),
        "window_s": window_s,
        "cluster_sizes": cluster_sizes,
    }


# --------------------------------------------------------------------------- #
# Guard (iv): Benjamini-Hochberg FDR
# --------------------------------------------------------------------------- #

def benjamini_hochberg(pvalues: dict, q: float = 0.10) -> dict:
    """Standard BH step-up FDR procedure across every cell tested in one sweep.

    Args:
        pvalues: {cell_id: p_value}. A cell with p_value=None (e.g. too few days to
            bootstrap) is EXCLUDED from the correction (never coerced to 0 or 1 -- that
            would silently bias the correction) and listed separately in
            `excluded_no_pvalue`.
        q: false-discovery-rate threshold, default 0.10 per the audit's spec.

    Returns dict: q, m (cells actually tested), threshold_rank, rejected (list of cell_ids
        surviving FDR correction, i.e. still "significant" after the multiple-comparisons
        adjustment), results ({cell_id: {p, rank, bh_critical, significant}}),
        excluded_no_pvalue (list of cell_ids that had no p-value to test).
    """
    excluded = [cid for cid, p in pvalues.items() if p is None]
    tested = sorted(((cid, p) for cid, p in pvalues.items() if p is not None),
                     key=lambda kv: kv[1])
    m = len(tested)
    results: dict = {}
    threshold_rank = 0
    if m > 0:
        # find largest rank k (1-indexed) such that p_(k) <= (k/m)*q
        for rank, (cid, p) in enumerate(tested, start=1):
            crit = (rank / m) * q
            if p <= crit:
                threshold_rank = rank
        for rank, (cid, p) in enumerate(tested, start=1):
            crit = round((rank / m) * q, 6)
            results[cid] = {
                "p": p, "rank": rank, "bh_critical": crit,
                "significant": rank <= threshold_rank,
            }
    rejected = [cid for cid, r in results.items() if r["significant"]]
    return {
        "q": q,
        "m": m,
        "threshold_rank": threshold_rank,
        "rejected": rejected,
        "results": results,
        "excluded_no_pvalue": excluded,
    }


# --------------------------------------------------------------------------- #
# Bundle: everything except FDR (which needs ALL cells in a sweep at once)
# --------------------------------------------------------------------------- #

def compute_cell_guards(
    day_trade_pnls: dict,
    entries: list,
    n_boot: int = DEFAULT_N_BOOT,
    seed: int = DEFAULT_SEED,
    cluster_window_s: float = 60.0,
    date_key: str = "date",
    ts_key: str = "entry_ts_et",
    symbol_key: str = "sym",
) -> dict:
    """Convenience bundle: guards (i)+(ii)+(iii) for ONE scorecard cell. Guard (iv) (FDR)
    is intentionally NOT bundled here -- it needs every cell's p-value in the same sweep,
    computed once by the caller via benjamini_hochberg() after calling this per cell."""
    day_pnls = {d: round(sum(v), 2) for d, v in day_trade_pnls.items()}
    return {
        "bootstrap": day_level_bootstrap(day_trade_pnls, n_boot=n_boot, seed=seed),
        "ex_best_day": ex_best_day(day_pnls),
        "signal_cluster": signal_cluster_n(
            entries, window_s=cluster_window_s,
            date_key=date_key, ts_key=ts_key, symbol_key=symbol_key,
        ),
    }
