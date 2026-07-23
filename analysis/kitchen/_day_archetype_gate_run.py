"""
DAY-ARCHETYPE PARTICIPATION GATE -- runner for the frozen pre-registration at
analysis/kitchen/prereg-day-archetype-gate-2026-07-23.json. Read that file first;
this script implements it verbatim (no post-hoc threshold changes).

Conditions the engine's own 190 real-OPRA-fill replay trades
(analysis/recommendations/engine-fullhist-replay-2026-07-23.json) on a CAUSAL
opening-range-compression classifier (first 30/60 true-ET minutes vs a trailing
20-day median) + optional prior-day VIX confirmation. 16-cell grid (2x2x2x2).

$0, local caches only. No orders, no params/config edits, no live wiring, no commits.
Writes analysis/kitchen/day-archetype-gate-episodes.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))
from lib.et_frame import parse_timestamp_et  # noqa: E402

REPLAY_PATH = ROOT / "analysis/recommendations/engine-fullhist-replay-2026-07-23.json"
INVENTORY_PATH = ROOT / "analysis/edge-matrix/day-inventory-2026-07-23.json"
SPY5M_PATH = ROOT / "backtest/data/spy_5m_2025-01-01_2026-07-22.csv"
PREREG_PATH = ROOT / "analysis/kitchen/prereg-day-archetype-gate-2026-07-23.json"
OUT_EPISODES = ROOT / "analysis/kitchen/day-archetype-gate-episodes.json"

ET = ZoneInfo("America/New_York")
WINDOWS = [30, 60]
THRESHOLDS = [0.60, 0.75]
ACTIONS = ["skip_day", "half_size"]
VIX_MODES = ["off", "on"]


# --------------------------------------------------------------------- utils
def is_est(date_: dt.date) -> bool:
    """True if `date_` (US) is in standard time (EST, UTC-5), i.e. NOT DST."""
    probe = dt.datetime(date_.year, date_.month, date_.day, 12, 0, tzinfo=ET)
    return probe.dst() == dt.timedelta(0)


def wallv1_to_true_et(naive_local: dt.datetime) -> dt.datetime:
    """Correct a wall-v1 (fixed -04:00 mislabeled) naive datetime to true ET.
    engine_fullhist_replay.py parses timestamp_et with plain pd.to_datetime
    (no utc=True) -- keeps the file's raw wall-clock numeral, which is 1h
    AHEAD of true ET on EST-month (winter) dates (documented DST-frame
    artifact, backtest/lib/et_frame.py)."""
    if is_est(naive_local.date()):
        return naive_local - dt.timedelta(hours=1)
    return naive_local


def one_sample_p(pnls: list[float]) -> float:
    """backtest/tools/pullback_hold_bull_replay.py:_one_sample_p, reused unchanged."""
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se_ = (var / n) ** 0.5
    if se_ == 0:
        return 1.0
    t = mean / se_
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))
    return max(0.0, min(1.0, p))


def bh_fdr(pvals: list[float], alpha: float = 0.10) -> list[bool]:
    """backtest/autoresearch/ribbon_rejection_wick_battery.py:bh_fdr, reused unchanged."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh_rank = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= rank / m * alpha:
            thresh_rank = rank
    survivor = [False] * m
    for rank, i in enumerate(order, start=1):
        survivor[i] = rank <= thresh_rank
    return survivor


# ------------------------------------------------------------- load: bars
spy = pd.read_csv(SPY5M_PATH)
spy["ts_true_et"] = parse_timestamp_et(spy["timestamp_et"], frame="et-v2")
spy["date"] = spy["ts_true_et"].dt.date.astype(str)
spy = spy.sort_values("ts_true_et").reset_index(drop=True)
rth = spy[
    (spy["ts_true_et"].dt.time >= dt.time(9, 30)) & (spy["ts_true_et"].dt.time < dt.time(16, 0))
].copy()
rth_by_date = {d: g for d, g in rth.groupby("date")}

print(f"SPY bars loaded: {len(spy)} total, {len(rth)} RTH (true-ET), {len(rth_by_date)} distinct RTH dates")

# ------------------------------------------------------------- load: day inventory
with open(INVENTORY_PATH, encoding="utf-8") as f:
    inv = json.load(f)
inv_days_sorted = sorted(inv["days"], key=lambda r: r["date"])
inv_dates_sorted = [r["date"] for r in inv_days_sorted]
inv_by_date = {r["date"]: r for r in inv_days_sorted}
heldout_set = set(inv.get("heldout_days", []))
print(f"Day universe: {len(inv_dates_sorted)} days, heldout={len(heldout_set)}")

# ------------------------------------------------------------- causal classifier
first_n_range: dict[int, dict[str, float | None]] = {n: {} for n in WINDOWS}
for n in WINDOWS:
    cutoff_time = (dt.datetime.combine(dt.date(2000, 1, 1), dt.time(9, 30)) + dt.timedelta(minutes=n)).time()
    for d in inv_dates_sorted:
        day_rows = rth_by_date.get(d)
        if day_rows is None or len(day_rows) == 0:
            first_n_range[n][d] = None
            continue
        window_rows = day_rows[day_rows["ts_true_et"].dt.time < cutoff_time]
        if len(window_rows) == 0:
            first_n_range[n][d] = None
            continue
        first_n_range[n][d] = float(window_rows["high"].max() - window_rows["low"].min())

trailing_median_n: dict[int, dict[str, float | None]] = {n: {} for n in WINDOWS}
for n in WINDOWS:
    seen: list[float | None] = []
    for d in inv_dates_sorted:
        prior_vals = [v for v in seen[-20:] if v is not None]
        trailing_median_n[n][d] = statistics.median(prior_vals) if len(prior_vals) >= 5 else None
        seen.append(first_n_range[n][d])

ratio: dict[int, dict[str, float | None]] = {n: {} for n in WINDOWS}
n_undefined = {n: 0 for n in WINDOWS}
for n in WINDOWS:
    for d in inv_dates_sorted:
        fr = first_n_range[n][d]
        tm = trailing_median_n[n][d]
        if fr is None or tm is None or tm == 0:
            ratio[n][d] = None
            n_undefined[n] += 1
        else:
            ratio[n][d] = fr / tm

for n in WINDOWS:
    defined = [v for v in ratio[n].values() if v is not None]
    print(
        f"window={n}min: {len(defined)}/{len(inv_dates_sorted)} days classifiable "
        f"(undefined={n_undefined[n]}), ratio median={statistics.median(defined):.3f} "
        f"IQR=[{statistics.quantiles(defined, n=4)[0]:.3f},{statistics.quantiles(defined, n=4)[2]:.3f}]"
    )

prior_vix_band: dict[str, str | None] = {}
for i, d in enumerate(inv_dates_sorted):
    prior_vix_band[d] = inv_days_sorted[i - 1]["vix_band"] if i > 0 else None

# ------------------------------------------------------------- load: replay trades
with open(REPLAY_PATH, encoding="utf-8") as f:
    replay = json.load(f)
trades = replay["trades"]
print(f"Replay trades loaded: {len(trades)} (all resolved=true per replay's own disclosure)")

for t in trades:
    naive = dt.datetime.fromisoformat(t["entry_time_et"])
    t["_true_entry_et"] = wallv1_to_true_et(naive)

baseline_dates = sorted({t["date"] for t in trades})
n_baseline_days = len(baseline_dates)
baseline_daily: dict[str, float] = {}
for t in trades:
    baseline_daily[t["date"]] = baseline_daily.get(t["date"], 0.0) + t["dollar_pnl"]
baseline_total = round(sum(t["dollar_pnl"] for t in trades), 2)
baseline_day_wins = sum(1 for v in baseline_daily.values() if v > 0)
baseline_day_wr = round(baseline_day_wins / n_baseline_days, 4)
print(
    f"BASELINE: n_trades={len(trades)} n_days={n_baseline_days} total_pnl={baseline_total:+.2f} "
    f"day_wr={baseline_day_wr:.4f} ({baseline_day_wins}/{n_baseline_days})"
)


# ------------------------------------------------------------- gate application
def gated_days_for(window_n: int, k: float, vix_mode: str) -> set[str]:
    gated = set()
    for d in inv_dates_sorted:
        r = ratio[window_n].get(d)
        if r is None or not (r < k):
            continue
        if vix_mode == "on":
            pvb = prior_vix_band.get(d)
            if pvb not in ("low", "mid"):
                continue
        gated.add(d)
    return gated


def cutoff_time_for(window_n: int) -> dt.time:
    return (dt.datetime.combine(dt.date(2000, 1, 1), dt.time(9, 30)) + dt.timedelta(minutes=window_n)).time()


def run_cell(window_n: int, k: float, action: str, vix_mode: str) -> dict:
    gated = gated_days_for(window_n, k, vix_mode)
    cutoff_t = cutoff_time_for(window_n)

    post_pnls: list[float] = []
    post_daily: dict[str, float] = {}
    n_zeroed = 0
    n_halved = 0
    n_pre_cutoff_retained = 0
    n_real_fills = 0  # non-zeroed trade slots (i.e. actually still a live entry)

    for t in trades:
        d = t["date"]
        base_pnl = t["dollar_pnl"]
        eligible = (d in gated) and (t["_true_entry_et"].time() >= cutoff_t)
        if not eligible:
            if d in gated and t["_true_entry_et"].time() < cutoff_t:
                n_pre_cutoff_retained += 1
            post_pnl = base_pnl
            n_real_fills += 1
        else:
            if action == "skip_day":
                post_pnl = 0.0
                n_zeroed += 1
            else:  # half_size
                post_pnl = base_pnl * 0.5
                n_halved += 1
                n_real_fills += 1
        post_pnls.append(post_pnl)
        post_daily[d] = post_daily.get(d, 0.0) + post_pnl

    total = round(sum(post_pnls), 2)
    n = len(post_pnls)
    expectancy = round(total / n, 2) if n else 0.0

    n_days = len(post_daily)
    day_wins = sum(1 for v in post_daily.values() if v > 0)
    day_wr = round(day_wins / n_days, 4) if n_days else 0.0

    desc = sorted(post_pnls, reverse=True)
    ex_top1 = round(total - sum(desc[:1]), 2) if n else 0.0
    ex_top3 = round(total - sum(desc[:3]), 2) if n else 0.0

    held_pnls = [
        p for t, p in zip(trades, post_pnls) if t["date"] in heldout_set
    ]
    held_total = round(sum(held_pnls), 2)

    p_raw = round(one_sample_p(post_pnls), 5)

    g1 = total > 0
    g2 = n_days > 0 and day_wins > (n_days / 2.0)
    g3 = ex_top1 > 0
    g4 = held_total > 0
    gates_passed = int(g1) + int(g2) + int(g3) + int(g4)

    cell_id = f"N{window_n}_k{int(k*100):03d}_{('skip' if action=='skip_day' else 'half')}_vix{vix_mode.upper()}"

    return {
        "cell_id": cell_id,
        "params": {
            "window_minutes": window_n,
            "compression_threshold_k": k,
            "action": action,
            "vix_confirmation": vix_mode,
        },
        "n_real_fills": n_real_fills,
        "n_zeroed_slots": n_zeroed,
        "n_halved_slots": n_halved,
        "n_pre_cutoff_retained": n_pre_cutoff_retained,
        "n_gated_days": len(gated),
        "expectancy": expectancy,
        "total_pnl": total,
        "day_wr": day_wr,
        "n_days_covered": n_days,
        "n_day_wins": day_wins,
        "ex_top1_total": ex_top1,
        "ex_top3_total": ex_top3,
        "held_out_total": held_total,
        "n_heldout_trade_slots": len(held_pnls),
        "p_raw": p_raw,
        "gates": {
            "g1_positive_aggregate": g1,
            "g2_day_majority": g2,
            "g3_survives_ex_top1": g3,
            "g4_held_out_positive": g4,
        },
        "gates_passed": gates_passed,
        "lift_vs_baseline": {
            "total_pnl_delta": round(total - baseline_total, 2),
            "day_wr_delta": round(day_wr - baseline_day_wr, 4),
        },
    }


cells = []
for window_n in WINDOWS:
    for k in THRESHOLDS:
        for action in ACTIONS:
            for vix_mode in VIX_MODES:
                cells.append(run_cell(window_n, k, action, vix_mode))

pvals = [c["p_raw"] for c in cells]
survivors = bh_fdr(pvals, alpha=0.10)
for c, surv in zip(cells, survivors):
    c["bh_fdr_survivor"] = surv

# ---- archetype cross-tab (descriptive only -- diagnostic, not gating) ----
# For each cell, what fraction of its gated days does day-inventory's own
# (non-causal, full-day) day_type classify as chop/range/trend?
for c in cells:
    window_n = c["params"]["window_minutes"]
    k = c["params"]["compression_threshold_k"]
    vix_mode = c["params"]["vix_confirmation"]
    gated = gated_days_for(window_n, k, vix_mode)
    dt_counts: dict[str, int] = {}
    for d in gated:
        dtp = inv_by_date.get(d, {}).get("day_type", "unknown")
        dt_counts[dtp] = dt_counts.get(dtp, 0) + 1
    n_g = len(gated) or 1
    c["archetype_coverage"] = (
        f"{len(gated)}/{len(inv_dates_sorted)} pop days gated "
        f"(chop={dt_counts.get('chop', 0)}[{100*dt_counts.get('chop', 0)/n_g:.0f}%] "
        f"range={dt_counts.get('range', 0)}[{100*dt_counts.get('range', 0)/n_g:.0f}%] "
        f"trend={dt_counts.get('trend', 0)}[{100*dt_counts.get('trend', 0)/n_g:.0f}%] "
        f"unclassified={dt_counts.get('unclassified', 0)})"
    )

print("\n=== CELL RESULTS ===")
for c in cells:
    print(
        f"{c['cell_id']:32s} n={c['n_real_fills']:3d} total={c['total_pnl']:+9.2f} "
        f"dayWR={c['day_wr']:.3f} ex1={c['ex_top1_total']:+9.2f} ex3={c['ex_top3_total']:+9.2f} "
        f"held={c['held_out_total']:+8.2f} p={c['p_raw']:.4f} bh={c['bh_fdr_survivor']} "
        f"gates={c['gates_passed']}/4 lift={c['lift_vs_baseline']['total_pnl_delta']:+8.2f}"
    )

n_pass = sum(1 for c in cells if c["gates_passed"] == 4)
print(f"\nCANDIDATE_PASS (4/4 gates): {n_pass}/16 cells")

# ------------------------------------------------------------- write episodes
with open(PREREG_PATH, encoding="utf-8") as f:
    prereg_snapshot = json.load(f)

episodes_doc = {
    "_doc": "Episode/cell output for the DAY-ARCHETYPE PARTICIPATION GATE study "
            "(analysis/kitchen/prereg-day-archetype-gate-2026-07-23.json, FROZEN before this run). "
            "Runner: analysis/kitchen/_day_archetype_gate_run.py. Analysis-only, $0, no orders/params/live-wiring/commits.",
    "generated_from": {
        "prereg": "analysis/kitchen/prereg-day-archetype-gate-2026-07-23.json",
        "replay": "analysis/recommendations/engine-fullhist-replay-2026-07-23.json",
        "day_inventory": "analysis/edge-matrix/day-inventory-2026-07-23.json",
        "spy_5m_source": "backtest/data/spy_5m_2025-01-01_2026-07-22.csv",
        "harvest_anatomy": "analysis/kitchen/HARVEST-DAY-ANATOMY-2026-07-23.md + day-archetype-map.json",
    },
    "prereg_content_sha256_16_check": None,
    "baseline": {
        "n_trades": len(trades),
        "n_days": n_baseline_days,
        "total_pnl": baseline_total,
        "day_wr": baseline_day_wr,
        "n_day_wins": baseline_day_wins,
    },
    "classifier_diagnostics": {
        str(n): {
            "n_days_classifiable": len(inv_dates_sorted) - n_undefined[n],
            "n_days_undefined": n_undefined[n],
        }
        for n in WINDOWS
    },
    "grid": {"n_knobs": 4, "n_cells": len(cells)},
    "cells": cells,
    "portfolio_level_bh_fdr": {
        "alpha": 0.10,
        "n_comparisons": len(cells),
        "n_survivors": sum(survivors),
    },
    "candidate_pass_count": n_pass,
    "verdict": (
        "NO CANDIDATE_PASS -- KILL (0/16 cells clear all 4 gates)"
        if n_pass == 0
        else f"{n_pass}/16 cells CANDIDATE_PASS -- see cells[] for detail, none auto-ship (OP-32 P1 routing)"
    ),
}

OUT_EPISODES.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_EPISODES, "w", encoding="utf-8") as f:
    json.dump(episodes_doc, f, indent=2, default=str)

print(f"\nWrote {OUT_EPISODES}")
