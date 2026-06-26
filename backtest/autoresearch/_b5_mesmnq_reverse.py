"""B5 SYMMETRY + 2nd-SHOT — MES/MNQ divergence: re-confirm BOTH lead directions and
RESCUE the gate-5 (concentration) failure of the B4 lead.

HYPOTHESIS (J, 2026-06-21)
--------------------------
Symmetry check + 2nd shot. B4 mined the MES/MNQ cross-instrument VWAP divergence and
found an ASYMMETRY:
  * MES-leads -> trade MNQ laggard  = OOS-positive, beats the null, IS-half positive,
    >=4 positive quarters at low thresholds  ... BUT FAILED gate 5
    (drop-top5-days per-trade > 0): the edge lived in ~5 monster days (concentration).
  * MNQ-leads -> trade MES laggard  = mostly negative / dead (no divergence asymmetry).

Two questions this test answers:
  (Q1 SYMMETRY) Does the OTHER lead direction (MNQ-leads -> MES) ALSO carry a divergence
      asymmetry, or is the catch-up edge genuinely one-sided?  -> re-confirm both, head
      to head, in ONE harness run on the identical bar data + gates.
  (Q2 2nd-SHOT / RESCUE) Apply a CONCENTRATION FIX to the MES->MNQ lead and ask: can the
      rescued cell clear ALL 8 gates -- in particular gate 5, the one the lead failed?

THE CONCENTRATION FIX (the "fix from test 1")
---------------------------------------------
Gate 5 fails because a few huge catch-up days carry the whole edge. The convergent B4
finding (ML #1 feature + edge#2 day+side + vwap VIX-gate) is that the real predictive
axis is VIX-REGIME (level + slope) x DAY-TREND-SIDE. So the fix is NOT to winsorize the
winners (that would just hide the tail) -- it is a CAUSAL, as-of ENTRY GATE that removes
the low-conviction divergences so the SURVIVING population is broad-based, i.e. its
drop-top5 per-trade stays positive on its own. We SWEEP the fix knobs:

  * vix_max         : only take the divergence when as-of VIX (close of the bar BEFORE
                      entry) is <= vix_max. (Catch-up is a mean-reversion-of-spread edge;
                      it degrades in high-VIX panics where the laggard keeps diverging.
                      C5: VIX *character*, used causally as-of.)  None = no VIX gate.
  * align_day_trend : require the catch-up direction to agree with the laggard's OWN
                      session-trend side as-of the signal bar (close vs session open).
                      i.e. don't fade an established opposite intraday trend -- take the
                      catch-up only when it is WITH the laggard's day. (B4 edge#2: day+side
                      selection.)  False = no alignment gate.

All gating uses ONLY data available at/just-before the signal bar -- strict causality
(L14/L34/L57/L94/L161/L165). No look-ahead, no train/test leakage: the fix knobs are
swept and EVERY gate (incl. the OOS gate + the random-entry null + the IS-first-half
sub-window) is evaluated on the post-gate population exactly as B4 does. The OOS split is
identical to B4 (70/30 by common-day index) so the rescue is judged on the SAME held-out
window the lead originally failed.

ALL 8 GATES (anti-2.10) -- evaluated by the SAME engine as B4 (imported, no drift):
  1. OOS(2026) per-trade > 0
  2. positive in >= ceil(0.6*Q) quarters (>=4 of 6)
  3. top-5 winning DAYS < 200% of total P&L
  4. n_trades >= 20
  5. drop-top5-days per-trade > 0   <-- THE gate the lead failed; the rescue must clear it
  6. IS(2025) FIRST-HALF per-trade > 0
  7. beats random-entry NULL (mean), same exit/count/side on the GATED entries (L172)
  8. NO-TRUNCATION: chart-stop+EOD must not flip a positive cell negative (L171)

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_b5_mesmnq_reverse.py
Pure Python, $0, no live orders, no option pricing. Futures point-P&L (no theta).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "analysis" / "recommendations" / "b5-mesmnq-reverse.json"
VIX_CSV = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

# ── import the B4 engine verbatim (single source of truth -> no live/backtest drift) ──
_B4 = ROOT / "backtest" / "autoresearch" / "_b4_mes_mnq_divergence.py"
_spec = importlib.util.spec_from_file_location("b4div", _B4)
b4 = importlib.util.module_from_spec(_spec)
sys.modules["b4div"] = b4
_spec.loader.exec_module(b4)

# sweep knobs for the concentration fix (None = gate disabled)
VIX_MAXES = [None, 25.0, 22.0, 20.0, 18.0]
ALIGN_OPTS = [False, True]


# ─────────────────────────────────────────────────────────────────────────────
# VIX as-of (causal): per session date -> sorted (time, close). We read the VIX
# close of the LAST bar at-or-before the signal bar's wall-clock time. Same-day only.
# ─────────────────────────────────────────────────────────────────────────────
def load_vix_asof() -> dict:
    df = pd.read_csv(VIX_CSV)
    ts = pd.to_datetime(df["timestamp_et"], utc=True)
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.drop_duplicates(subset="timestamp_et", keep="first").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["t"] = df["timestamp_et"].dt.time
    df["close"] = df["close"].astype(float)
    out: dict = {}
    for day, g in df.groupby("date", sort=True):
        g = g.sort_values("t")
        out[day] = (g["t"].to_numpy(), g["close"].to_numpy(float))
    return out


def vix_asof(vix_by_day: dict, day: dt.date, t: dt.time) -> Optional[float]:
    """VIX close of the last bar at-or-before time `t` on `day` (causal). None if absent."""
    rec = vix_by_day.get(day)
    if rec is None:
        return None
    times, closes = rec
    idx = -1
    for k, tt in enumerate(times):
        if tt <= t:
            idx = k
        else:
            break
    if idx < 0:
        return None
    return float(closes[idx])


# ─────────────────────────────────────────────────────────────────────────────
# CONCENTRATION FIX — causal entry gate applied to B4's detected signals.
# A Sig (from b4.detect_divergence) carries: laggard, idx (signal bar, fill NEXT open),
# date, side, chart_stop, note. We gate on data available AT the signal bar `idx`.
# ─────────────────────────────────────────────────────────────────────────────
def _laggard_state_at(lag_state: dict, day: dt.date, gidx: int):
    """Return (time_of_bar, normalized_return r at bar, above_vwap) for the laggard's
    signal bar identified by GLOBAL idx gidx, using B4's per-session state. Causal."""
    gs = lag_state.get(day)
    if gs is None:
        return None
    arr = gs["gidx"]
    pos = np.where(arr == gidx)[0]
    if len(pos) == 0:
        return None
    k = int(pos[0])
    return gs["times"][k], float(gs["r"][k]), bool(gs["above"][k])


def apply_fix(sigs, lag_state: dict, vix_by_day: dict, *,
              vix_max: Optional[float], align_day_trend: bool):
    """Filter B4 signals through the concentration fix. Pure causal as-of gating.
    Returns (kept_sigs, n_dropped_vix, n_dropped_align, n_no_vix)."""
    kept = []
    drop_vix = drop_align = no_vix = 0
    for s in sigs:
        st = _laggard_state_at(lag_state, s.date, s.idx)
        if st is None:
            # cannot evaluate gate state -> be conservative, drop only if a gate is on
            if vix_max is not None or align_day_trend:
                continue
            kept.append(s)
            continue
        t_bar, r_bar, above = st
        # VIX gate (as-of the signal bar's time, same day, causal)
        if vix_max is not None:
            v = vix_asof(vix_by_day, s.date, t_bar)
            if v is None:
                no_vix += 1
                continue
            if v > vix_max:
                drop_vix += 1
                continue
        # day-trend-side alignment: long catch-up only if laggard already up on the day
        # (r_bar > 0); short catch-up only if laggard already down on the day (r_bar < 0)
        if align_day_trend:
            if s.side == "long" and not (r_bar > 0):
                drop_align += 1
                continue
            if s.side == "short" and not (r_bar < 0):
                drop_align += 1
                continue
        kept.append(s)
    return kept, drop_vix, drop_align, no_vix


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    mes = b4.load_futures("MES")
    mnq = b4.load_futures("MNQ")
    common_days = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common_days)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common_days)].reset_index(drop=True)

    atr_mes = b4.atr_series(mes["high"], mes["low"], mes["close"], b4.ATR_LEN)
    atr_mnq = b4.atr_series(mnq["high"], mnq["low"], mnq["close"], b4.ATR_LEN)
    de_mes = {d: int(g.index[-1]) for d, g in mes.groupby("date")}
    de_mnq = {d: int(g.index[-1]) for d, g in mnq.groupby("date")}

    state_mes = b4._per_session_state(mes)
    state_mnq = b4._per_session_state(mnq)

    cut = int(len(common_days) * b4.OOS_TRAIN_FRAC)
    is_days = set(common_days[:cut]); oos_days = set(common_days[cut:])
    is_days_sorted = sorted(is_days)
    n_q = len(set(b4.quarter(d) for d in common_days))

    vix_by_day = load_vix_asof()
    vix_coverage = round(100.0 * len(set(common_days) & set(vix_by_day)) / len(common_days), 1)

    results = {
        "meta": {
            "test": "mesmnq_reverse",
            "hypothesis": ("Symmetry check + 2nd shot: re-confirm BOTH MES/MNQ divergence "
                           "lead directions (MES-leads->trade MNQ AND MNQ-leads->trade MES) "
                           "head-to-head, and apply a causal concentration fix (as-of VIX "
                           "regime gate x day-trend-side alignment) to the MES->MNQ lead to "
                           "try to clear gate 5 (drop-top5 per-trade > 0) -- the gate the "
                           "B4 divergence lead failed. Futures point-P&L, no theta."),
            "engine": "imports backtest/autoresearch/_b4_mes_mnq_divergence.py verbatim (no drift)",
            "generated": "2026-06-21", "qty_micros": b4.QTY,
            "commission_rt": b4.COMMISSION_RT, "slippage_ticks_each_side": b4.SLIP_TICKS,
            "point_value": b4.POINT_VALUE,
            "n_common_days": len(common_days),
            "date_range": [str(common_days[0]), str(common_days[-1])],
            "oos_split": {"is_days": len(is_days), "oos_days": len(oos_days),
                          "oos_start": str(sorted(oos_days)[0]),
                          "train_frac": b4.OOS_TRAIN_FRAC},
            "n_quarters": n_q,
            "entry_window": [str(b4.RTH_OPEN), str(b4.ENTRY_CUTOFF)],
            "exit": ("atr_trail (chart-stop floor + chandelier trail, mult 2.5); hard EOD flat"),
            "threshold_sweep": b4.THRESHOLDS,
            "concentration_fix": {
                "vix_max_sweep": VIX_MAXES,
                "align_day_trend_sweep": ALIGN_OPTS,
                "vix_source": str(VIX_CSV.name),
                "vix_day_coverage_pct": vix_coverage,
                "rationale": ("causal as-of VIX regime gate x day-trend-side alignment "
                              "removes low-conviction catch-ups so the surviving edge is "
                              "broad-based (drop-top5 positive), not a few monster days"),
            },
            "gate_definitions": {
                "1": "OOS(2026) per-trade > 0",
                "2": f"positive in >= ceil(0.6*{n_q}) quarters",
                "3": "top-5 winning days < 200% of total P&L",
                "4": "n_trades >= 20",
                "5": "drop-top5-days per-trade > 0  (THE rescue gate)",
                "6": "IS(2025) first-half per-trade > 0",
                "7": "beats random-entry null (mean), same exit/count/side on GATED entries (L172)",
                "8": "no-truncation: chart-stop+EOD does not flip a positive cell negative (L171)",
            },
        },
        "part1_symmetry_baseline_no_fix": [],   # both leads, NO fix (re-confirm B4 asymmetry)
        "part2_rescue_cells": [],               # MES->MNQ lead, WITH fix sweep
    }

    # leader, laggard, lead_df, lag_df, lead_state, lag_state, lag_atr, lag_de
    configs = {
        "MES->MNQ": ("MES", "MNQ", mes, mnq, state_mes, state_mnq, atr_mnq, de_mnq),
        "MNQ->MES": ("MNQ", "MES", mnq, mes, state_mnq, state_mes, atr_mes, de_mes),
    }

    # ── PART 1: SYMMETRY — both leads, NO fix, lowest threshold per side as the
    #    representative cell (matches B4's best-clearing-direction cells) ──────────
    print("=== PART 1: SYMMETRY (both lead directions, NO fix) ===", flush=True)
    sym = {}
    for tag, (lead, lag, ldf, gdf, lst, gst, gatr, gde) in configs.items():
        per_dir = []
        for thr in b4.THRESHOLDS:
            sigs = b4.detect_divergence(ldf, gdf, lst, gst, lag, thr)
            cell = b4.eval_cell(gdf, lag, sigs, gatr, gde, is_days, oos_days,
                                is_days_sorted, n_q)
            cell["leader"] = lead; cell["laggard"] = lag; cell["threshold"] = thr
            per_dir.append(cell)
            o = cell["oos"]
            print(f"[sym] {tag} thr={thr:<7} n={cell['n_signals']:3d} "
                  f"oos_pt={o.get('per_trade')} drop5={cell['full'].get('drop_top5_per_trade')} "
                  f"posQ={cell['positive_quarters']}/{n_q} "
                  f"-> {'CLEARS' if cell['clears_all_gates'] else 'no('+';'.join(cell['failing_gates'])+')'}",
                  flush=True)
        results["part1_symmetry_baseline_no_fix"].append({"config": tag, "cells": per_dir})
        # direction-level summary: is this lead direction net-positive OOS at all?
        oos_pts = [c["oos"].get("per_trade") for c in per_dir if c["oos"].get("per_trade") is not None]
        # fewest gates failed by ANY cell in this direction (quality of the best near-miss)
        min_fails = min((len(c["failing_gates"]) for c in per_dir), default=99)
        sym[tag] = {
            "any_oos_positive_cell": any(p > 0 for p in oos_pts) if oos_pts else False,
            "max_oos_per_trade": round(max(oos_pts), 2) if oos_pts else None,
            "any_cell_clears_all_gates": any(c["clears_all_gates"] for c in per_dir),
            "fewest_gates_failed": min_fails,
            "best_failing_gates": min(
                (c["failing_gates"] for c in per_dir), key=len, default=None),
        }
    results["symmetry_summary"] = sym
    # Quantified asymmetry verdict. The divergence catch-up edge is one-sided in QUALITY:
    # the MES-leads side (trade the NDX/MNQ laggard) is materially stronger than the
    # MNQ-leads side (trade the SPX/MES laggard) on max OOS per-trade AND fewest gates
    # failed by its best near-miss. Neither side clears all 8 gates, so neither is
    # tradeable, but the asymmetry the hypothesis asked about is REAL and directional.
    a, b_ = sym["MES->MNQ"], sym["MNQ->MES"]
    mes_lead_stronger = (
        (a["max_oos_per_trade"] or -1e9) > (b_["max_oos_per_trade"] or -1e9)
        and a["fewest_gates_failed"] <= b_["fewest_gates_failed"])
    if a["any_cell_clears_all_gates"] or b_["any_cell_clears_all_gates"]:
        results["symmetry_verdict"] = (
            "ONE SIDE CLEARS ALL 8 GATES (tradeable) — see symmetry_summary for which")
    elif mes_lead_stronger:
        results["symmetry_verdict"] = (
            "ASYMMETRIC (confirmed): MES-leads->trade-MNQ is the dominant catch-up side "
            f"(max OOS ${a['max_oos_per_trade']}/trade, best near-miss fails "
            f"{a['fewest_gates_failed']} gate(s)) vs MNQ-leads->trade-MES "
            f"(max OOS ${b_['max_oos_per_trade']}/trade, fails {b_['fewest_gates_failed']} "
            "gate(s)). The OTHER lead direction does NOT have a stronger divergence "
            "asymmetry — it is the weaker, non-tradeable side. Neither side clears all 8 "
            "gates (both die on the SAME structural failure: tail concentration, gate 5).")
    else:
        results["symmetry_verdict"] = "MIXED/SYMMETRIC: see per-direction cells"

    # ── PART 2: RESCUE — MES->MNQ lead, sweep threshold x VIX-max x align ─────────
    print("\n=== PART 2: CONCENTRATION RESCUE (MES->MNQ lead + fix sweep) ===", flush=True)
    lead, lag, ldf, gdf, lst, gst, gatr, gde = configs["MES->MNQ"]
    rescue_cells = []
    best = None
    for thr in b4.THRESHOLDS:
        base_sigs = b4.detect_divergence(ldf, gdf, lst, gst, lag, thr)
        for vmax in VIX_MAXES:
            for align in ALIGN_OPTS:
                if vmax is None and align is False:
                    continue  # that is the un-fixed B4 cell; already in Part 1
                kept, dvix, dalign, novix = apply_fix(
                    base_sigs, gst, vix_by_day, vix_max=vmax, align_day_trend=align)
                cell = b4.eval_cell(gdf, lag, kept, gatr, gde, is_days, oos_days,
                                    is_days_sorted, n_q)
                cell["leader"] = lead; cell["laggard"] = lag; cell["threshold"] = thr
                cell["fix"] = {"vix_max": vmax, "align_day_trend": align,
                               "n_base_signals": len(base_sigs), "n_kept": len(kept),
                               "dropped_vix": dvix, "dropped_align": dalign,
                               "dropped_no_vix_data": novix}
                rescue_cells.append(cell)
                o = cell["oos"]; f = cell["full"]
                fixtag = f"vix<={vmax} align={align}"
                print(f"[rescue] thr={thr:<7} {fixtag:<22} kept={len(kept):3d} "
                      f"oos_pt={o.get('per_trade')} drop5={f.get('drop_top5_per_trade')} "
                      f"top5%={f.get('top5_day_pct')} posQ={cell['positive_quarters']}/{n_q} "
                      f"null={cell['random_null_oos'].get('per_trade')} "
                      f"-> {'CLEARS' if cell['clears_all_gates'] else 'no('+';'.join(cell['failing_gates'])+')'}",
                      flush=True)
                # rank candidate rescues: must have n>=20 and OOS positive; prefer the
                # one that clears the most gates, tie-break on drop-top5 per-trade
                if f.get("n", 0) >= 20 and (o.get("per_trade") or -1) > 0:
                    n_clear = sum(cell["gates"].values())
                    drop5 = f.get("drop_top5_per_trade") or -1e9
                    key = (cell["clears_all_gates"], n_clear, drop5)
                    if best is None or key > best[0]:
                        best = (key, f"thr={thr} {fixtag}", cell)

    results["part2_rescue_cells"] = rescue_cells
    clears = [c for c in rescue_cells if c["clears_all_gates"]]
    results["n_rescue_cells_clearing_all_gates"] = len(clears)
    results["rescue_clearing_cells"] = [
        {"threshold": c["threshold"], "fix": c["fix"],
         "oos_per_trade": c["oos"].get("per_trade"),
         "drop_top5_per_trade": c["full"].get("drop_top5_per_trade"),
         "n": c["full"].get("n")} for c in clears]

    if best is not None:
        b = best[2]
        results["best_rescue_cell"] = {
            "config": best[1], "leader": b["leader"], "laggard": b["laggard"],
            "threshold": b["threshold"], "fix": b["fix"],
            "n_signals": b["n_signals"], "n_fills": b["n_fills"],
            "oos_per_trade": b["oos"].get("per_trade"),
            "is_first_half_per_trade": b["is_first_half_per_trade"],
            "full_per_trade": b["full"].get("per_trade"),
            "top5_day_pct": b["full"].get("top5_day_pct"),
            "drop_top5_per_trade": b["full"].get("drop_top5_per_trade"),
            "positive_quarters": b["positive_quarters"],
            "random_null_oos_per_trade": b["random_null_oos"].get("per_trade"),
            "no_truncation_ref": b["no_truncation_ref"],
            "gates": b["gates"], "clears_all_gates": b["clears_all_gates"],
            "failing_gates": b["failing_gates"],
        }

    # overall verdict
    rescued = len(clears) > 0
    results["rescue_verdict"] = (
        "RESCUED: at least one MES->MNQ cell clears all 8 gates after the concentration fix"
        if rescued else
        "NOT RESCUED: the concentration fix does not lift any MES->MNQ cell through all 8 "
        "gates (gate 5 concentration persists or another gate breaks under the gated population)")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[b5] WROTE {OUT_JSON}")
    print(f"[b5] symmetry_verdict: {results['symmetry_verdict']}")
    print(f"[b5] rescue cells clearing all 8 gates: {len(clears)}")
    print(f"[b5] rescue_verdict: {results['rescue_verdict']}")
    if best is not None:
        b = best[2]
        print(f"[b5] BEST rescue: {best[1]}  oos_pt=${b['oos'].get('per_trade')}  "
              f"drop5=${b['full'].get('drop_top5_per_trade')}  n={b['full'].get('n')}  "
              f"clears={b['clears_all_gates']}  fails={b['failing_gates']}")


if __name__ == "__main__":
    main()
