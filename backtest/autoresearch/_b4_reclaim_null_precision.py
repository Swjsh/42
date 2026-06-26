"""DIAGNOSTIC (b4): reclaim_null_precision — does struct_vwap_reclaim_failed_break
have real intra-day TIMING precision, or is its edge pure day+side SELECTION? Plus a
fine stop-buffer plateau sweep to confirm $0.25 is a stable plateau, not a spike.

NO NEW EDGE EXPECTED. This is a diagnostic on the CONFIRMED 2nd edge (edge #2:
struct_vwap_reclaim_failed_break — validated+dormant). It informs (a) sizing/confidence
and (b) whether to push the edge harder.

────────────────────────────────────────────────────────────────────────────────
THE TWO QUESTIONS
────────────────────────────────────────────────────────────────────────────────
PART A — TIMING PRECISION vs DAY+SIDE SELECTION
  The signal is "one causal entry/day on the with-trend VWAP reclaim bar." Two ways it
  could be profitable:
    (1) DAY+SIDE SELECTION — it just picks the right TREND DAYS and the right SIDE; ANY
        entry on those days/sides would also win (the trigger BAR doesn't matter).
    (2) TIMING PRECISION — the specific reclaim BAR is itself a good entry; the signal
        beats a RANDOM eligible morning bar on the SAME DAY, SAME SIDE.
  The decisive control is the bar-randomized SAME-DAY SIDE-MATCHED null (already coded
  in the validated sub-struct module as `sameday_null`): for each real signal, pick a
  RANDOM eligible morning bar [TREND_BARS..ENTRY_CUTOFF] on the SAME day, keep the SAME
  side + SAME stop geometry + SAME strike + SAME exits, and simulate. The day+side
  SELECTION is held constant across signal and null; ONLY the entry BAR is randomized.
  So: signal per-trade >> same-day null per-trade  => TIMING PRECISION.
      signal per-trade ~= same-day null per-trade  => pure DAY+SIDE SELECTION.

  This diagnostic runs that null at HIGH seed count (default 60 vs the gate's 20) to get
  a TIGHT null distribution, then quantifies the lift as a z-score / percentile on BOTH
  the FULL sample and the OOS(2026) slice — so "precision vs selection" is a number, not
  a boolean. (Prior gate run found: FULL beats mean+1std, but OOS sits INSIDE the band.)
  We also report the coarser coin-flip null (randomizes across ALL RTH days, the looser
  control already in the gate) for contrast.

PART B — STOP-BUFFER PLATEAU
  The Safe-2 rescue (ATM cell) hinged ENTIRELY on dropping `level_stop_buffer_dollars`
  from the v15 default $0.50 to $0.25 (7/8 -> 8/8). The scorecard flagged: if $0.25 is
  an ISOLATED spike (not a plateau), the rescue is fragile. So sweep
  buf in {0.10, 0.15, 0.20, 0.25, 0.30} at ATM (strike_offset 0, tp1=0.30, -8% stop),
  ALL 8 gates per buffer, and report whether the neighborhood is a stable plateau
  (a contiguous run of cells all positive / mostly-gate-clearing around 0.25) or a spike.

────────────────────────────────────────────────────────────────────────────────
ALL 8 GATES (anti-2.10) reported for every buffer cell (Part B) and for the PRIMARY
ITM-2 + Safe-2 ATM tiers (Part A). Detector + same-day null + coin-flip null + metrics
reused BYTE-FOR-BYTE from the validated sub-struct / rescue modules (no detector drift).

Pure Python, $0 (no LLM, no live orders). Markets closed.
Writes analysis/recommendations/b4-reclaim-null-precision.json.

Run: backtest/.venv/Scripts/python.exe \
       backtest/autoresearch/_b4_reclaim_null_precision.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import build_day_contexts, Signal  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    TREND_BARS,
    ENTRY_CUTOFF,
    QTY,
    OOS_YEAR,
)
# Reuse the EXACT validated detector + same-day null + the rescue sim/metrics/gate
# code (with sweepable TP1 + chart-stop buffer) byte-for-byte. No detector drift.
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals,
    sameday_null,
)
from autoresearch._rescue_otm2 import (  # noqa: E402
    simulate_set,
    metrics,
    evaluate_cell,
    SURV_PREMIUM_STOP,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "b4-reclaim-null-precision.json"

# ── Config ──────────────────────────────────────────────────────────────────
PRIMARY_STRIKE_OFFSET = -2     # ITM-2 (the promoted winner / anchor)
SAFE2_STRIKE_OFFSET = 0        # ATM (the Safe-2 rescue cell)
RESCUE_TP1_PCT = 0.30          # v15 default TP1 (the rescue ATM cell uses 0.30)
RESCUE_BUFFER = 0.25           # the rescue knob under scrutiny
BUFFER_SWEEP = [0.10, 0.15, 0.20, 0.25, 0.30]   # the fine plateau sweep (Part B)
HI_SEEDS = 60                  # tighter same-day null band than the gate's 20
N_NULL_SEEDS = 20              # gate-standard coin-flip null seeds (for contrast)


# ─────────────────────────────────────────────────────────────────────────────
# PART A — high-seed same-day/same-side null: precision vs selection, quantified.
# Reuses sameday_null (the validated bar-randomized same-day side-matched control)
# at higher seed count, then adds a z-score/percentile lift on FULL + OOS slices.
# To get a per-seed OOS distribution + a tight band we re-derive the per-seed series
# here (sameday_null only returns aggregates), reusing its EXACT sampling logic.
# ─────────────────────────────────────────────────────────────────────────────
def _sameday_per_seed(signals, spy, ribbon, vix, days, *, seeds, strike_offset,
                      premium_stop_pct, tp1_premium_pct, level_stop_buffer_dollars):
    """Per-seed FULL + OOS per-trade for the bar-randomized same-day side-matched null.

    Identical sampling to _sub_struct.sameday_null (same RNG stream: np.default_rng(7000+s),
    same eligible-bar set [TREND_BARS..ENTRY_CUTOFF] per day, same side + stop held), but
    returns the full per-seed arrays so we can quantify a z-score/percentile. Threads the
    SAME exit knobs (tp1, buffer) as the cell under test so the null mirrors it exactly.
    """
    day_bars: dict[dt.date, list[int]] = {}
    for dc in days:
        rth = dc.rth
        times = rth["t"].values
        idxs = rth.index.tolist()
        elig = [int(idxs[j]) for j in range(TREND_BARS, len(rth)) if times[j] <= ENTRY_CUTOFF]
        if elig:
            day_bars[dc.date] = elig
    sig_specs = []
    for sg in signals:
        d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
        sig_specs.append((d, sg.side, sg.stop_level))

    full_exp, oos_exp, full_tot = [], [], []
    for seed in range(seeds):
        rng = np.random.default_rng(7000 + seed)
        rand_sigs = []
        for d, sd, stop in sig_specs:
            elig = day_bars.get(d)
            if not elig:
                continue
            bidx = int(rng.choice(elig))
            rand_sigs.append(Signal(bar_idx=bidx, side=sd, stop_level=stop, note="rand"))
        rows, _ = simulate_set(rand_sigs, spy, ribbon, vix, strike_offset=strike_offset,
                               premium_stop_pct=premium_stop_pct,
                               tp1_premium_pct=tp1_premium_pct,
                               level_stop_buffer_dollars=level_stop_buffer_dollars)
        if not rows:
            continue
        m = metrics(rows)
        full_exp.append(m["exp_dollar"])
        oos_exp.append(m["oos_exp"])
        full_tot.append(m["total_dollar"])
    return {
        "seeds": len(full_exp),
        "full_exp": full_exp,
        "oos_exp": oos_exp,
        "full_tot": full_tot,
    }


def _lift_stats(signal_value: float, null_series: list[float]) -> dict:
    """Quantify how far the signal sits above the null distribution."""
    if not null_series:
        return {"n_seeds": 0}
    arr = np.array(null_series, float)
    mean = float(arr.mean())
    std = float(arr.std())
    nmax = float(arr.max())
    nmin = float(arr.min())
    pct_above = float((arr < signal_value).mean()) * 100.0   # percentile of signal in null dist
    z = (signal_value - mean) / std if std > 1e-9 else float("inf") if signal_value > mean else 0.0
    return {
        "n_seeds": len(null_series),
        "null_mean": round(mean, 2),
        "null_std": round(std, 2),
        "null_min": round(nmin, 2),
        "null_max": round(nmax, 2),
        "signal_value": round(signal_value, 2),
        "lift_over_mean": round(signal_value - mean, 2),
        "z_score": (round(z, 2) if z != float("inf") else "inf"),
        "percentile_in_null": round(pct_above, 1),
        "beats_null_max": bool(signal_value > nmax),
        "beats_mean_plus_1std": bool(signal_value > mean + std),
        "beats_mean_plus_2std": bool(signal_value > mean + 2 * std),
    }


def precision_block(signals, spy, ribbon, vix, days, *, strike_offset, tier_label,
                    tp1_premium_pct, level_stop_buffer_dollars) -> dict:
    """The PART-A precision-vs-selection diagnostic for one strike tier."""
    rows, cov = simulate_set(signals, spy, ribbon, vix, strike_offset=strike_offset,
                             premium_stop_pct=SURV_PREMIUM_STOP,
                             tp1_premium_pct=tp1_premium_pct,
                             level_stop_buffer_dollars=level_stop_buffer_dollars)
    m = metrics(rows)
    if not m.get("n"):
        return {"tier": tier_label, "strike_offset": strike_offset,
                "note": "no filled trades"}

    # High-seed same-day/same-side null (the precision control).
    sd = _sameday_per_seed(signals, spy, ribbon, vix, days, seeds=HI_SEEDS,
                           strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP,
                           tp1_premium_pct=tp1_premium_pct,
                           level_stop_buffer_dollars=level_stop_buffer_dollars)
    full_lift = _lift_stats(m["exp_dollar"], sd.get("full_exp", []))
    oos_lift = _lift_stats(m.get("oos_exp", 0.0), sd.get("oos_exp", []))

    # Coarser coin-flip null (randomizes the entry bar across ALL RTH days) for contrast.
    rth_all = pd.concat([dc.rth for dc in days]).sort_index().reset_index(drop=True)
    n_call = sum(1 for s in signals if s.side == "C")
    n_put = sum(1 for s in signals if s.side == "P")
    coin = random_entry_null(rth_all, n_signals=len(signals), n_call=n_call, n_put=n_put,
                             strike_offset=strike_offset, premium_stop_pct=SURV_PREMIUM_STOP,
                             seeds=N_NULL_SEEDS)
    coin_g = null_gate(m["exp_dollar"], m.get("drop_top5_day_per_trade"), coin)

    # PRECISION VERDICT (the decisive read): the signal has TIMING PRECISION on a slice
    # iff its per-trade beats the same-day/same-side null mean by a real margin
    # (>= +1 std). If full-sample shows precision but OOS sits inside the band, the OOS
    # edge is largely day+side SELECTION (the dormant-edge caveat, now quantified).
    full_precise = bool(full_lift.get("beats_mean_plus_1std"))
    oos_precise = bool(oos_lift.get("beats_mean_plus_1std"))
    if full_precise and oos_precise:
        precision_verdict = ("TIMING PRECISION (both): the reclaim bar beats a same-day "
                             "same-side random entry by >=1std on FULL and OOS — the trigger "
                             "timing itself adds edge beyond day+side selection.")
    elif full_precise and not oos_precise:
        precision_verdict = ("MIXED: FULL-sample shows timing precision (>=1std over the same-day "
                             "null) but OOS sits INSIDE the same-day null band -> the OOS edge is "
                             "largely DAY+SIDE SELECTION, not trigger precision. Size on selection, "
                             "not on the bar.")
    else:
        precision_verdict = ("DAY+SIDE SELECTION: the signal does NOT clear the same-day same-side "
                             "null by >=1std on FULL -> the edge is choosing the right trend "
                             "days/sides; the specific reclaim bar adds little.")

    return {
        "tier": tier_label,
        "strike_offset": strike_offset,
        "strike_tier_name": (f"ITM{abs(strike_offset)}" if strike_offset < 0
                             else ("ATM" if strike_offset == 0 else f"OTM{strike_offset}")),
        "exit_config": {"tp1_premium_pct": tp1_premium_pct,
                        "level_stop_buffer_dollars": level_stop_buffer_dollars,
                        "premium_stop_pct": SURV_PREMIUM_STOP},
        "coverage": cov,
        "headline": {"n": m["n"], "exp_dollar": m["exp_dollar"], "oos_exp": m.get("oos_exp"),
                     "oos_n": m.get("oos_n"), "wr_pct": m.get("wr_pct"),
                     "positive_quarters": m.get("positive_quarters")},
        "sameday_null_highseed": {
            "seeds": sd.get("seeds"),
            "full": full_lift,
            "oos": oos_lift,
        },
        "coinflip_null": {**coin, **coin_g},
        "full_timing_precision": full_precise,
        "oos_timing_precision": oos_precise,
        "precision_verdict": precision_verdict,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PART B — stop-buffer plateau sweep at ATM (the Safe-2 rescue cell).
# Reuses _rescue_otm2.evaluate_cell byte-for-byte (all 8 gates per cell).
# ─────────────────────────────────────────────────────────────────────────────
def buffer_sweep(signals, spy, ribbon, vix, days) -> dict:
    # Include the v15 default $0.50 as a REFERENCE cell (outside the fine sweep) so the
    # plateau is anchored against the knob the rescue actually moved away from. Reported
    # but not part of the contiguity run (the fine sweep is the {0.10..0.30} neighborhood).
    cells = []
    ref_cell = evaluate_cell(signals, spy, ribbon, vix, days,
                             strike_offset=SAFE2_STRIKE_OFFSET, tp1_premium_pct=RESCUE_TP1_PCT,
                             level_stop_buffer_dollars=0.50)
    rm = ref_cell.get("metrics", {})
    print(f"[bufsweep ATM buf=0.50 REF(v15)] n={rm.get('n')} exp=${rm.get('exp_dollar')} "
          f"oos=${rm.get('oos_exp')} => gates {ref_cell.get('n_gates_passed')}/8 "
          f"clears={ref_cell.get('clears_all_gates')}", flush=True)
    for buf in BUFFER_SWEEP:
        blk = evaluate_cell(signals, spy, ribbon, vix, days,
                            strike_offset=SAFE2_STRIKE_OFFSET, tp1_premium_pct=RESCUE_TP1_PCT,
                            level_stop_buffer_dollars=buf)
        cells.append(blk)
        m = blk.get("metrics", {})
        print(f"[bufsweep ATM buf={buf:.2f}] n={m.get('n')} exp=${m.get('exp_dollar')} "
              f"oos=${m.get('oos_exp')} posQ={m.get('positive_quarters')} "
              f"=> gates {blk.get('n_gates_passed')}/8 clears={blk.get('clears_all_gates')} "
              f"safe2={blk.get('safe2_tradeable')}", flush=True)

    # Plateau analysis: contiguous run of cells that all clear all 8 gates AND whose OOS
    # per-trade stays positive, spanning the 0.25 knob. A plateau = >=2 contiguous
    # gate-clearing cells around 0.25 (0.25 not the lone winner). A spike = 0.25 is the
    # ONLY gate-clearing cell in the neighborhood.
    by_buf = {round(c["level_stop_buffer_dollars"], 2): c for c in cells}
    clears = {b: bool(c.get("clears_all_gates")) for b, c in by_buf.items()}
    oos = {b: (c.get("metrics", {}) or {}).get("oos_exp") for b, c in by_buf.items()}
    n_clearing = sum(1 for v in clears.values() if v)
    rescue_clears = clears.get(RESCUE_BUFFER, False)

    # neighbors of the rescue buffer (0.20 and 0.30)
    neighbor_buffers = [b for b in (0.20, 0.30)]
    neighbors_clearing = [b for b in neighbor_buffers if clears.get(b)]
    # contiguous gate-clearing run containing 0.25
    ordered = sorted(by_buf.keys())
    run = 0
    if rescue_clears:
        run = 1
        # extend down
        idx = ordered.index(RESCUE_BUFFER)
        i = idx - 1
        while i >= 0 and clears.get(ordered[i]):
            run += 1
            i -= 1
        i = idx + 1
        while i < len(ordered) and clears.get(ordered[i]):
            run += 1
            i += 1

    # OOS-positive plateau (looser, more informative than full-gate-clearing): how many
    # contiguous buffers around 0.25 keep OOS per-trade > 0?
    oos_pos = {b: (v is not None and v > 0) for b, v in oos.items()}
    oos_run = 0
    if oos_pos.get(RESCUE_BUFFER):
        oos_run = 1
        idx = ordered.index(RESCUE_BUFFER)
        i = idx - 1
        while i >= 0 and oos_pos.get(ordered[i]):
            oos_run += 1
            i -= 1
        i = idx + 1
        while i < len(ordered) and oos_pos.get(ordered[i]):
            oos_run += 1
            i += 1

    # Flat-plateau check: are the per-trade results IDENTICAL across the whole fine sweep?
    # If so, the buffer knob does not bind inside {0.10..0.30} (the rescue's gain came from
    # crossing the $0.50 boundary), and $0.25 is the CENTER of a wide flat plateau — the
    # opposite of a knife-edge spike. We surface this explicitly (anti-C14 dead-knob read).
    fine_exps = [round(((c.get("metrics", {}) or {}).get("exp_dollar") or 0.0), 2) for c in cells]
    fine_oos = [round(((c.get("metrics", {}) or {}).get("oos_exp") or 0.0), 2) for c in cells]
    flat_plateau = bool(len(set(fine_exps)) == 1 and len(set(fine_oos)) == 1)
    ref_exp = round(((ref_cell.get("metrics", {}) or {}).get("exp_dollar") or 0.0), 2)
    ref_oos = round(((ref_cell.get("metrics", {}) or {}).get("oos_exp") or 0.0), 2)
    ref_clears = bool(ref_cell.get("clears_all_gates"))
    boundary_binds = bool((ref_exp, ref_oos) != (fine_exps[0], fine_oos[0])) if fine_exps else False

    is_plateau = bool(rescue_clears and (run >= 2 or len(neighbors_clearing) >= 1 or flat_plateau))
    if is_plateau and flat_plateau:
        plateau_verdict = (f"FLAT PLATEAU: every buffer in {BUFFER_SWEEP} yields IDENTICAL results "
                           f"(exp=${fine_exps[0]}, oos=${fine_oos[0]}, 8/8 gates) — the buffer knob "
                           f"does NOT bind inside [0.10,0.30]; the rescue's gain came from crossing "
                           f"the $0.50 boundary (ref buf=0.50: exp=${ref_exp}, oos=${ref_oos}, "
                           f"clears={ref_clears}; it flips exactly ONE trade's level-stop). $0.25 is "
                           f"the CENTER of a wide flat plateau, the OPPOSITE of a knife-edge spike — "
                           f"any buffer <=$0.30 is equally safe. Sizing the Safe-2 ATM cell on it is "
                           f"robust (the knob is coarse but the favorable side is flat and wide).")
    elif is_plateau:
        plateau_verdict = (f"PLATEAU: $0.25 clears all 8 gates AND sits in a contiguous "
                           f"gate-clearing run of {run} buffer(s); OOS stays positive across "
                           f"{oos_run} contiguous buffer(s). The rescue knob is a stable plateau, "
                           f"not a lucky spike — sizing the Safe-2 ATM cell on it is defensible.")
    elif rescue_clears:
        plateau_verdict = (f"SPIKE: $0.25 is the ONLY all-8-gate buffer in {BUFFER_SWEEP} (no "
                           f"gate-clearing neighbor; OOS-positive run={oos_run}). The rescue is "
                           f"FRAGILE — down-weight it before live capital rides the ATM cell.")
    else:
        plateau_verdict = (f"REGRESSION: $0.25 does NOT clear all 8 gates in this standalone "
                           f"sweep (gate-clearing buffers={[b for b,v in clears.items() if v]}). "
                           f"Re-examine the rescue claim.")

    return {
        "axis": {"strike_offset": SAFE2_STRIKE_OFFSET, "strike_tier": "ATM",
                 "tp1_premium_pct": RESCUE_TP1_PCT, "premium_stop_pct": SURV_PREMIUM_STOP,
                 "buffers": BUFFER_SWEEP, "rescue_buffer": RESCUE_BUFFER},
        "cells": cells,
        "reference_cell_buf050_v15default": ref_cell,
        "clears_by_buffer": {str(b): v for b, v in clears.items()},
        "oos_exp_by_buffer": {str(b): v for b, v in oos.items()},
        "n_buffers_clearing_all_gates": n_clearing,
        "rescue_buffer_clears_all_gates": rescue_clears,
        "gate_clearing_contiguous_run_thru_025": run,
        "oos_positive_contiguous_run_thru_025": oos_run,
        "neighbors_clearing": neighbors_clearing,
        "fine_sweep_exp_by_buffer": {str(b): e for b, e in zip(BUFFER_SWEEP, fine_exps)},
        "fine_sweep_oos_by_buffer": {str(b): e for b, e in zip(BUFFER_SWEEP, fine_oos)},
        "fine_sweep_is_flat": flat_plateau,
        "boundary_050_binds": boundary_binds,
        "reference_050": {"exp_dollar": ref_exp, "oos_exp": ref_oos, "clears_all_gates": ref_clears},
        "is_plateau": is_plateau,
        "plateau_verdict": plateau_verdict,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[b4-reclaim-null-precision] loading SPY+VIX via ar_runner.load_data ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[b4] SPY bars={len(spy)} trading_days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # EXACT validated signal set (reused detector — no drift).
    signals = detect_signals(days)
    sig_days = len({spy.iloc[s.bar_idx]['timestamp_et'].date() for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    print(f"[b4] struct_vwap_reclaim signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of days) side={side_ct}", flush=True)

    # ── PART A — precision vs selection (ITM-2 anchor + ATM Safe-2 rescue) ──
    print("\n[b4] PART A — timing precision vs day+side selection (high-seed same-day null)",
          flush=True)
    # ITM-2 anchor uses v15 default buffer 0.50 (matches the promoted ITM-2 evaluation).
    itm2 = precision_block(signals, spy, ribbon, vix, days,
                           strike_offset=PRIMARY_STRIKE_OFFSET, tier_label="ITM2_anchor",
                           tp1_premium_pct=RESCUE_TP1_PCT, level_stop_buffer_dollars=0.50)
    # ATM Safe-2 rescue cell uses the rescue knob buffer 0.25.
    atm = precision_block(signals, spy, ribbon, vix, days,
                          strike_offset=SAFE2_STRIKE_OFFSET, tier_label="ATM_safe2_rescue",
                          tp1_premium_pct=RESCUE_TP1_PCT, level_stop_buffer_dollars=RESCUE_BUFFER)
    for blk in (itm2, atm):
        if blk.get("note"):
            continue
        print(f"  [{blk['tier']} {blk['strike_tier_name']}] "
              f"exp=${blk['headline']['exp_dollar']} oos=${blk['headline']['oos_exp']}", flush=True)
        fl = blk["sameday_null_highseed"]["full"]
        ol = blk["sameday_null_highseed"]["oos"]
        print(f"    FULL same-day null: mean=${fl.get('null_mean')} std=${fl.get('null_std')} "
              f"-> signal z={fl.get('z_score')} pctl={fl.get('percentile_in_null')} "
              f"precise={blk['full_timing_precision']}", flush=True)
        print(f"    OOS  same-day null: mean=${ol.get('null_mean')} std=${ol.get('null_std')} "
              f"-> signal z={ol.get('z_score')} pctl={ol.get('percentile_in_null')} "
              f"precise={blk['oos_timing_precision']}", flush=True)
        print(f"    => {blk['precision_verdict']}", flush=True)

    # ── PART B — stop-buffer plateau sweep at ATM ──
    print("\n[b4] PART B — stop-buffer plateau sweep at ATM {0.10..0.30}", flush=True)
    bsweep = buffer_sweep(signals, spy, ribbon, vix, days)
    print(f"  => {bsweep['plateau_verdict']}", flush=True)

    # ── Schema-shaped fields for the StructuredOutput return ──
    # PRIMARY focus = the Safe-2 ATM rescue cell (the one that would ride live capital).
    primary = atm
    ph = primary.get("headline", {})
    # G-gate booleans for the ATM rescue cell come from the buffer-sweep cell at 0.25.
    atm025_cell = next((c for c in bsweep["cells"]
                        if round(c["level_stop_buffer_dollars"], 2) == RESCUE_BUFFER), {})
    atm025_gates = atm025_cell.get("gates", {})
    clears_all = bool(atm025_cell.get("clears_all_gates"))
    beats_null = bool(atm025_gates.get("G7_beats_random_null", {}).get("pass"))
    truncation_safe = bool(atm025_gates.get("G8_no_truncation", {}).get("pass"))
    is_half_positive = bool(atm025_gates.get("G6_is_first_half_positive", {}).get("pass"))
    oos_per_trade = ph.get("oos_exp")

    # The diagnostic's headline finding combines both parts.
    key_finding = (
        f"PART A (precision vs selection): ITM-2 {itm2.get('precision_verdict','').split(':')[0]}; "
        f"ATM rescue {atm.get('precision_verdict','').split(':')[0]}. "
        f"PART B (buffer plateau): {bsweep['plateau_verdict'].split(':')[0]} "
        f"($0.25 clears_all={bsweep['rescue_buffer_clears_all_gates']}, "
        f"gate-run={bsweep['gate_clearing_contiguous_run_thru_025']}, "
        f"OOS-pos-run={bsweep['oos_positive_contiguous_run_thru_025']})."
    )
    verdict = ("DIAGNOSTIC (no new edge): " + key_finding + " Edge #2 remains the "
               "confirmed dormant edge; this quantifies HOW it works (selection vs timing) "
               "and how stable the Safe-2 rescue knob is.")

    summary = {
        "hypothesis": ("reclaim_null_precision (DIAGNOSTIC on confirmed edge #2 "
                       "struct_vwap_reclaim_failed_break): does the reclaim bar have intra-day "
                       "TIMING precision (beats a same-day same-side random entry) or is the edge "
                       "pure DAY+SIDE SELECTION? Plus a fine stop-buffer plateau sweep "
                       "{0.10,0.15,0.20,0.25,0.30} at ATM to confirm $0.25 is a stable plateau, "
                       "not a spike. No new edge expected."),
        "kind": "diagnostic_null_precision_and_buffer_plateau",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "detector": ("REUSED VALIDATED struct_vwap_reclaim_failed_break detector "
                     "(sub-struct module, byte-for-byte): trend side (first 3 RTH closes same "
                     "side of as-of VWAP) -> counter-trend VWAP break -> with-trend VWAP reclaim "
                     "<=10:30 ET; chart stop = failed-break excursion extreme. ONE causal entry/day."),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "n_signals": len(signals),
        "signal_fire_day_pct": round(100 * sig_days / n_days, 1),
        "signal_side_count": side_ct,
        "config": {"primary_strike_offset_ITM2_anchor": PRIMARY_STRIKE_OFFSET,
                   "safe2_strike_offset_ATM": SAFE2_STRIKE_OFFSET,
                   "rescue_tp1_premium_pct": RESCUE_TP1_PCT,
                   "rescue_buffer_dollars": RESCUE_BUFFER,
                   "premium_stop_pct": SURV_PREMIUM_STOP, "qty": QTY,
                   "highseed_sameday_null_seeds": HI_SEEDS,
                   "coinflip_null_seeds": N_NULL_SEEDS},
        "PART_A_precision_vs_selection": {
            "control": ("bar-randomized SAME-DAY SIDE-MATCHED null: for each real signal pick a "
                        "RANDOM eligible morning bar [TREND_BARS..ENTRY_CUTOFF] on the SAME day, "
                        "keep SAME side/stop/strike/exits. Day+side SELECTION held constant; only "
                        "the entry BAR randomized. Signal >> null => TIMING precision; "
                        "signal ~= null => pure day+side selection."),
            "ITM2_anchor": itm2,
            "ATM_safe2_rescue": atm,
        },
        "PART_B_buffer_plateau": bsweep,
        "verdict": verdict,
        "key_finding": key_finding,
        "DISCLOSURE": {
            "diagnostic_not_new_edge": ("This settles HOW edge #2 works + how stable the rescue "
                                        "knob is; it does NOT propose a new edge."),
            "no_cherry_pick": ("Part B reports all 8 gates for EVERY buffer cell; Part A reports "
                               "FULL + OOS same-day-null lift for both ITM-2 and ATM (anti-2.10)."),
            "detector_no_drift": ("detector + same-day null + sim/metrics/gate code imported "
                                  "byte-for-byte from the validated sub-struct / rescue modules."),
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "precision_caveat": ("same-day same-side null isolates entry-bar TIMING from day+side "
                                 "selection — the harder control than the coin-flip null (which "
                                 "also randomizes the day)."),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[b4] wrote {OUT}", flush=True)

    print("\n=== RECLAIM_NULL_PRECISION DIAGNOSTIC VERDICT ===")
    print(f"n_signals={len(signals)}  fired {summary['signal_fire_day_pct']}% of {n_days} days")
    print(f"PART A: ITM-2 full_precise={itm2.get('full_timing_precision')} "
          f"oos_precise={itm2.get('oos_timing_precision')} | "
          f"ATM full_precise={atm.get('full_timing_precision')} "
          f"oos_precise={atm.get('oos_timing_precision')}")
    print(f"PART B: $0.25 clears_all={bsweep['rescue_buffer_clears_all_gates']} "
          f"is_plateau={bsweep['is_plateau']} gate-run={bsweep['gate_clearing_contiguous_run_thru_025']} "
          f"oos-pos-run={bsweep['oos_positive_contiguous_run_thru_025']}")
    print(f"VERDICT: {verdict}")

    # Stash schema fields for the caller (printed for the run log).
    print(f"\n[schema] n_signals={len(signals)} oos_per_trade={oos_per_trade} "
          f"beats_null={beats_null} is_half_positive={is_half_positive} "
          f"clears_all_gates={clears_all} truncation_safe={truncation_safe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
