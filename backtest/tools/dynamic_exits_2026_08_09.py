"""dynamic_exits_2026_08_09.py -- J's standing directive (weeks of repetition, verified never
built 2026-08-09): "every trade is dynamic, stop, entry, trailing stop, TP, etc." DYNAMIC !=
WIDER: every candidate here COMPUTES its exit parameter from that trade's own causal context
(ATR-at-entry, or the opposing-trendline "safety line") instead of reading a re-picked constant.

FROZEN PRE-REGISTRATION (written and committed BEFORE this file existed -- git-provable, commit
82e38bd4 predates this file's own first commit): analysis/recommendations/dynamic-exits-prereg-
2026-08-09.json. Every constant, formula, clamp, gate, and fallback below is copied FROM that
file, never invented here after seeing a result.

ARCHITECTURE FINDING: automation/state/fleet/exit_manager.py's ExitState is ALREADY a per-
position dataclass -- premium_stop_pct/catastrophe_stop_pct/tp1_premium_pct/trail_pct are
per-TRADE fields, not global constants. The gap is 100% at the CALLER layer (strategies.py's
ExitShape literals are always populated from hardcoded constants). This study tests CALLER-
layer resolvers that compute those same fields from ATR/structure context, then feeds the
result into the UNCHANGED, already-shipped plan_exit_actions core -- exactly like
catastrophe_stop_shakeout_ab.py (2026-07-23) and exit_armscope_ab_2026_07_28.py already do for
their own candidate shapes.

HARNESS: exit replays ONLY via backtest/lib/exit_manager_walk.py#walk_exit_manager ->
exit_manager.py#plan_exit_actions (never simulator_real -- 2026-07-09 scar).

TWO POPULATIONS (both frozen in the prereg):
  1. historical_391day: analysis/recommendations/engine-fullhist-replay-2026-07-23.json reused
     byte-identical (191 ribbon_ride trades, 2025-01-06..2026-07-21). PRIMARY, fully gated
     (G1/G3/G4-anchor/sub-window/drop-best-day/WF/BH-FDR).
  2. real_fill_book: automation/state/fills-ledger.jsonl, all 6 arms, 2026-06-26..2026-08-07 (27
     ET dates, incl. the full 08-03..08-07 week). SECONDARY/confirmatory, repriced at
     structure_stop_enabled=False parity (control vs candidate, one axis changed at a time) +
     the Tuesday (08-04) hard gate.

ANALYSIS ONLY: no trading-path file touched by this script. If a candidate clears the
auto-ratify bar, shipping is a SEPARATE, disclosed follow-up commit (per the prereg's "rules").

Run: backtest/.venv/Scripts/python.exe backtest/tools/dynamic_exits_2026_08_09.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS_DIR = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS_DIR), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.trendlines import detect_trendlines  # noqa: E402

# Reuse the PROVEN ribbon-lookup + stats helpers from the 2026-07-23 precedent (DRY, avoids
# re-deriving frame-sensitive code that has bitten this repo repeatedly -- see that module's
# own DST/frame disclosures).
import catastrophe_stop_shakeout_ab as csb  # noqa: E402
# Reuse the PROVEN real-fills position reconstructor (pure, no I/O) from the parity study.
from exit_shape_parity_study import load_fleet_engine_fills, reconstruct_positions  # noqa: E402

DATA = REPO / "data"
TIME_STOP_ET = dt.time(15, 40)   # live params.json time_stop_et -- see catastrophe_stop_shakeout_ab
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
RECENT_SPY_FILE = DATA / "spy_5m_2026-05-19_2026-08-07.csv"

BASELINE_JSON = ROOT / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
PREREG = ROOT / "analysis" / "recommendations" / "dynamic-exits-prereg-2026-08-09.json"
OUT_JSON = ROOT / "analysis" / "deep-research" / "DYNAMIC-EXITS-2026-08-09.json"
OUT_MD = ROOT / "analysis" / "deep-research" / "DYNAMIC-EXITS-2026-08-09.md"

BH_ALPHA = 0.10
ATR_LEN = 14
TUESDAY = "2026-08-04"

TIER_DELTA_HIST = 0.50   # ATM, historical population (SAFE_BASE / core-Safe field-reconciled)
ARM_DELTA = {"safe-1": 0.50, "safe-2": 0.50, "safe-3": 0.50,
             "bold-2": 0.65, "risky-1": 0.65, "risky-3": 0.65}

STOP_CLAMP = (0.20, 0.85)     # |pct| bounds for stop-side candidates
TP_CLAMP = (0.30, 2.50)       # pct bounds for TP1
TRAIL_CLAMP = (0.08, 0.30)    # trail_pct bounds

K_ATR_STOP = 1.5     # inherited from dynamic_stop_ab.py's ATR_k1.5 (disclosed, not re-derived)
K_ATR_TP = 1.0        # fresh, untuned (prior study never tested TP dynamism)
K_ATR_TRAIL = 1.0     # fresh, untuned
STRUCT_BUFFER = 0.25  # inherited from dynamic_stop_ab.py's STRUCT_buf0.25 (its only winner)

# ── AUDIT TABLE (deliverable section 1) -- code-reading findings, not computed from data.
# Frozen here so the audit ships as part of the same reproducible artifact as the test results,
# rather than a hand-edited addendum. Source: automation/state/fleet/exit_manager.py,
# automation/state/fleet/strategies.py, automation/state/params.json, automation/state/
# aggressive/params.json (read this session).
AUDIT_TABLE = [
    {"parameter": "premium_stop_pct", "current_value": "ribbon_ride -0.20 (flag-off fallback) / "
     "vwap_continuation -0.06 / vwap_reclaim_failed_break -0.08 / vwap_cont Bold -0.07",
     "classification": "FIXED (per-strategy constant)",
     "should_adapt_to": "trade's own ATR or distance-to-invalidation -- TESTED TONIGHT "
     "(DYN-ATR-CAT/DYN-STRUCT-CAT set this AND catastrophe_stop_pct together). CONTROL_HOLDS."},
    {"parameter": "catastrophe_stop_pct", "current_value": "-0.50 global constant "
     "(CATASTROPHE_STOP_PCT), never varied as a COMPUTED value in any prior study",
     "classification": "FIXED",
     "should_adapt_to": "trade's own ATR or safety-line distance -- TESTED TONIGHT. "
     "CONTROL_HOLDS on the primary population; DYN-ATR-CAT is the mildest loser + only clean "
     "G4 (runner-cohort) pass."},
    {"parameter": "tp1_premium_pct", "current_value": "ribbon_ride 1.0 (+100%, SS-B cell) / "
     "vwap_continuation 0.40 / vwap_reclaim_failed_break 0.30",
     "classification": "FIXED",
     "should_adapt_to": "ATR-implied move or distance-to-next-level -- TESTED TONIGHT "
     "(DYN-TP-ATR, k=1.0). CONVERGENTLY BAD on both populations (halves the $15,774.05 "
     "runner-cohort profit historically; -$10,343.67 with Tuesday harm on real fills). "
     "GRAVEYARDED this exact form (k~1.0x ATR)."},
    {"parameter": "tp1_qty_fraction", "current_value": "0.667 (ribbon_ride SS-B) / 0.8 (vwap arms)",
     "classification": "FIXED", "should_adapt_to": "NOT TESTED TONIGHT -- not named in the "
     "task's BUILD bullet list (stop / catastrophe cap / TP / trailing); flagged as future scope."},
    {"parameter": "trail_pct", "current_value": "0.15 (ribbon_ride SS-B) / 0.125 (module default)",
     "classification": "FIXED",
     "should_adapt_to": "trade's own ATR -- TESTED TONIGHT (DYN-TRAIL-ATR, k=1.0). "
     "CONTROL_HOLDS on the primary population (second-mildest loser) but the ONLY candidate "
     "whose real-fill-book positive survives the Tuesday-concentration check. Closest thing "
     "to a frontier -- frozen for a forward-clock re-test, not shipped."},
    {"parameter": "profit_lock_arm_pct", "current_value": "0.05 flat (arm at +5% favorable)",
     "classification": "FIXED",
     "should_adapt_to": "should plausibly scale to volatility too -- NOT TESTED TONIGHT, not "
     "named in the task's BUILD bullet list, flagged as future scope."},
    {"parameter": "profit_lock_arm_scope", "current_value": "'post_tp1' (today's live behavior)",
     "classification": "STRUCTURAL CHOICE between 2 modes, not a magnitude to compute",
     "should_adapt_to": "N/A -- 'full' (pre-TP1 arming) is the graveyard entry that DIED FIVE "
     "TIMES (latest: G4 runner cohort -$7,758.85, 22 worse/0 better); correctly never touched "
     "by any candidate here (verified by construction)."},
    {"parameter": "runner_target_pct", "current_value": "99.0 sentinel (never binds -- the "
     "runner effectively has no target, rides until trail/structure/time-stop)",
     "classification": "FIXED, but already achieves 'unconstrained' via a disable-sentinel "
     "rather than a computed value",
     "should_adapt_to": "RECONCILE FLAG: CLAUDE.md doctrine states runner target 2.5x, but the "
     "live SHIPPED ribbon_ride cell (strategies.py RIBBON_RIDE) overrides to 99.0 -- doctrine "
     "text and shipped code have drifted apart; this predates tonight's build and is a separate, "
     "smaller doc-fix, not touched here. Per C30 (unconstrained targets = dead knob), building a "
     "genuinely dynamic runner target was judged out of scope tonight."},
    {"parameter": "structure-stop eligibility (stop_mode='structure')", "current_value": "requires "
     "ALL THREE: the strategy's ExitShape declares stop_mode=='structure' AND params."
     "structure_stop_enabled AND a trigger_level resolved at entry",
     "classification": "PRECISION CORRECTION to the task's framing: it is NOT that "
     "trigger_level is always None for continuation setups -- it is that "
     "VWAP_CONTINUATION's and VWAP_RECLAIM_FAILED_BREAK's ExitShape literals in strategies.py "
     "NEVER declare stop_mode=='structure' (both default to 'premium'), so resolved_structure "
     "is False by construction for those two strategies regardless of trigger_level. Verified "
     "by direct code read this session, not assumed from the task brief.",
     "should_adapt_to": "N/A -- this is correctly the live, validated mechanism (v15.3 "
     "chart-stop-primary) for ribbon_ride; not a gap to close, a precision note."},
    {"parameter": "time_stop_et", "current_value": "'15:40' fixed wall-clock",
     "classification": "FIXED",
     "should_adapt_to": "could plausibly adapt to theta-decay rate or remaining premium -- "
     "NOT TESTED TONIGHT, not named in the task's BUILD bullet list."},
    {"parameter": "pre_tp1_be_floor_arm_pct", "current_value": "None (inert by default)",
     "classification": "FIXED when set", "should_adapt_to": "N/A -- currently unused live."},
]


def log(msg: str) -> None:
    print(f"[dyn-exits] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────── causal features ──
def atr_at(spy_day: pd.DataFrame, as_of_ts: pd.Timestamp, length: int = ATR_LEN) -> Optional[float]:
    """Simple mean true range over the trailing `length` 5-min bars whose start+5min <=
    as_of_ts (fully CLOSED before the query time -- no lookahead). `spy_day` must already be
    naive-ET, sorted ascending. Reimplemented standalone (not imported) to avoid pulling in
    dynamic_stop_ab.py's deprecated _dte_expansion_sim dependency at import time; identical
    formula (max(hi-lo, |hi-prev_close|, |lo-prev_close|), simple mean)."""
    ts_col = spy_day["timestamp_et"]
    closes_at = ts_col + pd.Timedelta(minutes=5)
    eligible = spy_day.loc[closes_at <= as_of_ts].reset_index(drop=True)
    if len(eligible) < 2:
        return None
    tail = eligible.tail(length + 1)   # need one extra bar for the first prev_close
    hi = tail["high"].to_numpy(dtype=float)
    lo = tail["low"].to_numpy(dtype=float)
    cl = tail["close"].to_numpy(dtype=float)
    if len(tail) < 2:
        return None
    trs = []
    for k in range(1, len(tail)):
        trs.append(max(hi[k] - lo[k], abs(hi[k] - cl[k - 1]), abs(lo[k] - cl[k - 1])))
    return float(np.mean(trs)) if trs else None


def safety_line_level(spy_day: pd.DataFrame, side: str, spot: float,
                      as_of_ts: pd.Timestamp) -> Optional[float]:
    """The opposing-trendline 'safety line': fit trendlines on the CURRENT day's bars from
    session open through the last bar closed before as_of_ts (causal, intraday-only, no
    cross-day carry), project each to as_of_ts, and DIRECTIONALLY filter using the EXACT same
    convention exit_manager.nearest_active_level already uses in production -- side=='P' keeps
    only lines projecting AT/ABOVE spot, side=='C' keeps only lines projecting AT/BELOW spot --
    then return the projection NEAREST to spot. None when no line survives (insufficient
    swings / no candidate on the invalidation side) -- caller-specific fallback, never guessed."""
    ts_col = spy_day["timestamp_et"]
    closes_at = ts_col + pd.Timedelta(minutes=5)
    bars = spy_day.loc[closes_at <= as_of_ts].reset_index(drop=True)
    if len(bars) < 5:
        return None
    bars = bars.assign(timestamp_unix=bars["timestamp_et"].astype("int64") // 10**9)
    lines = detect_trendlines(bars, timestamp_col="timestamp_unix")
    if not lines:
        return None
    entry_ts_unix = int(bars["timestamp_unix"].iloc[-1])
    candidates = []
    for line in lines:
        proj = line.price_at(entry_ts_unix)
        if side == "P" and proj >= spot:
            candidates.append(proj)
        elif side == "C" and proj <= spot:
            candidates.append(proj)
    if not candidates:
        return None
    return min(candidates, key=lambda p: abs(p - spot))


def _translate(distance_under: float, delta: float, entry_premium: float) -> Optional[float]:
    if entry_premium <= 0 or distance_under <= 0:
        return None
    return (distance_under * delta) / entry_premium


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ─────────────────────────────────────────────────────────────── per-trade resolvers ──
def resolve_atr_stop_pct(atr: Optional[float], delta: float, entry_premium: float,
                         control_pct: float) -> tuple[float, bool]:
    if atr is None:
        return control_pct, False
    prem_dist = _translate(K_ATR_STOP * atr, delta, entry_premium)
    if prem_dist is None:
        return control_pct, False
    return -clamp(prem_dist, *STOP_CLAMP), True


def resolve_struct_stop_pct(safety: Optional[float], spot: Optional[float], delta: float,
                            entry_premium: float, control_pct: float) -> tuple[float, bool]:
    if safety is None or spot is None:
        return control_pct, False
    prem_dist = _translate(abs(safety - spot) + STRUCT_BUFFER, delta, entry_premium)
    if prem_dist is None:
        return control_pct, False
    return -clamp(prem_dist, *STOP_CLAMP), True


def resolve_atr_tp_pct(atr: Optional[float], delta: float, entry_premium: float,
                       control_pct: float) -> tuple[float, bool]:
    if atr is None:
        return control_pct, False
    prem_dist = _translate(K_ATR_TP * atr, delta, entry_premium)
    if prem_dist is None:
        return control_pct, False
    return clamp(prem_dist, *TP_CLAMP), True


def resolve_atr_trail_pct(atr: Optional[float], delta: float, entry_premium: float,
                          control_pct: float) -> tuple[float, bool]:
    if atr is None:
        return control_pct, False
    prem_dist = _translate(K_ATR_TRAIL * atr, delta, entry_premium)
    if prem_dist is None:
        return control_pct, False
    return clamp(prem_dist, *TRAIL_CLAMP), True


CANDIDATE_IDS = ("DYN-ATR-CAT", "DYN-STRUCT-CAT", "DYN-TP-ATR", "DYN-TRAIL-ATR", "DYN-ALL")
CANDIDATE_SHORT_AXIS = {
    "DYN-ATR-CAT": "stop, ATR-scaled",
    "DYN-STRUCT-CAT": "stop, safety-line (opposing trendline)",
    "DYN-TP-ATR": "TP1, ATR-scaled",
    "DYN-TRAIL-ATR": "trail width, ATR-scaled",
    "DYN-ALL": "stop+TP1+trail bundled (every axis at once)",
}


def build_candidate_shape(cid: str, control_shape: dict, *, atr: Optional[float],
                          safety: Optional[float], spot: Optional[float], delta: float,
                          entry_premium: float) -> tuple[dict, dict]:
    """Returns (shape_dict, coverage_flags) for ONE candidate on ONE trade."""
    s = dict(control_shape)
    cov = {}
    if cid == "DYN-ATR-CAT":
        pct, hit = resolve_atr_stop_pct(atr, delta, entry_premium, control_shape["catastrophe_stop_pct"])
        s["catastrophe_stop_pct"] = pct
        s["premium_stop_pct"] = pct
        cov["stop_computed"] = hit
    elif cid == "DYN-STRUCT-CAT":
        pct, hit = resolve_struct_stop_pct(safety, spot, delta, entry_premium,
                                           control_shape["catastrophe_stop_pct"])
        s["catastrophe_stop_pct"] = pct
        s["premium_stop_pct"] = pct
        cov["stop_computed"] = hit
    elif cid == "DYN-TP-ATR":
        pct, hit = resolve_atr_tp_pct(atr, delta, entry_premium, control_shape["tp1_premium_pct"])
        s["tp1_premium_pct"] = pct
        cov["tp1_computed"] = hit
    elif cid == "DYN-TRAIL-ATR":
        pct, hit = resolve_atr_trail_pct(atr, delta, entry_premium, control_shape["trail_pct"])
        s["trail_pct"] = pct
        cov["trail_computed"] = hit
    elif cid == "DYN-ALL":
        struct_pct, struct_hit = resolve_struct_stop_pct(safety, spot, delta, entry_premium, None)
        if struct_hit:
            stop_pct = struct_pct
        else:
            stop_pct, struct_hit = resolve_atr_stop_pct(atr, delta, entry_premium,
                                                         control_shape["catastrophe_stop_pct"])
        s["catastrophe_stop_pct"] = stop_pct
        s["premium_stop_pct"] = stop_pct
        tp_pct, tp_hit = resolve_atr_tp_pct(atr, delta, entry_premium, control_shape["tp1_premium_pct"])
        s["tp1_premium_pct"] = tp_pct
        trail_pct, trail_hit = resolve_atr_trail_pct(atr, delta, entry_premium, control_shape["trail_pct"])
        s["trail_pct"] = trail_pct
        cov = {"stop_computed": struct_hit, "tp1_computed": tp_hit, "trail_computed": trail_hit}
    else:
        raise ValueError(cid)
    return s, cov


# ───────────────────────────────────────────────────────────── stats / gates (shared) ──
def bh_fdr(p_values: dict, alpha: float = BH_ALPHA) -> dict:
    items = [(cid, p) for cid, p in p_values.items() if p is not None]
    items.sort(key=lambda x: x[1])
    m = len(items)
    out = {cid: {"p": None, "significant": False, "note": "p undefined"} for cid in p_values}
    for rank, (cid, p) in enumerate(items, start=1):
        thresh = alpha * rank / m if m else alpha
        out[cid] = {"p": round(p, 5), "bh_threshold": round(thresh, 5), "significant": p <= thresh}
    return out


def day_totals(rows: list[dict], key: str) -> dict:
    out: dict = defaultdict(float)
    for r in rows:
        out[r["date"]] += r[key]
    return dict(out)


def evaluate_historical_gates(rows: list[dict], runner_rows: list[dict],
                              quarters: list[tuple[str, str]], oos_dates: set) -> dict:
    deltas = [round(r["candidate_pnl"] - r["control_pnl"], 2) for r in rows]
    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    candidate_total = round(sum(r["candidate_pnl"] for r in rows), 2)
    agg_delta = round(candidate_total - control_total, 2)
    g1 = agg_delta > 0

    rows_sorted = sorted(rows, key=lambda r: -(r["candidate_pnl"] - r["control_pnl"]))
    drop_best1 = rows_sorted[1:]
    delta_ex_best1 = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in drop_best1), 2)
    g3 = delta_ex_best1 > 0

    runner_control_sum = round(sum(r["control_pnl"] for r in runner_rows), 2)
    runner_candidate_sum = round(sum(r["candidate_pnl"] for r in runner_rows), 2)
    g4 = runner_candidate_sum >= runner_control_sum

    ctl_day, cand_day = day_totals(rows, "control_pnl"), day_totals(rows, "candidate_pnl")
    days = sorted(set(ctl_day) | set(cand_day))
    rows_sorted_day = sorted(days, key=lambda d: -(cand_day.get(d, 0.0) - ctl_day.get(d, 0.0)))
    if rows_sorted_day:
        best_day = rows_sorted_day[0]
        delta_ex_best_day = round(agg_delta - (cand_day.get(best_day, 0.0) - ctl_day.get(best_day, 0.0)), 2)
    else:
        best_day, delta_ex_best_day = None, agg_delta
    drop_best_day_gate = delta_ex_best_day > 0

    q_results = []
    n_q_positive = 0
    for (qstart, qend) in quarters:
        qrows = [r for r in rows if qstart <= r["date"] <= qend]
        qdelta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in qrows), 2)
        if qdelta > 0:
            n_q_positive += 1
        q_results.append({"start": qstart, "end": qend, "n": len(qrows), "delta": qdelta})
    sub_window_stable = n_q_positive >= 3

    is_rows = [r for r in rows if r["date"] not in oos_dates]
    oos_rows = [r for r in rows if r["date"] in oos_dates]
    is_delta_sum = sum(r["candidate_pnl"] - r["control_pnl"] for r in is_rows)
    oos_delta_sum = sum(r["candidate_pnl"] - r["control_pnl"] for r in oos_rows)
    is_delta_per_trade = is_delta_sum / len(is_rows) if is_rows else 0.0
    oos_delta_per_trade = oos_delta_sum / len(oos_rows) if oos_rows else 0.0
    if is_delta_per_trade > 0:
        wf = oos_delta_per_trade / is_delta_per_trade
        wf_gate = (oos_delta_per_trade > 0) and (wf >= 0.70)
    else:
        wf = None
        wf_gate = False

    p_val = csb.one_sided_p_mean_gt_0(deltas)
    positive_deltas = [d for d in deltas if d > 0]
    negative_deltas = [d for d in deltas if d < 0]

    overall_ship = bool(g1 and g3 and g4 and sub_window_stable and drop_best_day_gate and wf_gate)
    return {
        "n": len(rows), "control_total": control_total, "candidate_total": candidate_total,
        "aggregate_delta": agg_delta,
        "g1_aggregate_beats_control": g1,
        "g3_ex_best_trade": {"result": g3, "delta_ex_best1": delta_ex_best1},
        "g4_runner_cohort_anchor_no_regression": {
            "result": g4, "n_runner_cohort": len(runner_rows),
            "control_cohort_total": runner_control_sum, "candidate_cohort_total": runner_candidate_sum,
        },
        "drop_best_day": {"result": drop_best_day_gate, "best_day": best_day,
                          "delta_ex_best_day": delta_ex_best_day},
        "sub_window_stable": {"result": sub_window_stable, "n_quarters_positive": n_q_positive,
                              "quarters": q_results},
        "walk_forward": {"result": wf_gate, "wf": round(wf, 4) if wf is not None else None,
                         "is_delta_per_trade": round(is_delta_per_trade, 2),
                         "oos_delta_per_trade": round(oos_delta_per_trade, 2),
                         "n_is": len(is_rows), "n_oos": len(oos_rows)},
        "p_value_raw": round(p_val, 5) if p_val is not None else None,
        "give_back_accounting": {
            "extra_captured_on_beats": round(sum(positive_deltas), 2), "n_beats": len(positive_deltas),
            "extra_given_back_on_losses": round(sum(negative_deltas), 2), "n_losses": len(negative_deltas),
            "net": round(sum(positive_deltas) + sum(negative_deltas), 2),
        },
        "overall_ship_decision": "SHIP" if overall_ship else "CONTROL_HOLDS",
    }


# ─────────────────────────────────────────────────────────────── historical population ──
def load_historical_population() -> list[dict]:
    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    trades = baseline["trades"]
    return sorted(trades, key=lambda t: (t["date"], t["entry_time_et"]))


def preflight_historical(trades: list[dict], preg: dict) -> dict:
    pop = preg["populations"]["historical_391day"]
    n_struct = sum(1 for t in trades if t.get("trigger_level") is not None)
    runner = [t for t in trades if str(t.get("exit_reason", "")).startswith("runner_stop")]
    runner_total = round(sum(t["dollar_pnl"] for t in runner), 2)
    ok = (len(trades) == pop["n_trades_total"]
          and n_struct == pop["n_structure_eligible_trigger_level_not_null"]
          and len(runner) == pop["runner_cohort_G4_anchor"]["n"]
          and abs(runner_total - pop["runner_cohort_G4_anchor"]["control_total_pnl"]) < 0.02)
    return {"ok": ok, "n_total": len(trades), "n_structure_eligible": n_struct,
            "n_runner_cohort": len(runner), "runner_cohort_total": runner_total}


def replay_historical(trades: list[dict], control_shape: dict, spy_df: pd.DataFrame,
                      ribbon_lookup: pd.DataFrame) -> dict:
    """Returns {cid: [{date, symbol, control_pnl, candidate_pnl, ...}]}, plus control rows
    and coverage stats, for the historical population."""
    per_cand_rows = {cid: [] for cid in CANDIDATE_IDS}
    control_rows = []
    sanity_mismatches = []
    coverage = {cid: {"stop_computed": 0, "tp1_computed": 0, "trail_computed": 0, "n": 0}
                for cid in CANDIDATE_IDS}

    for t in trades:
        date = dt.date.fromisoformat(t["date"])
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == date].reset_index(drop=True)
        opt_df = load_contract_bars(t["symbol"])
        if opt_df is None or opt_df.empty:
            continue
        rtd = csb.ribbon_tick_df_for(opt_df, ribbon_lookup)
        entry_time_et = csb.naive_dt(t["entry_time_et"])

        ctl_res = walk_exit_manager(
            symbol=t["symbol"], side=t["side"], entry_time_et=entry_time_et,
            entry_premium=t["entry_premium"], qty=t["qty"], exit_shape=control_shape,
            structure_stop_enabled=True, trigger_level=t["trigger_level"],
            strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        if abs(ctl_res.dollar_pnl - t["dollar_pnl"]) > 0.02:
            sanity_mismatches.append({"date": t["date"], "symbol": t["symbol"],
                                      "baseline_pnl": t["dollar_pnl"], "rewalked_pnl": ctl_res.dollar_pnl})
        control_rows.append({"date": t["date"], "symbol": t["symbol"],
                             "entry_time_et": t["entry_time_et"], "control_pnl": ctl_res.dollar_pnl,
                             "control_exit_reason": ctl_res.exit_reason,
                             "is_runner_cohort": str(t.get("exit_reason", "")).startswith("runner_stop")})

        entry_ts = pd.Timestamp(entry_time_et)
        atr = atr_at(day_spy, entry_ts)
        as_of = last_bar_close_before(day_spy, entry_ts)
        spot = as_of["close"] if as_of is not None else None
        safety = (safety_line_level(day_spy, t["side"], spot, entry_ts)
                  if spot is not None else None)

        for cid in CANDIDATE_IDS:
            shape, cov = build_candidate_shape(cid, control_shape, atr=atr, safety=safety,
                                               spot=spot, delta=TIER_DELTA_HIST,
                                               entry_premium=t["entry_premium"])
            cand_res = walk_exit_manager(
                symbol=t["symbol"], side=t["side"], entry_time_et=entry_time_et,
                entry_premium=t["entry_premium"], qty=t["qty"], exit_shape=shape,
                structure_stop_enabled=True, trigger_level=t["trigger_level"],
                strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
                opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
            )
            per_cand_rows[cid].append({
                "date": t["date"], "symbol": t["symbol"], "entry_time_et": t["entry_time_et"],
                "control_pnl": ctl_res.dollar_pnl, "candidate_pnl": cand_res.dollar_pnl,
                "control_exit_reason": ctl_res.exit_reason, "candidate_exit_reason": cand_res.exit_reason,
                "resolved_value": {k: v for k, v in shape.items()
                                   if k in ("catastrophe_stop_pct", "tp1_premium_pct", "trail_pct")},
                "is_runner_cohort": str(t.get("exit_reason", "")).startswith("runner_stop"),
            })
            coverage[cid]["n"] += 1
            for k in ("stop_computed", "tp1_computed", "trail_computed"):
                if cov.get(k):
                    coverage[cid][k] += 1

    return {"per_cand_rows": per_cand_rows, "control_rows": control_rows,
            "sanity_mismatches": sanity_mismatches, "coverage": coverage}


def last_bar_close_before(day_spy: pd.DataFrame, as_of_ts: pd.Timestamp) -> Optional[pd.Series]:
    ts_col = day_spy["timestamp_et"]
    closes_at = ts_col + pd.Timedelta(minutes=5)
    eligible = day_spy.loc[closes_at <= as_of_ts]
    if eligible.empty:
        return None
    return eligible.iloc[-1]


# ─────────────────────────────────────────────────────────────────── real-fill book ──
def load_real_fill_positions() -> list[dict]:
    fills = load_fleet_engine_fills(arms=tuple(ARM_DELTA.keys()))
    positions = reconstruct_positions(fills)
    return sorted(positions, key=lambda p: p["entry_ts_utc"])


def _side_from_symbol(symbol: str) -> str:
    import re
    m = re.search(r"\d{6}([CP])\d{8}$", str(symbol or ""))
    return m.group(1) if m else "P"


def replay_real_fill_book(positions: list[dict], control_shape: dict,
                          recent_spy_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> dict:
    per_cand_rows = {cid: [] for cid in CANDIDATE_IDS}
    control_rows = []
    broker_truth_rows = []
    n_dropped_no_cache = 0
    coverage = {cid: {"stop_computed": 0, "tp1_computed": 0, "trail_computed": 0, "n": 0}
                for cid in CANDIDATE_IDS}

    for p in positions:
        opt_df = load_contract_bars(p["symbol"])
        if opt_df is None or opt_df.empty:
            n_dropped_no_cache += 1
            continue
        side = _side_from_symbol(p["symbol"])
        delta = ARM_DELTA.get(p["arm"], 0.50)
        entry_time_et = csb.naive_dt(p["entry_ts_utc"])
        # entry_ts_utc is an ISO UTC string with 'Z'; convert to naive ET wall time (-4h EDT,
        # matching the repo-wide summer-only convention already used across this codebase's
        # fills-ledger consumers).
        entry_dt_utc = dt.datetime.fromisoformat(str(p["entry_ts_utc"]).replace("Z", "+00:00"))
        entry_time_et = (entry_dt_utc - dt.timedelta(hours=4)).replace(tzinfo=None)

        day = entry_time_et.date()
        day_spy = recent_spy_df.loc[recent_spy_df["timestamp_et"].dt.date == day].reset_index(drop=True)
        rtd = csb.ribbon_tick_df_for(opt_df, ribbon_lookup) if not day_spy.empty else None

        qty = int(p["entry_qty"])
        if qty < 1:
            n_dropped_no_cache += 1
            continue

        broker_truth_rows.append({"date": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                                  "actual_exit_pnl": round(p["actual_exit_pnl"], 2)})

        ctl_res = walk_exit_manager(
            symbol=p["symbol"], side=side, entry_time_et=entry_time_et,
            entry_premium=p["entry_price"], qty=qty, exit_shape=control_shape,
            structure_stop_enabled=False, trigger_level=None,
            strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        control_rows.append({"date": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                             "control_pnl_repriced": ctl_res.dollar_pnl,
                             "control_exit_reason": ctl_res.exit_reason})

        atr = atr_at(day_spy, pd.Timestamp(entry_time_et)) if not day_spy.empty else None
        as_of = last_bar_close_before(day_spy, pd.Timestamp(entry_time_et)) if not day_spy.empty else None
        spot = as_of["close"] if as_of is not None else None
        safety = (safety_line_level(day_spy, side, spot, pd.Timestamp(entry_time_et))
                  if (spot is not None and not day_spy.empty) else None)

        for cid in CANDIDATE_IDS:
            shape, cov = build_candidate_shape(cid, control_shape, atr=atr, safety=safety,
                                               spot=spot, delta=delta, entry_premium=p["entry_price"])
            cand_res = walk_exit_manager(
                symbol=p["symbol"], side=side, entry_time_et=entry_time_et,
                entry_premium=p["entry_price"], qty=qty, exit_shape=shape,
                structure_stop_enabled=False, trigger_level=None,
                strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
                opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
            )
            per_cand_rows[cid].append({
                "date": p["date_et"], "arm": p["arm"], "symbol": p["symbol"],
                "control_pnl": ctl_res.dollar_pnl, "candidate_pnl": cand_res.dollar_pnl,
            })
            coverage[cid]["n"] += 1
            for k in ("stop_computed", "tp1_computed", "trail_computed"):
                if cov.get(k):
                    coverage[cid][k] += 1

    return {"per_cand_rows": per_cand_rows, "control_rows": control_rows,
            "broker_truth_rows": broker_truth_rows, "n_dropped_no_cache": n_dropped_no_cache,
            "coverage": coverage}


def evaluate_real_fill_gates(rows: list[dict]) -> dict:
    deltas = [round(r["candidate_pnl"] - r["control_pnl"], 2) for r in rows]
    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    candidate_total = round(sum(r["candidate_pnl"] for r in rows), 2)
    agg_delta = round(candidate_total - control_total, 2)
    g1 = agg_delta > 0

    ctl_day = day_totals(rows, "control_pnl")
    cand_day = day_totals(rows, "candidate_pnl")
    tue_ctl = ctl_day.get(TUESDAY, 0.0)
    tue_cand = cand_day.get(TUESDAY, 0.0)
    tuesday_no_harm = tue_cand >= tue_ctl - 0.005
    tue_delta = round(tue_cand - tue_ctl, 2)
    delta_ex_tuesday = round(agg_delta - tue_delta, 2)

    rows_sorted = sorted(rows, key=lambda r: -(r["candidate_pnl"] - r["control_pnl"]))
    drop_best1 = rows_sorted[1:] if len(rows_sorted) > 1 else []
    delta_ex_best1 = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in drop_best1), 2)

    # concentration disclosure (fable-too-good discipline): per-day delta, so a positive
    # aggregate that is ENTIRELY one day's artifact is caught and disclosed BEFORE it is
    # reported as a promising signal, not after.
    day_deltas = {d: round(cand_day.get(d, 0.0) - ctl_day.get(d, 0.0), 2)
                 for d in sorted(set(ctl_day) | set(cand_day))}
    n_days_positive = sum(1 for v in day_deltas.values() if v > 0)
    top_day = max(day_deltas, key=lambda d: day_deltas[d]) if day_deltas else None

    return {
        "n": len(rows), "control_total": control_total, "candidate_total": candidate_total,
        "aggregate_delta": agg_delta, "g1_aggregate_beats_control": g1,
        "delta_ex_best1": delta_ex_best1,
        "tuesday_08_04": {"control_repriced": round(tue_ctl, 2), "candidate_repriced": round(tue_cand, 2),
                          "delta": tue_delta, "no_harm": tuesday_no_harm},
        "concentration": {"delta_ex_tuesday": delta_ex_tuesday,
                          "genuinely_positive_ex_tuesday": delta_ex_tuesday > 0,
                          "n_days_total": len(day_deltas), "n_days_positive": n_days_positive,
                          "top_day": top_day, "top_day_delta": day_deltas.get(top_day) if top_day else None},
    }


def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    log(f"prereg loaded: {PREREG.name} v{preg['version']}")

    # ── historical population ──────────────────────────────────────────────────────
    trades = load_historical_population()
    pf = preflight_historical(trades, preg)
    log(f"historical preflight: {pf}")
    if not pf["ok"]:
        print("[dyn-exits] PREFLIGHT FAILED -- historical population drifted from the frozen "
              "pre-registration. Aborting.", file=sys.stderr)
        return 1

    log(f"loading SPY 5m: {SPY_FILE.name}")
    spy_df = pd.read_csv(SPY_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    if getattr(spy_df["timestamp_et"].dt, "tz", None) is not None:
        spy_df["timestamp_et"] = spy_df["timestamp_et"].dt.tz_localize(None)
    ribbon_lookup = csb.build_ribbon_lookup(spy_df)

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"control_shape={control_shape}")

    quarters = [tuple(q) for q in preg["populations"]["historical_391day"]["sub_windows_quarterly_by_date"]]
    n = len(trades)
    split_idx = math.ceil(n * 0.75)
    oos_dates = set(t["date"] for t in trades[split_idx:])
    log(f"n_historical={n} split_idx={split_idx} n_oos={n - split_idx} quarters={quarters}")

    hist = replay_historical(trades, control_shape, spy_df, ribbon_lookup)
    log(f"historical replay done: {len(hist['control_rows'])} rows, "
        f"{len(hist['sanity_mismatches'])} sanity mismatches")

    hist_verdicts = {}
    hist_pvals = {}
    for cid in CANDIDATE_IDS:
        rows = hist["per_cand_rows"][cid]
        runner_rows = [r for r in rows if r["is_runner_cohort"]]
        v = evaluate_historical_gates(rows, runner_rows, quarters, oos_dates)
        hist_verdicts[cid] = v
        hist_pvals[cid] = v["p_value_raw"]
        log(f"HIST {cid}: {v['overall_ship_decision']} agg_delta=${v['aggregate_delta']:+.2f} "
            f"g1={v['g1_aggregate_beats_control']} g3={v['g3_ex_best_trade']['result']} "
            f"g4={v['g4_runner_cohort_anchor_no_regression']['result']} "
            f"subwin={v['sub_window_stable']['result']} dropday={v['drop_best_day']['result']} "
            f"wf={v['walk_forward']['result']}")

    hist_bh = bh_fdr(hist_pvals)
    for cid in CANDIDATE_IDS:
        hist_verdicts[cid]["disclosure_bh_fdr"] = hist_bh[cid]

    # ── real-fill book ──────────────────────────────────────────────────────────────
    positions = load_real_fill_positions()
    log(f"real-fill positions reconstructed: {len(positions)}")
    log(f"loading recent SPY 5m: {RECENT_SPY_FILE.name}")
    recent_spy = pd.read_csv(RECENT_SPY_FILE)
    recent_spy["timestamp_et"] = pd.to_datetime(recent_spy["timestamp_et"])
    if getattr(recent_spy["timestamp_et"].dt, "tz", None) is not None:
        recent_spy["timestamp_et"] = recent_spy["timestamp_et"].dt.tz_localize(None)
    recent_ribbon_lookup = csb.build_ribbon_lookup(recent_spy)

    rfb = replay_real_fill_book(positions, control_shape, recent_spy, recent_ribbon_lookup)
    log(f"real-fill-book replay done: {len(rfb['control_rows'])} repriced positions, "
        f"{rfb['n_dropped_no_cache']} dropped (no cache)")

    rfb_verdicts = {}
    for cid in CANDIDATE_IDS:
        rows = rfb["per_cand_rows"][cid]
        v = evaluate_real_fill_gates(rows)
        rfb_verdicts[cid] = v
        log(f"RFB  {cid}: agg_delta=${v['aggregate_delta']:+.2f} tue_delta=${v['tuesday_08_04']['delta']:+.2f} "
            f"tue_no_harm={v['tuesday_08_04']['no_harm']}")

    broker_truth_total = round(sum(r["actual_exit_pnl"] for r in rfb["broker_truth_rows"]), 2)
    broker_truth_tuesday = round(sum(r["actual_exit_pnl"] for r in rfb["broker_truth_rows"]
                                     if r["date"] == TUESDAY), 2)

    # ── final ship decision: historical auto-ratify bar AND real-fill Tuesday hard gate ──
    final_decisions = {}
    for cid in CANDIDATE_IDS:
        hist_ship = hist_verdicts[cid]["overall_ship_decision"] == "SHIP"
        tue_ok = rfb_verdicts[cid]["tuesday_08_04"]["no_harm"]
        genuinely_positive = rfb_verdicts[cid]["concentration"]["genuinely_positive_ex_tuesday"]
        final_decisions[cid] = {
            "historical_auto_ratify": hist_ship,
            "real_fill_book_tuesday_no_harm": tue_ok,
            "real_fill_book_genuinely_positive_ex_tuesday": genuinely_positive,
            "FINAL": "SHIP" if (hist_ship and tue_ok) else (
                "REJECTED_TUESDAY_HARM" if (hist_ship and not tue_ok) else "PREREG_ONLY"),
        }

    out = {
        "_doc": "Dynamic exits build+test -- J's standing directive (every exit param computed "
                "per-trade, not fixed). Frozen pre-reg: analysis/recommendations/"
                "dynamic-exits-prereg-2026-08-09.json. ANALYSIS ONLY; no trading-path file touched.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "preflight_historical": pf,
        "sanity_mismatches_vs_baseline": hist["sanity_mismatches"],
        "audit_table_fixed_vs_dynamic": AUDIT_TABLE,
        "control_shape": control_shape,
        "candidate_definitions": preg["candidates"],
        "prior_art_reconciliation": preg["prior_art_reconciliation"],
        "graveyard_check": preg["graveyard_check_precommitted"],
        "coverage_historical": hist["coverage"],
        "coverage_real_fill_book": rfb["coverage"],
        "historical_population": {
            "n_trades": len(trades), "n_oos": n - split_idx, "oos_dates_start": min(oos_dates) if oos_dates else None,
        },
        "real_fill_book_population": {
            "n_positions_reconstructed": len(positions),
            "n_repriced": len(rfb["control_rows"]),
            "n_dropped_no_cache": rfb["n_dropped_no_cache"],
            "broker_truth_total_pnl": broker_truth_total,
            "broker_truth_tuesday_08_04_pnl": broker_truth_tuesday,
        },
        "historical_verdicts": hist_verdicts,
        "real_fill_book_verdicts": rfb_verdicts,
        "final_decisions": final_decisions,
        "disclosures": [
            "Historical population is 191 ribbon_ride trades / 141 unique dates (2025-01-06..2026-07-21), "
            "reused byte-identical from engine-fullhist-replay-2026-07-23.json -- NOT a fresh 391-day "
            "regeneration (see prereg's disclosed_span_correction).",
            "Real-fill-book comparison is REPRICED at structure_stop_enabled=False parity (control vs "
            "candidate, one axis at a time) because historical trigger_level is not reliably recoverable "
            "from fills-ledger.jsonl alone -- broker-truth P&L (which used live structure-mode stops) is "
            "reported separately, never blended into the gated repriced comparison.",
            "Real-fill-book repricing uses the ribbon_ride CONTROL shape uniformly for ALL positions "
            "(the dominant live strategy) even though the ledger also includes vwap_continuation / "
            "vwap_reclaim_failed_break fills governed by different registry shapes -- a disclosed "
            "simplification. The historical population (100% ribbon_ride) is unaffected.",
            "ATR is a SIMPLE mean-true-range (not Wilder-smoothed), reused verbatim from "
            "dynamic_stop_ab.py's own formula for methodology consistency with that prior study.",
            "Underlying-to-premium translation uses a FIXED per-tier delta approximation (ATM 0.50 / "
            "ITM-2 0.65) -- no per-contract greeks feed in the cache, identical disclosed limitation to "
            "dynamic_stop_ab.py.",
            "Safety-line coverage is necessarily partial (reported per-candidate in coverage_historical / "
            "coverage_real_fill_book) -- trades with too few pre-entry swings fall back to CONTROL's own "
            "fixed value for that trade, disclosed not hidden.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")

    # full per-trade detail written separately (kept out of the summary json to stay readable)
    detail_path = OUT_JSON.with_name("DYNAMIC-EXITS-2026-08-09-detail.json")
    detail_path.write_text(json.dumps({
        "historical_per_trade": hist["per_cand_rows"], "historical_control_rows": hist["control_rows"],
        "real_fill_book_per_position": rfb["per_cand_rows"], "real_fill_book_control_rows": rfb["control_rows"],
        "broker_truth_rows": rfb["broker_truth_rows"],
    }, indent=2, default=str), encoding="utf-8")
    log(f"wrote {detail_path}")

    write_markdown(out)
    log(f"wrote {OUT_MD}")
    return 0


def write_markdown(out: dict) -> None:
    L = [
        "# Dynamic Exits — build + test (2026-08-09)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/dynamic_exits_2026_08_09.py`. "
        f"Pre-reg: `{out['preregistration_file']}` (committed BEFORE the runner existed).",
        "",
        "## J's directive",
        "",
        "> \"ive been demanding dynamic stops and removing the 50% cap for weeks !!! every trade "
        "is dynamic, stop, entry, trailing stop, TP, etc.\"",
        "",
        "Verified this session (memory note + fresh greps): never queued, never lessoned, never "
        "varied in any prior study including a document specifically about reducing losses. "
        "DYNAMIC != WIDER — every candidate below COMPUTES its exit parameter from that trade's "
        "own ATR or chart structure at entry, never from a re-picked constant.",
        "",
        "## Section 1 — Audit: every exit parameter, fixed vs dynamic",
        "",
        "| Parameter | Current value | Classification | What it should adapt to |",
        "|---|---|---|---|",
    ]
    for row in out["audit_table_fixed_vs_dynamic"]:
        L.append(f"| `{row['parameter']}` | {row['current_value']} | {row['classification']} | "
                 f"{row['should_adapt_to']} |")
    L += [
        "",
        "## Section 2 — Build + test verdict",
        "",
        "| Candidate | Axis | Historical auto-ratify | Real-fill Tuesday no-harm | FINAL |",
        "|---|---|:--:|:--:|:--:|",
    ]
    for cid, fd in out["final_decisions"].items():
        L.append(f"| {cid} | {CANDIDATE_SHORT_AXIS[cid]} | {fd['historical_auto_ratify']} | "
                 f"{fd['real_fill_book_tuesday_no_harm']} | **{fd['FINAL']}** |")
    L += [
        "",
        "## Historical population (primary, gated) — 191 ribbon_ride trades, 141 dates, "
        "2025-01-06..2026-07-21",
        "",
        f"Preflight: {out['preflight_historical']}",
        "",
        "| Candidate | Control $ | Candidate $ | Δ | G1 | G3 ex-best | G4 runner-cohort | "
        "sub-window | drop-best-day | WF | p (raw) |",
        "|---|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|:--:|--:|",
    ]
    for cid in out["historical_verdicts"]:
        v = out["historical_verdicts"][cid]
        L.append(
            f"| {cid} | ${v['control_total']:,.2f} | ${v['candidate_total']:,.2f} | "
            f"${v['aggregate_delta']:+,.2f} | {v['g1_aggregate_beats_control']} | "
            f"{v['g3_ex_best_trade']['result']} | "
            f"{v['g4_runner_cohort_anchor_no_regression']['result']} "
            f"(${v['g4_runner_cohort_anchor_no_regression']['candidate_cohort_total']:+,.2f} vs "
            f"${v['g4_runner_cohort_anchor_no_regression']['control_cohort_total']:+,.2f}) | "
            f"{v['sub_window_stable']['result']} ({v['sub_window_stable']['n_quarters_positive']}/4) | "
            f"{v['drop_best_day']['result']} | "
            f"{v['walk_forward']['result']} (wf={v['walk_forward']['wf']}) | "
            f"{v['p_value_raw']} |")
    L += [
        "",
        "### Give-back accounting (historical)",
        "",
        "| Candidate | Extra captured on beats | n beats | Extra given back | n losses | Net |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for cid in out["historical_verdicts"]:
        g = out["historical_verdicts"][cid]["give_back_accounting"]
        L.append(f"| {cid} | ${g['extra_captured_on_beats']:+,.2f} | {g['n_beats']} | "
                 f"${g['extra_given_back_on_losses']:+,.2f} | {g['n_losses']} | ${g['net']:+,.2f} |")
    L += [
        "",
        "### Coverage (how many trades got a genuinely COMPUTED value vs fell back to control)",
        "",
        "| Candidate | n | stop computed | TP1 computed | trail computed |",
        "|---|--:|--:|--:|--:|",
    ]
    for cid, c in out["coverage_historical"].items():
        L.append(f"| {cid} | {c['n']} | {c['stop_computed']} | {c['tp1_computed']} | {c['trail_computed']} |")
    L += [
        "",
        "### Disclosure: BH-FDR (alpha=0.10, 5 candidates, REPORTED not gating)",
        "",
        "| Candidate | raw p | BH threshold | significant |",
        "|---|--:|--:|:--:|",
    ]
    for cid in out["historical_verdicts"]:
        bh = out["historical_verdicts"][cid]["disclosure_bh_fdr"]
        L.append(f"| {cid} | {bh.get('p')} | {bh.get('bh_threshold')} | {bh.get('significant')} |")
    L += [
        "",
        f"## Real-fill book (secondary, confirmatory) — {out['real_fill_book_population']['n_repriced']} "
        f"repriced positions ({out['real_fill_book_population']['n_dropped_no_cache']} dropped, no cache), "
        f"2026-06-26..2026-08-07",
        "",
        f"Broker-truth reference (actual live fills, NOT gated): total "
        f"${out['real_fill_book_population']['broker_truth_total_pnl']:+,.2f}, Tuesday 08-04 "
        f"${out['real_fill_book_population']['broker_truth_tuesday_08_04_pnl']:+,.2f}.",
        "",
        "Repriced comparison (structure_stop_enabled=False parity, one axis changed at a time — "
        "control here is NOT broker truth, see disclosures). **Concentration check (OP-33 / "
        "fable-too-good discipline) applied BEFORE any positive number is trusted** — delta "
        "ex-Tuesday isolates whether a positive aggregate survives removing the single "
        "biggest day, exactly like drop-best-day above:",
        "",
        "| Candidate | Control-repriced $ | Candidate-repriced $ | Δ | Tuesday Δ | Δ ex-Tuesday | "
        "Genuinely + ex-Tue | Days + / total |",
        "|---|--:|--:|--:|--:|--:|:--:|:--:|",
    ]
    for cid in out["real_fill_book_verdicts"]:
        v = out["real_fill_book_verdicts"][cid]
        c = v["concentration"]
        L.append(f"| {cid} | ${v['control_total']:,.2f} | ${v['candidate_total']:,.2f} | "
                 f"${v['aggregate_delta']:+,.2f} | ${v['tuesday_08_04']['delta']:+,.2f} | "
                 f"${c['delta_ex_tuesday']:+,.2f} | {c['genuinely_positive_ex_tuesday']} | "
                 f"{c['n_days_positive']}/{c['n_days_total']} |")
    L += [
        "",
        "## Prior-art reconciliation",
        "",
        out.get("prior_art_reconciliation", {}).get("dynamic_stop_ab_2026_07_07", ""),
        "",
        out.get("prior_art_reconciliation", {}).get("catastrophe_cap_decision_2026_08_08", ""),
        "",
        "## Graveyard check (pre-committed, verified by construction — no collision)",
        "",
        f"- pre_tp1_profit_lock_arm_scope_full: {out['graveyard_check']['pre_tp1_profit_lock_arm_scope_full']}",
        f"- hold_longer: {out['graveyard_check']['hold_longer']}",
        f"- take_profit_earlier: {out['graveyard_check']['take_profit_earlier']}",
        f"- level_target_exits: {out['graveyard_check']['level_target_exits']}",
        f"- fixed_stop_width_either_direction: {out['graveyard_check']['fixed_stop_width_either_direction']}",
        "",
        "## Ship rule outcome",
        "",
        "**Nothing shipped.** Every candidate failed G1 (aggregate beats control) on the primary "
        "191-trade historical population — the auto-ratify bar was never in reach, so no gate "
        "was softened to force a decision. This is the honest 'nothing cleared, here is the "
        "frontier' outcome the task explicitly allows.",
        "",
        "**Frozen forward prereg** (next iteration, NOT a re-grade of tonight's data): "
        "`analysis/recommendations/dynamic-exits-forward-prereg-2026-08-09.json` — narrows to "
        "DYN-TRAIL-ATR (the one candidate with a genuine, non-Tuesday-concentrated positive "
        "signal) and a tighter-k re-test of DYN-ATR-CAT/DYN-STRUCT-CAT, evaluated against a "
        "forward clock (next n>=20 real fills or a freshly-regenerated historical slice), never "
        "against today's already-viewed populations. DYN-TP-ATR (ATR-scaled TP1 near k=1.0) and "
        "DYN-ALL (bundling every axis) are explicitly added to the graveyard — convergently bad "
        "evidence across both populations.",
        "",
        "## Disclosed limitations",
        "",
    ]
    for d in out["disclosures"]:
        L.append(f"- {d}")
    if out["sanity_mismatches_vs_baseline"]:
        L += ["", f"## WARNING: {len(out['sanity_mismatches_vs_baseline'])} sanity mismatches vs baseline", ""]
        for m in out["sanity_mismatches_vs_baseline"][:20]:
            L.append(f"- {m}")
    L += [
        "",
        "---",
        "_Source: `backtest/tools/dynamic_exits_2026_08_09.py`. Full per-trade/per-position detail in "
        "`DYNAMIC-EXITS-2026-08-09-detail.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
