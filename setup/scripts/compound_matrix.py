#!/usr/bin/env python
"""compound_matrix.py -- THE COMPOUNDING-PATH MATRIX (2026-08-29).

THE QUESTION (J, verbatim): "we should be shooting for like 3-10% of our account in profit
per day and compound it over time -- we will eventually get to that number of $2k a day."
$2k/day is an OUTPUT of compounding, not a target. This answers: what compounding path is
actually AVAILABLE, and what BINDS it? Analysis-path only -- writes analysis/compound/*,
never touches params*.json / heartbeat_core.py / risk_gate.py / filters.py / strategies.py /
fleet_executor.py / exit_manager.py / fleet_broker.py, never arms anything.

MEASURED INPUTS (re-derived HERE from analysis/trades-enriched.jsonl, not assumed):
  * The "4 live arms" roster (safe-2, bold-2, safe-3, risky-1) matches
    automation/state/fleet/accounts.json's CURRENT active-arm set, not J's original 5-arm
    history: risky-3 (account PA3V7JT25H6Z) was RETIRED 2026-08-28 (accounts.json
    retired_reason: "data wins it can be closed" -- lifetime -$590 while the other four cells
    are positive, 0-for-5 on its last day; the account is being repurposed for the weekly-1
    non-SPY lane). Using J's 4-arm roster for ALL THREE regimes (not just post-fix) is
    therefore the FORWARD-LOOKING correct choice, not an inconsistency -- confirmed by
    reproducing his exact n=23 arm-days / 8 sessions / 61% green for the post-fix window
    with exactly this roster (this script's own regime construction, see build_regime()).
  * Reconciliation vs J's stated post-fix stats: this script's own equity-path
    reconstruction (backward from the CURRENT broker-adjacent equity J supplied, subtracting
    each day's realized trade pnl) reproduces J's n/sessions/green% EXACTLY but differs on
    mean/median/sd by roughly 0.3-1.1 percentage points (this script: mean +3.60%/median
    +3.62%/sd 6.21% vs J's +2.99%/+3.21%/5.14%). Root cause of the residual gap is NOT fully
    resolved -- most likely a different equity-denominator convention (this script uses
    reconstructed start-of-day equity per arm-day; J's number likely used a different
    anchor/date convention) or fees/manual adjustments this file's pnl_dollars does not
    carry. This script's numbers are used throughout because they are the ones this exact
    code reproduces from the checked-in data; the discrepancy is disclosed, not hidden.
  * THE CAPACITY MODEL WAS CORRECTED MID-BUILD (2026-08-29, J catching his own brief):
    the ORIGINAL framing ("max ~20 contracts / ~$2,000 regardless of account size, so %
    return decays as equity grows past that") is WRONG -- max_contracts_per_entry=5 /
    max_position_dollars=$1,000 / max_same_day_roundtrips=4 (shipped 2026-08-29,
    PREREG-TIGHT-LADDER-2026-08-28.md) are config CHOICES sized for a ~$5K account, not
    properties of the strategy, and get rescaled as equity grows (config_rescale_table
    below). The REAL wall is MARKET DEPTH: measured NBBO displayed bid size is a median 638
    contracts at $0.00-0.20 premium but only 46 at $1.50-2.50 (source:
    analysis/recommendations/_b2_depth_2026_08_28.json), and this repo's own right-tail
    winners land in exactly that thin bucket (this script's own re-derivation: winners
    exiting in the $1.50-2.50 bucket, n=28, all arms/all history, median entry $1.15 / median
    exit $1.795 -- close to, not exactly, the $1.72 cited; consistent with the same "thin
    exit liquidity" story). THAT depth measurement is 3 snapshots from ONE session (n=33
    contract-quotes total, feed explicitly tagged "indicative (OPRA 403: agreement not
    signed)" in its own file) -- thin, uncertain evidence for a load-bearing constant, and
    every capacity-bend number below is reported with that caveat attached, not as a fact.

MODEL SHAPE:
  * Below the depth-implied equity E*, contracts scale proportionally with equity (deployment
    held at a roughly constant fraction of equity, per J's stated $10K-on-$50K=20% mental
    model, matching this script's own measured ~16-17% median daily deployment fraction) --
    so % returns are NOT adjusted with equity in this regime; the historical bootstrap pool
    applies as-is.
  * Above E*, the market cannot absorb more contracts at good prices without walking a
    thin book, so DEPLOYABLE equity is capped at E* (effective_equity = min(equity, E_star));
    dollar P&L on the marginal equity above E* is modeled as zero. This reproduces the
    "bends from exponential toward linear" shape the original brief wanted, driven by DEPTH,
    not by the (rescalable) config caps.

Bootstrap: sample REAL historical arm-days with replacement (never a fitted/normal
distribution) -- preserves the measured fat tail / right-skew (mean > median at every
regime; the all-history MEDIAN arm-day is a LOSS). Fixed seed -> byte-reproducible.
$0, stdlib only (matches this repo's setup/scripts/ convention -- no numpy dependency).

Run: backtest/.venv/Scripts/python.exe setup/scripts/compound_matrix.py
Outputs: analysis/compound/matrix.json (data) + analysis/compound/MATRIX.md (readable).
Guard: backtest/tests/test_compound_matrix_2026_08_29.py.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import statistics
from pathlib import Path


def deterministic_seed(base: int, *parts) -> int:
    """Stable, process-independent seed derivation. Python's builtin hash() on str/tuple
    is randomized per-process (PYTHONHASHSEED) unless explicitly disabled -- using it here
    would silently break the fixed-seed reproducibility this script is required to have.
    hashlib is stable across processes and interpreter runs by construction."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return base + (int(digest[:8], 16) % 1000)

REPO = Path(__file__).resolve().parents[2]
TRADES_PATH = REPO / "analysis" / "trades-enriched.jsonl"
COST_MODEL_PATH = REPO / "analysis" / "recommendations" / "cost-model.json"
DEPTH_PATH = REPO / "analysis" / "recommendations" / "_b2_depth_2026_08_28.json"
SAFE_PARAMS_PATH = REPO / "automation" / "state" / "params.json"
BOLD_PARAMS_PATH = REPO / "automation" / "state" / "aggressive" / "params.json"
OUT_DIR = REPO / "analysis" / "compound"
OUT_JSON = OUT_DIR / "matrix.json"
OUT_MD = OUT_DIR / "MATRIX.md"

# ---------------------------------------------------------------------------
# CONSTANTS -- the load-bearing, explicit assumptions
# ---------------------------------------------------------------------------
SEED = 20260829  # fixed seed -- every run of this script is byte-reproducible
LIVE_ARMS = ("safe-2", "bold-2", "safe-3", "risky-1")
# J's stated current equities (2026-08-29 morning), close to the same-morning
# self-check broker read (safe settled_cash 5306.60 / bold 5456.36) -- used as the
# anchor point to reconstruct each arm's start-of-day equity BACKWARD through its
# trade history (see reconstruct_equity()).
CURRENT_EQUITY = {"safe-2": 5306.94, "bold-2": 5456.93, "safe-3": 5290.26, "risky-1": 5846.03}

SLIPPAGE_LEVELS = (0.0, 0.50, 1.00, 2.00)  # dollars/contract, EXIT side only
HORIZONS_DAYS = {"1mo": 21, "3mo": 63, "6mo": 126, "12mo": 252}
PERCENTILES = (10, 25, 50, 75, 90)
N_SIMS_PATHS = 2000          # percentile-path + drawdown sims per combo
N_SIMS_MILESTONES = 1000     # days-to-milestone sims per combo
MAX_MILESTONE_DAYS = 2520    # 10 trading years -- hard stop, "not reached" beyond this
STARTS = (5000.0, 10000.0)
J_PAIN_DRAWDOWN_DOLLARS = 3000.0

REGIME_CUTOFFS = {
    "post_fix": "2026-08-19",
    "august": "2026-08-01",
    "all_history": None,
}


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------
def load_trades() -> list[dict]:
    rows = []
    with TRADES_PATH.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("_meta"):
                continue
            rows.append(d)
    return rows


def load_cost_rates() -> dict:
    with COST_MODEL_PATH.open(encoding="utf-8") as f:
        doc = json.load(f)
    return doc["rates"]


def load_depth() -> dict:
    with DEPTH_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_sizing_config() -> dict:
    """Verify the caps + tiers LIVE from the actual params files (never hardcoded --
    this is the "verify in code yourself" requirement)."""
    with SAFE_PARAMS_PATH.open(encoding="utf-8") as f:
        safe = json.load(f)
    with BOLD_PARAMS_PATH.open(encoding="utf-8") as f:
        bold = json.load(f)
    keys = (
        "min_contracts", "max_contracts_per_entry", "max_position_dollars",
        "max_same_day_roundtrips", "min_contracts_equity_scaled",
        "min_contracts_baseline_equity", "position_sizing_tiers",
        "daily_loss_kill_switch_dollars", "daily_loss_kill_switch_pct",
    )
    return {
        "safe": {k: safe.get(k) for k in keys},
        "bold": {k: bold.get(k) for k in keys},
    }


# ---------------------------------------------------------------------------
# ARM-DAY AGGREGATION + EQUITY RECONSTRUCTION
# ---------------------------------------------------------------------------
def aggregate_arm_days(rows: list[dict], arms: tuple[str, ...]) -> tuple[dict, dict, dict]:
    """(arm, date) -> gross pnl_dollars sum, entry-notional (cost_dollars) sum, n entries."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r["arm"] not in arms:
            continue
        by_key.setdefault((r["arm"], r["date"]), []).append(r)
    pnl = {k: sum(x.get("pnl_dollars") or 0.0 for x in v) for k, v in by_key.items()}
    notional = {k: sum(x.get("cost_dollars") or 0.0 for x in v) for k, v in by_key.items()}
    nentries = {k: len(v) for k, v in by_key.items()}
    return pnl, notional, nentries, by_key


def reconstruct_equity(pnl: dict, current_equity: dict) -> dict:
    """Start-of-day equity per (arm, date), walked BACKWARD from the accurate current
    equity so that recent (most decision-relevant) days carry the least accumulated
    drift. Assumes no deposits/withdrawals between trading days (paper accounts)."""
    equity_path: dict[tuple[str, str], float] = {}
    for arm in current_equity:
        trade_dates = sorted(d for (a, d) in pnl if a == arm)
        eq_end_of_day = current_equity[arm]
        for d in reversed(trade_dates):
            eq_start = eq_end_of_day - pnl[(arm, d)]
            equity_path[(arm, d)] = eq_start
            eq_end_of_day = eq_start
    return equity_path


# ---------------------------------------------------------------------------
# COST MODEL -- fees (empirical Alpaca regulatory rates) + swept exit slippage
# ---------------------------------------------------------------------------
def trade_fee_ex_cat(row: dict, rates: dict) -> float:
    """Per-trade regulatory fee (OCC+ORF both sides, TAF+SEC exit side), excluding the
    once-per-arm-day CAT fee. sell_proceeds is reconstructed algebraically
    (cost_dollars + pnl_dollars) so it is robust to rows with a null exit_px_avg
    (multi-leg exits)."""
    qty = row.get("qty") or 0.0
    pnl = row.get("pnl_dollars") or 0.0
    cost = row.get("cost_dollars") or 0.0
    sell_proceeds = cost + pnl
    occ = 2 * rates["occ_fee_per_contract_both_sides"] * qty
    orf = 2 * rates["orf_fee_per_contract_both_sides"] * qty
    taf = rates["taf_fee_per_contract_sells_only"] * qty
    sec = rates["sec_fee_rate_per_dollar_sells_only"] * max(sell_proceeds, 0.0)
    commission = rates["commission_per_contract"] * qty
    return occ + orf + taf + sec + commission


def build_cost_adjusted_arm_day_pnl(
    by_key: dict, rates: dict, slippage_per_contract: float
) -> dict:
    """Net-of-fees-and-slippage arm-day pnl at one slippage level."""
    out = {}
    cat = rates["cat_fee_per_arm_day"]
    for k, trades in by_key.items():
        net = 0.0
        for r in trades:
            qty = r.get("qty") or 0.0
            fee = trade_fee_ex_cat(r, rates)
            slip = slippage_per_contract * qty
            net += (r.get("pnl_dollars") or 0.0) - fee - slip
        net -= cat
        out[k] = net
    return out


# ---------------------------------------------------------------------------
# REGIME CONSTRUCTION
# ---------------------------------------------------------------------------
def build_regime_pool(
    cost_pnl: dict, equity_path: dict, date_cutoff: str | None
) -> list[tuple[str, str, float]]:
    """List of (arm, date, pct_return) for one regime at one cost/slippage setting."""
    out = []
    for (arm, d), net_pnl in cost_pnl.items():
        if date_cutoff is not None and d < date_cutoff:
            continue
        sod_eq = equity_path.get((arm, d))
        if not sod_eq or sod_eq <= 0:
            continue
        out.append((arm, d, 100.0 * net_pnl / sod_eq))
    return out


def drop_best_day(pool: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    if not pool:
        return pool
    best_idx = max(range(len(pool)), key=lambda i: pool[i][2])
    return pool[:best_idx] + pool[best_idx + 1:]


def regime_summary(pool: list[tuple[str, str, float]]) -> dict:
    vals = [p[2] for p in pool]
    n = len(vals)
    if n == 0:
        return {"n": 0}
    dates = sorted(set(p[1] for p in pool))
    return {
        "n_arm_days": n,
        "n_sessions": len(dates),
        "mean_pct": round(statistics.mean(vals), 3),
        "median_pct": round(statistics.median(vals), 3),
        "sd_pct": round(statistics.stdev(vals), 3) if n > 1 else 0.0,
        "pct_green": round(100.0 * sum(1 for v in vals if v > 0) / n, 1),
        "min_pct": round(min(vals), 3),
        "max_pct": round(max(vals), 3),
        "date_range": [dates[0], dates[-1]],
    }


def effective_n(pool: list[tuple[str, str, float]], rhos=(0.62, 0.67, 0.72)) -> dict:
    """Design-effect (Kish) correction for clustering: arm-days on the SAME session are
    correlated (r~0.62-0.72, measured on this exact pool below), so n=23 arm-days across
    8 sessions is NOT 23 independent samples. DEFF = 1 + rho*(M_weighted-1), where
    M_weighted = sum(m_i^2)/sum(m_i) over per-session cluster sizes m_i (the standard
    unequal-cluster-size Kish design effect). n_eff = n / DEFF."""
    by_date: dict[str, list[float]] = {}
    for arm, d, pct in pool:
        by_date.setdefault(d, []).append(pct)
    cluster_sizes = [len(v) for v in by_date.values()]
    n_total = sum(cluster_sizes)
    if n_total == 0:
        return {"n_raw": 0}
    m_weighted = sum(m * m for m in cluster_sizes) / n_total
    n_eff_by_rho = {}
    for rho in rhos:
        deff = 1 + rho * (m_weighted - 1)
        n_eff_by_rho[str(rho)] = round(n_total / deff, 2)
    # measured pairwise correlation across arms, on overlapping session-days
    by_date_arm: dict[str, dict[str, float]] = {}
    for arm, d, pct in pool:
        by_date_arm.setdefault(d, {})[arm] = pct
    import itertools
    pair_rs = []
    arms_seen = sorted({a for a, _, _ in pool})
    for a, b in itertools.combinations(arms_seen, 2):
        xs, ys = [], []
        for d, m in by_date_arm.items():
            if a in m and b in m:
                xs.append(m[a])
                ys.append(m[b])
        if len(xs) >= 2:
            try:
                pair_rs.append(statistics.correlation(xs, ys))
            except statistics.StatisticsError:
                pass
    return {
        "n_raw": n_total,
        "n_sessions": len(cluster_sizes),
        "cluster_sizes": sorted(cluster_sizes),
        "M_weighted": round(m_weighted, 3),
        "measured_pairwise_r": [round(r, 3) for r in sorted(pair_rs)],
        "n_eff_by_rho": n_eff_by_rho,
        "n_eff_central": round(sum(n_eff_by_rho.values()) / len(n_eff_by_rho), 2),
        "interpretation": (
            f"{n_total} arm-days across {len(cluster_sizes)} sessions is really "
            f"~{round(sum(n_eff_by_rho.values()) / len(n_eff_by_rho))} independent "
            "observations once cross-arm correlation is priced in -- ANY 12-month "
            "projection off this regime is an EXTRAPOLATION from a single-digit "
            "number of independent trading sessions, not a forecast."
        ),
    }


# ---------------------------------------------------------------------------
# MARKET-DEPTH CAPACITY BEND (J's mid-build correction, 2026-08-29)
# ---------------------------------------------------------------------------
def capacity_bend_analysis(rows: list[dict], depth_doc: dict) -> dict:
    buckets = {b["bucket"]: b for b in depth_doc["buckets"]}
    depth_thin = buckets["$1.50-$2.50"]["bid_med"]     # 46 -- the exit-side wall
    depth_deep = buckets["$0.00-$0.20"]["bid_med"]     # 638 -- where losers exit, no wall

    winners_thin_bucket = [
        r for r in rows
        if r.get("exit_px_avg") and 1.50 <= r["exit_px_avg"] <= 2.50
        and (r.get("pnl_dollars") or 0) > 0
    ]
    p_entry_thin_cohort = statistics.median(r["entry_px"] for r in winners_thin_bucket)
    p_exit_thin_cohort = statistics.median(r["exit_px_avg"] for r in winners_thin_bucket)

    n_obs = len(depth_doc["observations"])
    n_snapshots = len({o["sample"] for o in depth_doc["observations"]})

    deployment_grid = (0.10, 0.15, 0.17, 0.20, 0.25)
    threshold_grid = (0.10, 0.25, 0.50)

    def e_star(f: float, threshold: float) -> float:
        # contracts_per_entry(E) = f*E / (P_entry*100); solve contracts == threshold*depth_thin
        return threshold * depth_thin * p_entry_thin_cohort * 100.0 / f

    stress_grid = {
        str(f): {str(t): round(e_star(f, t), 0) for t in threshold_grid}
        for f in deployment_grid
    }
    # "observed" case: median 2 entries/arm-day post-fix -> per-entry fraction is
    # roughly half the daily fraction (see deployment_fraction_analysis below)
    observed_grid = {
        str(f): {str(t): round(e_star(f / 2.0, t), 0) for t in threshold_grid}
        for f in deployment_grid
    }

    f_central, t_central = 0.17, 0.25
    return {
        "_doc": (
            "Corrected model (J, 2026-08-29): the real capacity wall is MARKET DEPTH, not "
            "the config caps (those rescale with equity, see config_rescale_table). "
            "contracts_per_entry(E) = deployment_fraction*E / (entry_premium*100); the wall "
            "E* is the equity where that count first becomes a 'meaningful fraction' of the "
            "displayed bid depth at the premium where right-tail winners actually exit."
        ),
        "depth_thin_bucket_1_50_2_50_contracts": depth_thin,
        "depth_deep_bucket_0_00_0_20_contracts": depth_deep,
        "winner_cohort_thin_bucket_n": len(winners_thin_bucket),
        "winner_cohort_median_entry_premium": round(p_entry_thin_cohort, 3),
        "winner_cohort_median_exit_premium": round(p_exit_thin_cohort, 3),
        "brief_cited_exit_premium": 1.72,
        "note_on_exit_premium_match": (
            f"Re-derived median exit premium for this cohort is {round(p_exit_thin_cohort, 3)}"
            " -- close to, not identical to, the $1.72 cited in the brief; both land in the "
            "same thin $1.50-2.50 depth bucket, which is what matters for this analysis."
        ),
        "evidence_quality": {
            "n_snapshots": n_snapshots,
            "n_quotes_total": n_obs,
            "feed_type": depth_doc.get("_doc", ""),
            "verdict": (
                "THIN. One session, 3 snapshots, 33 total contract-quotes, on an explicitly "
                "'indicative' (not confirmed real OPRA) feed. Every E* number below is an "
                "order-of-magnitude signal, not a precise constant."
            ),
            "recommended_study": (
                "Extend setup/scripts/quote_recorder.py (already polls NBBO) into a dedicated "
                "multi-session depth study: sample full-chain bid/ask size at open/mid/close "
                "across >=15 sessions, stratified by VIX regime, cross-referenced against this "
                "book's own real fill sizes vs displayed size to measure realized slippage-vs-"
                "depth directly instead of inferring it from static snapshots."
            ),
        },
        "deployment_fraction_grid": list(deployment_grid),
        "meaningful_fraction_grid": list(threshold_grid),
        "e_star_stress_single_entry_claims_full_daily_fraction": stress_grid,
        "e_star_observed_median_2_entries_per_day": observed_grid,
        "headline_central": {
            "deployment_fraction": f_central,
            "meaningful_fraction_threshold": t_central,
            "E_star_stress": round(e_star(f_central, t_central), 0),
            "E_star_observed": round(e_star(f_central / 2.0, t_central), 0),
            "interpretation": (
                "Central estimate: the market-depth wall likely starts binding somewhere "
                "between roughly $7.8K (conservative: one entry claims the whole day's "
                "deployment) and $15.6K (using the observed ~2 entries/day to split it) -- "
                "i.e. 1.5x-3x current equity, not $50K-$200K. Thin evidence (see above); "
                "treat as 'probably closer than it looks', not as a precise number."
            ),
        },
    }


def deployment_fraction_analysis(pool_meta, notional, nentries, equity_path, cutoff) -> dict:
    day_frac, entry_frac, entry_abs, entries_per_day = [], [], [], []
    for arm, d, _pct in pool_meta:
        eq = equity_path.get((arm, d))
        if not eq or eq <= 0:
            continue
        n_val = notional.get((arm, d), 0.0)
        ne = nentries.get((arm, d), 1) or 1
        day_frac.append(n_val / eq)
        entry_abs.append(n_val / ne)
        entry_frac.append((n_val / ne) / eq)
        entries_per_day.append(ne)
    if not day_frac:
        return {}
    return {
        "median_arm_day_notional": round(statistics.median(notional.get((a, d), 0.0) for a, d, _ in pool_meta), 2),
        "median_arm_day_deployment_fraction_pct": round(100 * statistics.median(day_frac), 2),
        "median_per_entry_notional": round(statistics.median(entry_abs), 2),
        "median_per_entry_deployment_fraction_pct": round(100 * statistics.median(entry_frac), 2),
        "median_entries_per_arm_day": statistics.median(entries_per_day),
        "j_cited_for_comparison": {"dollars_per_day": 891, "fraction_pct": 17},
    }


def min_contracts_floor_analysis(rows: list[dict], sizing: dict, f_central: float = 0.17) -> dict:
    """min_contracts is a FLOOR that OVER-leverages SMALL accounts (not a large-account
    wall). Below E_floor = min_contracts * typical_entry_premium * 100 / f, the floor
    forces more than the target deployment fraction per entry."""
    p_typical = statistics.median(r["entry_px"] for r in rows if r.get("entry_px"))
    safe_min = sizing["safe"]["min_contracts"]
    bold_min = sizing["bold"]["min_contracts"]
    e_floor_safe = safe_min * p_typical * 100.0 / f_central
    e_floor_bold = bold_min * p_typical * 100.0 / f_central
    return {
        "typical_entry_premium_all_trades_median": round(p_typical, 3),
        "safe_min_contracts": safe_min,
        "bold_min_contracts": bold_min,
        "equity_floor_safe": round(e_floor_safe, 0),
        "equity_floor_bold": round(e_floor_bold, 0),
        "interpretation": (
            f"At the {f_central:.0%} target deployment fraction, an account below roughly "
            f"${e_floor_safe:,.0f} (safe, min_contracts={safe_min}) / ${e_floor_bold:,.0f} "
            f"(bold, min_contracts={bold_min}) is FORCED to deploy MORE than the target "
            "fraction per entry -- the floor over-leverages a small account. Both live "
            "accounts (~$5.3-5.8K) sit comfortably above this today, but it binds for "
            "anyone starting smaller."
        ),
        "existing_mechanism_currently_off": (
            "params.json/aggressive/params.json ALREADY carry a min_contracts_equity_scaled "
            f"knob designed for exactly this (safe={sizing['safe']['min_contracts_equity_scaled']}, "
            f"bold={sizing['bold']['min_contracts_equity_scaled']}) -- it exists and is OFF, "
            "not missing."
        ),
    }


def config_rescale_table(sizing: dict, depth_thin: float, p_entry_thin: float,
                          p_typical: float, f_central: float = 0.17) -> list[dict]:
    """For each equity tier: what SHOULD max_position_dollars / max_contracts_per_entry be
    to preserve the target deployment fraction -- and where that collides with the
    (equity-independent) depth ceiling."""
    depth_cap_contracts = round(0.25 * depth_thin)  # central 25%-of-displayed-depth ceiling
    rows = []
    for equity in (10_000, 25_000, 50_000, 100_000):
        target_dollars = f_central * equity
        naive_contracts = target_dollars / (p_typical * 100.0)
        capped_contracts = min(naive_contracts, depth_cap_contracts)
        rows.append({
            "equity": equity,
            "target_per_entry_dollars_naive": round(target_dollars, 0),
            "naive_max_contracts_per_entry": round(naive_contracts, 1),
            "depth_capped_max_contracts_per_entry": min(round(naive_contracts, 1), depth_cap_contracts),
            "recommended_max_position_dollars": round(min(target_dollars, depth_cap_contracts * p_typical * 100), 0),
            "recommended_max_contracts_per_entry": min(round(naive_contracts), depth_cap_contracts),
            "depth_wall_binding": naive_contracts > depth_cap_contracts,
        })
    return rows


# ---------------------------------------------------------------------------
# BOOTSTRAP SIMULATION ENGINE (fixed seed -> reproducible)
# ---------------------------------------------------------------------------
def _step(equity: float, pct_return: float, e_star: float | None) -> float:
    eff_equity = equity if e_star is None else min(equity, e_star)
    return equity + (pct_return / 100.0) * eff_equity


def bootstrap_paths(
    pool: list[float], start_equity: float, e_star: float | None,
    n_sims: int, n_days: int, seed: int,
) -> dict:
    """Simulate n_sims equity paths of n_days trading days, resampling REAL historical
    arm-day % returns with replacement. Returns percentile equity at each horizon
    checkpoint plus drawdown/ruin statistics computed on the SAME simulated paths."""
    if not pool:
        return {"error": "empty pool"}
    rng = random.Random(seed)
    # only report checkpoints the requested horizon actually reaches -- calling with a
    # shorter n_days (e.g. a unit test, or a future partial-year run) must degrade
    # gracefully rather than index into an empty per-checkpoint list.
    checkpoints = sorted(v for v in HORIZONS_DAYS.values() if v <= n_days)
    horizon_by_day = {v: k for k, v in HORIZONS_DAYS.items() if v <= n_days}
    results_at_checkpoint: dict[int, list[float]] = {c: [] for c in checkpoints}
    max_dd_pct_list, max_dd_dollars_list = [], []
    hit_50pct_dd = 0
    below_start_12mo = 0
    longest_losing_streak_list = []
    hit_3000_dd = 0
    n_pool = len(pool)

    for _ in range(n_sims):
        equity = start_equity
        peak = start_equity
        max_dd_pct = 0.0
        max_dd_dollars = 0.0
        losing_streak = 0
        longest_losing_streak = 0
        for day in range(1, n_days + 1):
            r = pool[rng.randrange(n_pool)]
            equity = _step(equity, r, e_star)
            if equity > peak:
                peak = equity
            dd_dollars = peak - equity
            dd_pct = (dd_dollars / peak) if peak > 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
            if dd_dollars > max_dd_dollars:
                max_dd_dollars = dd_dollars
            if r < 0:
                losing_streak += 1
                longest_losing_streak = max(longest_losing_streak, losing_streak)
            else:
                losing_streak = 0
            if day in results_at_checkpoint:
                results_at_checkpoint[day].append(equity)
        max_dd_pct_list.append(max_dd_pct)
        max_dd_dollars_list.append(max_dd_dollars)
        longest_losing_streak_list.append(longest_losing_streak)
        if max_dd_pct >= 0.50:
            hit_50pct_dd += 1
        if max_dd_dollars >= J_PAIN_DRAWDOWN_DOLLARS:
            hit_3000_dd += 1
        if equity < start_equity:
            below_start_12mo += 1

    def pctl(vals: list[float], p: int) -> float:
        s = sorted(vals)
        k = (len(s) - 1) * (p / 100.0)
        f, c = int(k), min(int(k) + 1, len(s) - 1)
        if f == c:
            return s[f]
        return s[f] + (s[c] - s[f]) * (k - f)

    paths = {}
    for c in checkpoints:
        label = horizon_by_day[c]
        vals = results_at_checkpoint[c]
        paths[label] = {f"p{p}": round(pctl(vals, p), 2) for p in PERCENTILES}

    return {
        "start_equity": start_equity,
        "n_sims": n_sims,
        "equity_paths": paths,
        "drawdown": {
            "max_dd_pct_median": round(100 * pctl(max_dd_pct_list, 50), 2),
            "max_dd_pct_p90": round(100 * pctl(max_dd_pct_list, 90), 2),
            "max_dd_dollars_median": round(pctl(max_dd_dollars_list, 50), 2),
            "max_dd_dollars_p90": round(pctl(max_dd_dollars_list, 90), 2),
            "p_50pct_drawdown": round(hit_50pct_dd / n_sims, 4),
            f"p_{int(J_PAIN_DRAWDOWN_DOLLARS)}_dollar_drawdown": round(hit_3000_dd / n_sims, 4),
            "p_below_start_after_12mo": round(below_start_12mo / n_sims, 4),
            "longest_losing_streak_median_days": round(pctl(longest_losing_streak_list, 50), 1),
            "longest_losing_streak_p90_days": round(pctl(longest_losing_streak_list, 90), 1),
        },
    }


def simulate_milestones(
    pool: list[float], start_equity: float, e_star: float | None,
    targets: dict[str, float], n_sims: int, max_days: int, seed: int,
) -> dict:
    rng = random.Random(seed + 1)  # distinct stream from the path sim
    n_pool = len(pool)
    days_to: dict[str, list[float]] = {name: [] for name in targets}
    for _ in range(n_sims):
        equity = start_equity
        hit: dict[str, bool] = {name: False for name in targets}
        remaining = set(targets)
        for day in range(1, max_days + 1):
            r = pool[rng.randrange(n_pool)]
            equity = _step(equity, r, e_star)
            done_now = [name for name in remaining if equity >= targets[name]]
            for name in done_now:
                days_to[name].append(day)
                remaining.discard(name)
            if not remaining:
                break
        for name in remaining:
            days_to[name].append(None)  # never reached within max_days

    out = {}
    for name, vals in days_to.items():
        reached = [v for v in vals if v is not None]
        p_reached = len(reached) / len(vals)
        entry = {"p_reached_within_horizon": round(p_reached, 4), "horizon_days": max_days}
        if reached:
            s = sorted(reached)

            def pctl(p):
                k = (len(s) - 1) * (p / 100.0)
                f, c = int(k), min(int(k) + 1, len(s) - 1)
                return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)

            entry["days_p10"] = round(pctl(10), 1)
            entry["days_p50"] = round(pctl(50), 1)
            entry["days_p90"] = round(pctl(90), 1)
        out[name] = entry
    return out


def median_day_equity_for_2000(regime_stats: dict, e_star: float | None) -> dict:
    """Analytic (no simulation needed): equity at which the MEDIAN arm-day dollar P&L
    equals $2,000, both naive (uncapped) and depth-capped."""
    median_pct = regime_stats["median_pct"] / 100.0
    if median_pct <= 0:
        return {
            "reachable": False,
            "reason": "median arm-day is a LOSS in this regime -- no equity level makes "
            "$2,000/day the MEDIAN day; more capital cannot fix a negative median.",
        }
    naive_equity = 2000.0 / median_pct
    if e_star is None:
        return {"reachable": True, "naive_equity_for_median_2000": round(naive_equity, 0)}
    capped_dollar_at_wall = median_pct * e_star
    if capped_dollar_at_wall < 2000.0:
        return {
            "reachable": False,
            "naive_equity_for_median_2000": round(naive_equity, 0),
            "capped_median_dollar_ceiling": round(capped_dollar_at_wall, 2),
            "reason": (
                f"naive math says ${naive_equity:,.0f} equity, but the depth wall caps "
                f"deployable equity at ~${e_star:,.0f}, so the median day's dollar P&L "
                f"plateaus at ~${capped_dollar_at_wall:,.0f}/day -- BELOW $2,000 at ANY "
                "equity under this depth constraint. Scaling THIS account cannot reach "
                "$2,000/day as the median day; only more market depth (more names, "
                "slower/limit execution, or a bigger per-contract edge) can."
            ),
        }
    return {
        "reachable": True,
        "naive_equity_for_median_2000": round(naive_equity, 0),
        "capped_median_dollar_ceiling": round(capped_dollar_at_wall, 2),
    }


# ---------------------------------------------------------------------------
# WITHDRAWAL vs REINVEST
# ---------------------------------------------------------------------------
def withdrawal_comparison(
    pool: list[float], start_equity: float, e_star: float | None,
    withdraw_threshold: float, n_sims: int, n_days: int, seed: int,
) -> dict:
    rng_a = random.Random(seed + 2)
    rng_b = random.Random(seed + 2)  # SAME seed/stream -> same draws, only policy differs
    n_pool = len(pool)

    def run(withdraw: bool, rng: random.Random) -> list[float]:
        finals = []
        for _ in range(n_sims):
            equity = start_equity
            withdrawn = 0.0
            for day in range(1, n_days + 1):
                r = pool[rng.randrange(n_pool)]
                equity = _step(equity, r, e_star)
                if withdraw and day % 21 == 0 and equity > withdraw_threshold:
                    withdrawn += equity - withdraw_threshold
                    equity = withdraw_threshold
            finals.append(equity + withdrawn)
        return finals

    reinvest = run(False, rng_a)
    withdraw = run(True, rng_b)

    def med(vals):
        return round(statistics.median(vals), 2)

    below_wall = e_star is not None and withdraw_threshold < e_star
    return {
        "withdraw_threshold": withdraw_threshold,
        "threshold_vs_depth_wall": (
            f"BELOW the ~${e_star:,.0f} depth wall -- withdrawing here forgoes real compounding"
            if below_wall else
            f"AT/ABOVE the ~${e_star:,.0f} depth wall -- capital past the wall is already "
            "capped/idle inside the trading account, so withdrawing it costs ~nothing"
        ) if e_star is not None else "no depth cap applied",
        "policy_100pct_reinvest": {"median_combined_wealth_12mo": med(reinvest)},
        "policy_withdraw_above_threshold_monthly": {"median_combined_wealth_12mo": med(withdraw)},
        "cost_of_withdrawing": round(med(reinvest) - med(withdraw), 2),
        "note": (
            f"Same random draws for both policies (paired comparison). Withdraw policy caps "
            f"the TRADING account at ${withdraw_threshold:,.0f} monthly and sweeps the excess "
            "to cash (0% yield assumed); 'combined wealth' = trading equity + cash swept out. "
            "Reinvesting keeps compounding the swept cash INSIDE the trading account instead."
        ),
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    rows = load_trades()
    rates = load_cost_rates()
    depth_doc = load_depth()
    sizing = load_sizing_config()

    live_rows = [r for r in rows if r["arm"] in LIVE_ARMS]
    pnl, notional, nentries, by_key = aggregate_arm_days(live_rows, LIVE_ARMS)
    equity_path = reconstruct_equity(pnl, CURRENT_EQUITY)

    depth_buckets = {b["bucket"]: b for b in depth_doc["buckets"]}
    depth_thin = depth_buckets["$1.50-$2.50"]["bid_med"]
    winners_thin_bucket = [
        r for r in rows if r.get("exit_px_avg") and 1.50 <= r["exit_px_avg"] <= 2.50
        and (r.get("pnl_dollars") or 0) > 0
    ]
    p_entry_thin = statistics.median(r["entry_px"] for r in winners_thin_bucket)
    p_typical = statistics.median(r["entry_px"] for r in rows if r.get("entry_px"))

    capacity = capacity_bend_analysis(rows, depth_doc)
    e_star_central = capacity["headline_central"]["E_star_stress"]

    regimes_out: dict = {}
    bootstrap_out: dict = {}
    milestones_out: dict = {}

    for regime_name, cutoff in REGIME_CUTOFFS.items():
        # cost-adjusted pools at every slippage level (needed for BOTH stats + bootstrap)
        slippage_pools: dict[float, list[tuple[str, str, float]]] = {}
        for slip in SLIPPAGE_LEVELS:
            cost_pnl = build_cost_adjusted_arm_day_pnl(by_key, rates, slip)
            slippage_pools[slip] = build_regime_pool(cost_pnl, equity_path, cutoff)

        gross_pool = build_regime_pool(pnl, equity_path, cutoff)
        summary = regime_summary(gross_pool)
        eff_n = effective_n(gross_pool) if regime_name == "post_fix" else None
        deploy = deployment_fraction_analysis(gross_pool, notional, nentries, equity_path, cutoff)

        regimes_out[regime_name] = {
            "gross_stats": summary,
            "effective_n": eff_n,
            "deployment": deploy,
            "median_day_equity_for_2000_uncapped": median_day_equity_for_2000(summary, None),
            "median_day_equity_for_2000_depth_capped": median_day_equity_for_2000(summary, e_star_central),
        }
        if regime_name == "post_fix":
            regimes_out[regime_name]["j_stated"] = {
                "n_arm_days": 23, "mean_pct": 2.99, "median_pct": 3.21,
                "sd_pct": 5.14, "pct_green": 61,
            }
        elif regime_name == "august":
            regimes_out[regime_name]["j_stated"] = {"n_arm_days": 60, "mean_pct": 1.12, "pct_green": 53}
        else:
            regimes_out[regime_name]["j_stated"] = {
                "n_arm_days": 100, "mean_pct": 0.34, "median_pct": "NEGATIVE", "pct_green": 38,
            }

        regime_bootstrap: dict = {}
        regime_milestones: dict = {}
        targets = {"10k": 10_000.0, "25k": 25_000.0, "100k": 100_000.0}
        for slip in SLIPPAGE_LEVELS:
            pool_all = [p[2] for p in slippage_pools[slip]]
            pool_drop = [p[2] for p in drop_best_day(slippage_pools[slip])]
            slip_key = f"slippage_{slip:.2f}"
            regime_bootstrap[slip_key] = {"all_days": {}, "drop_best_day": {}}
            regime_milestones[slip_key] = {"all_days": {}, "drop_best_day": {}}
            for variant_name, pool_vals in (("all_days", pool_all), ("drop_best_day", pool_drop)):
                for start in STARTS:
                    seed_here = deterministic_seed(SEED, regime_name, slip, variant_name, start)
                    start_key = f"start_{int(start)}"
                    regime_bootstrap[slip_key][variant_name][start_key] = bootstrap_paths(
                        pool_vals, start, e_star_central, N_SIMS_PATHS, HORIZONS_DAYS["12mo"], seed_here,
                    )
                    if slip == 1.00:  # milestones only at the central slippage assumption
                        regime_milestones[slip_key][variant_name][start_key] = simulate_milestones(
                            pool_vals, start, e_star_central, targets,
                            N_SIMS_MILESTONES, MAX_MILESTONE_DAYS, seed_here,
                        )
        bootstrap_out[regime_name] = regime_bootstrap
        milestones_out[regime_name] = {k: v for k, v in regime_milestones.items() if v["all_days"]}

    # naive (uncapped) comparison -- reduced subset: central slippage, all-days, both starts, 3 regimes
    naive_comparison: dict = {}
    for regime_name, cutoff in REGIME_CUTOFFS.items():
        cost_pnl = build_cost_adjusted_arm_day_pnl(by_key, rates, 1.00)
        pool_vals = [p[2] for p in build_regime_pool(cost_pnl, equity_path, cutoff)]
        naive_comparison[regime_name] = {}
        for start in STARTS:
            seed_here = deterministic_seed(SEED, regime_name, "naive", start)
            start_key = f"start_{int(start)}"
            capped = bootstrap_paths(pool_vals, start, e_star_central, N_SIMS_PATHS, HORIZONS_DAYS["12mo"], seed_here)
            naive = bootstrap_paths(pool_vals, start, None, N_SIMS_PATHS, HORIZONS_DAYS["12mo"], seed_here)
            naive_comparison[regime_name][start_key] = {
                "depth_capped_12mo_p50": capped["equity_paths"]["12mo"]["p50"],
                "naive_uncapped_12mo_p50": naive["equity_paths"]["12mo"]["p50"],
                "capacity_bend_cost_12mo_p50": round(
                    naive["equity_paths"]["12mo"]["p50"] - capped["equity_paths"]["12mo"]["p50"], 2
                ),
            }

    # withdrawal comparison -- illustrative, post-fix regime, central slippage, $5,000 start
    post_fix_central_pool = [
        p[2] for p in build_regime_pool(
            build_cost_adjusted_arm_day_pnl(by_key, rates, 1.00), equity_path, REGIME_CUTOFFS["post_fix"]
        )
    ]
    # two thresholds: one BELOW the depth wall (withdrawing here has a real cost -- it
    # forgoes compounding that was still working) and one AT/ABOVE it (withdrawing here
    # should cost ~nothing, since that capital is already idle/capped inside the account).
    below_wall_threshold = round(e_star_central * 0.85, -2)
    withdrawal_below_wall = withdrawal_comparison(
        post_fix_central_pool, 5000.0, e_star_central, below_wall_threshold,
        N_SIMS_PATHS, HORIZONS_DAYS["12mo"], SEED + 3,
    )
    withdrawal_above_wall = withdrawal_comparison(
        post_fix_central_pool, 5000.0, e_star_central, 10_000.0,
        N_SIMS_PATHS, HORIZONS_DAYS["12mo"], SEED + 3,
    )

    min_floor = min_contracts_floor_analysis(rows, sizing)
    rescale_table = config_rescale_table(sizing, depth_thin, p_entry_thin, p_typical)

    ranked_constraints = [
        {
            "rank": 1,
            "type": "market_depth",
            "constraint": "Displayed exit-side liquidity at the $1.50-2.50 premium band "
                          f"(median {depth_thin} contracts) where right-tail winners actually exit.",
            "binds_at": f"~${capacity['headline_central']['E_star_stress']:,.0f}-"
                        f"${capacity['headline_central']['E_star_observed']:,.0f} equity "
                        "(1.5x-3x current), central assumption -- NOT a config number.",
            "fix": "Not fixable by more capital. Needs more market depth: trade across more "
                   "names (the multi-symbol lane already ships this), execute with limit "
                   "patience instead of market orders at size, or find a bigger "
                   "per-contract edge so fewer contracts are needed for the same dollars.",
        },
        {
            "rank": 2,
            "type": "evidence_quality",
            "constraint": "The depth measurement itself: 1 session, 3 snapshots, 33 quotes, "
                          "an 'indicative' (not confirmed OPRA) feed.",
            "binds_at": "Confidence in constraint #1's exact dollar value, not the path itself.",
            "fix": "Run the multi-session depth study named in capacity_bend.evidence_quality "
                   "before treating any specific E* number as more than an order of magnitude.",
        },
        {
            "rank": 3,
            "type": "config_rescale",
            "constraint": "max_contracts_per_entry=5 / max_position_dollars=$1,000 "
                          "(shipped 2026-08-29 for a ~$5K account) and position_sizing_tiers' "
                          "flat top bracket above $10K.",
            "binds_at": "Immediately above current equity if left un-rescaled -- but this is "
                        "a KNOB, not a wall.",
            "fix": "Rescale with equity per config_rescale_table -- but only up to the depth "
                   "ceiling (~12 contracts at the central 25%-of-depth assumption); do not "
                   "extrapolate max_contracts_per_entry past that even though the dollar cap "
                   "formula would suggest it.",
        },
        {
            "rank": 4,
            "type": "config_rescale",
            "constraint": "min_contracts (3 safe / 5 bold) as a FLOOR -- over-leverages "
                          "SMALL accounts, not large ones.",
            "binds_at": f"Below ~${min_floor['equity_floor_safe']:,.0f} (safe) / "
                        f"~${min_floor['equity_floor_bold']:,.0f} (bold); both live accounts "
                        "are already above this.",
            "fix": "min_contracts_equity_scaled already exists in both params files and is "
                   "OFF -- turning it on is the built-in fix, not a new build.",
        },
        {
            "rank": 5,
            "type": "evidence_quality",
            "constraint": "The all-history regime's MEDIAN arm-day is a loss (this script: "
                          f"{regimes_out['all_history']['gross_stats'].get('median_pct')}%); "
                          "post-fix is n=23 arm-days / ~8-10 effective independent sessions.",
            "binds_at": "Confidence in ANY forward projection, at any equity.",
            "fix": "No fix -- disclose it. Every post-fix-anchored number in this report is an "
                   "extrapolation from a single-digit number of independent sessions, and the "
                   "long-run all-history shape says the median day is a loss. Time, not "
                   "capital, is what would fix this.",
        },
    ]

    out = {
        "_doc": __doc__,
        "generated_at_et": dt.datetime.now().isoformat(),
        "seed": SEED,
        "n_sims_paths": N_SIMS_PATHS,
        "n_sims_milestones": N_SIMS_MILESTONES,
        "live_arms": list(LIVE_ARMS),
        "current_equity": CURRENT_EQUITY,
        "risky3_exclusion": (
            "risky-3 (PA3V7JT25H6Z) retired 2026-08-28 per automation/state/fleet/"
            "accounts.json retired_reason -- lifetime -$590 while the other four cells are "
            "positive; account repurposed for the weekly-1 non-SPY lane. Excluded from ALL "
            "THREE regimes here (not just post-fix) because it will not be part of forward "
            "compounding. This reproduces J's exact n=23/8-session/61%-green post-fix figures."
        ),
        "verified_sizing_config": sizing,
        "market_depth_measurement": {**capacity},
        "deployment_fraction": regimes_out["post_fix"]["deployment"],
        "min_contracts_floor": min_floor,
        "config_rescale_table": rescale_table,
        "regimes": regimes_out,
        "bootstrap": bootstrap_out,
        "milestones": milestones_out,
        "naive_vs_capacity_comparison": naive_comparison,
        "withdrawal_vs_reinvest": {
            "below_wall": withdrawal_below_wall,
            "at_or_above_wall": withdrawal_above_wall,
        },
        "ranked_constraints": ranked_constraints,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, sort_keys=False), encoding="utf-8")
    OUT_MD.write_text(render_markdown(out), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")


def render_markdown(out: dict) -> str:
    L = []
    a = L.append
    a("# Compound Matrix -- what compounding path is actually available")
    a("")
    a(f"_Generated {out['generated_at_et']} | seed={out['seed']} | "
      f"{out['n_sims_paths']} sims/path, {out['n_sims_milestones']} sims/milestone_")
    a("")
    a("> $2,000/day is an OUTPUT of compounding, not a target. This is the tool that answers "
      "what path gets there and what binds it. **Analysis-path only** -- no trading-engine "
      "file was touched, nothing armed.")
    a("")
    a("## Verdict")
    a("")
    cap = out["market_depth_measurement"]["headline_central"]
    a(f"- **The real wall is market depth, not account size.** Central estimate: returns hold "
      f"their measured shape up to roughly **${cap['E_star_stress']:,.0f}-${cap['E_star_observed']:,.0f}** "
      "equity (1.5x-3x today's ~$5.3-5.8K), then bend from exponential toward linear because "
      "the exit-side book (median 46 displayed contracts at the $1.50-2.50 premium where "
      "winners actually exit) can't absorb more size at a good price.")
    a("- **That number is uncertain** -- the depth measurement is 1 session / 3 snapshots / "
      "33 quotes on an indicative (not confirmed OPRA) feed. Treat it as an order of magnitude.")
    a("- **The $1,000/5-contract config caps shipped yesterday are NOT the wall** -- they're "
      "sized for today's ~$5K and should rescale with equity (table below), capped at the "
      "depth ceiling once that binds.")
    a("- **Post-fix (n=23 arm-days, ~8 sessions) is genuinely strong** (median "
      f"{out['regimes']['post_fix']['gross_stats'].get('median_pct')}%/day) but is only "
      f"~{out['regimes']['post_fix']['effective_n']['n_eff_central']} independent sessions "
      "once cross-arm correlation is priced in -- an extrapolation, not a forecast.")
    a("- **All-history's median arm-day is a LOSS** "
      f"({out['regimes']['all_history']['gross_stats'].get('median_pct')}%). Any 12-month "
      "number below assuming the recent hot streak persists says so in the same sentence.")
    dd_aug = out["bootstrap"]["august"]["slippage_1.00"]["all_days"]["start_5000"]["drawdown"]
    dd_all = out["bootstrap"]["all_history"]["slippage_1.00"]["all_days"]["start_5000"]["drawdown"]
    a(f"- **J's stated $3,000 pain threshold is likely to be hit outside the current hot "
      f"streak**: P($3,000 drawdown within 12mo) is {dd_aug['p_3000_dollar_drawdown']:.0%} "
      f"under the August regime and {dd_all['p_3000_dollar_drawdown']:.0%} under all-history "
      f"(vs {out['bootstrap']['post_fix']['slippage_1.00']['all_days']['start_5000']['drawdown']['p_3000_dollar_drawdown']:.0%} "
      "under post-fix specifically). Full table below.")
    a("")

    a("## Regimes re-derived from analysis/trades-enriched.jsonl (this script's own numbers)")
    a("")
    a("| Regime | n arm-days | sessions | mean%/day | median%/day | sd% | %green | J stated |")
    a("|---|---|---|---|---|---|---|---|")
    for name, label in (("post_fix", "Post-fix (>=08-19)"), ("august", "August (>=08-01)"), ("all_history", "All-history")):
        s = out["regimes"][name]["gross_stats"]
        j = out["regimes"][name]["j_stated"]
        a(f"| {label} | {s['n_arm_days']} | {s['n_sessions']} | {s['mean_pct']} | "
          f"{s['median_pct']} | {s['sd_pct']} | {s['pct_green']}% | "
          f"mean {j.get('mean_pct')}, median {j.get('median_pct','?')}, "
          f"{j.get('pct_green')}% green |")
    a("")
    a("4-arm roster used throughout (safe-2, bold-2, safe-3, risky-1): risky-3 retired "
      "2026-08-28, see `risky3_exclusion` in the JSON. Reproduces J's n/sessions/green% "
      "exactly; mean/median/sd differ by ~0.3-1.1pp, most likely an equity-denominator "
      "convention difference -- disclosed, not resolved.")
    a("")

    eff = out["regimes"]["post_fix"]["effective_n"]
    a("## Effective-n on the post-fix regime (the anti-self-deception check)")
    a("")
    a(f"- Raw: {eff['n_raw']} arm-days across {eff['n_sessions']} sessions, cluster sizes {eff['cluster_sizes']}")
    a(f"- Measured pairwise correlation across arms: {eff['measured_pairwise_r']}")
    a(f"- Effective n (Kish design effect, rho swept 0.62-0.72): **{eff['n_eff_central']}**")
    a(f"- {eff['interpretation']}")
    a("")

    a("## The capacity bend (market depth, not config)")
    a("")
    md = out["market_depth_measurement"]
    a(f"- Displayed bid depth: median **{md['depth_deep_bucket_0_00_0_20_contracts']}** "
      f"contracts at $0.00-0.20 premium (where losers exit -- deep, no wall) vs median "
      f"**{md['depth_thin_bucket_1_50_2_50_contracts']}** at $1.50-2.50 (where winners exit -- thin).")
    a(f"- Winner cohort landing in that thin bucket: n={md['winner_cohort_thin_bucket_n']}, "
      f"median entry ${md['winner_cohort_median_entry_premium']}, median exit "
      f"${md['winner_cohort_median_exit_premium']} ({md['note_on_exit_premium_match']})")
    a(f"- Evidence quality: {md['evidence_quality']['verdict']}")
    a(f"- Recommended follow-up study: {md['evidence_quality']['recommended_study']}")
    a("")
    a("**E\\* sensitivity grid** (equity where contracts-per-entry first hits the threshold "
      "fraction of displayed depth), stress case = one entry claims the whole day's deployment:")
    a("")
    a("| deployment f | thresh 10% | thresh 25% | thresh 50% |")
    a("|---|---|---|---|")
    for f, row in md["e_star_stress_single_entry_claims_full_daily_fraction"].items():
        a(f"| {float(f):.0%} | ${row['0.1']:,.0f} | ${row['0.25']:,.0f} | ${row['0.5']:,.0f} |")
    a("")
    a(f"Central (f=17%, thresh=25%): **${cap['E_star_stress']:,.0f}** (stress) to "
      f"**${cap['E_star_observed']:,.0f}** (observed ~2 entries/day). {cap['interpretation']}")
    a("")

    a("## Config caps that RESCALE with equity (not walls)")
    a("")
    a("| Equity | naive $/entry (17%) | naive max contracts | depth-capped max contracts | recommended max_position_dollars |")
    a("|---|---|---|---|---|")
    for r in out["config_rescale_table"]:
        a(f"| ${r['equity']:,.0f} | ${r['target_per_entry_dollars_naive']:,.0f} | "
          f"{r['naive_max_contracts_per_entry']} | {r['depth_capped_max_contracts_per_entry']} | "
          f"${r['recommended_max_position_dollars']:,.0f} |")
    a("")
    mf = out["min_contracts_floor"]
    a(f"- **min_contracts is a small-account floor, not a large-account wall.** {mf['interpretation']}")
    a(f"- {mf['existing_mechanism_currently_off']}")
    a("")

    a("## Milestone table (central slippage $1.00/contract, depth-capped, 4-arm roster)")
    a("")
    a("| Regime | Start | days to $10K (p10/p50/p90) | days to $25K | days to $100K |")
    a("|---|---|---|---|---|")
    for regime_name in ("post_fix", "august", "all_history"):
        m = out["milestones"].get(regime_name, {}).get("slippage_1.00", {}).get("all_days", {})
        for start_key, entry in m.items():
            def fmt(t):
                d = entry.get(t, {})
                if not d or not d.get("p_reached_within_horizon"):
                    return "not reached"
                if "days_p50" not in d:
                    return f"not reached ({d['p_reached_within_horizon']:.0%} of paths)"
                return f"{d['days_p10']:.0f}/{d['days_p50']:.0f}/{d['days_p90']:.0f} ({d['p_reached_within_horizon']:.0%})"
            a(f"| {regime_name} | {start_key.replace('start_','$')} | {fmt('10k')} | {fmt('25k')} | {fmt('100k')} |")
    a("")
    a("`(p_reached_within_horizon)` = fraction of the 10-year simulated paths that ever reach "
      "the target under the depth cap; a low fraction means most paths plateau below it.")
    a("")

    a("## The $2,000/day MEDIAN-day question")
    a("")
    for name in ("post_fix", "august", "all_history"):
        d = out["regimes"][name]["median_day_equity_for_2000_depth_capped"]
        a(f"- **{name}**: {d.get('reason') or ('reachable at ~$' + format(d.get('naive_equity_for_median_2000',0), ',.0f'))}")
    a("")

    a("## Naive (uncapped) vs depth-capped 12-month projection, $1.00 slippage")
    a("")
    a("_The 'naive' column is deliberately unconstrained (contracts scale with equity "
      "forever, no market-depth limit) -- the huge numbers are the point: this is what the "
      "brief's original wrong assumption ('returns hold at any size') implies, and it is "
      "obviously absurd. The depth-capped column is the realistic one._")
    a("")
    a("| Regime | Start | Naive p50 @12mo | Depth-capped p50 @12mo | Cost of the depth wall |")
    a("|---|---|---|---|---|")
    for regime_name, starts in out["naive_vs_capacity_comparison"].items():
        for start_key, d in starts.items():
            a(f"| {regime_name} | {start_key.replace('start_','$')} | "
              f"${d['naive_uncapped_12mo_p50']:,.0f} | ${d['depth_capped_12mo_p50']:,.0f} | "
              f"${d['capacity_bend_cost_12mo_p50']:,.0f} |")
    a("")
    a("All-history shows a NEGATIVE 'cost' (capped ends up higher than naive): expected, "
      "not a bug -- all-history's median day is a loss, so uncapped (proportional) "
      "compounding drags equity DOWN over time (volatility drag on a negative-median "
      "geometric walk), while the depth cap also limits DOWNSIDE dollar risk once equity "
      "has been above the wall, softening the decay.")
    a("")

    a("## Withdrawal vs reinvest (illustrative: post-fix regime, $5,000 start)")
    a("")
    wb = out["withdrawal_vs_reinvest"]["below_wall"]
    wa = out["withdrawal_vs_reinvest"]["at_or_above_wall"]
    a(f"**Threshold ${wb['withdraw_threshold']:,.0f} ({wb['threshold_vs_depth_wall']}):**")
    a(f"- 100% reinvest, median combined wealth @12mo: **${wb['policy_100pct_reinvest']['median_combined_wealth_12mo']:,.0f}**")
    a(f"- Withdraw above threshold monthly: **${wb['policy_withdraw_above_threshold_monthly']['median_combined_wealth_12mo']:,.0f}**")
    a(f"- Cost of withdrawing: **${wb['cost_of_withdrawing']:,.0f}**")
    a("")
    a(f"**Threshold ${wa['withdraw_threshold']:,.0f} ({wa['threshold_vs_depth_wall']}):**")
    a(f"- 100% reinvest, median combined wealth @12mo: **${wa['policy_100pct_reinvest']['median_combined_wealth_12mo']:,.0f}**")
    a(f"- Withdraw above threshold monthly: **${wa['policy_withdraw_above_threshold_monthly']['median_combined_wealth_12mo']:,.0f}**")
    a(f"- Cost of withdrawing: **${wa['cost_of_withdrawing']:,.0f}**")
    a("")
    a(f"{wb['note']} The below-wall case has a REAL cost because that capital was still "
      "compounding productively; the at/above-wall case costs ~nothing because the depth "
      "cap already made that capital idle inside the trading account too -- withdrawing it "
      "loses nothing.")
    a("")

    a("## Drawdown / ruin (central slippage $1.00/contract, depth-capped)")
    a("")
    a("| Regime | Start | Median max DD% | p90 max DD% | P(50% DD) | P($3,000 DD) | P(below start @12mo) | Longest losing streak (median/p90 days) |")
    a("|---|---|---|---|---|---|---|---|")
    for regime_name in ("post_fix", "august", "all_history"):
        for start in (5000, 10000):
            dd = out["bootstrap"][regime_name]["slippage_1.00"]["all_days"][f"start_{start}"]["drawdown"]
            a(f"| {regime_name} | ${start:,} | {dd['max_dd_pct_median']}% | {dd['max_dd_pct_p90']}% | "
              f"{dd['p_50pct_drawdown']:.1%} | {dd['p_3000_dollar_drawdown']:.1%} | "
              f"{dd['p_below_start_after_12mo']:.1%} | {dd['longest_losing_streak_median_days']:.0f}/"
              f"{dd['longest_losing_streak_p90_days']:.0f} |")
    a("")

    a("## Ranked: what actually binds the compounding path")
    a("")
    for c in out["ranked_constraints"]:
        a(f"**{c['rank']}. [{c['type']}] {c['constraint']}**")
        a(f"   - Binds at: {c['binds_at']}")
        a(f"   - Fix: {c['fix']}")
        a("")

    a("## Full data")
    a("")
    a("Every regime x slippage-level (0.00/0.50/1.00/2.00 per contract) x all-days/drop-best-day "
      "x $5,000/$10,000 start percentile path and drawdown stat lives in `analysis/compound/matrix.json` "
      "-- this file shows the central slippage assumption ($1.00/contract) for readability.")
    a("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
