"""trail_width_exit_ab.py -- TRAIL-WIDTH / TP1-SIZE exit knob A/B on the REAL-FILLS
population (DOJO-HARVEST-2026-07-21.md LANE-B HYPOTHESIS #3, "the live chandelier trail
is too tight and/or TP1 takes too much size too early").

Runs the FROZEN pre-registration (analysis/recommendations/trail-width-exit-prereg-
2026-07-21.json) -- no re-picks after seeing results (preflight hash-checked below).

RECONCILIATION (read before touching this file): analysis/recommendations/structure-
stop-reference-level-2026-07-20.json already returned NO-SHIP (REJECT_ALL_CANDIDATES,
FAIL on layer(a)) for widening the structure-stop's REFERENCE LEVEL (trigger-exact vs
zone-boundary vs none -- WHERE the chart-stop is anchored). This study is a DIFFERENT
knob: TRAIL WIDTH (the chandelier's trailing-stop distance off the high-water-mark once
profit-lock is armed) and TP1 SIZE (what fraction of the position sells at the first
partial). Neither candidate here touches the structure-stop reference; every candidate
still uses trigger-exact recovery (byte-identical to that study's REF-EXACT/CONTROL),
so this study does not silently re-open the already-killed axis.

ALSO ON THE RECORD (context, not this study's population): exit-variant-ab-wider-
trail25-2026-07-17.json already tested trail_pct=0.25 vs control=0.15 on a much larger
SYNTHETIC population (n=188 detector-fired ribbon_ride trades, IS 2025 + OOS 2026-YTD via
lib.orchestrator.run_backtest) and found it LOSES -$813.30 aggregate, FAILs every
regime-conditioned gate. That population is entry-detector-driven backtest trades, not
real fills -- cited here as prior evidence to reconcile against, not reused as this
study's population. THIS study replays the REAL-FILLS anchor per the task's explicit
instruction (metric = per-episode real-fill P&L via backtest/lib/exit_manager_walk.py).

POPULATION: every engine-attributed, non-crypto, option position reconstructed from
automation/state/fills-ledger.jsonl across ALL_LIVE_ARMS = FLEET_REST_ARMS (safe-1,
safe-3, risky-1, risky-3) + CORE_ARMS (safe-2, bold-2) -- the CORE arms are where ALL
real trading has happened since fleet_rest went dark 2026-07-09 (exit_shape_parity_
study.py's own 2026-07-21 docstring note sanctions this as the correct explicit,
NEW-study opt-in: `load_fleet_engine_fills(arms=ALL_LIVE_ARMS)`, never a silent default
change to an already-verdicted study). Restricted to positions with BOTH (a) a cached
real-OPRA 1-min-native 5-min bar CSV in backtest/data/options/{symbol}.csv (populated by
tools/fetch_option_data.py -- no network calls, no broker imports) and (b) SPY 5-min bar
coverage for that date (backtest/data/spy_5m_2026-05-19_2026-07-21.csv).

CONVENTION CARRIED FROM PRECEDENT (structure_stop_study.py / structure_stop_reference_
level_ab.py): the shared candidate exit shape is applied UNIFORMLY to every real-fills
option position in the anchor population, regardless of which strategy (ribbon_ride vs
vwap_continuation) actually fired live -- fills-ledger.jsonl carries no strategy/setup
tag, so this is the SAME real-fills anchor convention both frozen structure-stop studies
already used and that this task's reconciliation item points at. Disclosed, not hidden.

TRIGGER-LEVEL RECOVERY: identical backward-scan heuristic to structure_stop_study.py's
`recover_trigger_level_real_position` (detect_level_reclaim/detect_level_rejection
against the day's frozen LevelSet.active, lookback=8 bars / ~40min, closest-to-entry
first). A position with no recoverable trigger_level gets trigger_level=None passed to
every candidate identically -- ExitState.from_entry then resolves stop_mode="premium"
(the SAME degradation for control and every candidate), never a fabricated level.

METRIC: backtest/lib/exit_manager_walk.py `walk_exit_manager` -- the REAL exit_manager.
plan_exit_actions decision core (not a parallel reimplementation), ticked over the
cached 5-min option bars with `last_closed_5m_close` fed from the real SPY 5-min series
so structure_stop can actually fire. ribbon_flip_back is OFF (no historical ribbon-state
reconstruction available for arbitrary past dates -- same disclosed limitation every
prior real-fills study in this codebase carries).

CANDIDATE GRID -- chosen by a STATED RULE, never hand-picked to fit (see prereg file):
  Axis 1 (trail width ALONE, tp1_qty_fraction held at control 0.667):
    TRAIL-20 / TRAIL-25 / TRAIL-30 = trail_pct in {0.20, 0.25, 0.30} -- +0.05 steps from
    control (0.15) up to the dojo-evidence value (0.30), the same step-size and same cap
    the codebase's OWN exit_variant_ab.py precedent (trail_pct=0.25) already used once.
  Axis 2 (TP1 size ALONE, trail_pct held at control 0.15):
    TP1Q-050 / TP1Q-033 = tp1_qty_fraction in {0.5, 0.333} -- the two smaller fractions
    reachable under Rule 6's min-3-contracts floor (2-of-3 sold today -> 1-of-2 -> 1-of-3),
    i.e. selling fewer contracts at TP1 so more of the position can ride.
  Axis 3 (bundle, justified): RIDE-BUNDLE replays the EXACT dojo-sim cell verbatim --
    trail_pct=0.30, tp1_premium_pct=0.50, tp1_qty_fraction=0.5 -- since that IS the cell
    the hypothesis originated from; testing it directly on real fills is the most direct
    confirm/falsify available.

SHIP GATE (task's explicit 4 conditions, ALL required):
  1. aggregate:      sum(candidate_pnl) > sum(control_pnl) over the full population
  2. majority_days:  #days where day_candidate_total > day_control_total exceeds
                      #days where control >= candidate (ties count for neither side)
  3. drop_best_1:    remove the SINGLE position with the largest positive
                      (candidate-control) delta; remaining aggregate delta still > 0
  4. oos_holds:      population split at the stated midpoint date (median position-count,
                      same convention as structure-stop-reference-level-2026-07-20.json);
                      second-half (OOS) delta > 0, no sign flip vs first-half (IS)
Plus DISCLOSURE (not gating alone): one-sided BH-FDR test (alpha=0.10) on per-episode
paired deltas, and a drop-top-3 concentration check (precedent's stricter cousin of #3).

HONESTY (task requirement): every candidate reports GIVE-BACK ACCOUNTING -- the sum of
POSITIVE per-episode deltas (extra captured where the candidate beat control) separately
from the sum of NEGATIVE per-episode deltas (extra given back where the candidate lost
MORE than control, e.g. a wider trail riding a reversal further before it stops out).
"CONTROL holds" is reported as a valid, undecorated verdict when gates fail.

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches strategies.py,
params.json, exit_manager.py, or any trading-path file. No broker imports, no network
calls -- every input is a local cached CSV/JSONL already on disk.

Run: backtest/.venv/Scripts/python.exe backtest/tools/trail_width_exit_ab.py
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

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "tools"), str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.option_pricing_real import load_contract_bars  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.filters import detect_level_reclaim, detect_level_rejection  # noqa: E402
import tw8_level_context as lc  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from exit_manager import TIME_STOP_ET  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
FLEET_REST_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")
CORE_ARMS = ("safe-2", "bold-2")
ALL_LIVE_ARMS = FLEET_REST_ARMS + CORE_ARMS

PREREG = REPO / "analysis" / "recommendations" / "trail-width-exit-prereg-2026-07-21.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "trail-width-exit-2026-07-21.json"
OUT_MD = REPO / "analysis" / "recommendations" / "trail-width-exit-2026-07-21.md"

LEVEL_HISTORY_START = dt.date(2026, 5, 19)
LEVEL_HISTORY_END = dt.date(2026, 7, 21)
TRIGGER_RECOVERY_LOOKBACK_BARS = 8   # ~40 min; matches structure_stop_study.py precedent

BH_ALPHA = 0.10

CANDIDATE_DEFS = {
    # id            : (trail_pct, tp1_qty_fraction, tp1_premium_pct_or_None)
    "TRAIL-20":       (0.20, None, None),
    "TRAIL-25":       (0.25, None, None),
    "TRAIL-30":       (0.30, None, None),
    "TP1Q-050":       (None, 0.5,   None),
    "TP1Q-033":       (None, 0.333, None),
    "RIDE-BUNDLE":    (0.30, 0.5,   0.50),
}
CANDIDATE_IDS = tuple(CANDIDATE_DEFS.keys())


# ---------------------------------------------------------------------------------------------
# POPULATION -- pure functions, NO broker import, NO network call
# ---------------------------------------------------------------------------------------------
def load_fleet_engine_fills(arms: tuple = ALL_LIVE_ARMS) -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    with LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("arm") in arms and r.get("attribution") == "engine"
                    and not r.get("is_crypto") and r.get("is_option")):
                out.append(r)
    return out


def reconstruct_positions(fills: list[dict]) -> list[dict]:
    """Group raw fills into logical POSITIONS per (arm, symbol) -- same grouping rule as
    exit_shape_parity_study.reconstruct_positions, extended to also carry entry_ts_et
    (needed for trigger-level recovery + exit_manager_walk, which both key off ET-local
    wall-clock time, not UTC). PURE."""
    by_key: dict = defaultdict(list)
    for f in fills:
        by_key[(f["arm"], f["symbol"])].append(f)

    positions = []
    for (arm, symbol), group in by_key.items():
        group.sort(key=lambda x: x["ts_utc"])
        pos = None
        open_qty = 0.0
        for f in group:
            if f["side"] == "buy":
                if open_qty <= 1e-9:
                    if pos is not None:
                        positions.append(pos)
                    pos = {"arm": arm, "symbol": symbol, "entry_qty": 0.0, "entry_notional": 0.0,
                           "entry_ts_utc": f["ts_utc"], "entry_ts_et": f["ts_et"],
                           "date_et": f["date_et"], "exit_fills": []}
                pos["entry_qty"] += f["qty"]
                pos["entry_notional"] += f["qty"] * f["price"]
                open_qty += f["qty"]
            else:
                if pos is None:
                    continue
                pos["exit_fills"].append(f)
                open_qty -= f["qty"]
        if pos is not None:
            positions.append(pos)
    for p in positions:
        p["entry_price"] = round(p["entry_notional"] / p["entry_qty"], 4) if p["entry_qty"] else 0.0
        p["actual_exit_pnl"] = round(sum((ef["price"] - p["entry_price"]) * ef["qty"] * 100
                                          for ef in p["exit_fills"]), 2)
    return positions


def option_side_from_symbol(symbol: str) -> str:
    s = symbol[9]
    assert s in ("C", "P"), f"unexpected side char {s!r} in symbol {symbol!r}"
    return s


def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def anchor_population_signature(positions: list[dict]) -> list[dict]:
    sig = [{"date_et": p["date_et"], "symbol": p["symbol"], "arm": p["arm"],
            "entry_ts_utc": p["entry_ts_utc"], "entry_qty": p["entry_qty"]} for p in positions]
    return sorted(sig, key=lambda x: (x["date_et"], x["symbol"], x["arm"], x["entry_ts_utc"]))


def build_anchor_population() -> list[dict]:
    """ALL_LIVE_ARMS engine-attributed option positions, restricted to positions with a
    cached real-OPRA option-bar CSV AND a valid entry_price/qty. SPY-coverage is checked
    later (a single shared spy_full load), not per-position here."""
    fills = load_fleet_engine_fills()
    positions = reconstruct_positions(fills)
    out = []
    for p in positions:
        if p["entry_qty"] < 1 or p["entry_price"] <= 0:
            continue
        opt_df = load_contract_bars(p["symbol"])
        if opt_df is None or opt_df.empty:
            continue
        p = dict(p)
        p["side"] = option_side_from_symbol(p["symbol"])
        p["qty"] = int(round(p["entry_qty"]))
        out.append(p)
    return sorted(out, key=lambda x: (x["date_et"], x["symbol"], x["arm"], x["entry_ts_utc"]))


# ---------------------------------------------------------------------------------------------
# TRIGGER-LEVEL RECOVERY (identical heuristic to structure_stop_study.py)
# ---------------------------------------------------------------------------------------------
def recover_trigger_level(spy_full: pd.DataFrame, level_cache: dict, date: dt.date,
                          entry_ts_et: dt.datetime, side: str,
                          lookback_bars: int = TRIGGER_RECOVERY_LOOKBACK_BARS) -> tuple:
    level_set = lc.frozen_level_set_for_date(spy_full, date, level_cache)
    if level_set is None:
        return None, "no_level_set"
    day_bars = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] <= entry_ts_et)]
    day_bars = day_bars.tail(lookback_bars)
    if day_bars.empty:
        return None, "no_bars_before_entry"
    for idx in list(day_bars.index)[::-1]:
        bar = spy_full.loc[idx]
        lvl = (detect_level_reclaim(bar, level_set.active) if side == "C"
               else detect_level_rejection(bar, level_set.active))
        if lvl is not None:
            return lvl, "ok"
    return None, "no_trigger_bar_in_lookback"


# ---------------------------------------------------------------------------------------------
# CANDIDATE-SHAPE CONSTRUCTION -- pure, testable
# ---------------------------------------------------------------------------------------------
def build_shapes(control_shape: dict) -> dict:
    """control_shape read fresh from strategies.RIBBON_RIDE.exit.to_dict() -- CANDIDATE_DEFS
    only overrides the fields it names, everything else (premium_stop_pct, profit_lock_mode,
    runner_target_pct, stop_mode, catastrophe_stop_pct, profit_lock_arm_pct/scope) stays
    byte-identical to control, isolating exactly the axis under test."""
    shapes = {"CONTROL": dict(control_shape)}
    for cid, (trail_pct, tp1_qty_fraction, tp1_premium_pct) in CANDIDATE_DEFS.items():
        s = dict(control_shape)
        if trail_pct is not None:
            s["trail_pct"] = trail_pct
        if tp1_qty_fraction is not None:
            s["tp1_qty_fraction"] = tp1_qty_fraction
        if tp1_premium_pct is not None:
            s["tp1_premium_pct"] = tp1_premium_pct
        shapes[cid] = s
    return shapes


# ---------------------------------------------------------------------------------------------
# STATS -- one-sided BH-FDR (paired-delta mean > 0), inlined (no regime_conditioned_validator
# coupling -- this is a real-fills anchor study, not a regime-bucketed one)
# ---------------------------------------------------------------------------------------------
def one_sided_p_mean_gt_0(xs: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def bh_fdr_single(p: Optional[float], alpha: float = BH_ALPHA) -> dict:
    if p is None:
        return {"p": None, "threshold": alpha, "significant": False, "note": "p undefined (n<2)"}
    return {"p": round(p, 5), "threshold": alpha, "significant": p <= alpha,
            "note": "single-candidate BH-FDR degenerates to a plain one-sided test at alpha"}


# ---------------------------------------------------------------------------------------------
# REPLAY -- ONE position x ONE shape via the REAL exit_manager (exit_manager_walk.py)
# ---------------------------------------------------------------------------------------------
def replay_one(pos: dict, shape: dict, trigger_level: Optional[float],
               day_spy: pd.DataFrame) -> dict:
    opt_df = load_contract_bars(pos["symbol"])
    entry_time_et = dt.datetime.fromisoformat(pos["entry_ts_et"])
    res = walk_exit_manager(
        symbol=pos["symbol"], side=pos["side"], entry_time_et=entry_time_et,
        entry_premium=pos["entry_price"], qty=pos["qty"], exit_shape=shape,
        structure_stop_enabled=True, trigger_level=trigger_level, strategy="trail_width_ab",
        time_stop_et=TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=day_spy)
    return {"pnl": res.dollar_pnl, "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
            "n_legs": len(res.legs)}


# ---------------------------------------------------------------------------------------------
# GATES
# ---------------------------------------------------------------------------------------------
def day_totals(rows: list[dict], key: str) -> dict:
    out: dict = defaultdict(float)
    for r in rows:
        out[r["date_et"]] += r[key]
    return dict(out)


def evaluate_gates(rows: list[dict], midpoint_date: str) -> dict:
    """rows: one dict per position with control_pnl/candidate_pnl/date_et. Returns the 4
    task-mandated gates + disclosure stats (give-back accounting, BH-FDR, concentration)."""
    deltas = [round(r["candidate_pnl"] - r["control_pnl"], 2) for r in rows]
    control_total = round(sum(r["control_pnl"] for r in rows), 2)
    candidate_total = round(sum(r["candidate_pnl"] for r in rows), 2)
    agg_delta = round(candidate_total - control_total, 2)
    gate1_aggregate = agg_delta > 0

    ctl_day = day_totals(rows, "control_pnl")
    cand_day = day_totals(rows, "candidate_pnl")
    days = sorted(set(ctl_day) | set(cand_day))
    cand_wins = sum(1 for d in days if cand_day.get(d, 0.0) > ctl_day.get(d, 0.0))
    ctl_wins = sum(1 for d in days if ctl_day.get(d, 0.0) >= cand_day.get(d, 0.0))
    gate2_majority_days = cand_wins > ctl_wins

    rows_sorted_by_delta = sorted(rows, key=lambda r: -(r["candidate_pnl"] - r["control_pnl"]))
    drop_best_1 = rows_sorted_by_delta[1:]
    delta_ex_best1 = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in drop_best_1), 2)
    gate3_survives_drop_best1 = delta_ex_best1 > 0

    drop_top3 = rows_sorted_by_delta[3:]
    delta_ex_top3 = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in drop_top3), 2)

    first_half = [r for r in rows if r["date_et"] <= midpoint_date]
    second_half = [r for r in rows if r["date_et"] > midpoint_date]
    is_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in first_half), 2)
    oos_delta = round(sum(r["candidate_pnl"] - r["control_pnl"] for r in second_half), 2)
    sign_flip = (is_delta > 0) != (oos_delta > 0) if (is_delta != 0 and oos_delta != 0) else False
    gate4_oos_holds = (oos_delta > 0) and not sign_flip

    p_val = one_sided_p_mean_gt_0(deltas)
    bh = bh_fdr_single(p_val)

    positive_deltas = [d for d in deltas if d > 0]
    negative_deltas = [d for d in deltas if d < 0]
    extra_captured = round(sum(positive_deltas), 2)
    extra_given_back = round(sum(negative_deltas), 2)   # negative number by construction

    overall_ship = bool(gate1_aggregate and gate2_majority_days and gate3_survives_drop_best1
                        and gate4_oos_holds)

    return {
        "n": len(rows), "control_total": control_total, "candidate_total": candidate_total,
        "aggregate_delta": agg_delta,
        "gate1_aggregate_beats_control": gate1_aggregate,
        "gate2_majority_of_days": {"result": gate2_majority_days, "candidate_wins_days": cand_wins,
                                   "control_wins_or_ties_days": ctl_wins, "n_days": len(days)},
        "gate3_survives_drop_single_best_trade": {"result": gate3_survives_drop_best1,
                                                   "delta_ex_best1": delta_ex_best1,
                                                   "best1_trade": {
                                                       "date_et": rows_sorted_by_delta[0]["date_et"],
                                                       "symbol": rows_sorted_by_delta[0]["symbol"],
                                                       "delta": round(rows_sorted_by_delta[0]["candidate_pnl"]
                                                                     - rows_sorted_by_delta[0]["control_pnl"], 2),
                                                   } if rows_sorted_by_delta else None},
        "gate4_oos_holds": {"result": gate4_oos_holds, "is_delta_first_half": is_delta,
                            "oos_delta_second_half": oos_delta, "sign_flip": sign_flip,
                            "midpoint_date": midpoint_date, "n_first_half": len(first_half),
                            "n_second_half": len(second_half)},
        "disclosure_concentration_ex_top3": {"delta_ex_top3": delta_ex_top3,
                                             "survives_ex_top3": delta_ex_top3 > 0},
        "disclosure_bh_fdr": bh,
        "give_back_accounting": {
            "extra_captured_on_beats": extra_captured, "n_beats": len(positive_deltas),
            "extra_given_back_on_losses": extra_given_back, "n_losses": len(negative_deltas),
            "net": round(extra_captured + extra_given_back, 2),
        },
        "overall_ship_decision": "SHIP" if overall_ship else "CONTROL_HOLDS",
    }


# ---------------------------------------------------------------------------------------------
# PREFLIGHT
# ---------------------------------------------------------------------------------------------
def preflight() -> dict:
    positions = build_anchor_population()
    pop_sha16 = _content_hash(anchor_population_signature(positions))[:16]
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    expected_sha16 = preg["population"]["anchor_population_sha256_16"]
    expected_n = preg["population"]["n_positions"]
    return {
        "anchor_population_sha256_16": pop_sha16, "hash_ok": pop_sha16 == expected_sha16,
        "n_positions": len(positions), "n_ok": len(positions) == expected_n,
        "preregistration_version": preg.get("version"),
    }


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[trail-width-ab] preflight: {pf}", flush=True)
    if not (pf["hash_ok"] and pf["n_ok"]):
        print("[trail-width-ab] PREFLIGHT FAILED -- population drifted from the frozen "
              "pre-registration. Aborting (no re-picks, no stale-population runs).",
              file=sys.stderr)
        return 1

    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    midpoint_date = preg["gates"]["oos_midpoint_date"]

    print("[trail-width-ab] loading SPY 5m bars...", flush=True)
    spy_full = lc.load_spy_full(LEVEL_HISTORY_START, LEVEL_HISTORY_END)
    print(f"[trail-width-ab] spy_full: {len(spy_full)} rows, "
          f"{spy_full['date'].min()}..{spy_full['date'].max()}", flush=True)

    positions = build_anchor_population()
    print(f"[trail-width-ab] anchor population: {len(positions)} positions", flush=True)

    control_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    shapes = build_shapes(control_shape)
    print(f"[trail-width-ab] control_shape={control_shape}", flush=True)
    for cid in CANDIDATE_IDS:
        print(f"[trail-width-ab] {cid}_shape={shapes[cid]}", flush=True)

    level_cache: dict = {}
    n_recoverable = 0
    per_position_rows = {cid: [] for cid in CANDIDATE_IDS}
    control_rows = []
    n_skipped_no_spy_day = 0

    for pos in positions:
        date = dt.date.fromisoformat(pos["date_et"])
        entry_time_et = dt.datetime.fromisoformat(pos["entry_ts_et"])
        day_spy = spy_full.loc[spy_full["date"] == date].reset_index(drop=True)
        if day_spy.empty:
            n_skipped_no_spy_day += 1
            continue
        trigger_level, recovery_status = recover_trigger_level(
            spy_full, level_cache, date, entry_time_et, pos["side"])
        if trigger_level is not None:
            n_recoverable += 1

        ctl_res = replay_one(pos, shapes["CONTROL"], trigger_level, day_spy)
        control_rows.append({"date_et": pos["date_et"], "symbol": pos["symbol"], "arm": pos["arm"],
                             "control_pnl": ctl_res["pnl"], "actual_exit_pnl": pos["actual_exit_pnl"],
                             "recovery_status": recovery_status, "trigger_level": trigger_level,
                             "control_exit_reason": ctl_res["exit_reason"],
                             "control_hold_minutes": ctl_res["hold_minutes"]})

        for cid in CANDIDATE_IDS:
            cand_res = replay_one(pos, shapes[cid], trigger_level, day_spy)
            per_position_rows[cid].append({
                "date_et": pos["date_et"], "symbol": pos["symbol"], "arm": pos["arm"],
                "control_pnl": ctl_res["pnl"], "candidate_pnl": cand_res["pnl"],
                "control_exit_reason": ctl_res["exit_reason"],
                "candidate_exit_reason": cand_res["exit_reason"],
                "control_hold_minutes": ctl_res["hold_minutes"],
                "candidate_hold_minutes": cand_res["hold_minutes"],
                "recovery_status": recovery_status, "trigger_level": trigger_level,
            })

    print(f"[trail-width-ab] replayed {len(control_rows)} positions "
          f"({n_recoverable} recoverable trigger_level, {n_skipped_no_spy_day} skipped "
          f"no-SPY-day)", flush=True)

    control_total = round(sum(r["control_pnl"] for r in control_rows), 2)
    print(f"[trail-width-ab] CONTROL total = ${control_total:+.2f} (n={len(control_rows)})",
          flush=True)

    verdicts = {}
    for cid in CANDIDATE_IDS:
        v = evaluate_gates(per_position_rows[cid], midpoint_date)
        verdicts[cid] = v
        print(f"[trail-width-ab] {cid}: {v['overall_ship_decision']} -- "
              f"agg_delta=${v['aggregate_delta']:+.2f} gates="
              f"[{v['gate1_aggregate_beats_control']},"
              f"{v['gate2_majority_of_days']['result']},"
              f"{v['gate3_survives_drop_single_best_trade']['result']},"
              f"{v['gate4_oos_holds']['result']}]", flush=True)

    out = {
        "_doc": "TRAIL-WIDTH / TP1-SIZE exit knob A/B -- real-fills anchor, pre-registered, "
                "frozen before any candidate replay. ANALYSIS ONLY: no trading-path file "
                "touched by this run.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "control_shape": control_shape,
        "candidate_shapes": {cid: shapes[cid] for cid in CANDIDATE_IDS},
        "population": {
            "n_positions": len(positions), "n_replayed": len(control_rows),
            "n_skipped_no_spy_day": n_skipped_no_spy_day,
            "n_recoverable_trigger_level": n_recoverable,
            "arms": list(ALL_LIVE_ARMS),
            "date_span": f"{min(r['date_et'] for r in control_rows)}.."
                         f"{max(r['date_et'] for r in control_rows)}" if control_rows else None,
            "n_trading_days": len(set(r["date_et"] for r in control_rows)),
        },
        "control_total_pnl": control_total,
        "reconciliation_vs_structure_stop_reference_level_no_ship": (
            "structure-stop-reference-level-2026-07-20.json rejected widening the structure-"
            "stop REFERENCE LEVEL (trigger-exact/zone-boundary/none -- WHERE the chart-stop is "
            "anchored). Every candidate in THIS study still uses trigger-exact recovery "
            "(byte-identical to that study's REF-EXACT), varying only trail_pct/tp1_qty_"
            "fraction/tp1_premium_pct -- a disjoint knob. That axis is not re-opened here."
        ),
        "prior_evidence_context_exit_variant_ab_wider_trail25": (
            "analysis/recommendations/exit-variant-ab-wider-trail25-2026-07-17.json already "
            "tested trail_pct=0.25 vs 0.15 on a much larger SYNTHETIC detector-fired population "
            "(n=188, IS2025+OOS2026YTD) and found -$813.30 aggregate, FAIL on every regime-"
            "conditioned gate. Cited as prior evidence to reconcile against; not this study's "
            "population (this study uses the REAL-FILLS anchor per task instruction)."
        ),
        "verdicts": verdicts,
        "position_detail": per_position_rows,
        "control_position_detail": control_rows,
        "disclosures": [
            "ribbon_flip_back is OFF (no historical ribbon-state reconstruction for arbitrary "
            "past dates) -- same disclosed limitation exit_variant_ab.py and structure_stop_"
            "study.py both carry for the ribbon-flip secondary exit only; structure_stop/"
            "premium_stop/tp1/trail/runner_target/time_stop are ALL modeled via the real "
            "exit_manager.plan_exit_actions core.",
            "The shared candidate shape is applied UNIFORMLY to every real-fills option "
            "position regardless of which strategy (ribbon_ride vs vwap_continuation) actually "
            "fired live -- fills-ledger.jsonl carries no strategy/setup tag. Same convention "
            "structure_stop_study.py / structure_stop_reference_level_ab.py already used for "
            "their real-fills anchor layer.",
            "Trigger-level recovery is a backward-scan heuristic (lookback=8 bars/~40min), "
            "identical to structure_stop_study.recover_trigger_level_real_position. Positions "
            "with no recoverable trigger_level fall back to stop_mode=premium IDENTICALLY "
            "across control and every candidate -- never a fabricated level, never dropped.",
            "C6 fill-mark convention (exit_manager_walk.py): market-style stages (structure_"
            "stop/ribbon_flip/time_stop) fill at that bar's CLOSE minus $0.02 slippage; "
            "limit-style stages (tp1/premium_stop/trail/runner_target) fill exactly at the "
            "triggered premium level.",
            "Frictionless fills at trigger/stop/target levels beyond the $0.02 market-stage "
            "slippage above (no bid/ask spread or queue modelled) -- matches every prior study "
            "in this codebase (T3/T4/T5/T-W8/structure_stop_study/exit_variant_ab).",
            "ALL_LIVE_ARMS (fleet_rest + core) population per exit_shape_parity_study.py's own "
            "2026-07-21 sanctioned opt-in -- a NEW study, not a silent extension of an already-"
            "verdicted one (the frozen structure-stop studies keep their own pinned FLEET_"
            "REST_ARMS-only anchors untouched).",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[trail-width-ab] wrote {OUT_JSON}", flush=True)
    write_markdown(out)
    print(f"[trail-width-ab] wrote {OUT_MD}", flush=True)
    return 0


def write_markdown(out: dict) -> None:
    L = [
        "# TRAIL-WIDTH / TP1-SIZE exit A/B -- real-fills anchor (2026-07-21)",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/trail_width_exit_ab.py`. "
        f"Pre-reg: `{out['preregistration_file']}`.",
        "",
        f"**Control shape** (`strategies.RIBBON_RIDE.exit.to_dict()`): `{out['control_shape']}`",
        "",
        f"Population: {out['population']['n_replayed']} real-fills positions "
        f"({out['population']['n_recoverable_trigger_level']} recoverable trigger_level), "
        f"{out['population']['n_trading_days']} trading days, {out['population']['date_span']}, "
        f"arms={out['population']['arms']}. CONTROL total = ${out['control_total_pnl']:+.2f}.",
        "",
        "## Reconciliation vs the frozen structure-stop-reference-level NO-SHIP",
        "",
        out["reconciliation_vs_structure_stop_reference_level_no_ship"],
        "",
        "## Prior evidence on this axis (synthetic population, cited not reused)",
        "",
        out["prior_evidence_context_exit_variant_ab_wider_trail25"],
        "",
        "## Candidates",
        "",
        "| id | trail_pct | tp1_qty_fraction | tp1_premium_pct | n | control $ | candidate $ | "
        "agg delta | gate1 agg | gate2 days | gate3 drop-best1 | gate4 OOS | verdict |",
        "|---|--:|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|:--:|:--:|",
    ]
    for cid in out["verdicts"]:
        v = out["verdicts"][cid]
        s = out["candidate_shapes"][cid]
        L.append(
            f"| {cid} | {s['trail_pct']} | {s['tp1_qty_fraction']} | {s['tp1_premium_pct']} | "
            f"{v['n']} | ${v['control_total']:,.2f} | ${v['candidate_total']:,.2f} | "
            f"${v['aggregate_delta']:+,.2f} | {v['gate1_aggregate_beats_control']} | "
            f"{v['gate2_majority_of_days']['result']} | "
            f"{v['gate3_survives_drop_single_best_trade']['result']} | "
            f"{v['gate4_oos_holds']['result']} | **{v['overall_ship_decision']}** |")
    L += [
        "",
        "## Give-back accounting (honesty requirement -- both sides of the ledger)",
        "",
        "| id | extra captured on beats | n beats | extra given back on losses | n losses | net |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for cid in out["verdicts"]:
        g = out["verdicts"][cid]["give_back_accounting"]
        L.append(f"| {cid} | ${g['extra_captured_on_beats']:+,.2f} | {g['n_beats']} | "
                 f"${g['extra_given_back_on_losses']:+,.2f} | {g['n_losses']} | ${g['net']:+,.2f} |")
    L += [
        "",
        "## Disclosure: BH-FDR + concentration",
        "",
        "| id | BH-FDR p | significant (a=0.10) | delta ex-top3 | survives ex-top3 |",
        "|---|--:|:--:|--:|:--:|",
    ]
    for cid in out["verdicts"]:
        v = out["verdicts"][cid]
        bh = v["disclosure_bh_fdr"]
        c3 = v["disclosure_concentration_ex_top3"]
        L.append(f"| {cid} | {bh['p']} | {bh['significant']} | ${c3['delta_ex_top3']:+,.2f} | "
                 f"{c3['survives_ex_top3']} |")
    L += [
        "",
        "## Disclosed limitations",
        "",
    ]
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L += [
        "",
        "---",
        "_Source: `backtest/tools/trail_width_exit_ab.py`. Full per-position detail in the "
        "companion `.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
