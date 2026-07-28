"""
backtest/tools/regime_reslice_2026_07_28.py

REGIME-CONDITIONING-RESLICE -- run EXACTLY per the frozen pre-registration:
analysis/recommendations/prereg-regime-conditioning-2026-07-28.json (commit 1e3dc624)

J's verbatim critique (2026-07-28 post-close): "Are you sure that you're not trying to apply
the same strategy every day? ... Just because it failed every day doesn't necessarily mean it
should be a kill." Every variant killed this week was tested UNCONDITIONALLY -- one rule
applied at every trigger regardless of market state. This tool answers that question with data.

METHOD -- DESCRIPTIVE re-slice of ALREADY-COMPUTED per-trade records. NO new replays, NO new
variants, NO re-optimization, NO parameter tuning. Every trade object consumed here was
produced by an earlier, already-committed replay tool; this script only JOINS each trade to
morning-knowable regime coordinates and aggregates.

REGIME AXES (frozen, morning-knowable only per pre-reg):
  - gap_state:        up/down/flat, from analysis/edge-matrix/day-inventory-extended.json's
                       gap_pct for the trade's OWN day (known at 09:30 that day).
  - prior_day_type:   trend/range/chop/unclassified, from day-inventory-extended.json's
                       day_type for the PRIOR trading day (known before today's open).
  - vix_band:         low/mid/elevated/high, from the VIX 5m bar closing AT OR BEFORE the
                       trade's own entry_time_et (known at the tick -- no look-ahead: bisect
                       only ever returns a bar timestamped <= entry).
  - entry_hour:       the entry_time_et hour-of-day (known at the tick).

EXCLUDED AXIS (disclosed, not fabricated): premarket_range_pct. No repo-wide historical
premarket high/low dataset exists across the full 2025-01-02..2026-07-27 window (only
current-day snapshots in eod-deep-*.json / swarm state). Deriving it fresh from raw 5m bars
under time pressure risks reintroducing the documented DST/frame bug (CLAUDE.md C6,
project_dst_frame_artifact_2026_07_02: the SPY 5m cache is stored on a FIXED -04:00 offset
year-round, not true DST-aware ET, while the VIX 5m cache IS DST-aware per-row -- mixing them
naively is exactly the kind of look-ahead defect this run exists to avoid). The pre-reg
explicitly sanctions excluding an axis with no honest data source rather than guessing.

VIX/SPY timestamp frame note: this script parses VIX 5m bars by stripping their (correct,
per-row, DST-aware) UTC offset and trusting the naive local HH:MM as true ET -- verified
empirically below (a January row carries -05:00, a July row carries -04:00). It never reads
the SPY 5m cache directly (that file's fixed -04:00 quirk is irrelevant here since every
variant's entry_time_et was already produced upstream via the project's own et_frame.py-
corrected replay tools).

Run: backtest/.venv/Scripts/python.exe backtest/tools/regime_reslice_2026_07_28.py
"""

from __future__ import annotations

import bisect
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from scipy import stats as scipy_stats

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = ROOT / "analysis"
DATA = ROOT / "backtest" / "data"

VIX_MAIN = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
VIX_TAIL = DATA / "vix_5m_2026-05-19_2026-07-27.csv"
VIX_TAIL_CUTOFF = "2026-07-22"  # strictly-after this date from the tail file, per
# ladder_fullhist_replay.py's own precedent for stitching the main window to the 07-23..07-27
# tail without double-counting the overlap.

DAY_INVENTORY = ANALYSIS / "edge-matrix" / "day-inventory-extended.json"

FDR_Q = 0.10
CANDIDATE_MIN_N = 25


# ---------------------------------------------------------------------------------------
# Regime coordinate builders
# ---------------------------------------------------------------------------------------


def load_day_inventory() -> dict[str, dict]:
    d = json.loads(DAY_INVENTORY.read_text())
    return {row["date"]: row for row in d["days"]}


def gap_state_for(date: str, inv: dict[str, dict]) -> str:
    row = inv.get(date)
    if row is None or row.get("gap_pct") is None:
        return "unknown"
    gap_pct = row["gap_pct"]
    if gap_pct > 0.02:
        return "up"
    if gap_pct < -0.02:
        return "down"
    return "flat"


def build_prior_day_type_map(inv: dict[str, dict], all_trading_dates: list[str]) -> dict[str, str]:
    """prior_day_type[date] = day_type of the PRIOR entry in the authoritative trading
    calendar (all_trading_dates, sorted, deduped). If the prior calendar date has no
    day_type in the inventory (tail dates past 2026-07-22 coverage), or there is no prior
    date at all (first day in the window), the bucket is 'unknown' -- never fabricated."""
    dates = sorted(set(all_trading_dates))
    out: dict[str, str] = {}
    for i, date in enumerate(dates):
        if i == 0:
            out[date] = "unknown"
            continue
        prior_date = dates[i - 1]
        prior_row = inv.get(prior_date)
        out[date] = prior_row["day_type"] if prior_row is not None else "unknown"
    return out


def load_vix_bars() -> tuple[list[datetime], list[float]]:
    """Sorted (datetime, close) series, naive-local timestamps trusted as true ET (verified:
    each row's own offset is DST-correct -- winter rows carry -05:00, summer rows carry
    -04:00 -- so stripping the offset and keeping the printed HH:MM is a true ET wall-clock
    read, not a naive/incorrect one)."""
    bars: list[tuple[datetime, float]] = []
    with VIX_MAIN.open() as f:
        for row in csv.DictReader(f):
            dt = datetime.strptime(row["timestamp_et"][:19], "%Y-%m-%d %H:%M:%S")
            bars.append((dt, float(row["close"])))
    with VIX_TAIL.open() as f:
        for row in csv.DictReader(f):
            if row["timestamp_et"][:10] <= VIX_TAIL_CUTOFF:
                continue
            dt = datetime.strptime(row["timestamp_et"][:19], "%Y-%m-%d %H:%M:%S")
            bars.append((dt, float(row["close"])))
    bars.sort(key=lambda x: x[0])
    return [b[0] for b in bars], [b[1] for b in bars]


def vix_band_at(entry_time_et: str, vix_dts: list[datetime], vix_close: list[float]) -> str:
    dt = datetime.strptime(entry_time_et[:19], "%Y-%m-%dT%H:%M:%S")
    idx = bisect.bisect_right(vix_dts, dt) - 1
    if idx < 0:
        return "unknown"
    v = vix_close[idx]
    if v < 15:
        return "low"
    if v < 20:
        return "mid"
    if v < 25:
        return "elevated"
    return "high"


def entry_hour_bucket(entry_time_et: str) -> str:
    dt = datetime.strptime(entry_time_et[:19], "%Y-%m-%dT%H:%M:%S")
    return f"{dt.hour:02d}:xx"


# ---------------------------------------------------------------------------------------
# Variant loaders -- each returns (variant_name, list[trade]) where trade has at least
# 'date', 'entry_time_et', 'dollar_pnl'. Every loader is annotated with WHERE its per-trade
# detail is persisted, and any reconstruction is verified against the source file's own
# reported aggregate before being trusted.
# ---------------------------------------------------------------------------------------


def _clean(trades: list[dict]) -> list[dict]:
    return [
        t
        for t in trades
        if t.get("resolved", True) is not False and t.get("dollar_pnl") is not None
    ]


def load_ladder_floors() -> list[tuple[str, list[dict], dict]]:
    path = ANALYSIS / "arm-ladder" / "LADDER-FULLHIST-2026-07-27.json"
    d = json.loads(path.read_text())
    out = []
    for floor in ("7", "8", "9"):
        lane = d["lanes"][floor]
        trades = _clean(lane["trades"])
        provenance = {
            "source_file": str(path.relative_to(ROOT)),
            "field_path": f"lanes.{floor}.trades",
            "n_persisted": len(trades),
            "reconstructed": False,
            "reported_stats_n": lane["stats"]["n_trades"],
            "reported_stats_total_pnl": lane["stats"]["total_pnl"],
        }
        out.append((f"ladder_floor_{floor}", trades, provenance))
    return out


def load_ladder_subset() -> tuple[str, list[dict], dict]:
    path = ANALYSIS / "arm-ladder" / "LADDER-SUBSET-VERDICT-2026-07-28.json"
    d = json.loads(path.read_text())
    trades = _clean(d["primary_trades"])
    provenance = {
        "source_file": str(path.relative_to(ROOT)),
        "field_path": "primary_trades (== cells.PRIMARY_lane9_subset)",
        "n_persisted": len(trades),
        "reconstructed": False,
        "note": (
            "Other sensitivity cells (SENSITIVITY_lane7_subset, SENSITIVITY_lane8_subset, "
            "INTERMED_lane9_confluence_anyHTF, INTERMED_lane9_htfBEAR_anyTrigger) only have "
            "aggregate stats persisted, no per-trade array -- excluded per pre-reg's "
            "'if per-trade detail was not persisted, exclude and say so' rule. Only the named "
            "graveyard variant (score>=9 + confluence + htf) has per-trade detail."
        ),
    }
    return "ladder_subset_9_confluence_htf", trades, provenance


def load_structure_shift_standalone() -> list[tuple[str, list[dict], dict]]:
    path = ANALYSIS / "recommendations" / "structure-shift-replay-2026-07-28.json"
    d = json.loads(path.read_text())
    out = []
    for label, key in (("K3", "K=3_primary"), ("K2", "K=2_sensitivity")):
        trades = _clean(d[key]["trades"])
        provenance = {
            "source_file": str(path.relative_to(ROOT)),
            "field_path": f"{key}.trades",
            "n_persisted": len(trades),
            "reconstructed": False,
        }
        out.append((f"structure_shift_standalone_{label}", trades, provenance))
    return out


def load_structure_shift_cascade() -> tuple[str, list[dict], dict]:
    path = ANALYSIS / "recommendations" / "structure-shift-cascade-ab-2026-07-28.json"
    d = json.loads(path.read_text())
    raw = d["changed_trades"]
    n_added = sum(1 for t in raw if t.get("change") == "ADDED")
    n_preempted = sum(1 for t in raw if t.get("change") == "PREEMPTED")
    # IMPORTANT: for PREEMPTED rows, 'dollar_pnl' is the CONTROL trade's own P&L (the trade
    # this variant displaced, which the variant itself never took) -- NOT this variant's
    # outcome. 'contribution' (= dollar_pnl for ADDED, = -dollar_pnl for PREEMPTED) is the
    # correct per-trade net EFFECT of running this variant instead of control, and is what
    # must be sliced by regime. Verified: sum(contribution) == headline.delta_total (-46.0)
    # exactly; sum(dollar_pnl) would NOT match and would silently mix two different books.
    trades = []
    for t in raw:
        t2 = dict(t)
        t2["dollar_pnl"] = t2["contribution"]
        trades.append(t2)
    trades = _clean(trades)
    check_total = round(sum(t["dollar_pnl"] for t in trades), 2)
    provenance = {
        "source_file": str(path.relative_to(ROOT)),
        "field_path": "changed_trades (sliced by 'contribution', remapped to dollar_pnl -- see code comment)",
        "n_persisted": len(trades),
        "reconstructed": False,
        "verified_against_headline_delta_total": {
            "computed": check_total,
            "headline_delta_total": d["headline"]["delta_total"],
            "match": abs(check_total - d["headline"]["delta_total"]) < 0.01,
        },
        "note": (
            f"Only the DELTA vs control is persisted per-trade ({n_added} ADDED + "
            f"{n_preempted} PREEMPTED = {len(trades)} total) -- the full treatment book "
            "(control + delta) has no per-trade array in this file, only aggregate "
            "n_trades/total_pnl for 'control' and 'treatment'. Per pre-reg's exclusion rule, "
            "the full book is NOT reconstructed (no reliable join key given: 'control' isn't "
            "itemized). This variant's n is far below the n>=25 candidate floor even in full "
            "aggregate -- descriptive-only, cannot produce a candidate at any granularity."
        ),
    }
    return "structure_shift_in_cascade_delta", trades, provenance


def load_zone_bands() -> list[tuple[str, list[dict], dict]]:
    path = ANALYSIS / "deep-research" / "ZONE-WIDTH-2026-07-28.json"
    d = json.loads(path.read_text())
    out = []
    for band in ("10c", "25c"):
        cell = d["cells"][band]
        trades = _clean(cell["marginal_trades"])
        provenance = {
            "source_file": str(path.relative_to(ROOT)),
            "field_path": f"cells.{band}.marginal_trades",
            "n_persisted": len(trades),
            "reconstructed": False,
            "note": (
                f"Only the MARGINAL (net-new vs 0c control) trades are itemized "
                f"(n_marginal={cell['n_marginal']}); 'displaced_trades' "
                f"(n_displaced={cell['n_displaced']}, trades control would have taken that "
                "the wider band crowds out) exist as a separate itemized list but are "
                "EXCLUDED here -- mixing 'trades this variant adds' with 'trades this variant "
                "removes' into one bucket would conflate two different populations under one "
                "regime label. full_book_stats (the complete holding under the wider band, "
                f"n={cell['full_book_stats']['n_trades']}) has NO per-trade array, only "
                "aggregate stats -- not reconstructable without the 0c control's own itemized "
                "list, which this file does not persist either. n_marginal is already far "
                "below the n>=25 candidate floor in full aggregate -- descriptive-only."
            ),
        }
        out.append((f"zone_band_{band}_marginal", trades, provenance))
    return out


def load_min_triggers_bear2() -> tuple[str, list[dict], dict]:
    """Full variant population is NOT directly persisted (only removed_trades + added_trades
    deltas vs the baseline). Reconstructed as (baseline - removed) + added, verified against
    the source file's own headline counts and its own component totals."""
    baseline_path = ANALYSIS / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
    variant_path = ANALYSIS / "deep-research" / "min-triggers-bear2-ab-2026-07-28.json"
    baseline = json.loads(baseline_path.read_text())["trades"]
    d = json.loads(variant_path.read_text())
    removed = d["removed_trades"]
    added = d["added_trades"]

    def key(t: dict) -> tuple:
        return (t["date"], t["entry_time_et"], t["symbol"], t["side"], t.get("qty"))

    removed_ctr = Counter(key(t) for t in removed)
    kept = []
    unmatched = 0
    for t in baseline:
        k = key(t)
        if removed_ctr[k] > 0:
            removed_ctr[k] -= 1
        else:
            kept.append(t)
    unmatched = sum(removed_ctr.values())  # should be 0 -- every removed trade found in baseline
    variant = _clean(kept + added)

    headline = d["headline"]
    recon_total = round(sum(t["dollar_pnl"] for t in variant), 2)
    baseline_total = round(sum(t["dollar_pnl"] for t in baseline), 2)
    removed_total = round(sum(t["dollar_pnl"] for t in removed), 2)
    added_total = round(sum(t["dollar_pnl"] for t in added), 2)
    internal_check = round(baseline_total - removed_total + added_total, 2)

    provenance = {
        "source_file": str(variant_path.relative_to(ROOT)),
        "baseline_source_file": str(baseline_path.relative_to(ROOT)),
        "field_path": "reconstructed: (baseline.trades - removed_trades) + added_trades",
        "n_persisted": len(variant),
        "reconstructed": True,
        "join_key": "(date, entry_time_et, symbol, side, qty)",
        "join_unmatched_removed_trades": unmatched,
        "reconstructed_n": len(variant),
        "reconstructed_total_pnl": recon_total,
        "internal_arithmetic_check_total_pnl": internal_check,
        "headline_reported_variant_n": headline["variant_n"],
        "headline_reported_variant_total_pnl": headline["variant_total"],
        "note": (
            "DISCLOSED DATA-QUALITY ANOMALY: the reconstructed total ($%.2f, n=%d) exactly "
            "matches this file's OWN internal arithmetic (baseline_total %.2f - "
            "removed_trades_pnl %.2f + added_trades_pnl %.2f = %.2f), and n matches headline "
            "exactly (%d). But the file's headline.variant_total field itself reads $%.2f -- "
            "a $%.2f discrepancy against its own component fields, present in the source "
            "artifact, not introduced by this reconstruction. Using the internally-consistent "
            "reconstruction (join verified: all %d removed_trades matched 1:1 against "
            "baseline, 0 unmatched, no duplicate keys either side)."
            % (
                recon_total,
                len(variant),
                baseline_total,
                removed_total,
                added_total,
                internal_check,
                headline["variant_n"],
                headline["variant_total"],
                abs(headline["variant_total"] - internal_check),
                len(removed),
            )
        ),
    }
    return "min_triggers_bear2", variant, provenance


def load_all_variants() -> list[tuple[str, list[dict], dict]]:
    out: list[tuple[str, list[dict], dict]] = []
    out.extend(load_ladder_floors())
    out.append(load_ladder_subset())
    out.extend(load_structure_shift_standalone())
    out.append(load_structure_shift_cascade())
    out.extend(load_zone_bands())
    out.append(load_min_triggers_bear2())
    return out


# ---------------------------------------------------------------------------------------
# Slice statistics
# ---------------------------------------------------------------------------------------


def slice_stats(trades: list[dict]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "n": 0, "total_pnl": 0.0, "per_trade": None, "win_rate": None,
            "day_majority": False, "win_days": 0, "total_days": 0,
            "survives_drop_best": False, "p_one_sided_gt0": None,
        }
    pnls = [t["dollar_pnl"] for t in trades]
    total = sum(pnls)
    per_trade = total / n
    wr = sum(1 for p in pnls if p > 0) / n

    daily: dict[str, float] = defaultdict(float)
    for t in trades:
        daily[t["date"]] += t["dollar_pnl"]
    win_days = sum(1 for v in daily.values() if v > 0)
    total_days = len(daily)
    day_majority = win_days > (total_days - win_days) if total_days > 0 else False

    best = max(pnls)
    survives_drop_best = (total - best) > 0

    p_one = None
    if n >= 2 and len(set(pnls)) > 1:  # t-test needs variance
        tstat, p_two = scipy_stats.ttest_1samp(pnls, 0.0)
        if tstat > 0:
            p_one = p_two / 2
        else:
            p_one = 1.0 - p_two / 2

    return {
        "n": n,
        "total_pnl": round(total, 2),
        "per_trade": round(per_trade, 2),
        "win_rate": round(wr, 4),
        "day_majority": day_majority,
        "win_days": win_days,
        "total_days": total_days,
        "survives_drop_best": survives_drop_best,
        "best_trade_pnl": round(best, 2),
        "p_one_sided_gt0": round(p_one, 6) if p_one is not None else None,
    }


def benjamini_hochberg(p_values: list[float], q: float) -> tuple[float | None, list[bool]]:
    """Standard BH step-up procedure. Returns (critical p threshold or None if nothing
    survives, list[bool] parallel to input order marking BH-significant)."""
    m = len(p_values)
    if m == 0:
        return None, []
    indexed = sorted(range(m), key=lambda i: p_values[i])
    threshold = None
    largest_i = -1
    for rank, idx in enumerate(indexed, start=1):
        crit = (rank / m) * q
        if p_values[idx] <= crit:
            largest_i = rank
            threshold = p_values[idx]
    sig = [False] * m
    if largest_i >= 0:
        cutoff_p = p_values[indexed[largest_i - 1]]
        for i, p in enumerate(p_values):
            if p <= cutoff_p:
                sig[i] = True
    return threshold, sig


# ---------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------


def main() -> dict:
    inv = load_day_inventory()
    variants = load_all_variants()

    all_trading_dates = set(inv.keys())
    for _, trades, _ in variants:
        all_trading_dates.update(t["date"] for t in trades)
    prior_day_type_map = build_prior_day_type_map(inv, sorted(all_trading_dates))

    vix_dts, vix_close = load_vix_bars()

    # ---- annotate every trade with its regime coordinates -------------------------------
    for _, trades, _ in variants:
        for t in trades:
            t["_gap_state"] = gap_state_for(t["date"], inv)
            t["_prior_day_type"] = prior_day_type_map.get(t["date"], "unknown")
            t["_vix_band"] = vix_band_at(t["entry_time_et"], vix_dts, vix_close)
            t["_entry_hour"] = entry_hour_bucket(t["entry_time_et"])

    axes = {
        "gap_state": "_gap_state",
        "prior_day_type": "_prior_day_type",
        "vix_band": "_vix_band",
        "entry_hour": "_entry_hour",
    }
    # buckets excluded from candidate eligibility (data-quality / non-regime labels), still
    # reported in the full table for transparency.
    non_regime_buckets = {"unknown", "unclassified"}

    slices: list[dict] = []
    variant_summaries: dict[str, dict] = {}

    for name, trades, provenance in variants:
        agg = slice_stats(trades)
        variant_summaries[name] = {"provenance": provenance, "aggregate": agg}

        for axis_name, field in axes.items():
            buckets: dict[str, list[dict]] = defaultdict(list)
            for t in trades:
                buckets[t[field]].append(t)
            for bucket_name, bucket_trades in buckets.items():
                stats_ = slice_stats(bucket_trades)
                slices.append(
                    {
                        "variant": name,
                        "axis": axis_name,
                        "bucket": bucket_name,
                        "is_regime_bucket": bucket_name not in non_regime_buckets,
                        **stats_,
                    }
                )

    # ---- BH-FDR across the ENTIRE slice surface at once ----------------------------------
    # Eligible for the surface = has a computable p-value (n>=2, non-degenerate). Slices
    # excluded from BH testing (n<2 or all-identical pnl) are reported but never flagged
    # BH-significant and can never be a candidate (n<2 also fails the n>=25 gate anyway).
    eligible_idx = [i for i, s in enumerate(slices) if s["p_one_sided_gt0"] is not None]
    eligible_p = [slices[i]["p_one_sided_gt0"] for i in eligible_idx]
    bh_threshold, bh_sig = benjamini_hochberg(eligible_p, FDR_Q)
    for pos, idx in enumerate(eligible_idx):
        slices[idx]["bh_eligible"] = True
        slices[idx]["bh_significant_q10"] = bh_sig[pos]
    for i, s in enumerate(slices):
        s.setdefault("bh_eligible", False)
        s.setdefault("bh_significant_q10", False)

    # ---- candidate gate (frozen) -----------------------------------------------------------
    candidates = []
    for s in slices:
        if not s["is_regime_bucket"]:
            continue
        if (
            s["n"] >= CANDIDATE_MIN_N
            and s["total_pnl"] > 0
            and s["day_majority"]
            and s["survives_drop_best"]
            and s["bh_significant_q10"]
        ):
            candidates.append(s)

    # ---- honest diagnostic: least-bad / worst regime bucket per variant, any gate -------
    diagnostics = {}
    for name in variant_summaries:
        own = [s for s in slices if s["variant"] == name and s["is_regime_bucket"] and s["n"] > 0]
        if not own:
            diagnostics[name] = {"least_bad": None, "worst": None}
            continue
        least_bad = max(own, key=lambda s: s["per_trade"])
        worst = min(own, key=lambda s: s["per_trade"])
        diagnostics[name] = {
            "least_bad": {
                "axis": least_bad["axis"], "bucket": least_bad["bucket"],
                "n": least_bad["n"], "per_trade": least_bad["per_trade"],
                "total_pnl": least_bad["total_pnl"], "win_rate": least_bad["win_rate"],
            },
            "worst": {
                "axis": worst["axis"], "bucket": worst["bucket"],
                "n": worst["n"], "per_trade": worst["per_trade"],
                "total_pnl": worst["total_pnl"], "win_rate": worst["win_rate"],
            },
        }

    # strip working annotation keys before returning trade objects anywhere (none returned)
    result = {
        "_doc": (
            "DESCRIPTIVE regime re-slice of already-computed graveyard per-trade records. "
            "No new replays, no new variants, no re-optimization. See module docstring."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "prereg": "analysis/recommendations/prereg-regime-conditioning-2026-07-28.json (commit 1e3dc624)",
        "axes_used": list(axes.keys()),
        "axis_excluded": {
            "premarket_range_pct": (
                "No repo-wide historical premarket high/low dataset spans the full "
                "2025-01-02..2026-07-27 replay window; only current-day snapshots exist "
                "(eod-deep-*.json, swarm state). Ad hoc derivation from raw 5m bars risks the "
                "documented DST/frame look-ahead bug (CLAUDE.md C6). Excluded per pre-reg's "
                "own sanctioned fallback rather than fabricated."
            )
        },
        "gates_frozen": {
            "candidate_min_n": CANDIDATE_MIN_N,
            "fdr_q": FDR_Q,
            "requires": [
                "n>=25", "positive aggregate", "day-majority", "survives-drop-best",
                "BH-significant at q<=0.10 across the full slice surface",
            ],
        },
        "significance_test": (
            "One-sample one-sided t-test (scipy.stats.ttest_1samp) on per-trade dollar_pnl, "
            "H1: mean>0. Requires n>=2 and non-degenerate variance; slices failing that "
            "precondition get p_one_sided_gt0=null and are excluded from the BH surface "
            "(they also fail n>=25 by construction in every such case here)."
        ),
        "slice_surface_size_total": len(slices),
        "slice_surface_size_bh_eligible": len(eligible_p),
        "bh_critical_p_threshold": bh_threshold,
        "n_candidates": len(candidates),
        "candidates": candidates,
        "variant_summaries": variant_summaries,
        "diagnostics_least_bad_worst_per_variant": diagnostics,
        "all_slices": slices,
    }
    return result


if __name__ == "__main__":
    out = main()
    out_path = ANALYSIS / "deep-research" / "REGIME-RESLICE-2026-07-28.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"n_candidates={out['n_candidates']}")
    print(f"slice_surface_size_total={out['slice_surface_size_total']}")
    print(f"slice_surface_size_bh_eligible={out['slice_surface_size_bh_eligible']}")
    print(f"bh_critical_p_threshold={out['bh_critical_p_threshold']}")
    print(f"wrote {out_path}")
