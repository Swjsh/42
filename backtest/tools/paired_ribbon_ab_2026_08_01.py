"""paired_ribbon_ab_2026_08_01 -- WS4: the PAIRED ribbon change, the only honest "loosen
the ribbon" left after 2026-07-31.

FROZEN PRE-REG: analysis/recommendations/prereg-paired-ribbon-2026-08-01.json
(PAIRED-RIBBON-AB-2026-08-01, frozen 2026-08-01 12:43 ET, committed e5e323f2 BEFORE this
file existed). Read that file for hypothesis, cohort, gates and ship rule; this module is
the RUNNER, not a second copy of the spec.

THE CHANGE (one paired treatment, no grid):
  ENTRY  SCOPED per-bar bypass of filter 5 (ribbon MA-stack veto) via run_arm_scoped's
         monkeypatch: evaluate_* runs with PRODUCTION semantics first; only when the
         result's blockers == {5} EXACTLY and the setup carries a static-level-tied
         trigger is the bar re-evaluated with disable_filters=[5] (unblocking it, no
         demerit). Trendline-only setups keep their production bypass+demerit path
         BYTE-UNTOUCHED.
         AS-BUILT NOTE (first-run invariant catch, 2026-08-01 13:2x ET): the prereg's
         primary mechanism was plain disable_filters=[5], frozen together with a HARD
         INVARIANT (every added entry level-anchored) and the fallback "implement the
         scoped bypass if the invariant breaks". The invariant BROKE on first run: a
         trendline-only bear entry (2026-05-19 14:20 P737) was admitted by deletion.
         ROOT CAUSE (filters.py:1654-1657): the trendline-only chop demerit is charged
         only `if 5 in blockers` -- under disable_filters=[5] blocker 5 is never
         appended, the demerit silently vanishes, and trendline-only setups score +1
         higher than production. Deletion is therefore NOT equal to the scoped bypass
         (the 07-31 study's ARM_A/ARM_B equivalence narrative missed this crack; its
         NULL verdict is unaffected). The scoped wrapper below is the pre-registered
         fallback, engaged exactly as frozen.
  EXIT   every PAIRED-book trade carrying a static-level-tied trigger walks the REAL
         exit_manager with ribbon_flip_back structurally suppressed (ribbon_tick_df=None;
         plan_exit_actions consumes the flag at exactly its two exit-trigger sites,
         exit_manager.py:430+483, nothing else reads it). Non-level-anchored trades keep
         the standard walk. All other exit stages unchanged (structure_stop, -50%
         catastrophe, TP1, chandelier trail, runner_target, 15:40 time stop).

WHY PAIRED: filter5-ribbon-2026-07-31 found 76.2% of deletion-unlocked trades die on the
ribbon_flip_back EXIT (vs 9.9% of control book) -- entry veto and exit trigger read the
SAME lagging ribbon, so entry-only relaxation manufactures round-trips. That study's
closing note pre-registered exactly this paired arm as the only untested version.

MACHINERY: reused by IMPORT from filter5_ribbon_fate_2026_07_31 (run_arm monkeypatch with
dual-binding parity, cohort stats, attribution, OPRA measurability, G1 relabeling). New
code here: per-trade exit-suppression walk, exit-delta-aware changed-trade scoring, the
both-ways walk behind G5's exit-lever fire count, and the OPRA cache snapshot guard
(a backfill ran overnight; both arms must price against the identical cache).

Run: backtest/.venv/Scripts/python.exe backtest/tools/paired_ribbon_ab_2026_08_01.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
TOOLS = REPO / "tools"
for _p in (str(ROOT), str(REPO), str(TOOLS), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import filter5_ribbon_fate_2026_07_31 as f5  # noqa: E402 -- the reused cohort machinery
import engine_fullhist_replay as efr  # noqa: E402
import elite_bear_level_reject_gate_ab as eb  # noqa: E402
import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import CACHE_DIR, load_contract_bars, option_symbol  # noqa: E402

PREREG_PATH = ROOT / "analysis" / "recommendations" / "prereg-paired-ribbon-2026-08-01.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "paired-ribbon-2026-08-01.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "paired-ribbon-2026-08-01.md"

# Static-level-tied triggers (prereg cohort_definition; side-disjoint names, union is safe).
LEVEL_TIED_TRIGGERS = frozenset({
    "level_reclaim", "confluence", "sequence_reclaim",          # bull (filters.py:1265)
    "level_rejection", "fhh_level_rejection", "sequence_rejection",  # bear (1723 minus trendline)
})

# POPULATION COUNT CLARIFICATION (first-run assert fired 2026-08-01 13:0x ET, diagnosed
# before any fix): the frame contains 394 distinct dates = 391 FULL RTH sessions + 3 HALF
# DAYS (2025-07-03, 2025-11-28, 2025-12-24 early closes). The brief's "verified 391"
# counts full sessions; the FRAME -- byte-identical to the one filter5-ribbon-2026-07-31's
# CONTROL ran (both source CSVs untouched since 2026-07-31 14:16, mtime-verified) -- has
# always carried the half days. The frozen prereg file is NOT edited; this is a
# denominator-labeling clarification, not a population change, and the binding parity
# proof is CONTROL_RAW_ENTRY_ANCHOR below. Both asserts abort on ANY drift.
EXPECTED_FRAME_DATES = 394
EXPECTED_HALF_DAYS = frozenset({dt.date(2025, 7, 3), dt.date(2025, 11, 28),
                                dt.date(2025, 12, 24)})
CONTROL_RAW_ENTRY_ANCHOR = 211       # 07-31 run: 191 walked + 20 no_opra (cache-independent)
RUNNER_FLOOR = 1.00                  # G4 zero tolerance (prereg; stricter than 07-31's 0.95)
FIRE_FLOOR_FULL = 10                 # G5a
FIRE_FLOOR_RECENT = 2                # G5a
EXIT_LEVER_FIRE_FLOOR = 5            # G5b
PERM_SEED = 20260801
PERM_N = 10_000


def log(msg: str) -> None:
    print(f"[paired-ribbon] {msg}", flush=True)


def is_level_anchored(triggers) -> bool:
    return any(t in LEVEL_TIED_TRIGGERS for t in (triggers or []))


def raw_key(t) -> tuple:
    """Identity of a RAW run_backtest trade (pre-walk): mirrors f5._key's walked-row identity
    so raw and walked books diff on the same coordinates."""
    edate = eb.entry_date(t)
    return (edate.isoformat(), f5.naive_dt(t.entry_time_et).isoformat(),
            option_symbol(edate, int(t.strike), t.side), t.side)


# ============================================================== suppression self-test

def _suppression_self_test() -> None:
    """Prove the suppression mechanism BEFORE 400 walks build on it: the same entry, same
    bars, walked twice -- ribbon flipping against the position exits ribbon_flip_back with
    the ribbon feed attached and does NOT with ribbon_tick_df=None. Mirrors the standing
    pytest guard (backtest/tests/test_paired_ribbon_suppression_2026_08_01.py); repeated
    here so a direct module run can never proceed on a broken mechanism (C7)."""
    ts0 = dt.datetime(2026, 7, 1, 10, 0)
    n = 8
    opt = pd.DataFrame({
        "timestamp_et": [ts0 + dt.timedelta(minutes=5 * i) for i in range(n)],
        "open": [1.00] * n, "high": [1.02] * n, "low": [0.98] * n, "close": [1.00] * n,
    })
    ribbon = pd.DataFrame({"timestamp_et": opt["timestamp_et"], "stack": ["BULL"] * n})
    spy = pd.DataFrame({
        "timestamp_et": [ts0 - dt.timedelta(minutes=5)] + list(opt["timestamp_et"]),
        "close": [100.0] * (n + 1),
    })
    shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": 9.9, "tp1_qty_fraction": 0.667,
             "profit_lock_mode": "trailing", "runner_target_pct": 99.0}
    kw = dict(symbol="SPY260701P00100000", side="P", entry_time_et=ts0, entry_premium=1.0,
              qty=3, exit_shape=shape, structure_stop_enabled=False, trigger_level=None,
              strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
              opt_df=opt, five_min_spy_df=spy)
    with_ribbon = walk_exit_manager(ribbon_tick_df=ribbon, **kw)
    without = walk_exit_manager(ribbon_tick_df=None, **kw)
    assert with_ribbon.exit_reason == "ribbon_flip_back", (
        f"self-test: ribbon-attached walk should exit ribbon_flip_back, got "
        f"{with_ribbon.exit_reason!r}")
    assert "ribbon" not in (without.exit_reason or ""), (
        f"self-test: suppressed walk still exited on the ribbon: {without.exit_reason!r}")
    log("suppression self-test PASS (ribbon walk -> ribbon_flip_back; None walk -> "
        f"{without.exit_reason})")


# ============================================================== scoped entry arm

def run_arm_scoped(label: str, spy_df, vix_df):
    """PAIRED's entry arm: f5.run_arm's dual-binding monkeypatch pattern (same asserts,
    same finally-restore), but the wrapper implements the SCOPED filter-5 bypass instead
    of injecting kwargs:

      1. call the ORIGINAL evaluate_* with the caller's own kwargs -> production
         semantics, trendline-only demerit intact;
      2. iff set(result.blockers) == {5} AND the setup carries a static-level-tied
         trigger, re-evaluate the SAME bar with disable_filters=[5] -> the level-anchored
         setup unblocks with deletion semantics (no demerit), everything else untouched.

    Double-evaluation is side-effect-safe by construction: the production parity
    cross-check (_ENGINE_SCORE_ASSERT, orchestrator.py:1040) already drives every bar
    through both module bindings, so evaluate_* is exercised >=2x per bar in EVERY run.
    Both bindings get the same wrapper, keeping that parity assert live and meaningful.
    """
    import lib.orchestrator as orch_mod
    import lib.engine.score as score_mod

    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup
    assert score_mod.evaluate_bearish_setup is orig_bear, (
        "lib.engine.score no longer shares filters.evaluate_bearish_setup with "
        "lib.orchestrator -- dual patch would score two different functions")
    assert score_mod.evaluate_bullish_setup is orig_bull, (
        "lib.engine.score no longer shares filters.evaluate_bullish_setup")

    scoped_fires = {"bear": 0, "bull": 0}

    def _wrap(orig, side):
        def inner(ctx, **kw):
            res = orig(ctx, **kw)
            if set(res.blockers or []) == {5} and is_level_anchored(res.triggers_fired):
                scoped_fires[side] += 1
                merged = sorted(set(kw.get("disable_filters") or []) | {5})
                res = orig(ctx, **dict(kw, disable_filters=merged))
            return res
        return inner

    _bear = _wrap(orig_bear, "bear")
    _bull = _wrap(orig_bull, "bull")
    orch_mod.evaluate_bearish_setup = _bear
    orch_mod.evaluate_bullish_setup = _bull
    score_mod.evaluate_bearish_setup = _bear
    score_mod.evaluate_bullish_setup = _bull
    t0 = time.time()
    try:
        r = f5.run_backtest(spy_df, vix_df, start_date=f5.FULL_START, end_date=f5.FULL_END,
                            **efr.SAFE_BASE_LIVE)
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull
        score_mod.evaluate_bearish_setup = orig_bear
        score_mod.evaluate_bullish_setup = orig_bull
    log(f"  {label}: {len(r.trades)} raw entries in {time.time() - t0:.1f}s "
        f"(scoped-bypass re-evals: bear={scoped_fires['bear']} bull={scoped_fires['bull']}, "
        f"counts include the dual-binding parity double-visit)")
    return r, scoped_fires


# ============================================================== walks

def derive_rows_paired(label: str, r, spy_df: pd.DataFrame, ribbon_lookup, exit_shape: dict,
                       snapshot: frozenset,
                       suppress_pred: Callable[[object], bool],
                       dual_walk_suppressed: bool = False):
    """f5.derive_rows with three additions (everything else byte-equivalent):
      1. OPRA cache SNAPSHOT gate: a contract absent from the start-of-run snapshot is
         excluded (reason no_opra) even if a concurrent backfill wrote it mid-run.
      2. suppress_pred(t): True -> this trade walks with ribbon_tick_df=None.
      3. dual_walk_suppressed: suppressed trades are ALSO walked standard, recording
         (std_exit_reason, std_dollar_pnl) -- the G5b exit-lever fire count evidence.
    """
    rows, skipped, excluded = [], {"no_opra": 0, "no_spy_day": 0}, []

    def _excluded(edate, symbol, t, reason):
        return {"arm": label, "date": edate.isoformat(),
                "entry_time_et": f5.naive_dt(t.entry_time_et).isoformat(),
                "side": t.side, "symbol": symbol, "reason": reason,
                "setup": t.setup, "triggers": list(t.triggers_fired),
                "level": float(t.rejection_level) if t.rejection_level else None}

    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol) if symbol in snapshot else None
        if opt_df is None:
            skipped["no_opra"] += 1
            excluded.append(_excluded(edate, symbol, t, "no_opra"))
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            skipped["no_spy_day"] += 1
            excluded.append(_excluded(edate, symbol, t, "no_spy_day"))
            continue
        entry_time_et = f5.naive_dt(t.entry_time_et)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        suppressed = bool(suppress_pred(t))
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        kw = dict(symbol=symbol, side=t.side, entry_time_et=entry_time_et,
                  entry_premium=float(t.entry_premium), qty=int(t.qty),
                  exit_shape=exit_shape, structure_stop_enabled=True,
                  trigger_level=trigger_level, strategy="ribbon_ride",
                  time_stop_et=efr.TIME_STOP_ET, opt_df=opt_df, five_min_spy_df=day_spy)
        res = walk_exit_manager(ribbon_tick_df=(None if suppressed else rtd), **kw)
        row = {
            "arm": label, "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "side": t.side, "setup": t.setup, "tier": eb.classify_tier(t.triggers_fired),
            "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": list(t.triggers_fired), "level": trigger_level,
            "level_anchored": is_level_anchored(t.triggers_fired),
            "ribbon_exit_suppressed": suppressed,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
        }
        if suppressed and dual_walk_suppressed:
            std = walk_exit_manager(ribbon_tick_df=rtd, **kw)
            row["std_exit_reason"] = std.exit_reason
            row["std_dollar_pnl"] = std.dollar_pnl
            row["exit_lever_fired"] = (std.exit_reason != res.exit_reason
                                       or round(std.dollar_pnl, 2) != round(res.dollar_pnl, 2))
        rows.append(row)
    log(f"  {label}: {len(rows)} real-OPRA walks "
        f"(excluded: no_opra={skipped['no_opra']} no_spy_day={skipped['no_spy_day']})")
    return rows, skipped, excluded


# ============================================================== scoring (exit-delta aware)

def score_paired(control_rows: list[dict], arm_rows: list[dict], recent_dates: set) -> dict:
    """f5.score_arm extended for a treatment that changes EXITS of common trades: changed
    days and G3's drop-best consider added, dropped AND common-trade P&L deltas (prereg
    changed_trade_semantics)."""
    ctrl_by_key = {f5._key(r): r for r in control_rows}
    arm_by_key = {f5._key(r): r for r in arm_rows}
    added = [arm_by_key[k] for k in arm_by_key if k not in ctrl_by_key]
    dropped = [ctrl_by_key[k] for k in ctrl_by_key if k not in arm_by_key]
    common_keys = [k for k in arm_by_key if k in ctrl_by_key]
    common_changed = []
    for k in common_keys:
        d = arm_by_key[k]["dollar_pnl"] - ctrl_by_key[k]["dollar_pnl"]  # RAW -- rounding
        # each delta before summing drifts the identity check by up to 0.005*n_changed
        if abs(d) > 0.005:
            common_changed.append({**arm_by_key[k], "pnl_delta": d,
                                   "ctrl_pnl": ctrl_by_key[k]["dollar_pnl"],
                                   "ctrl_exit_reason": ctrl_by_key[k]["exit_reason"]})

    out = {"arm": "PAIRED"}
    for wname, wdates in (("full", None), ("recent25", recent_dates)):
        c = f5.window_slice(control_rows, wdates)
        a = f5.window_slice(arm_rows, wdates)
        c_total = round(sum(r["dollar_pnl"] for r in c), 2)
        a_total = round(sum(r["dollar_pnl"] for r in a), 2)
        w_added = f5.window_slice(added, wdates)
        w_dropped = f5.window_slice(dropped, wdates)
        w_common = f5.window_slice(common_changed, wdates)
        contributions = ([r["dollar_pnl"] for r in w_added]
                         + [-r["dollar_pnl"] for r in w_dropped]
                         + [r["pnl_delta"] for r in w_common])
        delta = round(a_total - c_total, 2)
        ident = round(sum(contributions), 2)
        assert abs(ident - delta) < 0.05, (
            f"{wname}: delta identity broke -- window delta {delta} != "
            f"sum(contributions) {ident} (added-dropped+common)")
        changed_days = sorted({r["date"] for r in w_added} | {r["date"] for r in w_dropped}
                              | {r["date"] for r in w_common})
        day_deltas = {}
        for d in changed_days:
            cd = sum(r["dollar_pnl"] for r in c if r["date"] == d)
            ad = sum(r["dollar_pnl"] for r in a if r["date"] == d)
            day_deltas[d] = round(ad - cd, 2)
        n_up = sum(1 for v in day_deltas.values() if v > 0)
        n_dn = sum(1 for v in day_deltas.values() if v < 0)
        best_contrib = max(contributions, default=0.0)
        out[wname] = {
            "control": {"n": len(c), "total": c_total},
            "arm": {"n": len(a), "total": a_total},
            "delta_total": delta,
            "n_added": len(w_added), "n_dropped": len(w_dropped),
            "n_common_exit_changed": len(w_common),
            "added_stats": f5.cohort_stats(w_added),
            "dropped_stats": f5.cohort_stats(w_dropped),
            "common_exit_delta_total": round(sum(r["pnl_delta"] for r in w_common), 2),
            "n_changed_days": len(changed_days),
            "n_days_improved": n_up, "n_days_worsened": n_dn,
            "day_deltas": day_deltas,
            "best_single_contribution": round(best_contrib, 2),
            "delta_minus_best_contribution": round(delta - max(best_contrib, 0.0), 2),
            "p_value_one_sided": permutation_p(contributions),
            "n_contributions": len(contributions),
        }
    out["runner_cohort"] = {"control": f5.runner_cohort(control_rows),
                            "arm": f5.runner_cohort(arm_rows)}
    rc, ra = out["runner_cohort"]["control"], out["runner_cohort"]["arm"]
    exit_lever_rows = [r for r in arm_rows if r.get("ribbon_exit_suppressed")]
    lever_fired = [r for r in exit_lever_rows if r.get("exit_lever_fired")]
    out["exit_lever"] = {
        "n_suppressed_walks": len(exit_lever_rows),
        "n_fired_full": len(lever_fired),
        "n_fired_recent": len(f5.window_slice(lever_fired, recent_dates)),
        "fired_delta_total": round(sum(r["dollar_pnl"] - r["std_dollar_pnl"]
                                       for r in lever_fired), 2),
    }
    out["gates"] = {
        "G1_recent_window_positive": {
            "delta_total_recent": out["recent25"]["delta_total"],
            "pass": out["recent25"]["delta_total"] > 0},
        "G2_day_majority_recent": {
            "improved": out["recent25"]["n_days_improved"],
            "worsened": out["recent25"]["n_days_worsened"],
            "pass": out["recent25"]["n_days_improved"] > out["recent25"]["n_days_worsened"]},
        "G3_survives_drop_best_recent": {
            "delta_minus_best": out["recent25"]["delta_minus_best_contribution"],
            "best_single_contribution": out["recent25"]["best_single_contribution"],
            "pass": out["recent25"]["delta_minus_best_contribution"] > 0},
        "G4_runner_cohort_zero_tolerance": {
            "control_n": rc["n"], "arm_n": ra["n"],
            "control_total": rc["total"], "arm_total": ra["total"],
            "floor": RUNNER_FLOOR,
            "pass": (ra["n"] >= rc["n"] * RUNNER_FLOOR
                     and ra["total"] >= rc["total"] * RUNNER_FLOOR)},
        "G5_fire_count_L243_both_levers": {
            "n_added_full": out["full"]["n_added"],
            "n_added_recent": out["recent25"]["n_added"],
            "exit_lever_fires_full": out["exit_lever"]["n_fired_full"],
            "floors": {"added_full": FIRE_FLOOR_FULL, "added_recent": FIRE_FLOOR_RECENT,
                       "exit_lever_full": EXIT_LEVER_FIRE_FLOOR},
            "pass": (out["full"]["n_added"] >= FIRE_FLOOR_FULL
                     and out["recent25"]["n_added"] >= FIRE_FLOOR_RECENT
                     and out["exit_lever"]["n_fired_full"] >= EXIT_LEVER_FIRE_FLOOR)},
    }
    for g in out["gates"].values():
        g["status"] = "PASS" if g["pass"] else "FAIL"
    out["all_gates_pass"] = all(g["pass"] for g in out["gates"].values())
    out["verdict"] = "SHIP_CANDIDATE" if out["all_gates_pass"] else "NULL"
    out["common_changed_detail"] = sorted(
        ({"date": r["date"], "entry_time_et": r["entry_time_et"], "side": r["side"],
          "symbol": r["symbol"], "ctrl_exit": r["ctrl_exit_reason"],
          "arm_exit": r["exit_reason"], "ctrl_pnl": r["ctrl_pnl"],
          "arm_pnl": r["dollar_pnl"], "pnl_delta": round(r["pnl_delta"], 2)}
         for r in common_changed), key=lambda x: (x["date"], x["entry_time_et"]))
    return out


def permutation_p(contributions: list[float]) -> Optional[float]:
    """One-sided sign-flip permutation p on mean(contribution) > 0. Seeded, advisory."""
    if not contributions:
        return None
    rng = random.Random(PERM_SEED)
    obs = sum(contributions) / len(contributions)
    ge = 0
    for _ in range(PERM_N):
        s = sum(c if rng.random() < 0.5 else -c for c in contributions)
        if s / len(contributions) >= obs:
            ge += 1
    return round(ge / PERM_N, 4)


def exit_transition_matrix(arm_rows: list[dict]) -> dict:
    """For suppressed trades that changed outcome: standard-walk exit -> suppressed exit,
    with n and total P&L delta. THE mechanism table -- where do the ribbon round-trips go."""
    from collections import defaultdict
    cells = defaultdict(lambda: {"n": 0, "pnl_delta_total": 0.0})
    for r in arm_rows:
        if not r.get("exit_lever_fired"):
            continue
        key = f"{(r['std_exit_reason'] or '').split(' @')[0]} -> {(r['exit_reason'] or '').split(' @')[0]}"
        cells[key]["n"] += 1
        cells[key]["pnl_delta_total"] = round(
            cells[key]["pnl_delta_total"] + r["dollar_pnl"] - r["std_dollar_pnl"], 2)
    return dict(sorted(cells.items(), key=lambda kv: -kv[1]["n"]))


# ============================================================== main

def main() -> int:
    t_start = time.time()
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    log(f"pre-reg {prereg['prereg_id']} frozen {prereg['frozen_at_et']}")
    _suppression_self_test()

    snapshot = frozenset(p.stem for p in CACHE_DIR.glob("SPY*.csv"))
    log(f"OPRA cache snapshot: {len(snapshot)} contracts (frozen for BOTH arms)")

    spy_df, vix_df = f5.load_extended_data()
    day_bars = spy_df.groupby(spy_df["timestamp_et"].dt.date).size()
    day_bars = day_bars[(day_bars.index >= f5.FULL_START) & (day_bars.index <= f5.FULL_END)]
    all_days = sorted(day_bars.index)
    half_days = {d for d, n in day_bars.items() if n < 70}
    assert len(all_days) == EXPECTED_FRAME_DATES, (
        f"population drift: {len(all_days)} dates in frame != {EXPECTED_FRAME_DATES} "
        f"(391 full + 3 half) -- data changed underneath the study, aborting")
    assert half_days == EXPECTED_HALF_DAYS, (
        f"half-day set drifted: {sorted(half_days)} != {sorted(EXPECTED_HALF_DAYS)} -- aborting")
    recent_dates = f5.recent_window_dates(spy_df)
    log(f"population {len(all_days)} frame dates ({len(all_days) - len(half_days)} full "
        f"sessions + {len(half_days)} half days, disclosed) {all_days[0]}..{all_days[-1]}; "
        f"recent window {len(recent_dates)} days {min(recent_dates)}..{max(recent_dates)}")

    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"exit shape (strategies.py#RIBBON_RIDE): {exit_shape}")

    log("CONTROL: run_backtest(**SAFE_BASE_LIVE) + blockers==[5] capture")
    r_ctrl, cand = f5.run_arm("CONTROL", spy_df, vix_df, capture_blockers5=True)
    cand.assert_dual_patch_observed()
    log(f"  capture dedupe: {cand.duplicate_hits} duplicate hits suppressed (dual patch live)")
    assert len(r_ctrl.trades) == CONTROL_RAW_ENTRY_ANCHOR, (
        f"CONTROL parity anchor broke: {len(r_ctrl.trades)} raw entries != "
        f"{CONTROL_RAW_ENTRY_ANCHOR} (07-31 run). Entry engine drifted -- aborting.")
    log(f"  CONTROL raw-entry parity anchor OK ({CONTROL_RAW_ENTRY_ANCHOR})")

    log("PAIRED: scoped filter-5 bypass (per-bar re-eval, level-anchored only -- "
        "prereg fallback engaged after the deletion invariant broke on first run)")
    r_arm, scoped_fires = run_arm_scoped("PAIRED", spy_df, vix_df)

    # HARD INVARIANT (prereg): every ADDED raw entry must be level-anchored.
    ctrl_raw = {raw_key(t) for t in r_ctrl.trades}
    added_raw = [t for t in r_arm.trades if raw_key(t) not in ctrl_raw]
    not_anchored = [t for t in added_raw if not is_level_anchored(t.triggers_fired)]
    assert not not_anchored, (
        "INVARIANT BROKE: deletion admitted non-level-anchored entries -- "
        + "; ".join(f"{raw_key(t)} triggers={list(t.triggers_fired)}" for t in not_anchored)
        + " -- deletion no longer equals the scoped bypass on this population. ABORTING "
        "(implement the scoped filters.py flag instead of shipping a mismeasured cohort).")
    log(f"  added-raw invariant OK: {len(added_raw)} added entries, ALL level-anchored")

    log("walking exits (CONTROL standard everywhere; PAIRED suppressed for level-anchored)")
    ctrl_rows, ctrl_skip, ctrl_excl = derive_rows_paired(
        "CONTROL", r_ctrl, spy_df, ribbon_lookup, exit_shape, snapshot,
        suppress_pred=lambda t: False)
    arm_rows, arm_skip, arm_excl = derive_rows_paired(
        "PAIRED", r_arm, spy_df, ribbon_lookup, exit_shape, snapshot,
        suppress_pred=lambda t: is_level_anchored(t.triggers_fired),
        dual_walk_suppressed=True)

    n_supp = sum(1 for r in arm_rows if r["ribbon_exit_suppressed"])
    log(f"  PAIRED book: {len(arm_rows)} walks, {n_supp} ribbon-suppressed "
        f"({sum(1 for r in arm_rows if r.get('exit_lever_fired'))} exit-lever fires)")

    measurability = f5.opra_measurability(ctrl_rows, ctrl_excl, arm_rows, arm_excl,
                                          recent_dates)
    for wd in measurability["windows"].values():   # rename the generic ARM_A key honestly
        wd["PAIRED"] = wd.pop("ARM_A")
    scored = score_paired(ctrl_rows, arm_rows, recent_dates)
    scored = f5.relabel_g1_measurability(scored, measurability)

    out = {
        "_doc": __doc__,
        "generated_at_et": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prereg_path": str(PREREG_PATH.relative_to(ROOT)).replace("\\", "/"),
        "prereg_id": prereg["prereg_id"],
        "prereg_frozen_at_et": prereg["frozen_at_et"],
        "prereg_commit": "e5e323f2 (runner did not exist at freeze commit)",
        "window": {"start": f5.FULL_START.isoformat(), "end": f5.FULL_END.isoformat(),
                   "n_trading_days": len(all_days),
                   "recent_n_days": len(recent_dates),
                   "recent_start": min(recent_dates).isoformat(),
                   "recent_end": max(recent_dates).isoformat()},
        "opra_cache_snapshot": {"n_contracts": len(snapshot),
                                "rule": prereg["population"]["opra_cache_snapshot_rule"]},
        "entry_mechanism_asbuilt": {
            "mechanism": "scoped per-bar filter-5 bypass (run_arm_scoped): production "
                         "evaluate first; re-eval with disable_filters=[5] ONLY when "
                         "blockers=={5} and the setup is level-anchored. No demerit.",
            "prereg_deviation": "NONE -- this IS the prereg's frozen fallback. The primary "
                                "mechanism (plain disable_filters=[5]) was tried first and "
                                "its HARD INVARIANT broke: deletion admitted a trendline-"
                                "only bear entry (2026-05-19 14:20 P737).",
            "root_cause_of_invariant_break": "filters.py:1654-1657 charges the trendline-"
                                "only chop demerit only `if 5 in blockers`; under "
                                "disable_filters=[5] the blocker is never appended, the "
                                "demerit vanishes, and trendline-only setups score +1 vs "
                                "production. Deletion therefore != scoped bypass. The "
                                "07-31 study's ARM_A==ARM_B equivalence narrative missed "
                                "this crack (its NULL verdict is unaffected -- both arms "
                                "carried the same crack).",
            "scoped_bypass_reeval_fires": scoped_fires,
        },
        "control_parity": {
            "raw_entries": len(r_ctrl.trades), "anchor": CONTROL_RAW_ENTRY_ANCHOR,
            "walked": len(ctrl_rows),
            "walked_total": round(sum(r["dollar_pnl"] for r in ctrl_rows), 2),
            "anchor_0731_walked": 191, "anchor_0731_total": 5005.95,
            "note": ("walked figures reproduce 07-31 to the cent iff the OPRA cache is "
                     "unchanged; a richer cache (overnight backfill) raises walks -- "
                     "disclosed, both arms share the identical snapshot")},
        "cohort_rule": {"level_tied_triggers": sorted(LEVEL_TIED_TRIGGERS)},
        "opra_exclusions": {"CONTROL": ctrl_skip, "PAIRED": arm_skip,
                            "note": "excluded from every total, never BS-synthesized"},
        "opra_measurability": measurability,
        "arms": {"PAIRED_relax_entry_suppress_exit": scored},
        "attribution_added_vs_preempted": f5.attribution_block(ctrl_rows, arm_rows),
        "exit_transition_matrix_suppressed_trades": exit_transition_matrix(arm_rows),
        "gates_frozen": prereg["gates_frozen"],
        "ship_rule": prereg["ship_rule"],
        "trades": {"CONTROL": ctrl_rows, "PAIRED": arm_rows},
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")

    s = scored
    log(f"PAIRED: full delta ${s['full']['delta_total']:+,.2f} | "
        f"recent25 delta ${s['recent25']['delta_total']:+,.2f} | "
        f"added {s['full']['n_added']} | exit-lever fires {s['exit_lever']['n_fired_full']} | "
        f"verdict {s['verdict']}")
    log(f"done in {time.time() - t_start:.1f}s")
    return 0


# ============================================================== markdown

def _measurability_md(out: dict) -> str:
    """Window-stratified OPRA exclusions (f5's renderer expects an 'ARM_A' key this study
    honestly renames to 'PAIRED', so the table is rendered here)."""
    m = out.get("opra_measurability")
    if not m:
        return ""
    L = ["## OPRA coverage — window-stratified exclusions", ""]
    L.append("Every unpriceable entry is excluded from every total and NEVER "
             "Black-Scholes-synthesized; a measured delta covers the PRICEABLE subset only.")
    L.append("")
    L.append("| window | arm | walked | excluded (no OPRA) | excluded (no SPY day) |")
    L.append("|---|---|--:|--:|--:|")
    for w, wd in m["windows"].items():
        for arm in ("CONTROL", "PAIRED"):
            a = wd[arm]
            L.append(f"| {w} | {arm} | {a['walked']} | {a['excluded_no_opra']} | "
                     f"{a['excluded_no_spy_day']} |")
    L.append("")
    L.append("| window | raw added entries | measurable | unmeasurable (no OPRA) | measurable % |")
    L.append("|---|--:|--:|--:|--:|")
    for w, wd in m["windows"].items():
        a = wd["added_by_arm"]
        L.append(f"| {w} | {a['raw_entries']} | {a['measurable']} | "
                 f"{a['unmeasurable_no_opra']} | {a['measurable_pct']}% |")
    z = m.get("recent25_days_with_zero_opra_coverage", {})
    L.append("")
    L.append(f"Recent-25 days with ZERO cached OPRA coverage: {z.get('n', '?')} "
             f"({', '.join(z.get('days', [])) or 'none'}).")
    L.append("")
    return "\n".join(L)


def write_markdown(out: dict) -> None:
    s = out["arms"]["PAIRED_relax_entry_suppress_exit"]
    L = []
    L.append("# PAIRED RIBBON A/B — relax filter 5 + suppress ribbon_flip_back for "
             "level-anchored setups (2026-08-01)")
    L.append("")
    L.append(f"**VERDICT: {s['verdict']}** — pre-reg `{out['prereg_path']}` frozen "
             f"**{out['prereg_frozen_at_et']}** ({out['prereg_commit']}), runner "
             f"`backtest/tools/paired_ribbon_ab_2026_08_01.py`.")
    L.append("")
    L.append("ONE paired treatment, no grid (m=1): level-anchored setups lose the ribbon "
             "MA-stack veto at ENTRY (filter 5) **and** the ribbon_flip_back EXIT — they keep "
             "structure_stop, −50% catastrophe cap, TP1, chandelier trail, runner target, "
             "15:40 time stop. Motivated by filter5-ribbon-2026-07-31's mechanism finding: "
             "76.2% of entry-only-unlocked trades were round-tripped by the same lagging "
             "ribbon at exit.")
    L.append("")
    L.append("## Windows")
    L.append("")
    L.append("| window | control | paired | delta | added | dropped | exit-changed common | "
             "days +/− | p (1-sided) |")
    L.append("|---|--:|--:|--:|--:|--:|--:|:--|--:|")
    for w in ("full", "recent25"):
        x = s[w]
        L.append(f"| {w} | ${x['control']['total']:,.2f} (n={x['control']['n']}) | "
                 f"${x['arm']['total']:,.2f} (n={x['arm']['n']}) | "
                 f"**${x['delta_total']:+,.2f}** | {x['n_added']} | {x['n_dropped']} | "
                 f"{x['n_common_exit_changed']} | "
                 f"{x['n_days_improved']}/{x['n_days_worsened']} | {x['p_value_one_sided']} |")
    L.append("")
    add = s["full"]["added_stats"]
    L.append(f"Added cohort (full, real exits): n={add['n']} total=${add['total']:,.2f} "
             f"WR={add['wr']} per-trade=${add['per_trade'] or 0:,.2f} "
             f"ex-best=${add['total_ex_best'] or 0:,.2f}")
    L.append(f"Common-trade exit deltas (full): n={s['full']['n_common_exit_changed']} "
             f"total=${s['full']['common_exit_delta_total']:+,.2f}")
    L.append("")
    L.append("## Gates")
    L.append("")
    L.append("| gate | result | status |")
    L.append("|---|---|:--:|")
    _hide = {"pass", "status", "undetermined_because", "verdict_unchanged"}
    for gid, g in s["gates"].items():
        detail = ", ".join(f"{k}={v}" for k, v in g.items() if k not in _hide)
        L.append(f"| {gid} | {detail} | {g.get('status')} |")
    g1 = s["gates"]["G1_recent_window_positive"]
    if g1.get("status") == "UNDETERMINED":
        L.append("")
        L.append(f"> **G1 is UNDETERMINED, not FAIL.** {g1['undetermined_because']}")
        L.append(">")
        L.append(f"> **{g1.get('verdict_unchanged', '')}**")
    L.append("")
    L.append("## The exit lever — did the suppression itself fire? (G5b / L243)")
    L.append("")
    el = s["exit_lever"]
    L.append(f"- suppressed walks: **{el['n_suppressed_walks']}** | outcomes changed vs a "
             f"standard walk of the SAME entry: **{el['n_fired_full']}** full-window "
             f"({el['n_fired_recent']} recent) | P&L moved by the suppression alone: "
             f"**${el['fired_delta_total']:+,.2f}**")
    L.append("")
    L.append("Exit transition matrix (standard walk → suppressed walk, changed trades only):")
    L.append("")
    L.append("| transition | n | P&L delta |")
    L.append("|---|--:|--:|")
    for k, v in out["exit_transition_matrix_suppressed_trades"].items():
        L.append(f"| {k} | {v['n']} | ${v['pnl_delta_total']:+,.2f} |")
    L.append("")
    L.append("## Where the entry-side delta comes from (added vs pre-empted)")
    at = out["attribution_added_vs_preempted"]
    L.append("")
    L.append(f"- Added cohort total: **${at['added_total_the_gate_was_blocking_this']:,.2f}**")
    L.append(f"- Pre-emption contribution: **${at['delta_from_preemption']:+,.2f}** "
             f"({at['pct_of_delta_from_preemption']}% of the added−dropped part)")
    L.append("")
    L.append("| exit reason | added cohort | control book |")
    L.append("|---|--:|--:|")
    for k in sorted(set(at["added_exit_reason_mix"]) | set(at["control_exit_reason_mix"])):
        a = at["added_exit_reason_mix"].get(k, {"n": 0, "pct": 0.0})
        c = at["control_exit_reason_mix"].get(k, {"n": 0, "pct": 0.0})
        L.append(f"| {k} | {a['n']} ({a['pct']}%) | {c['n']} ({c['pct']}%) |")
    L.append("")
    L.append(_measurability_md(out))
    L.append("## Control parity")
    cp = out["control_parity"]
    L.append("")
    L.append(f"- raw entries {cp['raw_entries']} == anchor {cp['anchor']} (07-31) — entry "
             f"engine unchanged")
    L.append(f"- walked {cp['walked']} / ${cp['walked_total']:,.2f} vs 07-31's "
             f"{cp['anchor_0731_walked']} / ${cp['anchor_0731_total']:,.2f} — {cp['note']}")
    L.append("")
    L.append("## Ship rule (frozen)")
    L.append("")
    L.append(out["ship_rule"])
    L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
