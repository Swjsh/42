"""zone_width_fullhist_replay.py -- ZONE-WIDTH pre-registered 3-cell band study (2026-07-28).

LANE: "LEVELS ARE ZONES" (J standing doctrine, LESSONS-LEARNED.md:5048 -- 2026-07-17 10:15,
SPY 747.27 vs PDL 747.88, 61c shy, zero triggers: "levels are not ever exact to the penny!
its zones!!"). detect_level_rejection (backtest/lib/filters.py:540) demands a strict cross:
high > level AND close < level. This study measures what a symmetric proximity band adds --
MARGINAL trades only, separated from the shared base -- through the FULL production cascade.

===========================================================================================
PRE-REGISTRATION (frozen BEFORE the run; stated verbatim in the session transcript first)
===========================================================================================
HYPOTHESIS: widening the rejection test symmetrically by band b adds marginal trades whose
expectancy is comparable to the base engine's; concretely, the marginal cohort at b=10c
and/or b=25c is profitable through the full production entry cascade + real exit walk.

BANDED PREDICATE (exact, frozen) -- in-process monkeypatch of lib.filters.
detect_level_rejection (established pattern: zone_rejection_band_study.py:263), reaching
BOTH production call sites (levels_active filters.py:1480 + FHH filters.py:1541; bull-side
detect_level_reclaim untouched -- lane is the REJECTION test only, disclosed asymmetry):
  1. STRICT-PRESERVING: if the production strict predicate fires on any level (high > lvl
     AND close < lvl), return the production result unchanged (max such lvl). The shared
     base is preserved bit-for-bit.
  2. WICK-DEFERENCE: else, if production's wick fall-through detect_wick_rejection_bearish
     (module constants WICK_MIN_PCT_OF_RANGE/WICK_MIN_DOLLARS/WICK_CLOSE_TOLERANCE, read at
     call time) would fire on the SAME levels list, return None -- so filters.py:1528-1536's
     wick-promotion path executes unchanged. Without this the patch would intercept and
     potentially re-level existing wick trades, contaminating the shared base. (Side effect,
     disclosed: production never wick-tests the FHH level, so banded-FHH fires are also
     suppressed on bars where a wick pattern exists vs FHH -- slightly conservative.)
  3. BANDED FALL-THROUGH: else fire on any lvl with high > lvl - b AND close < lvl + b;
     return max such lvl (production tiebreak). At b=0 this is algebraically the production
     predicate, so the control cell is run with the UNPATCHED engine.
     KNOWN PROPERTY, DISCLOSED NOT PATCHED: the touch-side relaxation (high in (lvl-b, lvl])
     has no effective close constraint (close <= high <= lvl < lvl+b auto-satisfies), so
     green approach bars can fire. Deliberately NO unregistered red-close knob is added;
     the engine's own downstream gates (entry_bar_body_pct_min etc.) are the only screens.
     If green approaches poison the marginal cohort, the cells will show it -- that IS the
     answer, not a reason to re-tune mid-run.

CELLS (3 ONLY): b in {0.00 (control == unpatched production), 0.10, 0.25} dollars.

POPULATION / MACHINERY (reused, not re-derived): 390-RTH-day window 2025-01-02..2026-07-27
via ladder_fullhist_replay.load_extended_data(); entries via lib.orchestrator.run_backtest(
**engine_fullhist_replay.SAFE_BASE_LIVE) -- the full production cascade including
block_level_rejection=True, the sweep blocker, the L96 trendline_only interaction, NOT_FLAT
and the audited entry+1 convention (markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md
-- run_backtest's own entry layer, same as the engine-fullhist scorecard); exits via
backtest/lib/exit_manager_walk.walk_exit_manager under strategies.py#RIBBON_RIDE.exit.
to_dict() -- byte-identical to ladder_fullhist_replay.run_baseline. Real OPRA fills only
(run_backtest(use_real_fills=True) refuses uncached entries at the entry layer; the exit
walk's own OPRA lookup is a second check, counted).

MARGINAL DECOMPOSITION: trades matched control<->cell on the key (entry_time_et, side,
strike, qty, entry_premium@4dp, rejection_level@2dp). Matched = SHARED (control's walked
exit reused -- identical inputs => identical deterministic walk). Cell-only = MARGINAL
(walked fresh). Control-only = DISPLACED (control P&L foregone -- NOT_FLAT crowd-out or
gate flips, e.g. a banded level_rejection fire un-setting trendline_only_setup and
re-enabling filters 5/8, the L96 mechanism). Same-bar displaced+marginal pairs (shifted
trades) are counted as a separate diagnostic but stay in the marginal cohort (disclosed).

PASS BAR (frozen): a band cell is ship-eligible ONLY if its MARGINAL cohort has
  (a) positive aggregate P&L, (b) day-majority (win days > half of days with >=1 marginal
  trade), (c) survives-drop-best, (d) held-out (dates >= 2026-03-06, the same last-25%
  cutoff LADDER-FULLHIST-2026-07-27 used, touched once) positive
AND (e) net effect (marginal_total - displaced_total) >= 0.
Marginal n < 15 => evidence_thin advisory. ALL 3 cells reported, nulls plainly.

VERIFICATION ANCHOR: the control run must reproduce analysis/arm-ladder/
LADDER-FULLHIST-2026-07-27.json baseline_binary_engine.stats exactly (n=191,
total +$5,306.95, WR 0.2984, n_excluded_no_opra=18). Mismatch => VERIFICATION FAILED,
loud halt, no cell numbers reported as valid.

PRIOR ART (cited, not re-derived): backtest/tools/zone_rejection_band_study.py (2026-07-17)
tested a DIFFERENT predicate (approach-side only, red-close required, SS-B exits, window
..2026-07-08) -- NULL both accounts. markdown/research/EDGE-MATRIX-FULLHIST-2026-07-23.md:172
measured the raw bear-level-rejection signal family at -$28.84/trade (n=518, BH-significant
loser) OUTSIDE the engine cascade. This study is the first ZONE test run THROUGH the full
production engine on the full 390-day window with the real exit core.

Run: backtest/.venv/Scripts/python.exe backtest/tools/zone_width_fullhist_replay.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib import filters as filters_mod                    # noqa: E402
import elite_bear_level_reject_gate_ab as eb              # noqa: E402
import strategies as fleet_strategies                     # noqa: E402
import engine_fullhist_replay as efr                      # noqa: E402
import ladder_fullhist_replay as lfr                      # noqa: E402
from lib.orchestrator import run_backtest                 # noqa: E402
from lib.exit_manager_walk import walk_exit_manager       # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402

BANDS = (0.0, 0.10, 0.25)          # frozen pre-reg: 3 cells ONLY
FULL_START = lfr.FULL_START        # 2025-01-02
FULL_END = lfr.FULL_END            # 2026-07-27

OUT_DIR = ROOT / "analysis" / "deep-research"
OUT_JSON = OUT_DIR / "ZONE-WIDTH-2026-07-28.json"
OUT_MD = OUT_DIR / "ZONE-WIDTH-2026-07-28.md"

# Frozen verification anchor -- LADDER-FULLHIST-2026-07-27.json baseline_binary_engine.stats
ANCHOR_N_TRADES = 191
ANCHOR_TOTAL_PNL = 5306.95
ANCHOR_WIN_RATE = 0.2984
ANCHOR_N_NO_OPRA = 18
ANCHOR_HELD_OUT_CUTOFF = "2026-03-06"

_ORIG_DETECT = filters_mod.detect_level_rejection
_ORIG_WICK = filters_mod.detect_wick_rejection_bearish


def log(msg: str) -> None:
    print(f"[zone-width] {msg}", flush=True)


# =============================================================================== predicate

def make_banded_detector(band: float, fire_log: list):
    """The frozen pre-registered predicate. See module docstring steps 1-3."""
    def _banded(bar, levels_active):
        strict = _ORIG_DETECT(bar, levels_active)
        if strict is not None:
            return strict                                   # step 1: strict-preserving
        if not levels_active or band <= 0:
            return None                                     # b=0 == production exactly
        wick = _ORIG_WICK(
            bar, levels_active,
            min_wick_pct_of_range=filters_mod.WICK_MIN_PCT_OF_RANGE,
            min_wick_dollars=filters_mod.WICK_MIN_DOLLARS,
            close_tolerance_above_level=filters_mod.WICK_CLOSE_TOLERANCE,
        )
        if wick is not None:
            return None                                     # step 2: wick-deference
        high = float(bar["high"])
        close = float(bar["close"])
        fired = [lvl for lvl in levels_active if high > lvl - band and close < lvl + band]
        if not fired:
            return None
        lvl = max(fired)                                    # step 3: production tiebreak
        fire_log.append({
            "ts": efr.naive_dt(bar["timestamp_et"]).isoformat(),
            "level": float(round(lvl, 4)),
            "mode": "pierced_close_in_zone" if high > lvl else "approach_touch",
            "high": high, "close": close,
        })
        return float(lvl)
    return _banded


# =============================================================================== trade identity

def trade_key(t) -> tuple:
    return (
        efr.naive_dt(t.entry_time_et).isoformat(),
        str(t.side), int(t.strike), int(t.qty),
        round(float(t.entry_premium), 4),
        round(float(t.rejection_level), 2) if t.rejection_level is not None else None,
    )


# =============================================================================== exit walk

def walk_trades(trades, spy_rth: pd.DataFrame, ribbon_lookup: pd.DataFrame,
                exit_shape: dict) -> tuple[dict, list]:
    """Byte-identical machinery to ladder_fullhist_replay.run_baseline, keyed by trade_key.
    Returns ({key: row}, [excluded_keys])."""
    walked: dict = {}
    excluded: list = []
    for t in trades:
        key = trade_key(t)
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            excluded.append(key)
            continue
        day_spy = spy_rth.loc[spy_rth["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            excluded.append(key)
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et,
            entry_premium=float(t.entry_premium), qty=int(t.qty), exit_shape=exit_shape,
            structure_stop_enabled=True,
            trigger_level=(float(t.rejection_level) if t.rejection_level else None),
            strategy="ribbon_ride", time_stop_et=efr.TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        walked[key] = {
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": eb.classify_tier(t.triggers_fired),
            "symbol": symbol, "qty": int(t.qty),
            "entry_premium": round(float(t.entry_premium), 4),
            "triggers": t.triggers_fired, "rejection_level": t.rejection_level,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "hold_minutes": res.hold_minutes, "resolved": res.resolved,
        }
    return walked, excluded


def annotate_band_fire(row: dict, fire_log: list) -> dict:
    """Best-effort diagnostic: nearest band-branch fire strictly BEFORE entry within 10min
    (the trigger bar precedes the entry+1 fill bar)."""
    entry_ts = dt.datetime.fromisoformat(row["entry_time_et"])
    best, best_d = None, None
    for f in fire_log:
        fts = dt.datetime.fromisoformat(f["ts"])
        d = entry_ts - fts
        if dt.timedelta(0) < d <= dt.timedelta(minutes=10) and (best_d is None or d < best_d):
            best, best_d = f, d
    out = dict(row)
    out["band_fire_mode"] = best["mode"] if best else None
    out["band_fire_level"] = best["level"] if best else None
    out["band_fire_ts"] = best["ts"] if best else None
    return out


# =============================================================================== stats helpers

def cohort_stats(rows: list[dict], all_dates: list, cutoff: dt.date) -> dict:
    return lfr.lane_stats(rows, all_dates, cutoff)


def gate_eval(marginal_stats: dict, net_effect: float) -> dict:
    n = marginal_stats["n_trades"]
    g = {
        "a_positive_aggregate": bool(n > 0 and marginal_stats["total_pnl"] > 0),
        "b_day_majority": bool(marginal_stats["day_majority"]["is_majority"] is True),
        "c_survives_drop_best": bool(
            marginal_stats["survives_dropping_best_trade"]["still_positive"] is True),
        "d_held_out_positive": bool(
            marginal_stats["held_out_last_25pct"]["n_trades"] > 0
            and marginal_stats["held_out_last_25pct"]["total_pnl"] > 0),
        "e_net_effect_nonnegative": bool(net_effect >= 0),
    }
    g["ship_eligible"] = all(g.values())
    g["evidence_thin"] = n < 15
    return g


# =============================================================================== main

def main() -> int:
    t_start = time.time()
    log("PRE-REGISTRATION echo (frozen before run): 3 cells b in {0.00 control, 0.10, 0.25}; "
        "predicate = strict-preserving + wick-deference + banded fall-through "
        "(high > lvl-b AND close < lvl+b, max tiebreak); pass bar = marginal cohort "
        "positive-aggregate AND day-majority AND drop-best AND held-out-positive AND "
        "net-effect >= 0. See module docstring for the full frozen text.")

    log(f"loading extended SPY/VIX data {FULL_START}..{FULL_END} (ladder machinery)")
    spy_df_raw, vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    ribbon_lookup = efr.build_ribbon_lookup(spy_df_raw)
    exit_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    all_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())
    window_days = (FULL_END - FULL_START).days
    cutoff = FULL_START + dt.timedelta(days=round(window_days * 0.75))
    assert cutoff.isoformat() == ANCHOR_HELD_OUT_CUTOFF, (
        f"held-out cutoff drifted: {cutoff} != {ANCHOR_HELD_OUT_CUTOFF}")
    log(f"  {len(spy_rth)} RTH rows, {len(all_dates)} RTH days, held-out cutoff {cutoff}")

    # ---------------- CONTROL (b=0.00): the UNPATCHED production engine ----------------
    log("CELL b=0.00 (control): run_backtest(**SAFE_BASE_LIVE), UNPATCHED")
    t0 = time.time()
    assert filters_mod.detect_level_rejection is _ORIG_DETECT, "patch leaked before control"
    r_ctrl = run_backtest(spy_df_raw, vix_df, start_date=FULL_START, end_date=FULL_END,
                          **efr.SAFE_BASE_LIVE)
    log(f"  control entry layer: {len(r_ctrl.trades)} raw entries ({time.time()-t0:.1f}s)")
    t0 = time.time()
    ctrl_walked, ctrl_excluded = walk_trades(r_ctrl.trades, spy_rth, ribbon_lookup, exit_shape)
    ctrl_stats = cohort_stats(list(ctrl_walked.values()), all_dates, cutoff)
    log(f"  control exit layer: n={ctrl_stats['n_trades']} total=${ctrl_stats['total_pnl']:+.2f} "
        f"WR={ctrl_stats['win_rate']} no_opra={len(ctrl_excluded)} ({time.time()-t0:.1f}s)")

    verification = {
        "expected": {"n_trades": ANCHOR_N_TRADES, "total_pnl": ANCHOR_TOTAL_PNL,
                     "win_rate": ANCHOR_WIN_RATE, "n_excluded_no_opra": ANCHOR_N_NO_OPRA},
        "observed": {"n_trades": ctrl_stats["n_trades"], "total_pnl": ctrl_stats["total_pnl"],
                     "win_rate": ctrl_stats["win_rate"], "n_excluded_no_opra": len(ctrl_excluded)},
    }
    verification["pass"] = (
        ctrl_stats["n_trades"] == ANCHOR_N_TRADES
        and abs(ctrl_stats["total_pnl"] - ANCHOR_TOTAL_PNL) <= 0.01
        and abs((ctrl_stats["win_rate"] or 0) - ANCHOR_WIN_RATE) <= 0.0001
        and len(ctrl_excluded) == ANCHOR_N_NO_OPRA
    )
    log(f"VERIFICATION ANCHOR (vs LADDER-FULLHIST baseline): pass={verification['pass']} "
        f"{verification['observed']}")
    if not verification["pass"]:
        log("VERIFICATION FAILED -- control does not reproduce the pinned ladder baseline. "
            "Halting; writing failure record only.")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps({
            "_doc": __doc__, "generated_at": dt.datetime.now().isoformat(),
            "verdict": "VERIFICATION_FAILED", "verification": verification,
        }, indent=2, default=str), encoding="utf-8")
        return 1

    ctrl_keys = {trade_key(t): t for t in r_ctrl.trades}

    # ---------------- band cells ----------------
    cells: dict = {}
    for band in BANDS[1:]:
        label = f"{int(round(band*100))}c"
        fire_log: list = []
        log(f"CELL b={band:.2f} ({label}): patched run_backtest")
        t0 = time.time()
        filters_mod.detect_level_rejection = make_banded_detector(band, fire_log)
        try:
            r_cell = run_backtest(spy_df_raw, vix_df, start_date=FULL_START,
                                  end_date=FULL_END, **efr.SAFE_BASE_LIVE)
        finally:
            filters_mod.detect_level_rejection = _ORIG_DETECT
        log(f"  entry layer: {len(r_cell.trades)} raw entries, {len(fire_log)} band-branch "
            f"fires ({time.time()-t0:.1f}s)")

        cell_keys = {trade_key(t): t for t in r_cell.trades}
        shared_keys = [k for k in cell_keys if k in ctrl_keys]
        marginal_raw = [t for k, t in cell_keys.items() if k not in ctrl_keys]
        displaced_keys = [k for k in ctrl_keys if k not in cell_keys]

        t0 = time.time()
        marg_walked, marg_excluded = walk_trades(marginal_raw, spy_rth, ribbon_lookup,
                                                 exit_shape)
        marg_rows = [annotate_band_fire(row, fire_log) for row in marg_walked.values()]
        log(f"  marginal exit layer: {len(marg_rows)} walked, {len(marg_excluded)} no-OPRA "
            f"({time.time()-t0:.1f}s)")

        shared_rows = [ctrl_walked[k] for k in shared_keys if k in ctrl_walked]
        displaced_rows = [ctrl_walked[k] for k in displaced_keys if k in ctrl_walked]

        marg_stats = cohort_stats(marg_rows, all_dates, cutoff)
        displ_stats = cohort_stats(displaced_rows, all_dates, cutoff)
        full_book = shared_rows + marg_rows
        book_stats = cohort_stats(full_book, all_dates, cutoff)
        net_effect = round(marg_stats["total_pnl"] - displ_stats["total_pnl"], 2)

        # shifted-pair diagnostic: displaced + marginal sharing an entry timestamp
        marg_ts = {r["entry_time_et"] for r in marg_rows}
        n_shifted_pairs = sum(1 for r in displaced_rows if r["entry_time_et"] in marg_ts)

        mode_counts: dict = {}
        for f in fire_log:
            mode_counts[f["mode"]] = mode_counts.get(f["mode"], 0) + 1

        gates = gate_eval(marg_stats, net_effect)
        cells[label] = {
            "band_dollars": band,
            "n_raw_entries": len(r_cell.trades),
            "n_shared": len(shared_rows), "n_marginal": len(marg_rows),
            "n_marginal_no_opra": len(marg_excluded),
            "n_displaced": len(displaced_rows), "n_shifted_pairs_same_bar": n_shifted_pairs,
            "n_band_branch_fires": len(fire_log), "fire_mode_counts": mode_counts,
            "fire_log_sample_first_50": fire_log[:50],
            "marginal_stats": marg_stats, "displaced_stats": displ_stats,
            "full_book_stats": book_stats, "net_effect_vs_control": net_effect,
            "gates": gates,
            "marginal_trades": marg_rows, "displaced_trades": displaced_rows,
        }
        log(f"  [{label}] marginal n={marg_stats['n_trades']} "
            f"pnl=${marg_stats['total_pnl']:+.2f} WR={marg_stats['win_rate']} | "
            f"displaced n={len(displaced_rows)} pnl=${displ_stats['total_pnl']:+.2f} | "
            f"net=${net_effect:+.2f} | ship_eligible={gates['ship_eligible']}")

    control_cell = {
        "band_dollars": 0.0, "n_raw_entries": len(r_ctrl.trades),
        "n_shared": ctrl_stats["n_trades"], "n_marginal": 0, "n_marginal_no_opra": 0,
        "n_displaced": 0, "n_band_branch_fires": 0,
        "full_book_stats": ctrl_stats, "net_effect_vs_control": 0.0,
        "note": "control == unpatched production engine; marginal is definitionally empty",
    }

    total_elapsed = round(time.time() - t_start, 1)
    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat(),
                   "n_calendar_rth_days": len(all_dates)},
        "held_out_split": {"cutoff_date": cutoff.isoformat(),
                           "note": "last ~25% by date, touched once, reported not tuned "
                                   "(same cutoff as LADDER-FULLHIST-2026-07-27)"},
        "verification_anchor": verification,
        "cells": {"0c": control_cell, **cells},
        "runtime_seconds": total_elapsed,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD} ({total_elapsed}s total)")
    return 0


# =============================================================================== markdown

def _pnl(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def write_markdown(out: dict) -> None:
    v = out["verification_anchor"]
    c0 = out["cells"]["0c"]
    L = ["# ZONE-WIDTH -- pre-registered 3-cell band study (levels-are-zones), "
         "2025-01-02..2026-07-27", ""]
    L.append(f"Generated {out['generated_at']}. Runner: "
             f"`backtest/tools/zone_width_fullhist_replay.py`. "
             f"Runtime {out['runtime_seconds']}s.")
    L.append("")
    L.append("## Verdict first")
    L.append("")
    L.append("| Cell | Marginal n | Marginal P&L | Marginal WR | Day-majority | Drop-best | "
             "Held-out (>=2026-03-06) | Displaced n / P&L | NET vs control | Ship-eligible |")
    L.append("|---|--:|--:|--:|---|---|---|---|--:|:--:|")
    L.append(f"| **0c (control)** | 0 (definitional) | -- | -- | -- | -- | -- | 0 / -- | $0.00 | -- |")
    for label in ("10c", "25c"):
        c = out["cells"][label]
        m = c["marginal_stats"]
        d = c["displaced_stats"]
        g = c["gates"]
        dm = m["day_majority"]
        held = m["held_out_last_25pct"]
        L.append(
            f"| **{label}** | {m['n_trades']} | {_pnl(m['total_pnl'])} | {m['win_rate']} | "
            f"{dm['win_days']}/{dm['total_trading_days']} ({dm['is_majority']}) | "
            f"{_pnl(m['survives_dropping_best_trade']['total_minus_best'])} "
            f"({m['survives_dropping_best_trade']['still_positive']}) | "
            f"{held['n_trades']}tr {_pnl(held['total_pnl'])} | "
            f"{c['n_displaced']} / {_pnl(d['total_pnl'])} | "
            f"{_pnl(c['net_effect_vs_control'])} | "
            f"{'YES' if g['ship_eligible'] else 'NO'}"
            f"{' (thin)' if g['evidence_thin'] else ''} |"
        )
    L.append("")
    L.append(f"Control full book (must equal LADDER-FULLHIST baseline): "
             f"n={c0['full_book_stats']['n_trades']}, "
             f"{_pnl(c0['full_book_stats']['total_pnl'])}, "
             f"WR={c0['full_book_stats']['win_rate']}. "
             f"**Verification anchor pass: {v['pass']}.**")
    L.append("")
    L.append("## Pre-registration (frozen before the run)")
    L.append("")
    L.append("Stated in-session before any cell ran; frozen verbatim in this runner's module "
             "docstring (`backtest/tools/zone_width_fullhist_replay.py`). Cells: band b in "
             "{0.00 control, 0.10, 0.25} applied to `detect_level_rejection` as: "
             "(1) strict-preserving (production fire always returned unchanged), "
             "(2) wick-deference (production's `detect_wick_rejection_bearish` fall-through "
             "keeps ownership of its bars), (3) banded fall-through "
             "`high > level - b AND close < level + b`, max-level tiebreak. Pass bar on the "
             "MARGINAL cohort: positive aggregate AND day-majority AND survives-drop-best AND "
             "held-out positive AND net-effect >= 0. n<15 = evidence-thin advisory.")
    L.append("")
    L.append("## Per-cell detail")
    L.append("")
    for label in ("10c", "25c"):
        c = out["cells"][label]
        L.append(f"### Cell {label} (band ${c['band_dollars']:.2f})")
        L.append("")
        L.append(f"- Band-branch fires (trigger-level, pre-cascade): {c['n_band_branch_fires']} "
                 f"-- modes {c['fire_mode_counts']}")
        L.append(f"- Raw entries {c['n_raw_entries']} = shared {c['n_shared']} + marginal "
                 f"{c['n_marginal']} (+{c['n_marginal_no_opra']} marginal no-OPRA excluded); "
                 f"displaced {c['n_displaced']} (same-bar shifted pairs: "
                 f"{c['n_shifted_pairs_same_bar']})")
        b = c["full_book_stats"]
        L.append(f"- Full book under this band: n={b['n_trades']} {_pnl(b['total_pnl'])} "
                 f"WR={b['win_rate']} maxDD={_pnl(b['max_drawdown'])} "
                 f"vs control {_pnl(c0['full_book_stats']['total_pnl'])}")
        gates = c["gates"]
        L.append(f"- Gates: {gates}")
        if c["marginal_trades"]:
            L.append("")
            L.append("| Date | Entry | Tier | Triggers | Level | Fire mode | P&L | Exit |")
            L.append("|---|---|---|---|---|---|--:|---|")
            for r in sorted(c["marginal_trades"], key=lambda x: x["entry_time_et"]):
                L.append(f"| {r['date']} | {r['entry_time_et'][11:16]} | {r['tier']} | "
                         f"{','.join(r['triggers'])} | {r['rejection_level']} | "
                         f"{r.get('band_fire_mode')} | {_pnl(r['dollar_pnl'])} | "
                         f"{r['exit_reason']} |")
        if c["displaced_trades"]:
            L.append("")
            L.append("Displaced (control trades this band's cascade removed):")
            L.append("")
            L.append("| Date | Entry | Tier | Triggers | Control P&L (foregone) |")
            L.append("|---|---|---|---|--:|")
            for r in sorted(c["displaced_trades"], key=lambda x: x["entry_time_et"]):
                L.append(f"| {r['date']} | {r['entry_time_et'][11:16]} | {r['tier']} | "
                         f"{','.join(r['triggers'])} | {_pnl(r['dollar_pnl'])} |")
        L.append("")
    L.append("## Disclosures")
    L.append("")
    L.append("- MEASURED replay, not realized fills: the banded trigger does not exist in "
             "production; entries flow through run_backtest's audited entry+1 layer and the "
             "real `walk_exit_manager` exit core, real OPRA fills only.")
    L.append("- The band patch reaches BOTH bear call sites (levels_active + FHH); the bull "
             "`detect_level_reclaim` is untouched (lane = rejection only). Wick-deference "
             "also suppresses banded-FHH fires where a wick pattern exists vs FHH "
             "(production never wick-tests FHH) -- slightly conservative, disclosed.")
    L.append("- Touch-side banded fires have no effective close constraint (green approach "
             "bars can fire) -- known property of the pre-registered predicate, deliberately "
             "not patched mid-run.")
    L.append("- Safe-account config only (SAFE_BASE_LIVE), matching the ladder baseline's "
             "scope; Bold not run.")
    L.append("- `block_level_rejection=True` is live in SAFE_BASE_LIVE: single-trigger "
             "LEVEL-tier entries are suppressed by the production cascade, so marginal "
             "trades are band-fires that compose into multi-trigger setups (or FHH/confluence "
             "paths). A small marginal n is the cascade working, not a bug.")
    L.append("- Same-bar shifted pairs (displaced control trade + marginal cell trade on one "
             "bar, e.g. via the L96 trendline_only interaction) stay in the marginal cohort "
             "and are counted separately.")
    L.append("- The motivating 2026-07-17 10:15 live miss was 61c shy -- OUTSIDE both "
             "pre-registered bands (10c/25c). These cells cannot capture that specific "
             "incident; widening beyond 25c was deliberately NOT added post-hoc.")
    L.append("")
    L.append("---")
    L.append("_Raw JSON with per-trade detail + fire-log sample: "
             "`analysis/deep-research/ZONE-WIDTH-2026-07-28.json`._")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
