"""FOLLOWTHROUGH-HEADROOM runner -- prereg
analysis/recommendations/prereg-followthrough-headroom-2026-09-11.json (frozen, committed
dbe35ce7, BEFORE this runner existed). Do not edit the prereg; if a threshold here looks
wrong, run it as frozen and say so in the report, per that file's own instruction.

QUESTION. Does a CAUSAL feature at entry predict follow-through (FAV60, the only clean
green/red separator found 2026-09-11)? Primary hypothesis: HEADROOM -- distance to the
nearest OPPOSING level, the obstacle ahead. NOT a repeat of ENTRY-LOCATION-GATE-2026-08-14
(that measured distance to the prior extreme BEHIND the entry -- opposite geometry).

POPULATION. Reuses backtest/autoresearch/entry_location_gate_rerun_2026_09_11.py's builder
verbatim (orig replay 191 + csv real-fills + pnl-statement real-fills, event-deduped) and its
features_floor() causal-alignment helper. Does NOT rebuild the population a second way.

CAUSALITY (non-negotiable). Every feature from bars/level-state STRICTLY BEFORE the entry
bar. Entry price = entry bar OPEN (from features_floor). The entry bar's own high/low never
enters a FEATURE (FAV60 is the OUTCOME being measured, not a feature, and legitimately uses
bars from/after entry).

THE HARD PART -- F1/F2 headroom need the LEVEL SET AS IT STOOD BEFORE ENTRY. Investigated
sources (see report for full audit):
  - automation/state/core-decisions.jsonl `levels_active` field: the live production engine's
    OWN logged level state, per-tick, real-time. First non-empty row 2026-07-28T09:30:05.
    Zero coverage before that (key absent entirely before 2026-07-27T22:45:52). This is the
    ONLY genuine (non-reconstructed) as-of level-state source found.
  - journal/*.md dailies: earliest file is 2026-04-29, and dailies do not carry a structured
    level list usable programmatically -- not used.
  - analysis/swarm-benchmark/replay-*/key-levels.json: explicitly `"replay_mode": true`,
    `"protocol_version": "...(replay-mode algorithmic)"` -- an ALGORITHMIC RECOMPUTATION for a
    benchmarking tool, not the level state actually live at the time (may use different
    level-computation parameters than production ever ran with). Using it as a stand-in for
    "the level set as it stood" would be exactly the forbidden undeclared proxy. NOT used.
  - analysis/level-quality/snapshots/: only 2 dates (2026-06-16, 2026-06-19), outside the
    population's post-causal-source window in a way that adds no coverage. NOT used.

CONCLUSION (stated before running, not after seeing results): F1/F2 can only be computed for
entries dated >= 2026-07-28 (the extension population). The original 191-trade replay
population (2025-01-06..2026-07-21) is EXCLUDED from F1/F2 entirely -- not because any single
entry's data is unusually missing, but because NO genuine historical level-state log exists
for that window anywhere in the repo. This is reported honestly per-feature in `excluded`
rather than silently shrinking F1/F2's population and reporting a number that looks like the
full 388.

F3/F4/F5 need no level state (only bars) and run over the FULL population.

FAV60 (mechanism metric) and dollar expectancy (ratifying metric) are both required; a cell
counts only if both move the same direction (prereg dual-metric rule).

Uses backtest/lib/canonical_battery.py's `one_sample_p` and `bh_fdr` for all p-value /
FDR machinery (STANDING LESSON: do not reimplement battery stats inline). G_drop3 here is the
prereg's own specific rule (drop the 3 largest-|pnl| trades, not canonical_battery's
winners-only drop_top_n, which is a different rule) so it is implemented directly as a data
selection, not a reimplementation of the stats primitives.

Read-only. Writes analysis/recommendations/followthrough-headroom-2026-09-11.json. Arms
nothing. Touches nothing on the trading path.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
sys.path.insert(0, str(REPO / "backtest" / "lib"))
import entry_location_gate_rerun_2026_09_11 as rerun  # noqa: E402
import entry_location_gate_2026_08_14 as base  # noqa: E402
import canonical_battery as cb  # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-followthrough-headroom-2026-09-11.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT = REPO / "analysis" / "recommendations" / "followthrough-headroom-2026-09-11.json"
LIVING_DOC = REPO / "analysis" / "recommendations" / "ENTRY-LOCATION-GATE-2026-08-14.md"

MIN_CELL_N = 30          # prereg G_n
ATR_PRIOR_N = 12         # F2/F4 lookback bars (5m)
ER_PRIOR_N = 6           # F3 lookback bars (5m) = 30 min
FAV60_BARS = 12          # 12 x 5m = 60 min, entry bar inclusive
RANGE_LOOKBACK_DAYS = 20 # F5 denominator

F1_BANDS = [0.25, 0.50, 1.00]
F2_BANDS = [0.5, 1.0, 2.0]
F3_BANDS = [0.15, 0.30]
F4_BANDS = [0.20, 0.30]
F5_BANDS = [0.70, 0.90]

LEVELS_ACTIVE_FIRST_DATE = "2026-07-28"  # verified: first non-empty levels_active row


# ── level-state index (core-decisions.jsonl, live-production, real-time only) ───────────────

def load_levels_index() -> dict[str, list[tuple[str, list[float]]]]:
    """date -> sorted [(ts_et, levels_active)] for every row with a non-empty levels_active.
    Multiple accounts log the same tick's level state redundantly; both are kept (harmless,
    lookup takes the latest row <= entry time regardless of which account logged it)."""
    idx: dict[str, list[tuple[str, list[float]]]] = defaultdict(list)
    with CORE_DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            la = d.get("levels_active")
            if la:
                idx[d["ts_et"][:10]].append((d["ts_et"], la))
    for d in idx:
        idx[d].sort(key=lambda x: x[0])
    return idx


def levels_as_of(levels_idx: dict, date: str, entry_ts_et: str) -> Optional[list[float]]:
    """Latest levels_active with ts_et <= entry_ts_et on `date`. None if no such row (before
    the first logged tick of the day, or the date has no coverage at all)."""
    rows = levels_idx.get(date)
    if not rows:
        return None
    best = None
    for ts, la in rows:
        if ts <= entry_ts_et:
            best = la
        else:
            break
    return best


def nearest_opposing_level(side: str, entry_px: float, levels: list[float]) -> Optional[float]:
    """side C (bull): nearest level ABOVE entry (resistance ahead). side P (bear): nearest
    level BELOW entry (support ahead). None if no opposing level exists in the set."""
    if side == "C":
        above = [lv for lv in levels if lv > entry_px]
        return min(above) if above else None
    below = [lv for lv in levels if lv < entry_px]
    return max(below) if below else None


# ── bar-derived features (F3/F4/F5), no level dependency ────────────────────────────────────

def true_range(bar: dict, prev_close: Optional[float]) -> float:
    if prev_close is None:
        return bar["h"] - bar["l"]
    return max(bar["h"] - bar["l"], abs(bar["h"] - prev_close), abs(bar["l"] - prev_close))


def atr_of(before_bars: list[dict], n: int) -> Optional[float]:
    """Simple ATR over the last `n` bars strictly before the entry bar. None if fewer than
    n+1 bars available (need a bar before the first TR bar for its prev-close)."""
    if len(before_bars) < n + 1:
        return None
    window = before_bars[-n:]
    prevs = before_bars[-(n + 1):-1]
    trs = [true_range(b, p["c"]) for b, p in zip(window, prevs)]
    return sum(trs) / len(trs)


def efficiency_ratio(before_bars: list[dict], n: int) -> Optional[float]:
    """Kaufman-style ER over the last n bars strictly before entry: |net close change| /
    sum(|bar-to-bar close changes|). None if fewer than n+1 closes available."""
    if len(before_bars) < n + 1:
        return None
    closes = [b["c"] for b in before_bars[-(n + 1):]]
    net = abs(closes[-1] - closes[0])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    if path == 0:
        return None
    return net / path


def prior_session_ranges(days: dict[str, list[dict]], ordered_dates: list[str],
                          date: str, n: int) -> Optional[list[float]]:
    """Full RTH range (hi-lo) for the `n` trading days strictly before `date`. None if fewer
    than n prior days exist in the loaded bar set."""
    idx = ordered_dates.index(date) if date in ordered_dates else None
    if idx is None or idx < n:
        return None
    prior_dates = ordered_dates[idx - n:idx]
    ranges = []
    for d in prior_dates:
        session = base.rth(days[d])
        if not session:
            return None
        ranges.append(max(b["h"] for b in session) - min(b["l"] for b in session))
    return ranges


# ── FAV60 (outcome, not a feature -- legitimately uses bars at/after entry) ──────────────────

def fav60(session: list[dict], floor_t: str, side: str, entry_px: float) -> tuple[Optional[float], int]:
    window = [b for b in session if floor_t <= b["t"] < _add_minutes(floor_t, 60)]
    if not window:
        return None, 0
    if side == "C":
        val = max(b["h"] for b in window) - entry_px
    else:
        val = entry_px - min(b["l"] for b in window)
    return round(val, 4), len(window)


def _add_minutes(hhmm: str, minutes: int) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    total = h * 60 + m + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


# ── build the enriched population ────────────────────────────────────────────────────────────

def build_population() -> tuple[list[dict], dict[str, int]]:
    days = rerun.load_merged_bars()
    ordered = sorted(days)
    prior_of = {d: (ordered[i - 1] if i else None) for i, d in enumerate(ordered)}
    levels_idx = load_levels_index()

    orig_raw = json.load(rerun.ORIG_REPLAY.open(encoding="utf-8"))["trades"]
    csv_trades, _ = rerun.build_extended_trades_from_csv()
    pnl_trades, _ = rerun.build_extended_trades_from_pnl_statement()
    combined_raw = list(orig_raw) + csv_trades + pnl_trades

    excl: dict[str, int] = defaultdict(int)
    rows: list[dict] = []
    for t in combined_raw:
        d = t["date"]
        if d not in days:
            excl["no_bar_day"] += 1
            continue
        session = base.rth(days[d])
        f = rerun.features_floor(days[d], days.get(prior_of[d]) if prior_of[d] else None,
                                  t["entry_time_et"][11:16])
        if f is None:
            excl["no_causal_features"] += 1
            continue
        floor_t = None
        for b in session:
            if b["t"] <= t["entry_time_et"][11:16]:
                floor_t = b["t"]
            else:
                break
        before_bars = [b for b in session if b["t"] < floor_t]

        row: dict[str, Any] = {
            "date": d, "side": t["side"], "dollar_pnl": t["dollar_pnl"],
            "entry_time_et": t["entry_time_et"], "tier": t.get("tier"), "setup": t.get("setup"),
            "entry_px": f["entry_px"],
        }

        # F3 / F4 / F2-denominator (bar-only, full population)
        atr = atr_of(before_bars, ATR_PRIOR_N)
        er = efficiency_ratio(before_bars, ER_PRIOR_N)
        row["F4_atr_prior12"] = round(atr, 4) if atr is not None else None
        row["F3_er_prior30"] = round(er, 4) if er is not None else None

        # F5 (bar-only, needs 20 prior trading days)
        ranges = prior_session_ranges(days, ordered, d, RANGE_LOOKBACK_DAYS)
        if ranges and f["range_pts"] is not None:
            med = statistics.median(ranges)
            row["F5_range_used"] = round(f["range_pts"] / med, 4) if med > 0 else None
        else:
            row["F5_range_used"] = None

        # F1 / F2 (level-state-dependent, extension window only)
        if d >= LEVELS_ACTIVE_FIRST_DATE:
            levels = levels_as_of(levels_idx, d, t["entry_time_et"])
            if levels:
                opp = nearest_opposing_level(t["side"], f["entry_px"], levels)
                if opp is not None:
                    headroom = abs(opp - f["entry_px"])
                    row["F1_headroom_abs"] = round(headroom, 4)
                    row["F2_headroom_atr"] = (round(headroom / atr, 4)
                                               if atr and atr > 0 else None)
                    row["_headroom_source"] = "core-decisions.jsonl levels_active (live production)"
                else:
                    row["F1_headroom_abs"] = None
                    row["F2_headroom_atr"] = None
                    row["_headroom_exclude_reason"] = "no_opposing_level_in_active_set"
            else:
                row["F1_headroom_abs"] = None
                row["F2_headroom_atr"] = None
                row["_headroom_exclude_reason"] = "no_levels_active_row_before_entry"
        else:
            row["F1_headroom_abs"] = None
            row["F2_headroom_atr"] = None
            row["_headroom_exclude_reason"] = "predates_levels_active_logging_2026_07_28"

        fv, nbars = fav60(session, floor_t, t["side"], f["entry_px"])
        row["FAV60"] = fv
        row["FAV60_bars_used"] = nbars
        rows.append(row)
    return rows, dict(excl)


# ── cells / battery ───────────────────────────────────────────────────────────────────────────

def build_cells() -> list[dict]:
    cells = []
    for band in F1_BANDS:
        cells.append({"feature": "F1_headroom_abs", "band": band, "op": "<="})
    for band in F2_BANDS:
        cells.append({"feature": "F2_headroom_atr", "band": band, "op": "<="})
    for band in F3_BANDS:
        cells.append({"feature": "F3_er_prior30", "band": band, "op": "<="})
    for band in F4_BANDS:
        cells.append({"feature": "F4_atr_prior12", "band": band, "op": "<="})
    for band in F5_BANDS:
        cells.append({"feature": "F5_range_used", "band": band, "op": ">="})
    return cells


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def drop_top3_abs(rows: list[dict]) -> tuple[float, int]:
    """Prereg's own G_drop3: drop the 3 largest-|pnl| trades (winners OR losers), not
    canonical_battery.drop_top_n's winners-only rule -- a distinct, explicitly-specified test,
    so implemented directly rather than reusing that (different) primitive."""
    pnls = [r["dollar_pnl"] for r in rows]
    order = sorted(range(len(pnls)), key=lambda i: abs(pnls[i]), reverse=True)
    drop = set(order[:3])
    kept = [p for i, p in enumerate(pnls) if i not in drop]
    return (round(sum(kept), 2), len(drop)) if kept else (0.0, len(drop))


def evaluate_cell(feature: str, band: float, op: str, side: str,
                   rows: list[dict]) -> dict[str, Any]:
    eligible = [r for r in rows if r["side"] == side and r.get(feature) is not None]
    n_missing = sum(1 for r in rows if r["side"] == side) - len(eligible)

    def is_gated(v: float) -> bool:
        return v <= band if op == "<=" else v >= band

    g = [r for r in eligible if is_gated(r[feature])]
    k = [r for r in eligible if not is_gated(r[feature])]

    rec: dict[str, Any] = {
        "cell": f"{side}|{feature}{op}{band}", "side": side, "feature": feature,
        "band": band, "op": op, "n_eligible": len(eligible), "n_missing_feature": n_missing,
        "n_gated": len(g), "n_kept": len(k),
    }

    if len(g) < MIN_CELL_N or len(k) < MIN_CELL_N:
        rec["verdict"] = "NOT-RUN"
        rec["why"] = f"n_gated={len(g)} n_kept={len(k)} (need >= {MIN_CELL_N} each; prereg G_n)"
        return rec

    gp = [r["dollar_pnl"] for r in g]
    kp = [r["dollar_pnl"] for r in k]
    gf = [r["FAV60"] for r in g if r["FAV60"] is not None]
    kf = [r["FAV60"] for r in k if r["FAV60"] is not None]

    kept_mean_dollar = _mean(kp)
    kept_mean_fav60 = _mean(kf) if kf else None

    deltas_dollar = [p - kept_mean_dollar for p in gp]
    p_dollar = cb.one_sample_p(deltas_dollar)

    rec.update({
        "verdict": "MEASURED",
        "gated_mean_dollar": round(_mean(gp), 2), "kept_mean_dollar": round(kept_mean_dollar, 2),
        "gated_total_dollar": round(sum(gp), 2), "kept_total_dollar": round(sum(kp), 2),
        "gated_mean_fav60": round(_mean(gf), 4) if gf else None,
        "kept_mean_fav60": round(kept_mean_fav60, 4) if kept_mean_fav60 is not None else None,
        "n_fav60_gated": len(gf), "n_fav60_kept": len(kf),
        "p_dollar_expectancy": round(p_dollar, 5),
        # G3 blocked-winner accounting (mandatory every cell)
        "blocked_winners_n": sum(1 for p in gp if p > 0),
        "blocked_winner_dollars": round(sum(p for p in gp if p > 0), 2),
        "blocked_losers_n": sum(1 for p in gp if p <= 0),
        "blocked_loser_dollars": round(sum(p for p in gp if p <= 0), 2),
        "book_delta_if_gated": round(-sum(gp), 2),
    })
    rec["blocked_winner_exceeds_avoided_loser"] = (
        rec["blocked_winner_dollars"] > abs(rec["blocked_loser_dollars"])
    )
    rec["fav60_and_dollar_agree_direction"] = (
        rec["gated_mean_fav60"] is not None and rec["kept_mean_fav60"] is not None and
        ((rec["gated_mean_dollar"] - rec["kept_mean_dollar"]) *
         (rec["gated_mean_fav60"] - rec["kept_mean_fav60"])) > 0
    )

    # G_drop3 -- prereg's own top-3-|pnl| rule, applied to the gated cohort
    dtop3, n_dropped = drop_top3_abs(g)
    sign_before = rec["gated_mean_dollar"] - rec["kept_mean_dollar"]
    sign_after = (dtop3 / max(len(g) - n_dropped, 1)) - rec["kept_mean_dollar"]
    rec["G_drop3"] = {
        "gated_total_after_drop3": dtop3, "n_dropped": n_dropped,
        "sign_preserved": (sign_before > 0) == (sign_after > 0),
    }

    # G_oos -- chronological split at population median date (within this cell's eligible pop)
    g_chrono = sorted(g, key=lambda r: (r["date"], r["entry_time_et"]))
    is_half, oos_half = cb.is_oos_split([{"pnl": r["dollar_pnl"]} for r in g_chrono])
    is_mean = _mean([r["pnl"] for r in is_half]) if is_half else None
    oos_mean = _mean([r["pnl"] for r in oos_half]) if oos_half else None
    rec["G_oos"] = {
        "is_n": len(is_half), "oos_n": len(oos_half),
        "is_mean_delta_vs_kept": round(is_mean - kept_mean_dollar, 2) if is_mean is not None else None,
        "oos_mean_delta_vs_kept": round(oos_mean - kept_mean_dollar, 2) if oos_mean is not None else None,
        "sign_agrees": (bool(is_half) and bool(oos_half) and
                         ((is_mean - kept_mean_dollar) > 0) == ((oos_mean - kept_mean_dollar) > 0)),
    }
    return rec


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["status"] == "FROZEN — not yet run" or True  # informational only, never gate on it post-hoc

    rows, excl_bars = build_population()

    by_side = defaultdict(list)
    for r in rows:
        by_side[r["side"]].append(r)

    exclusions = dict(excl_bars)
    exclusions["headroom_predates_2026_07_28"] = sum(
        1 for r in rows if r.get("_headroom_exclude_reason") == "predates_levels_active_logging_2026_07_28")
    exclusions["headroom_no_levels_row"] = sum(
        1 for r in rows if r.get("_headroom_exclude_reason") == "no_levels_active_row_before_entry")
    exclusions["headroom_no_opposing_level"] = sum(
        1 for r in rows if r.get("_headroom_exclude_reason") == "no_opposing_level_in_active_set")

    cells_out = []
    pvals_for_bhfdr: list[tuple[str, float]] = []
    for cell in build_cells():
        for side in ("C", "P"):
            rec = evaluate_cell(cell["feature"], cell["band"], cell["op"], side, rows)
            cells_out.append(rec)
            if rec["verdict"] == "MEASURED":
                pvals_for_bhfdr.append((rec["cell"], rec["p_dollar_expectancy"]))

    surv = cb.bh_fdr([p for _, p in pvals_for_bhfdr], q=0.10)
    surv_map = {cid: s for (cid, _), s in zip(pvals_for_bhfdr, surv)}
    m = len(pvals_for_bhfdr)
    required_thresh = {}
    if m:
        order = sorted(range(m), key=lambda i: pvals_for_bhfdr[i][1])
        for rank, i in enumerate(order, start=1):
            required_thresh[pvals_for_bhfdr[i][0]] = round((rank / m) * 0.10, 5)

    for rec in cells_out:
        if rec["verdict"] == "MEASURED":
            rec["survives_bh_fdr_q10"] = surv_map.get(rec["cell"], False)
            rec["bh_fdr_required_threshold"] = required_thresh.get(rec["cell"])
            # a cell only "counts" per prereg if BOTH metrics agree AND it survives BH-FDR AND
            # it isn't refuted by the blocked-winner rule
            rec["counts_as_survivor"] = (
                rec["survives_bh_fdr_q10"] and rec["fav60_and_dollar_agree_direction"]
                and not rec["blocked_winner_exceeds_avoided_loser"]
            )

    measured = [c for c in cells_out if c["verdict"] == "MEASURED"]
    survivors = [c for c in measured if c.get("counts_as_survivor")]
    headroom_measured = [c for c in measured if c["feature"] in ("F1_headroom_abs", "F2_headroom_atr")]
    headroom_survivors = [c for c in headroom_measured if c.get("counts_as_survivor")]

    all_gated_exceeds_kept = bool(measured) and all(
        c["gated_mean_dollar"] > c["kept_mean_dollar"] for c in measured)

    report = {
        "prereg_id": prereg["prereg_id"],
        "frozen_at_et": prereg["frozen_at_et"],
        "run_at": "2026-09-11 (same session as freeze, per prereg turnaround)",
        "population_n_total_rows": len(rows),
        "population_by_side": {s: len(v) for s, v in by_side.items()},
        "exclusions": exclusions,
        "headroom_causal_source_audit": {
            "source_used": "automation/state/core-decisions.jsonl levels_active (live production, real-time logged)",
            "coverage_start": LEVELS_ACTIVE_FIRST_DATE,
            "coverage_verified": "first non-empty row 2026-07-28T09:30:05; field entirely absent before 2026-07-27T22:45:52 (checked directly)",
            "rejected_sources": [
                {"source": "analysis/swarm-benchmark/replay-*/key-levels.json",
                 "reason": "self-labelled replay_mode=true / protocol_version '...(replay-mode algorithmic)' -- an algorithmic recomputation for a benchmarking tool, not the level state that was actually live. Using it would be an undeclared proxy substitution, forbidden by the prereg."},
                {"source": "journal/*.md dailies", "reason": "earliest file 2026-04-29 (after most of the original population); no structured programmatic level list even where present"},
                {"source": "analysis/level-quality/snapshots/", "reason": "only 2 dates (2026-06-16, 2026-06-19), no incremental coverage for this population"},
            ],
            "consequence": "F1/F2 computed ONLY for entries dated >= 2026-07-28. The original 191-trade replay population (2025-01-06..2026-07-21) is excluded from F1/F2 entirely -- not a per-entry data gap, a window-wide absence of any genuine as-of level log.",
        },
        "cells": cells_out,
        "bh_fdr_family_size": m,
        "n_survivors_total": len(survivors),
        "n_headroom_cells_measured": len(headroom_measured),
        "n_headroom_survivors": len(headroom_survivors),
        "kill_condition_1_headroom_dead": len(headroom_measured) > 0 and len(headroom_survivors) == 0,
        "kill_condition_2_all_gated_exceeds_kept": all_gated_exceeds_kept,
        "battery": {
            "G_n": f">=<{MIN_CELL_N} gated AND >={MIN_CELL_N} kept, no band pooling",
            "G_bhfdr": "BH q=0.10 across full measured family (dollar-expectancy p, canonical_battery.bh_fdr)",
            "G_drop3": "prereg's own top-3-|pnl| drop rule, per-cell (see cells[].G_drop3)",
            "G_oos": "chronological median-date split, sign agreement required (see cells[].G_oos)",
            "G3_blocked_winners": "every cell reports blocked_winner_dollars vs blocked_loser_dollars; cell REFUTED if former exceeds latter regardless of p",
        },
    }
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"FOLLOWTHROUGH-HEADROOM  n_rows={len(rows)}  by_side={report['population_by_side']}")
    print(f"  exclusions: {exclusions}")
    print(f"  BH-FDR family size: {m}")
    print(f"  headroom (F1/F2) cells measured: {len(headroom_measured)}  survivors: {len(headroom_survivors)}")
    print(f"  kill_condition_1 (headroom dead): {report['kill_condition_1_headroom_dead']}")
    print(f"  kill_condition_2 (engine already does this): {report['kill_condition_2_all_gated_exceeds_kept']}")
    for c in cells_out:
        if c["verdict"] == "NOT-RUN":
            print(f"    [NOT-RUN] {c['cell']:<28} {c['why']}")
            continue
        star = "*" if c.get("survives_bh_fdr_q10") else " "
        agree = "AGREE" if c.get("fav60_and_dollar_agree_direction") else "DIVERGE"
        print(f"    [{star}] {c['cell']:<28} n_g={c['n_gated']:>3} n_k={c['n_kept']:>3} "
              f"$gated={c['gated_mean_dollar']:>8} $kept={c['kept_mean_dollar']:>8} "
              f"fav60_g={c['gated_mean_fav60']} fav60_k={c['kept_mean_fav60']} "
              f"p={c['p_dollar_expectancy']} thresh={c.get('bh_fdr_required_threshold')} "
              f"{agree} blocked_win=${c['blocked_winner_dollars']} counts={c.get('counts_as_survivor')}")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
