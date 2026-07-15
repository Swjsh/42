"""bold_strike_axis_ab.py -- BOLD-STRIKE-X-FLOOR-COLLISION (2026-07-15).

Queue item: automation/overnight/queue.md ## EOD-2026-07-15 FIXES #1. Bold's <$2K equity tier
(V15_BOLD_TIERS, crypto/lib/strike_selection.py: strike_offset=-3, label "OTM-3") and
min_entry_premium=0.30 (aggressive/params.json ENTRY-1, shipped 2026-07-09) are mutually
exclusive for a meaningful fraction of Bold's own afternoon trading window: 2026-07-15 13:56 ET
ENTER_BULL resolved SPY 757C @ $0.08 -> SKIP_MIN_PREMIUM_FLOOR, five ticks straight. OTM-3 is
also the documented bleed cohort (edge-hunt 2026-06-20: "ITM+tight=edge, OTM+wide=bleed"; the
2026-07-14 Safe strike-AB convention reconciliation found ATM the only cell clearing zero
expectancy under honest friction -- but that is the SAFE account's exit shape/sizing, and
C29/L149 (strike verdicts do not transfer across accounts/exit shapes) is exactly why this
script re-runs the axis under BOLD's own consumed shape/sizing/floor instead of copying that
verdict).

Frozen pre-registration: analysis/recommendations/prereg-bold-strike-axis-2026-07-15.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift between what's frozen on
disk and what this runner executes).

REUSE (OP-22), not reinvention:
  * ribbon_ride_strike_exit_ab.load_cohort() / .fetch_entry_and_bars() / .strike_for() -- the
    SAME canonical, strike-independent ribbon_ride signal cohort (both directions, L2 gate, cap
    OFF; n=250, 2025-01-06..2026-06-17) and the SAME corrected (`>`, fill-bar-excluded) OPRA bar
    loader every strike-AB study in this lineage shares. Imported directly, not re-derived.
  * structure_stop_study.SS_B_SHAPE / STRUCTURE_BUFFER["SS-B"] -- Bold's live-consumed ribbon_ride
    exit shape, VERIFIED (not assumed) byte-identical to this constant by the 2026-07-14
    reconciliation's 2026-07-15 08:23 ET follow-up (strategies.py is SHARED across accounts;
    traced field-by-field against automation/state/fleet/strategies.py's RIBBON_RIDE.exit).
  * strike_ab_convention_reconciliation.replay_generic() -- the exact tested friction/stage-fix/
    structure-stop replay function from the Safe reconciliation study's job1a, imported and
    called unchanged (only strike/time-stop/qty/floor inputs vary here).
  * autoresearch.null_baseline.random_entry_null / null_gate/ autoresearch.ribbon_rejection_
    wick_battery.bh_fdr -- the canonical random-entry-null + BH-FDR battery (ribbon_ride_strike_
    exit_ab.py's exact convention), reused unchanged. The Safe reconciliation study explicitly
    skipped this ("out of scope for a convention decomposition") -- this task requires it, so it
    is run here, adapted to route every null draw through Bold's OWN shape/time-stop/floor gate.

BOLD-SPECIFIC DEVIATIONS FROM BOTH SOURCE STUDIES (each disclosed in the frozen pre-reg too):
  1. Strike cells = {OTM-3 (control, Bold's CURRENT live <$2K tier), OTM-2, OTM-1, ATM, ITM-1,
     ITM-2} -- 6 cells, not the 4 the Safe studies tested (adds OTM-3 as control + ITM-1).
  2. time_stop_et = 15:40 (aggressive/params.json, the REAL live-consumed value), NOT the 15:50
     exit_manager module default the Safe reconciliation study's job1a used.
  3. min_entry_premium floor = 0.30 applied IN-SIM: a signal whose raw entry-bar OPEN premium at
     a given strike is < 0.30 does NOT trade at that cell (SKIP_MIN_PREMIUM_FLOOR) -- this is the
     floor-collision mechanism itself, modeled rather than assumed. floor_clearance_rate reported
     per cell, overall and afternoon-only (entry_ts >= 12:00 ET).
  4. QTY = 5 (Bold's REAL live base_qty at the <$2K tier, aggressive/params.json
     position_sizing_tiers[0]), NOT the QTY=10 "relative dollars" convention both source studies
     used -- this study's decision is Bold-tier-specific, so dollar figures are Bold-real-size.
  5. Random-entry null draws from Bold's OWN entry gate (09:35-15:00 ET, aggressive/params.json),
     not null_baseline's generic (09:35-15:45) default.
  6. BH-FDR + null computed across all 6 cells (required by this task; the Safe reconciliation
     study's job1a explicitly did not run this).

ANALYSIS ONLY. No params/config/trading-path file touched. No orders placed. Does NOT flip
V15_BOLD_TIERS or aggressive/params.json even if a cell clears every gate -- see the frozen
pre-reg's decision_rule.live_flip_deferred (same-night live flip after a -$369 Bold day
warrants a one-morning J REVOKE window; the scorecard records the recommendation + one-line
diff + guard-test spec instead).

Run: backtest/.venv/Scripts/python.exe backtest/tools/bold_strike_axis_ab.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import ribbon_ride_strike_exit_ab as rrse                              # noqa: E402
import structure_stop_study as sss                                     # noqa: E402
import t4_exit_matrix as t4                                            # noqa: E402
import strike_ab_convention_reconciliation as sacr                     # noqa: E402
from autoresearch.null_baseline import random_entry_null               # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA  # noqa: E402

SMOKE = "--smoke" in sys.argv

PREREG = REPO / "analysis" / "recommendations" / "prereg-bold-strike-axis-2026-07-15.json"
EXPECTED_PREREG_SHA16 = "770439aea2083210"
EXPECTED_PREREG_VERSION = 1

OUT_JSON = REPO / "analysis" / "recommendations" / ("bold-strike-axis-2026-07-15-SMOKE.json" if SMOKE
                                                     else "bold-strike-axis-2026-07-15.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("bold-strike-axis-2026-07-15-SMOKE.md" if SMOKE
                                                   else "bold-strike-axis-2026-07-15.md")

QTY = 5                            # Bold's REAL live base_qty at the <$2K tier (aggressive/params.json)
NULL_SEEDS = 3 if SMOKE else 20    # ribbon_ride_strike_exit_ab.py's "~20 seeds" convention (smoke: fast check)
MIN_ENTRY_PREMIUM = 0.30           # aggressive/params.json ENTRY-1 (min_entry_premium)
AFTERNOON_CUTOFF = dt.time(12, 0)  # queue item's own "after ~noon" framing
BOLD_TIME_STOP = dt.time(15, 40)   # aggressive/params.json time_stop_et -- the REAL live value
BOLD_ENTRY_GATE = (dt.time(9, 35), dt.time(15, 0))  # aggressive/params.json entry window

STRIKE_CELLS = [("OTM-3", 3), ("OTM-2", 2), ("OTM-1", 1), ("ATM", 0), ("ITM-1", -1), ("ITM-2", -2)]
CONTROL_STRIKE = "OTM-3"

SS_B_SHAPE = dict(sss.SS_B_SHAPE)
SS_B_BUFFER = sss.STRUCTURE_BUFFER["SS-B"]


def log(msg: str) -> None:
    print(f"[bold-strike-ab] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PRE-FLIGHT -- never run a drifted spec
# ---------------------------------------------------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    ok = (recomputed == EXPECTED_PREREG_SHA16 == stored and preg.get("version") == EXPECTED_PREREG_VERSION)
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
           "expected_sha16": EXPECTED_PREREG_SHA16, "version": preg.get("version"), "status": preg.get("status")}


# ---------------------------------------------------------------------------------------------
# ONE CELL -- replay w/ the min-entry-premium floor gate applied IN-SIM (the point of this study)
# ---------------------------------------------------------------------------------------------
def build_trades(prepped: list[dict], so: int) -> tuple[list[dict], dict]:
    """Returns (trades, floor_stats). trades: signals w/ local OPRA coverage AND entry premium
    clearing the 0.30 floor, replayed through Bold's SS-B shape (honest friction, corrected
    fill-bar convention, stage-fix applied, structure-stop chart layer ON, 15:40 time stop).
    floor_stats reports the floor-collision mechanism itself, overall and afternoon-only."""
    trades: list[dict] = []
    n_no_bars = 0
    n_floor_skip = 0
    n_floor_skip_pm = 0
    n_traded_pm = 0
    n_opportunities_pm = 0
    for s in prepped:
        is_pm = s["entry_ts_obj"].time() >= AFTERNOON_CUTOFF
        fetched = rrse.fetch_entry_and_bars(float(s["entry_spot"]), s["side"], s["date_obj"],
                                            s["entry_ts_obj"], so, old_semantics=False)
        if fetched is None:
            n_no_bars += 1
            continue
        entry_premium_raw, walk_bars = fetched
        if is_pm:
            n_opportunities_pm += 1
        if entry_premium_raw < MIN_ENTRY_PREMIUM:
            n_floor_skip += 1
            if is_pm:
                n_floor_skip_pm += 1
            continue
        if not walk_bars:
            n_no_bars += 1
            continue
        ss_time = s["ss_time"]
        r = sacr.replay_generic(entry_premium_raw, s["side"], QTY, walk_bars, ss_time, SS_B_SHAPE,
                                BOLD_TIME_STOP, friction=True, stage_fix=True, use_structure=True)
        trades.append({"date": s["date_obj"], "direction": s["direction"], "side": s["side"],
                       "pnl": r["pnl"]})
        if is_pm:
            n_traded_pm += 1

    n_opportunities = len(trades) + n_floor_skip
    floor_clearance_rate = round(len(trades) / n_opportunities, 4) if n_opportunities else None
    floor_clearance_rate_pm = round(n_traded_pm / n_opportunities_pm, 4) if n_opportunities_pm else None
    floor_stats = {
        "n_no_local_bars": n_no_bars, "n_floor_skipped": n_floor_skip,
        "n_opportunities": n_opportunities, "floor_clearance_rate": floor_clearance_rate,
        "n_floor_skipped_afternoon": n_floor_skip_pm, "n_afternoon_opportunities": n_opportunities_pm,
        "floor_clearance_rate_afternoon": floor_clearance_rate_pm,
    }
    return trades, floor_stats


def both_halves(trades: list[dict]) -> dict:
    ordered = sorted(trades, key=lambda t: t["date"])
    n = len(ordered)
    mid = n // 2
    first, second = ordered[:mid], ordered[mid:]
    f_tot = round(sum(t["pnl"] for t in first), 2)
    s_tot = round(sum(t["pnl"] for t in second), 2)
    return {"first_half": {"n": len(first), "total": f_tot},
           "second_half": {"n": len(second), "total": s_tot},
           "both_positive": bool(first and second and f_tot > 0 and s_tot > 0)}


def cell_summary(trades: list[dict], floor_stats: dict) -> dict:
    b = t4.battery(trades)
    bh = both_halves(trades)
    n_is = sum(1 for t in trades if t["date"] < rrse.OOS_BOUNDARY)
    n_oos = sum(1 for t in trades if t["date"] >= rrse.OOS_BOUNDARY)
    oos_exp = round(b["oos_total"] / n_oos, 2) if n_oos and b.get("oos_total") is not None else None
    return {**floor_stats,
           "n": b.get("n"), "total": b.get("total"), "expectancy": b.get("expectancy"), "wr": b.get("wr"),
           "n_is": n_is, "n_oos": n_oos, "oos_total": b.get("oos_total"), "oos_expectancy": oos_exp,
           "oos_positive": b.get("oos_positive"), "wf": b.get("wf"), "wf_ge_070": b.get("wf_ge_070"),
           "qpf": b.get("qpf"), "exp_drop_top3": b.get("exp_drop_top3"),
           "edge_capture_rel": b.get("edge_capture_rel"),
           "sub_window_stable": bh["both_positive"],
           "both_halves": {"first": bh["first_half"], "second": bh["second_half"]}}


# ---------------------------------------------------------------------------------------------
# NULL -- random-entry inside BOLD's OWN entry gate, routed through the SAME shape/floor gate.
# ---------------------------------------------------------------------------------------------
def make_bold_null_sim_fn(so: int, spy_by_date: dict):
    def _sim(entry_bar_idx, entry_bar, spy_df, ribbon_df, rejection_level, triggers_fired,
             side, qty, setup, premium_stop_pct, strike_offset):
        entry_ts = entry_bar["timestamp_et"]
        if hasattr(entry_ts, "to_pydatetime"):
            entry_ts = entry_ts.to_pydatetime()
        if getattr(entry_ts, "tzinfo", None) is not None:
            entry_ts = entry_ts.replace(tzinfo=None)
        date = entry_ts.date()
        entry_spot = float(entry_bar["close"])
        fetched = rrse.fetch_entry_and_bars(entry_spot, side, date, entry_ts, so, old_semantics=False)
        if fetched is None:
            return None
        entry_premium_raw, norm_bars = fetched
        if entry_premium_raw < MIN_ENTRY_PREMIUM:
            return None   # floor-skip -- the null respects the SAME floor gate the real cells do
        ss_time = None
        if rejection_level is not None:
            day_bars = spy_by_date.get(date)
            if day_bars is not None:
                sub = day_bars[day_bars["timestamp_et"] >= entry_ts]
                ss_time = sss.structure_stop_signal_time(sub, side, float(rejection_level), SS_B_BUFFER)
        r = sacr.replay_generic(entry_premium_raw, side, qty, norm_bars, ss_time, SS_B_SHAPE, BOLD_TIME_STOP,
                                friction=True, stage_fix=True, use_structure=True)
        return SimpleNamespace(dollar_pnl=r["pnl"])
    return _sim


def run_null(so: int, spy_full: pd.DataFrame, spy_by_date: dict, trades: list[dict]) -> dict:
    n_call = sum(1 for t in trades if t["side"] == "C")
    n_put = sum(1 for t in trades if t["side"] == "P")
    sim_fn = make_bold_null_sim_fn(so, spy_by_date)
    return random_entry_null(
        rth=spy_full, n_signals=len(trades), n_call=n_call, n_put=n_put,
        strike_offset=so, premium_stop_pct=SS_B_SHAPE.get("premium_stop_pct", -0.5),
        qty=QTY, entry_gate=BOLD_ENTRY_GATE, seeds=NULL_SEEDS,
        setup="BOLD_STRIKE_AXIS_AB_NULL", sim_fn=sim_fn,
    )


def empirical_p_null(real_per_trade, null_by_seed: list[float]) -> float:
    if real_per_trade is None or not null_by_seed:
        return 1.0
    ge = sum(1 for v in null_by_seed if v >= real_per_trade)
    return round((1 + ge) / (1 + len(null_by_seed)), 4)


# ---------------------------------------------------------------------------------------------
# GATES + DECISION (frozen pre-reg's ratification_gates / decision_rule)
# ---------------------------------------------------------------------------------------------
def gate_check(cell: dict, control: dict) -> dict:
    ecr = cell.get("edge_capture_rel")
    ctl_ecr = control.get("edge_capture_rel")
    anchor_ok = bool(ecr is not None and ctl_ecr is not None and ecr >= ctl_ecr)
    gates = {
        "oos_positive": bool(cell.get("oos_positive")),
        "wf_ge_070": bool(cell.get("wf_ge_070")),
        "sub_window_stable": bool(cell.get("sub_window_stable")),
        "anchor_no_regression": anchor_ok,
        "bh_fdr_survivor": bool(cell.get("bh_fdr_survivor")),
    }
    gates["all_5_pass"] = all(gates.values())
    return gates


def decide(label: str, cell: dict, control: dict, gates: dict) -> dict:
    beats_control_oos = bool(cell.get("oos_expectancy") is not None and control.get("oos_expectancy") is not None
                             and cell["oos_expectancy"] > control["oos_expectancy"])
    can_trade = bool(cell.get("floor_clearance_rate") is not None and cell["floor_clearance_rate"] >= 0.70
                     and cell.get("floor_clearance_rate_afternoon") is not None
                     and cell["floor_clearance_rate_afternoon"] >= 0.70)
    ship_ready = bool(beats_control_oos and gates["all_5_pass"] and can_trade)
    fails = []
    if not beats_control_oos:
        fails.append("A_does_not_beat_control_oos")
    if not gates["all_5_pass"]:
        fails.extend(f"B_gate_fail_{k}" for k, v in gates.items() if k != "all_5_pass" and not v)
    if not can_trade:
        fails.append("C_floor_clearance_below_70pct_overall_or_afternoon")
    return {"label": label, "beats_control_oos": beats_control_oos, "can_actually_trade": can_trade,
           "ship_ready": ship_ready, "fails": fails}


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    t_start = _time_mod.time()
    pf = preflight()
    log(f"preflight: {pf}")
    if not pf["ok"]:
        log("PREREG HASH/VERSION MISMATCH -- refusing to run a drifted spec. Aborting.")
        return 1

    log(f"{'SMOKE' if SMOKE else 'FULL'} run -- loading cohort (reused from ribbon_ride_strike_exit_ab)")
    prepped, spy_full, spy_by_date = rrse.load_cohort()
    log(f"cohort n={len(prepped)}")

    cells: dict = {}
    nulls: dict = {}
    for label, so in STRIKE_CELLS:
        t0 = _time_mod.time()
        trades, floor_stats = build_trades(prepped, so)
        cells[label] = cell_summary(trades, floor_stats)
        null = run_null(so, spy_full, spy_by_date, trades)
        p_null = empirical_p_null(cells[label].get("expectancy"), null.get("per_trade_by_seed", []))
        cells[label]["p_null"] = p_null
        nulls[label] = {"seeds": null.get("seeds"), "n_eligible": null.get("n_eligible"),
                       "n_drawn": null.get("n_drawn"), "per_trade_mean": null.get("per_trade_mean"),
                       "per_trade_max": null.get("per_trade_max")}
        elapsed = round(_time_mod.time() - t0, 1)
        log(f"{label} (so={so}): n={cells[label]['n']} exp=${cells[label]['expectancy']} "
            f"OOS_exp=${cells[label]['oos_expectancy']} floor_clear={cells[label]['floor_clearance_rate']} "
            f"floor_clear_pm={cells[label]['floor_clearance_rate_afternoon']} p_null={p_null} ({elapsed}s)")

    # BH-FDR across all 6 cells
    bh_input = [{"p_null": cells[lbl]["p_null"]} for lbl, _so in STRIKE_CELLS]
    bh_fdr(bh_input, alpha=FDR_ALPHA)
    for (lbl, _so), b in zip(STRIKE_CELLS, bh_input):
        cells[lbl]["bh_fdr_survivor"] = b["bh_fdr_survivor"]
        cells[lbl]["bh_rank"] = b["bh_rank"]
    log(f"BH-FDR (alpha={FDR_ALPHA}) across {len(bh_input)} cells: "
        f"{sum(1 for b in bh_input if b['bh_fdr_survivor'])} survivors")

    control = cells[CONTROL_STRIKE]
    gates: dict = {}
    decisions: dict = {}
    for label, _so in STRIKE_CELLS:
        gates[label] = gate_check(cells[label], control)
        decisions[label] = decide(label, cells[label], control, gates[label])

    candidates = [lbl for lbl, _so in STRIKE_CELLS if lbl != CONTROL_STRIKE]
    ship_ready_cells = [lbl for lbl in candidates if decisions[lbl]["ship_ready"]]
    winner = None
    if ship_ready_cells:
        winner = max(ship_ready_cells,
                    key=lambda lbl: (cells[lbl]["oos_expectancy"] or -1e18,
                                     cells[lbl]["floor_clearance_rate_afternoon"] or -1))

    elapsed_total = round(_time_mod.time() - t_start, 1)

    out = {
        "_doc": ("BOLD-STRIKE-X-FLOOR-COLLISION strike-axis A/B, Gamma-Risky-2's <$2K tier. "
                "ANALYSIS ONLY -- no params/config/trading-path file touched, no orders placed, "
                "no live tier flip regardless of verdict (see decision_rule.live_flip_deferred "
                "in the frozen pre-reg). Source: backtest/tools/bold_strike_axis_ab.py."),
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "preflight": pf,
        "prereg_path": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "signal_cohort": {"n_raw": len(prepped),
                          "n_call_bull": sum(1 for s in prepped if s["side"] == "C"),
                          "n_put_bear": sum(1 for s in prepped if s["side"] == "P")},
        "method_summary": {
            "exit_shape": "SS_B_SHAPE (structure_stop_study.py), VERIFIED byte-identical to Bold's "
                          "live-consumed ribbon_ride exit (strategies.py shared across accounts).",
            "shape_literal": SS_B_SHAPE, "structure_stop_chart_layer": True,
            "time_stop_et": str(BOLD_TIME_STOP), "min_entry_premium_floor": MIN_ENTRY_PREMIUM,
            "afternoon_cutoff_et": str(AFTERNOON_CUTOFF), "qty": QTY,
            "friction": "ON (lib.simulator_credit haircuts)", "fill_bar_convention": ">  (corrected)",
            "stage_label_fix": True, "null_seeds": NULL_SEEDS, "null_entry_gate_et": [str(t) for t in BOLD_ENTRY_GATE],
            "bh_fdr_alpha": FDR_ALPHA,
        },
        "control": CONTROL_STRIKE,
        "cells": cells,
        "nulls": nulls,
        "gates": gates,
        "decisions": decisions,
        "verdict": {
            "any_ship_ready": bool(ship_ready_cells), "ship_ready_cells": ship_ready_cells,
            "winner": winner, "null_result": (winner is None),
            "control_floor_collision": {
                "floor_clearance_rate": control.get("floor_clearance_rate"),
                "floor_clearance_rate_afternoon": control.get("floor_clearance_rate_afternoon"),
                "note": "OTM-3's own floor-clearance rate -- the incident this study investigates.",
            },
        },
        "disclosures": [
            "MEASURED (real OPRA local cache), not REALIZED -- scorecard/simulation-replay artifact, "
            "no broker fills exist for these strike/floor combinations.",
            "Signals with no recoverable trigger_level fall back to SS-B's premium-only "
            "catastrophe-cap behavior (never dropped for that reason), per structure_stop_study's "
            "documented fallback contract -- same convention every study in this lineage uses.",
            "min_entry_premium floor is checked against the RAW entry-bar OPEN premium (before "
            "entry slippage) -- the same fill-price proxy every study in this lineage treats as "
            "the plan-time premium; friction is applied only to trades that clear the floor.",
            "edge_capture_rel (anchor gate) uses the account-agnostic J_WINNERS/J_LOSERS SPY-price-"
            "level pattern anchor (t4_exit_matrix.battery) at QTY=5 -- NOT directly comparable to "
            "OP-16's $1542 absolute or the Safe studies' QTY=10 figures (disclosed, not conflated); "
            "the gate itself (candidate_ecr >= control_ecr) is scale-invariant within this study.",
            "Random-entry null is SEED-LEVEL (20 seeds, add-one empirical p_null over seed means), "
            "drawn from Bold's OWN (09:35,15:00) ET entry gate and routed through the identical "
            "shape/time-stop/floor gate as the real cells -- distinct from a generic coin-flip.",
            "Risk-cap notional clamps (per_trade_risk_cap_pct, daily_loss_kill_switch_pct) are NOT "
            "modeled -- same disclosed gap every strike-AB study in this lineage carries.",
            "ONE process, no multiprocessing.Pool (see prereg method.process_note) -- the in-memory "
            "per-symbol OPRA bar cache is process-local; concurrent workers would multiply cache "
            "misses, not parallelize usefully, on this data source.",
        ],
        "runtime_seconds": elapsed_total,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({elapsed_total}s total)")
    log(f"VERDICT: any_ship_ready={bool(ship_ready_cells)} winner={winner} "
       f"ship_ready_cells={ship_ready_cells}")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# BOLD strike-axis A/B — BOLD-STRIKE-X-FLOOR-COLLISION")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/bold_strike_axis_ab.py`. "
             f"Pre-reg: `{out['prereg_path']}`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE RUN — reduced signal count + seeds, pipeline verification only, "
                 "NOT a decision-grade result.**")
    L.append("")
    sc_ = out["signal_cohort"]
    L.append(f"**Signal cohort:** n={sc_['n_raw']} (call/bull={sc_['n_call_bull']}, "
             f"put/bear={sc_['n_put_bear']}). Control: **{out['control']}** (Bold's current live "
             f"<$2K tier).")
    L.append("")
    ms = out["method_summary"]
    L.append(f"**Method:** SS-B exit shape (structure-stop chart layer ON) + honest friction + "
             f"time_stop={ms['time_stop_et']} ET + qty={ms['qty']} (Bold's real live size) + "
             f"min_entry_premium floor={ms['min_entry_premium_floor']} applied IN-SIM + BH-FDR "
             f"(alpha={ms['bh_fdr_alpha']}) across all 6 cells.")
    L.append("")
    L.append("## Per-cell table")
    L.append("")
    L.append("| strike | n | exp $/tr | OOS exp $/tr | WR | OOS+ | WF | sub_win | anchor_ok | "
             "bh_survivor | floor_clear | floor_clear_PM | n_opp | n_opp_PM |")
    L.append("|---|--:|--:|--:|--:|:--:|--:|:--:|:--:|:--:|--:|--:|--:|--:|")
    for lbl, _so in [("OTM-3", None), ("OTM-2", None), ("OTM-1", None), ("ATM", None),
                     ("ITM-1", None), ("ITM-2", None)]:
        c = out["cells"][lbl]
        g = out["gates"][lbl]
        L.append(f"| {lbl}{' (control)' if lbl == out['control'] else ''} | {c['n']} | "
                 f"${c['expectancy']} | ${c['oos_expectancy']} | {c['wr']} | {c['oos_positive']} | "
                 f"{c['wf']} | {c['sub_window_stable']} | {g['anchor_no_regression']} | "
                 f"{c.get('bh_fdr_survivor')} | {c['floor_clearance_rate']} | "
                 f"{c['floor_clearance_rate_afternoon']} | {c['n_opportunities']} | "
                 f"{c['n_afternoon_opportunities']} |")
    L.append("")
    L.append("## Decisions (per candidate, vs OTM-3 control)")
    L.append("")
    for lbl, _so in [("OTM-2", None), ("OTM-1", None), ("ATM", None), ("ITM-1", None), ("ITM-2", None)]:
        d = out["decisions"][lbl]
        L.append(f"- **{lbl}**: beats_control_OOS={d['beats_control_oos']}, "
                 f"can_actually_trade={d['can_actually_trade']}, **ship_ready={d['ship_ready']}**"
                 + (f" -- fails: {d['fails']}" if d["fails"] else ""))
    L.append("")
    v = out["verdict"]
    L.append("## Verdict")
    L.append("")
    if v["any_ship_ready"]:
        L.append(f"**SHIP-READY candidate(s): {v['ship_ready_cells']}. Winner (highest OOS "
                 f"expectancy, tie-break floor-clearance-PM): {v['winner']}.**")
    else:
        L.append("**NULL RESULT — no candidate clears beats-control-OOS + all 5 ratification "
                 "gates + >=70% floor clearance (overall AND afternoon). Valid outcome, reported "
                 "honestly, not a study failure.**")
    cfc = v["control_floor_collision"]
    L.append("")
    L.append(f"OTM-3 control's own floor-collision: floor_clearance_rate={cfc['floor_clearance_rate']}, "
             f"floor_clearance_rate_afternoon={cfc['floor_clearance_rate_afternoon']}.")
    L.append("")
    L.append("**Live flip deferred per task instruction** — this study does NOT flip "
             "`crypto/lib/strike_selection.py#V15_BOLD_TIERS` or `aggressive/params.json` tonight "
             "regardless of verdict; recommendation only, for a same-morning J REVOKE window.")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
