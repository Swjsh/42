"""bull_vix_soft_mode_2026_08_03.py -- REAL SEQUENTIAL A/B for `vix_soft_mode_bull` (ARM_C).

Executes analysis/recommendations/prereg-bull-vix-soft-mode-2026-08-03.json's ARM_C EXACTLY as
frozen. This prereg specified a NEW code path (filters.py#evaluate_bullish_setup's
`vix_soft_mode_bull` parameter, orchestrator.py#run_backtest's matching kwarg) that did not
exist when the prereg was written -- that code was built and guard-tested THIS session
(backtest/tests/test_bull_vix_soft_mode_2026_08_03.py, vary-and-assert + RED-proof) before this
runner was written. This file is the "real run" the prereg's own text repeatedly points to.

WHY SEQUENTIAL RE-ADMISSION IS NECESSARY (not just reading run_backtest(...).trades directly):
run_backtest()'s own bar-walk loop IS already single-position-sequential (it skips the bar
pointer forward past an assumed exit before considering a new entry -- orchestrator.py's own
module docstring, point 5: "After exit, jump bar pointer past the exit bar (no re-entry until
flat)"), BUT that skip-forward decision uses run_backtest's OWN internal exit simulation, which
this repo's own established doctrine treats as KNOWN-DIVERGENT from the correct exit (every
cited full-population study -- engine_fullhist_replay.py, ladder_fullhist_replay.py,
bull_gate_f5class_requal_2026_08_01.py -- discards `t.dollar_pnl`/`t.exit_time_et`'s implicit
timing and re-derives the TRUE exit via `lib.exit_manager_walk.walk_exit_manager`). Once the
TRUE exit times are known, TWO INDEPENDENT run_backtest() calls (CONTROL vs ARM_C) can each have
admitted a candidate whose TRUE exit overlaps a later admitted candidate -- exactly the
mechanism `backtest/tools/bold_adaptive_sizing_2026_08_02.py` discovered and fixed via
`_sequential_admit` (re-walk one-position-at-a-time using the CORRECTED exit_time_et). That
function is REUSED here verbatim (imported, not reimplemented) per the task's explicit
instruction.

METHOD:
  ENTRY layer   run_backtest(**engine_fullhist_replay.SAFE_BASE_LIVE) -- CONTROL (unchanged) and
                ARM_C (+ vix_soft_mode_bull=True). Byte-identical Safe production config
                otherwise (elite_bear_level_reject_gate_ab.SAFE_BASE, field-reconciled prod
                config, initial_equity refreshed to $1,746.75 -- this repo's established
                convention, see engine_fullhist_replay.py's own docstring).
  EXIT layer    lib.exit_manager_walk.walk_exit_manager, RIBBON_RIDE exit shape,
                structure_stop_enabled=True, time_stop 15:40 ET -- the SAME re-derivation every
                cited full-population study in this repo uses. run_backtest's own
                dollar_pnl/exit_time_et are DISCARDED; only entry metadata survives.
  SEQUENCING    `_sequential_admit` (bold_adaptive_sizing_2026_08_02, imported) applied
                INDEPENDENTLY to CONTROL's and ARM_C's candidate rows -> CONTROL_SEQUENTIAL /
                ARM_C_SEQUENTIAL -- the TRUE, honestly-replayed populations.
  DECOMPOSITION ADDED cohort (ARM_C_SEQUENTIAL rows whose (symbol, entry_time_et) key never
                appears in CONTROL's own CANDIDATE pool at all -- only possible via the new
                soft-demerit path) vs PRE-EMPTED cohort (CONTROL_SEQUENTIAL rows absent from
                ARM_C_SEQUENTIAL, displaced by an earlier ARM_C-only trade occupying the slot).
                Mirrors bold_adaptive_sizing_2026_08_02.decompose()'s method exactly (built
                fresh here, not imported, since this study's day-level delta gates (G1-G3) are
                DEFINED DIFFERENTLY in this prereg than in that one -- see gates below).

GATES (frozen in the prereg, reproduced here verbatim, not reinterpreted):
  G1 (PRIMARY)  recent-25-trading-day delta (ARM_C_SEQUENTIAL total - CONTROL_SEQUENTIAL total,
                both restricted to the 25 newest trading dates in the population frame) > 0.
  G2            among recent-window days whose book changed (CONTROL day-total != ARM_C
                day-total), n_improved > n_worsened.
  G3            recent-window delta minus the SINGLE best-contributing changed trade (added:
                +pnl: pre-empted: -pnl) remains > 0.
  G4            in ARM_C, both COUNT and TOTAL P&L of runner-cohort exits (exit_reason
                containing "runner" or "trail", case-insensitive) must be >= 95% of CONTROL's,
                over the FULL population. Zero tolerance. This is a SAFE-only study (CONTROL is
                literally SAFE_BASE_LIVE, not Bold) -- the runner-cohort anchor used is THIS
                STUDY's own freshly-computed CONTROL_SEQUENTIAL runner cohort, never Bold's
                separate n=32/$14,539.40 anchor (that anchor belongs to a DIFFERENT study, a
                DIFFERENT account, and is not cited anywhere in this file).
  G5            ARM_C must ADD >= 10 new entries over the full population AND >= 2 over the
                recent window (L243 fire-count floor).
  Ship rule     G1 AND G2 AND G3 AND G4 AND G5, all-or-nothing, exactly as frozen.

Run: backtest/.venv/Scripts/python.exe backtest/tools/bull_vix_soft_mode_2026_08_03.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import elite_bear_level_reject_gate_ab as eb  # noqa: E402  -- SAFE_BASE, classify_tier, entry_date
import engine_fullhist_replay as efr  # noqa: E402  -- SAFE_BASE_LIVE, build_ribbon_lookup, naive_dt, ribbon_tick_df_for
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
from bold_adaptive_sizing_2026_08_02 import _sequential_admit  # noqa: E402  -- REUSED, not rebuilt
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402

DATA = REPO / "data"
OLD_SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
OLD_VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
NEW_SPY_FILE = DATA / "spy_5m_2026-05-19_2026-07-27.csv"
NEW_VIX_FILE = DATA / "vix_5m_2026-05-19_2026-07-27.csv"
OLD_WINDOW_END = dt.date(2026, 7, 22)   # engine_fullhist_replay.py's own window boundary

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 27)         # prereg population.window_end (NOT the sibling's 07-31)
TIME_STOP_ET = dt.time(15, 40)
RECENT_N = 25
BH_ALPHA = 0.10

PREREG = ROOT / "analysis" / "recommendations" / "prereg-bull-vix-soft-mode-2026-08-03.json"
OUT_JSON = ROOT / "analysis" / "recommendations" / "bull-vix-soft-mode-2026-08-03.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "bull-vix-soft-mode-2026-08-03.md"
EXPECTED_DAYS_CROSSCHECK = 390   # FREQUENCY-CEILING-2026-08-03.md's own count, same end date


def log(msg: str) -> None:
    print(f"[bull-vix-soft-mode] {msg}", flush=True)


# ============================================================================== data loading
def load_extended_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """OLD file (byte-identical to engine_fullhist_replay.py's window) + the strictly-after-
    07-22 tail of the NEW file -- identical merge to ladder_fullhist_replay.py/
    day_report_card.py, per the prereg's own population.spy_source citation. Plain
    pd.to_datetime (wall-v1) on BOTH spy and vix, matching run_backtest's own internal parse
    convention -- NOT et-v2 (mixing frames is the actual DST footgun this repo has already
    hit once; using the SAME plain convention consistently on both sides, like every one of
    these three canonical tools does, is what keeps them trustworthy)."""
    spy_old = pd.read_csv(OLD_SPY_FILE)
    spy_old["timestamp_et"] = pd.to_datetime(spy_old["timestamp_et"])
    spy_new = pd.read_csv(NEW_SPY_FILE)
    spy_new["timestamp_et"] = pd.to_datetime(spy_new["timestamp_et"])
    spy_tail = spy_new[spy_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    spy_df = (pd.concat([spy_old, spy_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))

    vix_old = pd.read_csv(OLD_VIX_FILE)
    vix_old["timestamp_et"] = pd.to_datetime(vix_old["timestamp_et"])
    vix_new = pd.read_csv(NEW_VIX_FILE)
    vix_new["timestamp_et"] = pd.to_datetime(vix_new["timestamp_et"])
    vix_tail = vix_new[vix_new["timestamp_et"].dt.date > OLD_WINDOW_END]
    vix_df = (pd.concat([vix_old, vix_tail], ignore_index=True)
                .sort_values("timestamp_et").reset_index(drop=True))
    return spy_df, vix_df


def rth_trading_days(spy_df: pd.DataFrame) -> list[dt.date]:
    mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    days = sorted(spy_df.loc[mask, "timestamp_et"].dt.date.unique())
    return [d for d in days if FULL_START <= d <= FULL_END]


# ============================================================================== entry+exit replay
def replay_rows(r, spy_df: pd.DataFrame, ribbon_lookup: pd.DataFrame) -> tuple[list[dict], int, int, int]:
    """Mirror of engine_fullhist_replay.py's main() per-trade loop (ENTRY trusted from
    run_backtest(use_real_fills=True), EXIT independently re-derived via walk_exit_manager --
    never run_backtest's own dollar_pnl), extended with exit_time_et (required by
    _sequential_admit) and side/symbol (required for keying). Rows with no resolvable exit
    (fill landed on the day's last bar) are DROPPED, not zeroed -- C7, matches
    bull_gate_f5class_requal_2026_08_01.py's identical convention."""
    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    rows: list[dict] = []
    n_no_opra = 0
    n_no_spy_day = 0
    n_unwalkable = 0
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue

        entry_time_et = efr.naive_dt(t.entry_time_et)
        entry_premium = float(t.entry_premium)
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        qty = int(t.qty)
        tier = eb.classify_tier(t.triggers_fired)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)

        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=correct_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        if res.exit_time_et is None:
            n_unwalkable += 1
            continue

        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "exit_time_et": res.exit_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": tier, "symbol": symbol,
            "qty": qty, "entry_premium": round(entry_premium, 4), "triggers": list(t.triggers_fired or []),
            "trigger_level": trigger_level,
            "dollar_pnl": round(float(res.dollar_pnl), 2), "exit_reason": res.exit_reason,
            "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
        })
    return rows, n_no_opra, n_no_spy_day, n_unwalkable


def _key(row: dict) -> tuple:
    return (row["symbol"], row["entry_time_et"])


# ============================================================================== stats / gates
def _drop_best(pnls: list[float]) -> tuple[float, bool]:
    """Only drops an actual WINNER -- matches bull_gate_f5class_requal_2026_08_01.drop_best's
    semantics exactly (an all-losing/zero-winner population's drop-best equals its raw total)."""
    if not pnls:
        return 0.0, False
    winners = [p for p in pnls if p > 0]
    if not winners:
        total = sum(pnls)
        return round(total, 2), total > 0
    remainder = sum(pnls) - max(winners)
    return round(remainder, 2), remainder > 0


def _population_stats(rows: list[dict], recent_dates: set) -> dict:
    pnls = [r["dollar_pnl"] for r in rows]
    n = len(pnls)
    total = round(sum(pnls), 2)
    wins = [p for p in pnls if p > 0]
    remainder, remainder_pos = _drop_best(pnls)
    recent_rows = [r for r in rows if dt.date.fromisoformat(r["date"]) in recent_dates]
    recent_total = round(sum(r["dollar_pnl"] for r in recent_rows), 2)
    return {
        "n": n, "total_pnl": total,
        "win_rate": round(len(wins) / n, 4) if n else None,
        "avg_pnl_per_trade": round(total / n, 2) if n else None,
        "drop_best": {"remainder": remainder, "still_positive": remainder_pos},
        "recent_25": {"n": len(recent_rows), "total_pnl": recent_total},
    }


def _day_totals(rows: list[dict]) -> dict:
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["dollar_pnl"], 2)
    return by_day


def _is_runner_cohort(row: dict) -> bool:
    er = (row.get("exit_reason") or "").lower()
    return ("runner" in er) or ("trail" in er)


def one_sample_p(pnls: list[float]) -> float:
    """One-sided p-value, mean > 0 -- degenerates to a plain threshold at alpha=0.10 for this
    study's single hypothesis (matches elite_bear_level_reject_gate_ab.py's own disclosed
    'single candidate -- degenerates to a plain one-sided threshold' convention)."""
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se = (var / n) ** 0.5
    if se == 0:
        return 0.0 if mean > 0 else 1.0
    tstat = mean / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(tstat) / (2 ** 0.5))))))


def decompose(control_sequential: list[dict], armc_sequential: list[dict],
              control_candidate_keys: set) -> dict:
    """ADDED cohort (armc_sequential rows whose key never appears in CONTROL's own CANDIDATE
    pool at all) vs PRE-EMPTED cohort (control_sequential rows absent from armc_sequential,
    displaced by an earlier ARM_C-only trade). Mirrors bold_adaptive_sizing_2026_08_02.
    decompose()'s method (same accounting identity), rebuilt here (not imported) because this
    study also needs day-scoped slices for G1-G3 that tool's version doesn't carry."""
    armc_keys = {_key(r) for r in armc_sequential}
    added = [r for r in armc_sequential if _key(r) not in control_candidate_keys]
    preempted = [r for r in control_sequential if _key(r) not in armc_keys]
    added_total = round(sum(r["dollar_pnl"] for r in added), 2)
    preempted_total = round(sum(r["dollar_pnl"] for r in preempted), 2)
    armc_total = round(sum(r["dollar_pnl"] for r in armc_sequential), 2)
    control_total = round(sum(r["dollar_pnl"] for r in control_sequential), 2)
    gain = round(armc_total - control_total, 2)
    identity_check = round(added_total - preempted_total, 2)
    return {
        "_doc": "gain_over_control == added_total - preempted_total (accounting identity, verified below).",
        "added_cohort": {"n": len(added), "total_pnl": added_total, "trades": added},
        "preempted_cohort": {"n": len(preempted), "total_pnl": preempted_total, "trades": preempted},
        "gain_over_control_sequential": gain,
        "identity_check_added_minus_preempted": identity_check,
        "identity_holds": abs(gain - identity_check) < 0.02,
    }


def main() -> int:
    t_start = time.time()
    if not PREREG.exists():
        log(f"FAIL: prereg {PREREG} not found -- refusing to run an un-pre-registered study.")
        return 2
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    log(f"loaded prereg {PREREG.name} (frozen {prereg['frozen_at_et']}, status={prereg['status'][:40]}...)")

    log("loading merged full-history SPY/VIX data (2025-01-02..2026-07-27, prereg population)")
    spy_df, vix_df = load_extended_data()
    all_days = rth_trading_days(spy_df)
    log(f"population: {len(all_days)} RTH trading days {all_days[0]}..{all_days[-1]} "
        f"(FREQUENCY-CEILING-2026-08-03.md same-end-date cross-check: {EXPECTED_DAYS_CROSSCHECK})")
    if len(all_days) < RECENT_N:
        log("FATAL: fewer than 25 trading days in population -- cannot define recent window")
        return 1
    recent_dates = set(all_days[-RECENT_N:])
    recent_start, recent_end = min(recent_dates), max(recent_dates)
    log(f"recent-{RECENT_N} window: {recent_start}..{recent_end}")

    log("precomputing ribbon lookup (continuous RTH close series, shared by both arms)")
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)

    log("=== CONTROL: run_backtest(**SAFE_BASE_LIVE) -- vix_soft_mode_bull=False (default) ===")
    t0 = time.time()
    r_control = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **efr.SAFE_BASE_LIVE)
    log(f"  done in {time.time() - t0:.1f}s -- {len(r_control.trades)} raw entries")

    log("=== ARM_C: run_backtest(**SAFE_BASE_LIVE, vix_soft_mode_bull=True) ===")
    t0 = time.time()
    armc_cfg = dict(efr.SAFE_BASE_LIVE, vix_soft_mode_bull=True)
    r_armc = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **armc_cfg)
    log(f"  done in {time.time() - t0:.1f}s -- {len(r_armc.trades)} raw entries "
        f"(ENGINE-SCORE ASSERT-AGREE did not raise -- orchestrator/engine.score parity for the "
        f"new kwarg holds under a real full-population run, not just the unit-level guard)")

    log("re-deriving exits via walk_exit_manager (RIBBON_RIDE, structure-stop) for both arms")
    control_rows, c_no_opra, c_no_spy, c_unwalkable = replay_rows(r_control, spy_df, ribbon_lookup)
    armc_rows, a_no_opra, a_no_spy, a_unwalkable = replay_rows(r_armc, spy_df, ribbon_lookup)
    log(f"  CONTROL candidate rows: {len(control_rows)} (excluded: no_opra={c_no_opra} "
        f"no_spy_day={c_no_spy} unwalkable={c_unwalkable})")
    log(f"  ARM_C   candidate rows: {len(armc_rows)} (excluded: no_opra={a_no_opra} "
        f"no_spy_day={a_no_spy} unwalkable={a_unwalkable})")

    control_candidate_keys = {_key(r) for r in control_rows}

    log("sequential re-admission (one-position-at-a-time, corrected exit_time_et) -- "
        "bold_adaptive_sizing_2026_08_02._sequential_admit, reused verbatim")
    control_sequential = _sequential_admit(control_rows)
    armc_sequential = _sequential_admit(armc_rows)
    log(f"  CONTROL: {len(control_rows)} candidates -> {len(control_sequential)} sequential "
        f"(self-pre-emption: {len(control_rows) - len(control_sequential)})")
    log(f"  ARM_C:   {len(armc_rows)} candidates -> {len(armc_sequential)} sequential "
        f"(pre-emption: {len(armc_rows) - len(armc_sequential)})")

    control_stats = _population_stats(control_sequential, recent_dates)
    armc_stats = _population_stats(armc_sequential, recent_dates)
    log(f"CONTROL_SEQUENTIAL: n={control_stats['n']} total=${control_stats['total_pnl']:+.2f} "
        f"recent25=${control_stats['recent_25']['total_pnl']:+.2f}")
    log(f"ARM_C_SEQUENTIAL:   n={armc_stats['n']} total=${armc_stats['total_pnl']:+.2f} "
        f"recent25=${armc_stats['recent_25']['total_pnl']:+.2f}")

    decomp = decompose(control_sequential, armc_sequential, control_candidate_keys)
    log(f"DECOMPOSITION: added n={decomp['added_cohort']['n']} total=${decomp['added_cohort']['total_pnl']:+.2f} "
        f"| preempted n={decomp['preempted_cohort']['n']} total=${decomp['preempted_cohort']['total_pnl']:+.2f} "
        f"| identity_holds={decomp['identity_holds']}")

    # ------------------------------------------------------------------ G1: recent-25 delta > 0
    control_day_totals = _day_totals(control_sequential)
    armc_day_totals = _day_totals(armc_sequential)
    recent_control_total = round(sum(v for d, v in control_day_totals.items()
                                      if dt.date.fromisoformat(d) in recent_dates), 2)
    recent_armc_total = round(sum(v for d, v in armc_day_totals.items()
                                   if dt.date.fromisoformat(d) in recent_dates), 2)
    recent_delta = round(recent_armc_total - recent_control_total, 2)
    g1 = recent_delta > 0
    log(f"G1 (PRIMARY) recent-{RECENT_N} delta: ARM_C ${recent_armc_total:+.2f} - CONTROL "
        f"${recent_control_total:+.2f} = ${recent_delta:+.2f} -- PASS={g1}")

    # ------------------------------------------------------------------ G2: day-majority (recent, changed days only)
    recent_date_strs = {d.isoformat() for d in recent_dates}
    changed_days = []
    n_improved = 0
    n_worsened = 0
    for d in sorted(recent_date_strs):
        c = control_day_totals.get(d, 0.0)
        a = armc_day_totals.get(d, 0.0)
        if abs(a - c) < 0.005:
            continue
        changed_days.append({"date": d, "control_pnl": c, "armc_pnl": a, "delta": round(a - c, 2)})
        if a > c:
            n_improved += 1
        else:
            n_worsened += 1
    g2 = n_improved > n_worsened
    log(f"G2 day-majority (recent, changed days): improved={n_improved} worsened={n_worsened} "
        f"(n_changed_days={len(changed_days)}) -- PASS={g2}")

    # ------------------------------------------------------------------ G3: drop-best on the delta
    recent_added = [r for r in decomp["added_cohort"]["trades"]
                    if dt.date.fromisoformat(r["date"]) in recent_dates]
    recent_preempted = [r for r in decomp["preempted_cohort"]["trades"]
                         if dt.date.fromisoformat(r["date"]) in recent_dates]
    contributions = ([r["dollar_pnl"] for r in recent_added]
                      + [-r["dollar_pnl"] for r in recent_preempted])
    best_contribution = max(contributions) if contributions else 0.0
    dropped_delta = round(recent_delta - max(0.0, best_contribution), 2)
    g3 = dropped_delta > 0
    log(f"G3 drop-best: recent_delta ${recent_delta:+.2f} - best_contribution "
        f"${max(0.0, best_contribution):+.2f} = ${dropped_delta:+.2f} -- PASS={g3}")

    # ------------------------------------------------------------------ G4: runner-cohort no-regression (full pop, zero tolerance)
    control_runner = [r for r in control_sequential if _is_runner_cohort(r)]
    armc_runner = [r for r in armc_sequential if _is_runner_cohort(r)]
    control_runner_n, control_runner_pnl = len(control_runner), round(sum(r["dollar_pnl"] for r in control_runner), 2)
    armc_runner_n, armc_runner_pnl = len(armc_runner), round(sum(r["dollar_pnl"] for r in armc_runner), 2)
    g4_count_ok = armc_runner_n >= 0.95 * control_runner_n if control_runner_n else True
    g4_pnl_ok = armc_runner_pnl >= 0.95 * control_runner_pnl if control_runner_pnl > 0 else armc_runner_pnl >= control_runner_pnl
    g4 = bool(g4_count_ok and g4_pnl_ok)
    log(f"G4 runner-cohort (full pop, SAFE-side anchor = this study's OWN CONTROL, zero "
        f"tolerance): CONTROL n={control_runner_n} ${control_runner_pnl:+.2f} | ARM_C "
        f"n={armc_runner_n} ${armc_runner_pnl:+.2f} -- count_ok={g4_count_ok} pnl_ok={g4_pnl_ok} "
        f"PASS={g4}")

    # ------------------------------------------------------------------ G5: fire-count floor (L243)
    n_added_full = decomp["added_cohort"]["n"]
    n_added_recent = len(recent_added)
    g5 = (n_added_full >= 10) and (n_added_recent >= 2)
    log(f"G5 fire-count floor: added full_pop={n_added_full} (need >=10) recent={n_added_recent} "
        f"(need >=2) -- PASS={g5}")

    all_gates = {"G1_recent_window_positive_PRIMARY": g1, "G2_day_majority_recent": g2,
                 "G3_survives_drop_best_recent": g3, "G4_runner_anchor_no_regression": g4,
                 "G5_fire_count_L243": g5}
    ship = all(all_gates.values())
    verdict = "SHIP" if ship else "NULL"
    log(f"GATES: {all_gates}")
    log(f"VERDICT: {verdict}")

    # ------------------------------------------------------------------ advisory BH-FDR (added cohort)
    added_pnls = [r["dollar_pnl"] for r in decomp["added_cohort"]["trades"]]
    p_val = one_sample_p(added_pnls)
    bh_significant = p_val <= BH_ALPHA   # single hypothesis -- degenerates to a plain threshold
    log(f"ADVISORY BH-FDR (added cohort, n={len(added_pnls)}, single-hypothesis degenerate "
        f"threshold alpha={BH_ALPHA}): p={p_val:.5f} significant={bh_significant} "
        f"(NOT a ship gate -- reported_not_gating per the prereg)")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "prereg_frozen_at_et": prereg["frozen_at_et"],
        "account_scope": "SAFE ONLY (CONTROL = SAFE_BASE_LIVE, elite_bear_level_reject_gate_ab.SAFE_BASE "
                          "+ initial_equity=1746.75). No Bold cell computed -- the frozen prereg's CONTROL "
                          "is SAFE_BASE_LIVE verbatim, not a Bold config, so Bold's separate n=32/$14,539.40 "
                          "runner anchor is inapplicable here and is not cited anywhere in this file.",
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                   "n_trading_days": len(all_days),
                   "n_trading_days_crosscheck_source": "FREQUENCY-CEILING-2026-08-03.md (same end date)",
                   "n_trading_days_crosscheck_value": EXPECTED_DAYS_CROSSCHECK},
        "recent_window": {"n": RECENT_N, "start": recent_start.isoformat(), "end": recent_end.isoformat()},
        "raw_entries": {"control": len(r_control.trades), "arm_c": len(r_armc.trades)},
        "candidate_rows": {
            "control": {"n": len(control_rows), "n_excluded_no_opra": c_no_opra,
                        "n_excluded_no_spy_day": c_no_spy, "n_excluded_unwalkable": c_unwalkable},
            "arm_c": {"n": len(armc_rows), "n_excluded_no_opra": a_no_opra,
                      "n_excluded_no_spy_day": a_no_spy, "n_excluded_unwalkable": a_unwalkable},
        },
        "sequential_admission": {
            "control": {"candidates": len(control_rows), "sequential": len(control_sequential),
                        "self_preempted": len(control_rows) - len(control_sequential)},
            "arm_c": {"candidates": len(armc_rows), "sequential": len(armc_sequential),
                      "preempted": len(armc_rows) - len(armc_sequential)},
        },
        "control_sequential": control_stats,
        "arm_c_sequential": armc_stats,
        "day_level": {
            "recent_control_total": recent_control_total, "recent_armc_total": recent_armc_total,
            "recent_delta": recent_delta, "changed_days": changed_days,
            "n_improved": n_improved, "n_worsened": n_worsened,
        },
        "drop_best_on_delta": {
            "recent_delta": recent_delta, "best_single_contribution": round(max(0.0, best_contribution), 2),
            "remainder": dropped_delta, "still_positive": g3,
        },
        "decomposition": decomp,
        "runner_cohort": {
            "control": {"n": control_runner_n, "total_pnl": control_runner_pnl},
            "arm_c": {"n": armc_runner_n, "total_pnl": armc_runner_pnl},
            "count_ok_ge_95pct": g4_count_ok, "pnl_ok_ge_95pct": g4_pnl_ok,
        },
        "fire_count": {"n_added_full_population": n_added_full, "n_added_recent_window": n_added_recent,
                        "floor_full": 10, "floor_recent": 2},
        "advisory_bh_fdr": {"population": "added_cohort", "n": len(added_pnls), "p_value": round(p_val, 5),
                             "alpha": BH_ALPHA, "significant": bh_significant, "gates": False},
        "gates": all_gates,
        "verdict": verdict,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"total runtime {out['runtime_seconds']}s")
    return 0 if ship else 1


def write_markdown(out: dict) -> None:
    cs, as_ = out["control_sequential"], out["arm_c_sequential"]
    dl = out["day_level"]
    dc = out["decomposition"]
    rc = out["runner_cohort"]
    fc = out["fire_count"]
    bh = out["advisory_bh_fdr"]
    L = [
        "# BULL-VIX-SOFT-MODE-SOLE-BLOCKER -- real sequential A/B, 2026-08-03",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/bull_vix_soft_mode_2026_08_03.py`.",
        f"Prereg (frozen first): `{out['prereg']}` ({out['prereg_frozen_at_et']}).",
        f"Scope: {out['account_scope']}",
        f"Window: {out['window']['start']}..{out['window']['end']} "
        f"({out['window']['n_trading_days']} RTH trading days; cross-check vs "
        f"{out['window']['n_trading_days_crosscheck_source']}: "
        f"{out['window']['n_trading_days_crosscheck_value']}).",
        f"Recent-{out['recent_window']['n']} window: {out['recent_window']['start']}.."
        f"{out['recent_window']['end']}.",
        "",
        f"## VERDICT: {out['verdict']}",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for k, v in out["gates"].items():
        L.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    L += [
        "",
        "## Per-cell table (real sequential populations, one-position-at-a-time)",
        "",
        "| | CONTROL_SEQUENTIAL | ARM_C_SEQUENTIAL |",
        "|---|---|---|",
        f"| n (full population) | {cs['n']} | {as_['n']} |",
        f"| Total P&L (full population) | ${cs['total_pnl']:+,.2f} | ${as_['total_pnl']:+,.2f} |",
        f"| Win rate | {cs['win_rate']} | {as_['win_rate']} |",
        f"| Avg $/trade | ${cs['avg_pnl_per_trade']:+.2f} | ${as_['avg_pnl_per_trade']:+.2f} |",
        f"| Drop-best remainder (full pop) | ${cs['drop_best']['remainder']:+,.2f} "
        f"({'still +' if cs['drop_best']['still_positive'] else 'flips -'}) | "
        f"${as_['drop_best']['remainder']:+,.2f} "
        f"({'still +' if as_['drop_best']['still_positive'] else 'flips -'}) |",
        f"| Recent-{out['recent_window']['n']} n | {cs['recent_25']['n']} | {as_['recent_25']['n']} |",
        f"| Recent-{out['recent_window']['n']} total P&L (**G1 PRIMARY**) | "
        f"${cs['recent_25']['total_pnl']:+,.2f} | ${as_['recent_25']['total_pnl']:+,.2f} |",
        "",
        "## Day-level delta (G1/G2/G3 basis)",
        "",
        f"Recent-window day-total delta: ARM_C ${dl['recent_armc_total']:+,.2f} - CONTROL "
        f"${dl['recent_control_total']:+,.2f} = **${dl['recent_delta']:+,.2f}**",
        f"Changed days in recent window: {len(dl['changed_days'])} "
        f"(improved={dl['n_improved']} worsened={dl['n_worsened']})",
        f"Drop-best-on-delta: best single contribution "
        f"${out['drop_best_on_delta']['best_single_contribution']:+,.2f}, remainder "
        f"${out['drop_best_on_delta']['remainder']:+,.2f} "
        f"(still_positive={out['drop_best_on_delta']['still_positive']})",
        "",
        "## Decomposition: added vs pre-empted (full population)",
        "",
        f"- ADDED cohort (only possible via the new soft-demerit path): n={dc['added_cohort']['n']} "
        f"total=${dc['added_cohort']['total_pnl']:+,.2f}",
        f"- PRE-EMPTED cohort (CONTROL's own sequential trades displaced by an earlier "
        f"ARM_C-only trade): n={dc['preempted_cohort']['n']} total=${dc['preempted_cohort']['total_pnl']:+,.2f}",
        f"- gain_over_control_sequential=${dc['gain_over_control_sequential']:+,.2f}, "
        f"identity_holds={dc['identity_holds']}",
        f"- **Oracle-vs-sequential gap**: the prereg's motivating oracle figure "
        f"(FREQUENCY-CEILING-2026-08-03.md sec 4) was +$8,738.00 total / +$112.03 per "
        f"day-that-fires across 78 unsequenced, independently-priced sole-blocker candidates. "
        f"This run's ADDED cohort (the honest, sequentially-admitted analog) is "
        f"n={dc['added_cohort']['n']} total=${dc['added_cohort']['total_pnl']:+,.2f} -- see report "
        f"prose for the gap explanation.",
        "",
        "## Runner cohort (G4, zero tolerance, full population, THIS study's own SAFE CONTROL)",
        "",
        f"CONTROL n={rc['control']['n']} total=${rc['control']['total_pnl']:+,.2f} | "
        f"ARM_C n={rc['arm_c']['n']} total=${rc['arm_c']['total_pnl']:+,.2f} -- "
        f"count_ok={rc['count_ok_ge_95pct']} pnl_ok={rc['pnl_ok_ge_95pct']}",
        "",
        "## Fire count (G5, L243)",
        "",
        f"n_added full_population={fc['n_added_full_population']} (floor {fc['floor_full']}) | "
        f"recent_window={fc['n_added_recent_window']} (floor {fc['floor_recent']})",
        "",
        "## Advisory BH-FDR (NOT a ship gate)",
        "",
        f"Population: {bh['population']} (n={bh['n']}). p={bh['p_value']} alpha={bh['alpha']} "
        f"significant={bh['significant']}.",
        "",
        "---",
        "_Source: `backtest/tools/bull_vix_soft_mode_2026_08_03.py`. Raw JSON: "
        "`analysis/recommendations/bull-vix-soft-mode-2026-08-03.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
