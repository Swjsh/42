"""filter5_ribbon_fate_2026_07_31 -- measure what FILTER 5 (the ribbon MA-stack veto) costs,
then decide its fate on evidence.

FROZEN PRE-REG: analysis/recommendations/prereg-filter5-ribbon-2026-07-31.json
(FILTER5-RIBBON-MA-STACK-FATE-2026-07-31, frozen 2026-07-31 17:34 ET, BEFORE this file ran).
Read that file for the hypothesis, arms, cohorts, gates and ship rule; this module is the
RUNNER, not a second copy of the spec.

WHAT FILTER 5 IS (read from backtest/lib/filters.py this session, not from memory):
  BULL (line ~1174):  ribbon_now.stack != "BULL"  -> blockers.append(5)
  BEAR (line ~1506):  not (stack == "BEAR" or structure_shift)  -> blockers.append(5)
  stack is the Saty Pivot Ribbon (EMA 13 / 20 / 48 on 5-min SPY closes, backtest/lib/ribbon.py)
  and demands a STRICT fast>pivot>slow (or fast<pivot<slow) ordering AT THE TRIGGER BAR.
  Anything else is "MIXED" and vetoes the trade.

WHY THIS EXISTS: on 2026-07-31 J called a long off the 737.68 low at 10:15 ET. Bull score hit
9-10/11, the level was tracked, a wick_reclaim shadow signal fired at 10:21 -- and the counted
path was blocked on FILTER 5, which flipped BULL->MIXED at 10:16 and never restacked through a
+4.82 bounce. It blocked all 5 live arms. That is n=1 and proves nothing on its own; this
module measures the gate over the whole population instead.

METHOD (three arms, one shared population, real exits):
  CONTROL  run_backtest(**SAFE_BASE_LIVE) -- live production config.
  ARM_A    CONTROL + disable_filters=[5]           -- delete filter 5 outright (both sides).
  ARM_B    CONTROL + filter5_level_anchored_bypass -- remove blocker 5 (and charge a -1 score
           demerit) ONLY for setups carrying a static-level-tied trigger. Shaped exactly like
           the 2026-05-09 trendline_only_setup precedent that already strips 5/8/9 in
           production for trendline-only bear setups.
  ARM_C    NOT RUN. The structure-shift-as-filter-5-replacement was already pre-registered and
           tested on 2026-07-28 (structure-shift-cascade-ab-2026-07-28.json): delta -$46,
           g1/g3/g4/g5 FAIL. Re-running it would be retesting a graveyard entry. Cited in the
           scorecard's `arm_c_not_run` block rather than silently omitted.

ARM_B PLUMBING: the flag lives in filters.py (default False, byte-identical when off, guarded
by backtest/tests/test_filter5_level_anchored_bypass.py, RED-proofed against 3 mutants). It is
deliberately NOT yet threaded through run_backtest / engine_cli / params.json -- production
wiring is built only if the arm WINS, never speculatively. The arm is run here by a pure
pass-through monkeypatch that injects the kwarg into orch_mod.evaluate_* (the same technique
structure_shift_cascade_ab.py uses for candidate capture; originals restored in `finally`).

EXITS: every entry in every arm is re-walked through the REAL live exit core
(automation/state/fleet/exit_manager.plan_exit_actions via lib/exit_manager_walk) with the
RIBBON_RIDE registry exit shape. Each arm's own run_backtest `dollar_pnl` is DISCARDED --
simulate_trade_real is known-divergent from the live exit manager (2026-07-09 sim-parity scar).
entry+1 convention is enforced by walk_exit_manager itself (first bar STRICTLY after entry).

P&L: real cached OPRA contracts ONLY. Contracts with no cached CSV are excluded and COUNTED
per arm; nothing is Black-Scholes-synthesized into a total.

Run: backtest/.venv/Scripts/python.exe backtest/tools/filter5_ribbon_fate_2026_07_31.py
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import engine_fullhist_replay as efr  # noqa: E402 -- SAFE_BASE_LIVE, ribbon lookup, TIME_STOP_ET
import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- entry_date, classify_tier
import strategies as fleet_strategies  # noqa: E402
import lib.orchestrator as orch_mod  # noqa: E402
import lib.engine.score as score_mod  # noqa: E402 -- holds its OWN by-name bindings (score.py:66)
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402

DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY = DATA / "spy_5m_2026-05-19_2026-07-31.csv"
NEW_VIX = DATA / "vix_5m_2026-05-19_2026-07-31.csv"
OLD_WINDOW_END = dt.date(2026, 7, 22)
FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 31)

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-filter5-ribbon-2026-07-31.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "filter5-ribbon-2026-07-31.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "filter5-ribbon-2026-07-31.md"

RECENT_TRADING_DAYS = 25          # backtest/autoresearch/recency_check.py convention
RUNNER_NO_REGRESSION_FLOOR = 0.95  # G4
FIRE_FLOOR_FULL = 10               # G5
FIRE_FLOOR_RECENT = 2              # G5


# ARM_B's ACTUAL measured result from the 2026-07-31 run, recorded verbatim so the scorecard
# still reports the cell after the flag was reverted out of filters.py. Every number here was
# produced by this same script with the flag present -- transcribed, not estimated. Delete this
# constant only together with the graveyard entry it documents.
ARM_B_RUN_2026_07_31 = {
    "arm": "ARM_B_level_anchored_bypass",
    "status": "RUN_2026_07_31_THEN_FLAG_REVERTED",
    "measured_identical_to_ARM_A": True,
    "raw_entries": 229, "real_opra_walks": 204,
    "full": {"delta_total": 738.60, "n_added": 21, "n_dropped": 8},
    "recent25": {"delta_total": -68.00, "n_added": 3, "n_dropped": 0},
    "gates": {
        "G1_recent_window_positive": {"delta_total_recent": -68.0, "pass": False},
        "G2_day_majority_recent": {"improved": 1, "worsened": 1, "pass": False},
        "G3_survives_drop_best_recent": {"delta_minus_best": -122.0, "pass": False},
        "G4_runner_anchor_no_regression": {"control_n": 39, "arm_n": 39, "pass": True},
        "G5_fire_count": {"n_added_full": 21, "n_added_recent": 3, "pass": True},
    },
    "all_gates_pass": False,
    "verdict": "NULL",
    "why_identical_to_arm_a": (
        "Structural, not coincidental. detect_ribbon_flip_bullish requires "
        "ribbon_history[-1].stack == 'BULL' (filters.py ~796), so when filter 5 blocks a bull "
        "setup the ribbon_flip trigger CANNOT be in its trigger set -- min_triggers=2 must "
        "therefore have been met by {level_reclaim, confluence, sequence_reclaim}. Every bull "
        "setup filter 5 alone blocks is level-anchored BY CONSTRUCTION. On the bear side the "
        "trendline-only cohort already has its own filter-5 relaxation (2026-05-09). Scoping "
        "the bypass to level-anchored setups therefore excludes nothing that deletion admits."
    ),
}


def log(msg: str) -> None:
    print(f"[filter5-fate] {msg}", flush=True)


def naive_dt(ts) -> dt.datetime:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.replace(tzinfo=None)
    return ts


# ============================================================================== data

def load_extended_data():
    """OLD full-history file + the strictly-later tail of the newest file.

    VIX's timestamp_et is deliberately left as a RAW STRING column: this CSV spans a DST
    transition, and pre-parsing it with pd.to_datetime (without utc=True) yields an
    object-dtype column of Timestamps that fails run_backtest's own is_datetime64_any_dtype
    branch and silently changes P&L. Root-caused in structure_shift_cascade_ab.py lines
    286-297 -- do not "fix" this.
    """
    spy_old = pd.read_csv(OLD_SPY)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))

    vix_old = pd.read_csv(OLD_VIX)
    vix_new = pd.read_csv(NEW_VIX)
    _vix_new_dates = pd.to_datetime(vix_new["timestamp_et"]).dt.date
    vix_tail = vix_new[_vix_new_dates > OLD_WINDOW_END].reset_index(drop=True)
    vix_df = pd.concat([vix_old, vix_tail], ignore_index=True)
    return spy_df, vix_df


def recent_window_dates(spy_df: pd.DataFrame, n: int = RECENT_TRADING_DAYS) -> set:
    days = sorted({d for d in spy_df["timestamp_et"].dt.date if d <= FULL_END})
    return set(days[-n:])


# ============================================================================== arms

def run_arm(label: str, spy_df, vix_df, *, disable_filters=None,
            level_anchored_bypass: bool = False, capture_blockers5: bool = False):
    """One arm. Monkeypatches the evaluate_* bindings as a PURE PASS-THROUGH -- it either
    injects the ARM_B kwarg or records blockers==[5] bars, never alters a result. Originals
    restored in `finally` regardless of outcome.

    BOTH module bindings are patched, deliberately: `lib.orchestrator` and `lib.engine.score`
    each did `from .filters import evaluate_*` (score.py:66), so they hold INDEPENDENT
    references. run_backtest cross-checks its own scoring against engine.score_bar on every
    bar (`_ENGINE_SCORE_ASSERT`, orchestrator.py:1040) -- patching only the orchestrator side
    makes that assert fire on bar 48 of the first day. Patching both keeps the parity
    assertion LIVE and meaningful for every arm rather than switching it off via
    GAMMA_ENGINE_SCORE_ASSERT=0: the assert is now a free, per-bar proof that the two scoring
    paths agree under the treatment too, not just under CONTROL.
    """
    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup
    assert score_mod.evaluate_bearish_setup is orig_bear, (
        "lib.engine.score no longer shares filters.evaluate_bearish_setup with lib.orchestrator "
        "-- the dual patch below would be scoring two different functions"
    )
    assert score_mod.evaluate_bullish_setup is orig_bull, (
        "lib.engine.score no longer shares filters.evaluate_bullish_setup with lib.orchestrator"
    )
    cand = {"bear": [], "bull": []}

    def _bear(ctx, **kw):
        if level_anchored_bypass:
            kw = dict(kw, filter5_level_anchored_bypass=True)
        res = orig_bear(ctx, **kw)
        if capture_blockers5 and res.blockers == [5]:
            cand["bear"].append({
                "date": ctx.timestamp_et.date().isoformat(),
                "timestamp_et": ctx.timestamp_et.isoformat(),
                "score": res.bear_score,
                "triggers": list(res.triggers_fired),
                "level": res.rejection_level,
                "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
            })
        return res

    def _bull(ctx, **kw):
        if level_anchored_bypass:
            kw = dict(kw, filter5_level_anchored_bypass=True)
        res = orig_bull(ctx, **kw)
        if capture_blockers5 and res.blockers == [5]:
            cand["bull"].append({
                "date": ctx.timestamp_et.date().isoformat(),
                "timestamp_et": ctx.timestamp_et.isoformat(),
                "score": res.bull_score,
                "triggers": list(res.triggers_fired),
                "level": res.reclaim_level,
                "ribbon_stack": ctx.ribbon_now.stack if ctx.ribbon_now is not None else None,
            })
        return res

    kwargs = dict(efr.SAFE_BASE_LIVE)
    if disable_filters is not None:
        kwargs["disable_filters"] = disable_filters

    orch_mod.evaluate_bearish_setup = _bear
    orch_mod.evaluate_bullish_setup = _bull
    score_mod.evaluate_bearish_setup = _bear
    score_mod.evaluate_bullish_setup = _bull
    t0 = time.time()
    try:
        r = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **kwargs)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
        score_mod.evaluate_bearish_setup = orig_bear
        score_mod.evaluate_bullish_setup = orig_bull
    log(f"  {label}: {len(r.trades)} raw entries in {time.time() - t0:.1f}s")
    return r, cand


# ============================================================================== exits

def derive_rows(label: str, r, spy_df: pd.DataFrame, ribbon_lookup, exit_shape: dict):
    """Re-walk every entry through the REAL exit manager. Byte-identical machinery to
    engine_fullhist_replay.py's own loop."""
    rows, skipped = [], {"no_opra": 0, "no_spy_day": 0}
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            skipped["no_opra"] += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            skipped["no_spy_day"] += 1
            continue
        entry_time_et = naive_dt(t.entry_time_et)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=efr.ribbon_tick_df_for(opt_df, ribbon_lookup),
            five_min_spy_df=day_spy,
        )
        rows.append({
            "arm": label, "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "side": t.side, "setup": t.setup, "tier": eb.classify_tier(t.triggers_fired),
            "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": list(t.triggers_fired), "level": trigger_level,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
        })
    log(f"  {label}: {len(rows)} real-OPRA walks "
        f"(excluded: no_opra={skipped['no_opra']} no_spy_day={skipped['no_spy_day']})")
    return rows, skipped


# ============================================================================== stats

def _key(row) -> tuple:
    """Trade identity for the control/arm diff: same day, same entry instant, same contract."""
    return (row["date"], row["entry_time_et"], row["symbol"], row["side"])


def cohort_stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "total": 0.0, "wr": None, "per_trade": None,
                "total_ex_best": None, "n_days": 0}
    pnls = [r["dollar_pnl"] for r in rows]
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": len(rows),
        "total": total,
        "wr": round(wins / len(rows), 4),
        "per_trade": round(total / len(rows), 2),
        "total_ex_best": round(total - max(pnls), 2),
        "n_days": len({r["date"] for r in rows}),
    }


def window_slice(rows: list[dict], dates: Optional[set]) -> list[dict]:
    if dates is None:
        return rows
    return [r for r in rows if dt.date.fromisoformat(r["date"]) in dates]


def runner_cohort(rows: list[dict]) -> dict:
    sel = [r for r in rows
           if "runner" in (r["exit_reason"] or "").lower() or "trail" in (r["exit_reason"] or "").lower()]
    return {"n": len(sel), "total": round(sum(r["dollar_pnl"] for r in sel), 2)}


def score_arm(label: str, control_rows: list[dict], arm_rows: list[dict],
              recent_dates: set) -> dict:
    ctrl_by_key = {_key(r): r for r in control_rows}
    arm_by_key = {_key(r): r for r in arm_rows}
    added_keys = [k for k in arm_by_key if k not in ctrl_by_key]
    dropped_keys = [k for k in ctrl_by_key if k not in arm_by_key]
    added = [arm_by_key[k] for k in added_keys]
    dropped = [ctrl_by_key[k] for k in dropped_keys]

    out = {"arm": label}
    for wname, wdates in (("full", None), ("recent25", recent_dates)):
        c = window_slice(control_rows, wdates)
        a = window_slice(arm_rows, wdates)
        c_total = round(sum(r["dollar_pnl"] for r in c), 2)
        a_total = round(sum(r["dollar_pnl"] for r in a), 2)
        w_added = window_slice(added, wdates)
        w_dropped = window_slice(dropped, wdates)
        # per-day delta over days whose book changed
        changed_days = sorted({r["date"] for r in w_added} | {r["date"] for r in w_dropped})
        day_deltas = {}
        for d in changed_days:
            cd = sum(r["dollar_pnl"] for r in c if r["date"] == d)
            ad = sum(r["dollar_pnl"] for r in a if r["date"] == d)
            day_deltas[d] = round(ad - cd, 2)
        n_up = sum(1 for v in day_deltas.values() if v > 0)
        n_dn = sum(1 for v in day_deltas.values() if v < 0)
        # drop-best: remove the single largest positive contributor among ADDED trades
        delta = round(a_total - c_total, 2)
        best_added = max((r["dollar_pnl"] for r in w_added), default=0.0)
        out[wname] = {
            "control": {"n": len(c), "total": c_total},
            "arm": {"n": len(a), "total": a_total},
            "delta_total": delta,
            "n_added": len(w_added), "n_dropped": len(w_dropped),
            "added_stats": cohort_stats(w_added),
            "dropped_stats": cohort_stats(w_dropped),
            "n_changed_days": len(changed_days), "n_days_improved": n_up, "n_days_worsened": n_dn,
            "day_deltas": day_deltas,
            "best_added_trade": round(best_added, 2),
            "delta_minus_best_added": round(delta - best_added, 2),
        }
    out["runner_cohort"] = {
        "control": runner_cohort(control_rows),
        "arm": runner_cohort(arm_rows),
    }
    rc, ra = out["runner_cohort"]["control"], out["runner_cohort"]["arm"]
    out["gates"] = {
        "G1_recent_window_positive": {
            "delta_total_recent": out["recent25"]["delta_total"],
            "pass": out["recent25"]["delta_total"] > 0},
        "G2_day_majority_recent": {
            "improved": out["recent25"]["n_days_improved"],
            "worsened": out["recent25"]["n_days_worsened"],
            "pass": out["recent25"]["n_days_improved"] > out["recent25"]["n_days_worsened"]},
        "G3_survives_drop_best_recent": {
            "delta_minus_best": out["recent25"]["delta_minus_best_added"],
            "pass": out["recent25"]["delta_minus_best_added"] > 0},
        "G4_runner_anchor_no_regression": {
            "control_n": rc["n"], "arm_n": ra["n"],
            "control_total": rc["total"], "arm_total": ra["total"],
            "pass": (ra["n"] >= rc["n"] * RUNNER_NO_REGRESSION_FLOOR
                     and ra["total"] >= rc["total"] * RUNNER_NO_REGRESSION_FLOOR)},
        "G5_fire_count": {
            "n_added_full": out["full"]["n_added"], "n_added_recent": out["recent25"]["n_added"],
            "floor_full": FIRE_FLOOR_FULL, "floor_recent": FIRE_FLOOR_RECENT,
            "pass": (out["full"]["n_added"] >= FIRE_FLOOR_FULL
                     and out["recent25"]["n_added"] >= FIRE_FLOOR_RECENT)},
    }
    out["all_gates_pass"] = all(g["pass"] for g in out["gates"].values())
    out["verdict"] = "SHIP_CANDIDATE" if out["all_gates_pass"] else "NULL"
    return out


def attribution_block(control_rows: list[dict], arm_rows: list[dict]) -> dict:
    """WHERE the headline delta actually comes from — the artifact hunt, run before reporting.

    A raw '+$738.60 from deleting filter 5' invites the wrong conclusion. This decomposes it
    into (i) the trades filter 5 was actually blocking and (ii) control trades that merely
    VANISH because an unlocked earlier entry consumed the one-position-at-a-time slot /
    escalation lock. Only (i) is evidence about the gate; (ii) is position-sequencing luck.
    Also reports the exit-reason mix of the added cohort against the control book's, because
    that is where the mechanism shows itself.
    """
    from collections import Counter

    ck = {_key(r) for r in control_rows}
    ak = {_key(r) for r in arm_rows}
    added = [r for r in arm_rows if _key(r) not in ck]
    dropped = [r for r in control_rows if _key(r) not in ak]
    added_days = {r["date"] for r in added}
    dropped_days = {r["date"] for r in dropped}

    def mix(rows):
        c = Counter((r["exit_reason"] or "").split(" @")[0] for r in rows)
        n = max(1, len(rows))
        return {k: {"n": v, "pct": round(100.0 * v / n, 1)} for k, v in c.most_common()}

    add_total = round(sum(r["dollar_pnl"] for r in added), 2)
    drop_total = round(sum(r["dollar_pnl"] for r in dropped), 2)
    return {
        "_doc": "Decomposition of the full-window delta. delta_total == added_total - dropped_total.",
        "added_total_the_gate_was_blocking_this": add_total,
        "dropped_total_preempted_not_blocked": drop_total,
        "delta_from_preemption": round(-drop_total, 2),
        "pct_of_delta_from_preemption": (
            round(100.0 * (-drop_total) / (add_total - drop_total), 1)
            if (add_total - drop_total) else None),
        "dropped_days_that_also_gained_a_trade": {
            "n": len(dropped_days & added_days), "of": len(dropped_days),
            "days": sorted(dropped_days & added_days)},
        "added_exit_reason_mix": mix(added),
        "control_exit_reason_mix": mix(control_rows),
        "finding": (
            "The gate's own block-set (the ADDED cohort) is worth ~$0/trade. Essentially ALL of "
            "the positive full-window delta is pre-emption: unlocked entries occupy the "
            "single-position slot and prevent later CONTROL losers from ever being taken, on "
            "days that also carry an added trade. That is a sequencing side-effect, not "
            "evidence that filter 5 blocks money. Separately, the added cohort's exit mix is "
            "dominated by ribbon_flip_back versus the control book's premium_stop -- entries "
            "admitted against a non-stacked ribbon are closed by the ribbon-flip EXIT almost "
            "immediately. The entry veto and the exit rule read the SAME lagging indicator, so "
            "removing the veto alone mostly manufactures round-trips."),
    }


# ============================================================================== main

def main() -> int:
    t_start = time.time()
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"pre-reg {prereg['prereg_id']} frozen {prereg['frozen_at_et']}")

    spy_df, vix_df = load_extended_data()
    log(f"data: spy rows={len(spy_df)} "
        f"{spy_df['timestamp_et'].min()} .. {spy_df['timestamp_et'].max()}")
    recent_dates = recent_window_dates(spy_df)
    log(f"recent window = {len(recent_dates)} trading days "
        f"{min(recent_dates)} .. {max(recent_dates)}")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"exit shape (strategies.py#RIBBON_RIDE): {exit_shape}")

    log("CONTROL: run_backtest(**SAFE_BASE_LIVE) + blockers==[5] capture")
    r_ctrl, cand = run_arm("CONTROL", spy_df, vix_df, capture_blockers5=True)
    log("ARM_A: disable_filters=[5]")
    r_a, _ = run_arm("ARM_A", spy_df, vix_df, disable_filters=[5])

    # ARM_B is run ONLY if the scoped-bypass flag exists in filters.py. It was implemented,
    # guard-tested, RED-proofed and RUN on 2026-07-31 -- and measured BYTE-IDENTICAL to ARM_A
    # (229 raw entries, 204 real-OPRA walks, full delta +$738.60, recent delta -$68.00, same
    # 21 added / 8 dropped trades). That equivalence is STRUCTURAL, not a coincidence: when the
    # bull ribbon is not BULL-stacked, detect_ribbon_flip_bullish cannot fire (it requires
    # ribbon_history[-1].stack == "BULL"), so every bull setup filter 5 alone blocks must have
    # reached min_triggers=2 via {level_reclaim, confluence, sequence_reclaim} -- it is
    # level-anchored BY CONSTRUCTION. On the bear side the trendline-only cohort already has
    # its own filter-5 relaxation. Scoping therefore excludes NOTHING that deletion admits.
    # Because the arm nulled AND is provably redundant with an existing production kwarg, the
    # flag was REVERTED out of filters.py rather than left as a dead default-off knob in the
    # repo's most consumer-heavy hot-path file (C14). ARM_A alone reproduces the entire
    # finding. To re-measure ARM_B, re-add the flag and this block runs itself again.
    _bull_sig = inspect.signature(orch_mod.evaluate_bullish_setup).parameters
    arm_b_available = "filter5_level_anchored_bypass" in _bull_sig
    if arm_b_available:
        log("ARM_B: filter5_level_anchored_bypass=True")
        r_b, _ = run_arm("ARM_B", spy_df, vix_df, level_anchored_bypass=True)
    else:
        log("ARM_B: SKIPPED -- flag not present in filters.py (reverted after nulling; "
            "measured byte-identical to ARM_A on 2026-07-31, see module docstring)")
        r_b = None

    log("walking exits through the REAL exit_manager")
    ctrl_rows, ctrl_skip = derive_rows("CONTROL", r_ctrl, spy_df, ribbon_lookup, exit_shape)
    a_rows, a_skip = derive_rows("ARM_A", r_a, spy_df, ribbon_lookup, exit_shape)
    if r_b is not None:
        b_rows, b_skip = derive_rows("ARM_B", r_b, spy_df, ribbon_lookup, exit_shape)
    else:
        b_rows, b_skip = None, None

    def cand_stats(side: str) -> dict:
        rows = cand[side]
        recent = [c for c in rows if dt.date.fromisoformat(c["date"]) in recent_dates]
        return {
            "n_bars_full": len(rows), "n_days_full": len({c['date'] for c in rows}),
            "n_bars_recent25": len(recent), "n_days_recent25": len({c['date'] for c in recent}),
            "sample_recent": recent[-8:],
        }

    scored = {"ARM_A_delete": score_arm("ARM_A_delete", ctrl_rows, a_rows, recent_dates)}
    if b_rows is not None:
        scored["ARM_B_level_anchored_bypass"] = score_arm(
            "ARM_B_level_anchored_bypass", ctrl_rows, b_rows, recent_dates)
    else:
        scored["ARM_B_level_anchored_bypass"] = ARM_B_RUN_2026_07_31

    out = {
        "_doc": __doc__,
        "generated_at_et": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prereg_path": str(PREREG_PATH.relative_to(ROOT)).replace("\\", "/"),
        "prereg_id": prereg["prereg_id"],
        "prereg_frozen_at_et": prereg["frozen_at_et"],
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                   "recent_n_days": len(recent_dates),
                   "recent_start": min(recent_dates).isoformat(),
                   "recent_end": max(recent_dates).isoformat()},
        "filter_5_definition": prereg["filter_5_definition_as_read"],
        "provenance_finding": prereg["provenance_finding_stated_before_measurement"],
        "arm_c_not_run": prereg["arms_frozen"]["ARM_C_structure_shift_replacement"],
        "cohort_A_blocked_by_filter5_alone": {
            "_doc": "Bars where filter 5 was the ONLY blocker -- captured during the CONTROL "
                    "run by a pure pass-through monkeypatch. These are raw SIGNAL bars, not "
                    "trades: the engine's escalation lock / one-position-at-a-time rules mean "
                    "only some become entries. The REALIZED version of this cohort is each "
                    "arm's `added_stats` below, which is walked through real exits.",
            "bear": cand_stats("bear"), "bull": cand_stats("bull"),
        },
        "cohort_B_allowed_by_filter5": {
            "_doc": "CONTROL's own entered book -- every trade taken WITH filter 5 satisfied.",
            "full": cohort_stats(ctrl_rows),
            "recent25": cohort_stats(window_slice(ctrl_rows, recent_dates)),
            "runner_cohort": runner_cohort(ctrl_rows),
        },
        "opra_exclusions": {"CONTROL": ctrl_skip, "ARM_A": a_skip, "ARM_B": b_skip,
                            "note": "excluded from every total, never BS-synthesized"},
        "arms": scored,
        "attribution": attribution_block(ctrl_rows, a_rows),
        "gates_frozen": prereg["gates_frozen"],
        "ship_rule": prereg["ship_rule"],
        "trades": {k: v for k, v in
                   (("CONTROL", ctrl_rows), ("ARM_A", a_rows), ("ARM_B", b_rows))
                   if v is not None},
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"done in {time.time() - t_start:.1f}s")

    for name, s in scored.items():
        log(f"{name}: full delta ${s['full']['delta_total']:+,.2f} | "
            f"recent25 delta ${s['recent25']['delta_total']:+,.2f} | "
            f"added {s['full']['n_added']} | verdict {s['verdict']}")
    return 0


def write_markdown(out: dict) -> None:
    L = []
    L.append("# FILTER 5 (ribbon MA-stack) — cost measurement + fate decision (2026-07-31)")
    L.append("")
    L.append(f"Pre-reg `{out['prereg_path']}` frozen **{out['prereg_frozen_at_et']}**, before any run. "
             f"Runner: `backtest/tools/filter5_ribbon_fate_2026_07_31.py`.")
    L.append("")
    L.append("## What filter 5 is")
    fd = out["filter_5_definition"]
    L.append(f"- **BULL** (`filters.py:{fd['bull_path_line']}`): `{fd['bull_rule']}`")
    L.append(f"- **BEAR** (`filters.py:{fd['bear_path_line']}`): `{fd['bear_rule']}`")
    L.append(f"- Ribbon: {fd['ribbon_definition']}")
    L.append(f"- Existing precedent: {fd['existing_scoped_bypass_precedent']}")
    L.append("")
    L.append("## Provenance")
    pf = out["provenance_finding"]
    L.append(f"**{pf['claim']}**")
    for e in pf["evidence_checked"]:
        L.append(f"- {e}")
    L.append(f"\n{pf['consequence']}")
    L.append("")
    L.append("## Cohort A — setups filter 5 blocked ALONE (blockers == [5])")
    ca = out["cohort_A_blocked_by_filter5_alone"]
    L.append("")
    L.append("| side | bars (full) | days (full) | bars (recent 25d) | days (recent) |")
    L.append("|---|--:|--:|--:|--:|")
    for side in ("bull", "bear"):
        s = ca[side]
        L.append(f"| {side} | {s['n_bars_full']} | {s['n_days_full']} | "
                 f"{s['n_bars_recent25']} | {s['n_days_recent25']} |")
    L.append("")
    L.append("## Cohort B — the book filter 5 ALLOWED (CONTROL)")
    cb = out["cohort_B_allowed_by_filter5"]
    L.append("")
    L.append("| window | n | total | WR | per-trade | total ex-best |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for w in ("full", "recent25"):
        s = cb[w]
        L.append(f"| {w} | {s['n']} | ${s['total']:,.2f} | {s['wr']} | "
                 f"${s['per_trade']:,.2f} | ${s['total_ex_best']:,.2f} |")
    L.append("")
    L.append("## Where the delta actually comes from (artifact hunt)")
    at = out["attribution"]
    L.append("")
    L.append(f"- Trades filter 5 was ACTUALLY blocking (added cohort): **${at['added_total_the_gate_was_blocking_this']:,.2f}**")
    L.append(f"- Control trades that merely VANISH (pre-empted by an unlocked earlier entry): "
             f"${at['dropped_total_preempted_not_blocked']:,.2f} -> contributes "
             f"**${at['delta_from_preemption']:+,.2f}** ({at['pct_of_delta_from_preemption']}% of the delta)")
    dd = at["dropped_days_that_also_gained_a_trade"]
    L.append(f"- Pre-empted days that also carry an added trade: **{dd['n']} of {dd['of']}**")
    L.append("")
    L.append("| exit reason | added cohort | control book |")
    L.append("|---|--:|--:|")
    for k in sorted(set(at["added_exit_reason_mix"]) | set(at["control_exit_reason_mix"])):
        a = at["added_exit_reason_mix"].get(k, {"n": 0, "pct": 0.0})
        c = at["control_exit_reason_mix"].get(k, {"n": 0, "pct": 0.0})
        L.append(f"| {k} | {a['n']} ({a['pct']}%) | {c['n']} ({c['pct']}%) |")
    L.append("")
    L.append(f"**{at['finding']}**")
    L.append("")
    L.append("## Arms")
    for name, s in out["arms"].items():
        if "full" not in s or "control" not in s.get("full", {}):
            L.append("")
            L.append(f"### {name} — **{s['verdict']}** ({s.get('status', '')})")
            L.append("")
            L.append(f"- full delta ${s['full']['delta_total']:+,.2f} "
                     f"(added {s['full']['n_added']}, dropped {s['full']['n_dropped']})")
            L.append(f"- recent25 delta ${s['recent25']['delta_total']:+,.2f} "
                     f"(added {s['recent25']['n_added']})")
            L.append(f"- gates: " + ", ".join(
                f"{g}={'PASS' if v['pass'] else 'FAIL'}" for g, v in s["gates"].items()))
            L.append("")
            L.append(f"{s['why_identical_to_arm_a']}")
            continue
        L.append("")
        L.append(f"### {name} — **{s['verdict']}**")
        L.append("")
        L.append("| window | control | arm | delta | added | dropped | days +/- |")
        L.append("|---|--:|--:|--:|--:|--:|:--|")
        for w in ("full", "recent25"):
            x = s[w]
            L.append(f"| {w} | ${x['control']['total']:,.2f} (n={x['control']['n']}) | "
                     f"${x['arm']['total']:,.2f} (n={x['arm']['n']}) | "
                     f"**${x['delta_total']:+,.2f}** | {x['n_added']} | {x['n_dropped']} | "
                     f"{x['n_days_improved']}/{x['n_days_worsened']} |")
        L.append("")
        add = s["full"]["added_stats"]
        L.append(f"Added-trade cohort (full window, real exits): n={add['n']} "
                 f"total=${add['total']:,.2f} WR={add['wr']} per-trade=${add['per_trade'] or 0:,.2f} "
                 f"ex-best=${add['total_ex_best'] or 0:,.2f}")
        L.append("")
        L.append("| gate | result | pass |")
        L.append("|---|---|:--:|")
        for gid, g in s["gates"].items():
            detail = ", ".join(f"{k}={v}" for k, v in g.items() if k != "pass")
            L.append(f"| {gid} | {detail} | {'PASS' if g['pass'] else 'FAIL'} |")
    L.append("")
    L.append("## ARM_C (structure-shift replacement) — not run")
    L.append("")
    L.append(out["arm_c_not_run"])
    L.append("")
    L.append("## Ship rule")
    L.append("")
    L.append(out["ship_rule"])
    L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
