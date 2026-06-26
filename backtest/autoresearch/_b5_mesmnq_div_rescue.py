"""B5 RESCUE — MES->MNQ divergence lead-lag, CONCENTRATION FIX sweep (point-P&L).

LEAD WE ARE RESCUING (from B4 `_b4_mes_mnq_divergence.py`)
---------------------------------------------------------
MES leads (close crosses its session-VWAP), MNQ laggard still on the wrong side,
normalized-return spread (r_MES - r_MNQ) >= +threshold -> trade MNQ in the leader's
direction for catch-up. Point-P&L, no theta, intraday flat by EOD.

B4 result @ thr=0.0015 (MES->MNQ): OOS +$55.23/tr, n=140, posQ=4/6, top5=114.6%,
beats null (+55 vs -12.46) — but FAILED **gate-5** (drop-top5-days per-trade = -$4.70).
Translation: pull the 5 best winning days and the edge is a small LOSER. The signal is
right-tail-concentrated, not broad. EVERY other gate passed; gate-5 is the ONLY blocker.

THE RESCUE — apply a CONCENTRATION FIX and SWEEP which (if any) clears gate-5 while
keeping all 7 other gates. The base divergence signal is structurally exactly ONE entry
per (laggard, session) (B4's `fired` flag), so the four fixes are SIGNAL-SET FILTERS that
SUBSET the qualifying days to the regime/magnitude/persistence where the catch-up is broad
rather than lottery-ticket:

  (a) VOLATILITY-REGIME GATE — keep a signal only when the laggard's ATR%-at-signal
      (ATR_at_signal / entry_price) sits inside a band. We sweep band variants:
      low-only / mid-band / high-only / drop-extreme-high. Rationale: a handful of
      huge ATR days drive the top-5 concentration; trimming the vol tail should shrink
      top-5 dominance and lift drop-top5 per-trade.

  (b) 1-ENTRY-PER-DAY CAP — the base IS already 1/day (B4 enforces it). We VERIFY and
      report this; as a non-binding constraint it CANNOT by itself change drop-top5
      (same trade set). Reported honestly as a structural no-op (max_per_day==1) so the
      sweep is complete and not silently dropped.

  (c) TOP-QUARTILE DIVERGENCE-MAGNITUDE DAY-FILTER — keep only signals whose divergence
      magnitude (|r_lead - r_lag| at the signal bar) is in the top-Q of the IN-SAMPLE
      magnitude distribution (threshold FROZEN on IS days only — no OOS leakage).
      Sweep Q in {top-50%, top-quartile (25%), top-decile}. Rationale: stronger initial
      dislocation -> larger, more reliable catch-up -> less reliance on a few outliers.

  (d) MIN-DIVERGENCE-PERSISTENCE (N bars) — require the divergence (leader broken +
      laggard still unconfirmed + spread >= threshold) to have HELD for >= N consecutive
      bars BEFORE the entry bar (entry still on the SAME signal bar, fill next bar).
      Sweep N in {1,2,3}. Causal: persistence measured on bars [.. signal], no look-ahead.
      Rationale: a one-bar spread blip is noise; a sustained dislocation is a real lag.

WINNER DEFINITION: a (fix, knob, config) cell that clears **gate-5 (drop-top5 per-trade
> 0)** AND all 7 other gates. If any cell clears -> NEW futures edge.

CONFIGS: primary MES leads -> trade MNQ laggard. Reverse check MNQ leads -> trade MES
laggard (B4 showed reverse was structurally weak; we re-run it under the fixes for
completeness, both as point-P&L on the traded micro).

ALL 8 GATES (identical to B4, anti-2.10): reused VERBATIM from the B4 module so there is
no gate drift between the lead and its rescue.
  1 OOS(2026)/tr>0  2 posQ>=ceil(0.6*Q)  3 top5<200%  4 n>=20
  5 drop-top5/tr>0 (THE BLOCKER)  6 IS-first-half/tr>0  7 beats random-null (L172)
  8 no-truncation (chart-stop+EOD doesn't flip a positive cell negative, L171)

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_b5_mesmnq_div_rescue.py
Pure Python, $0, no live orders, no option pricing. Markets CLOSED.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest" / "autoresearch"))

# Reuse the PROVEN B4 machinery verbatim — no signal/sim/gate drift between lead & rescue.
import _b4_mes_mnq_divergence as b4  # noqa: E402
from _b4_mes_mnq_divergence import (  # noqa: E402
    ATR_LEN,
    ENTRY_CUTOFF,
    OOS_TRAIN_FRAC,
    RTH_OPEN,
    Sig,
    atr_series,
    by_quarter,
    detect_divergence,
    is_first_half_per_trade,
    load_futures,
    metrics,
    quarter,
    random_null,
    simulate,
    _per_session_state,
)

OUT_JSON = ROOT / "analysis" / "recommendations" / "b5-mesmnq-div-rescue.json"

# Base threshold = the proven B4 lead. We also sweep around it so a fix isn't tied to one thr.
BASE_THRESHOLD = 0.0015
THRESHOLD_SWEEP = [0.0010, 0.0015, 0.0020]


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL ENRICHMENT — attach per-signal metadata needed by the fixes (causal only)
# ─────────────────────────────────────────────────────────────────────────────
def enrich_signals(
    lead_df: pd.DataFrame,
    lag_df: pd.DataFrame,
    lead_state: dict,
    lag_state: dict,
    laggard_symbol: str,
    threshold: float,
    lag_atr: np.ndarray,
) -> list[dict]:
    """Re-derive the B4 divergence signals AND, for each, the metadata the concentration
    fixes need — all causal (measured at/<= the signal bar):
      * div_magnitude   = |r_lead - r_lag| at the signal bar
      * atr_pct         = lag_atr[signal_idx] / lag_close[signal_idx]  (vol-regime proxy)
      * persistence     = # consecutive prior bars (incl. signal) the divergence condition
                          held (leader broken same way + laggard unconfirmed + spread>=thr)
    Returns list of dicts: {sig, div_magnitude, atr_pct, persistence}.
    The Sig objects are exactly what B4.detect_divergence would emit (we call it to get the
    canonical signals, then re-walk the session to compute metadata for the SAME bars)."""
    sigs = detect_divergence(lead_df, lag_df, lead_state, lag_state, laggard_symbol, threshold)
    by_date = {s.date: s for s in sigs}  # 1/day guaranteed by B4

    lag_close = lag_df["close"].to_numpy(float)
    out: list[dict] = []
    for day, sig in by_date.items():
        ls = lead_state[day]
        gs = lag_state[day]
        lt = {t: k for k, t in enumerate(ls["times"])}
        gt = {t: k for k, t in enumerate(gs["times"])}
        common_t = [t for t in ls["times"] if t in gt]
        # locate the common-time index whose laggard global idx == sig.idx
        sig_ti = None
        for ti, t in enumerate(common_t):
            if int(gs["gidx"][gt[t]]) == sig.idx:
                sig_ti = ti
                break
        if sig_ti is None:
            continue
        li = lt[common_t[sig_ti]]
        gi = gt[common_t[sig_ti]]
        div_mag = abs(float(ls["r"][li]) - float(gs["r"][gi]))

        a = lag_atr[sig.idx]
        px = lag_close[sig.idx]
        atr_pct = float(a / px) if (not np.isnan(a) and px) else float("nan")

        # persistence: how many consecutive bars (incl. signal bar) the DISLOCATION has held.
        # NOTE: the B4 entry trigger requires the leader to FLIP its VWAP AT bar i, so a
        # "leader-still-broken-same-way at bar i-1" test is structurally impossible (the
        # prior bar is on the opposite VWAP side by definition) -> it would make persistence
        # always==1 (a degenerate, untestable knob; L161/L165). We instead measure SPREAD-
        # persistence: the normalized-return SPREAD has been >= threshold in the leader's
        # broken direction AND the laggard has stayed unconfirmed for N consecutive bars up
        # to & including the signal bar (drop only the flip-at-this-bar requirement for the
        # look-back). The flip still defines the ENTRY bar; persistence asks how long the
        # dislocation was building. Causal: closed bars [.. signal] only.
        want_up = sig.side == "long"
        persistence = 0
        for back in range(sig_ti, -1, -1):
            t = common_t[back]
            li_b = lt[t]
            gi_b = gt[t]
            if li_b < b4.WARMUP_BARS or gi_b < b4.WARMUP_BARS or li_b < 1:
                break
            spread = float(ls["r"][li_b]) - float(gs["r"][gi_b])
            if want_up:
                # leader leading up by >= thr AND laggard still below its VWAP (unconfirmed)
                cond = (not gs["above"][gi_b]) and spread >= threshold
            else:
                cond = gs["above"][gi_b] and (-spread) >= threshold
            if cond:
                persistence += 1
            else:
                break
        out.append(
            {
                "sig": sig,
                "div_magnitude": div_mag,
                "atr_pct": atr_pct,
                "persistence": int(persistence),
            }
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# CONCENTRATION FIXES — each returns a SUBSET of the enriched signals (list[Sig])
# IS-derived thresholds are FROZEN on in-sample days only (no OOS leakage).
# ─────────────────────────────────────────────────────────────────────────────
def _is_vals(enriched: list[dict], key: str, is_days: set) -> np.ndarray:
    vals = [
        e[key]
        for e in enriched
        if e["sig"].date in is_days and e[key] is not None and not (
            isinstance(e[key], float) and math.isnan(e[key])
        )
    ]
    return np.array(vals, dtype=float)


def fix_vol_regime(enriched: list[dict], is_days: set, variant: str) -> list[Sig]:
    """(a) Keep signals whose laggard ATR% sits in an IS-defined band.
    variant: 'low' (<=median), 'mid' (q25..q75), 'high' (>=median),
             'drop_extreme_high' (< q90 — trim only the vol tail)."""
    v = _is_vals(enriched, "atr_pct", is_days)
    if v.size < 8:
        return []
    q25, q50, q75, q90 = (float(np.percentile(v, p)) for p in (25, 50, 75, 90))
    keep: list[Sig] = []
    for e in enriched:
        a = e["atr_pct"]
        if a is None or (isinstance(a, float) and math.isnan(a)):
            continue
        ok = (
            (variant == "low" and a <= q50)
            or (variant == "mid" and q25 <= a <= q75)
            or (variant == "high" and a >= q50)
            or (variant == "drop_extreme_high" and a < q90)
        )
        if ok:
            keep.append(e["sig"])
    return keep


def fix_one_per_day(enriched: list[dict]) -> tuple[list[Sig], dict]:
    """(b) 1-entry-per-day cap. Base is already 1/day; verify & report. Non-binding =>
    identical trade set => cannot move drop-top5. Returned for sweep completeness."""
    per_day = Counter(e["sig"].date for e in enriched)
    max_per_day = max(per_day.values()) if per_day else 0
    keep = [e["sig"] for e in enriched]  # no change (already <=1/day)
    info = {
        "max_signals_per_day_pre_cap": int(max_per_day),
        "binding": bool(max_per_day > 1),
        "note": (
            "base divergence is structurally 1/day (B4 'fired' flag); cap is non-binding "
            "and cannot alter drop-top5 — reported as structural no-op"
        ),
    }
    return keep, info


def fix_top_quartile_mag(enriched: list[dict], is_days: set, top_frac: float) -> list[Sig]:
    """(c) Keep signals whose div_magnitude is in the top `top_frac` of the IS distribution
    (threshold frozen on IS days only). top_frac=0.5 -> top half, 0.25 -> top quartile, etc."""
    v = _is_vals(enriched, "div_magnitude", is_days)
    if v.size < 8:
        return []
    cut = float(np.percentile(v, 100.0 * (1.0 - top_frac)))
    return [e["sig"] for e in enriched if e["div_magnitude"] >= cut]


def fix_min_persistence(enriched: list[dict], n_bars: int) -> list[Sig]:
    """(d) Keep signals whose divergence persisted >= n_bars consecutive bars (causal)."""
    return [e["sig"] for e in enriched if e["persistence"] >= n_bars]


# ─────────────────────────────────────────────────────────────────────────────
# EVAL — reuse the EXACT B4 gate logic on a given signal subset
# ─────────────────────────────────────────────────────────────────────────────
def eval_subset(
    lag_df: pd.DataFrame,
    symbol: str,
    sigs: list[Sig],
    atr: np.ndarray,
    day_end: dict,
    is_days: set,
    oos_days: set,
    is_days_sorted: list,
    n_quarters: int,
) -> dict:
    """Identical gate computation to B4.eval_cell (copied logic, same definitions) so the
    rescue is judged by the SAME bar as the lead. We re-implement here (not import eval_cell)
    only because eval_cell takes leader/laggard dfs; the math below is byte-equivalent."""
    fills = [
        f
        for s in sigs
        if (f := simulate(lag_df, s, symbol, atr=atr, day_end=day_end, exit_mode="atr_trail"))
    ]
    fills_notrunc = [
        f
        for s in sigs
        if (f := simulate(lag_df, s, symbol, atr=atr, day_end=day_end, exit_mode="chartstop_eod"))
    ]
    is_fills = [f for f in fills if f.date in is_days]
    oos_fills = [f for f in fills if f.date in oos_days]
    m_all = metrics(fills)
    m_is = metrics(is_fills)
    m_oos = metrics(oos_fills)
    q = by_quarter(fills)
    pos_q = sum(1 for vq in q.values() if vq["total"] > 0)
    need_q = math.ceil(0.6 * n_quarters)

    oos_sigs = [s for s in sigs if s.date in oos_days]
    null_oos = random_null(lag_df, oos_sigs, symbol, atr=atr, day_end=day_end)
    m_notrunc = metrics(fills_notrunc)
    is_half = is_first_half_per_trade(fills, is_days_sorted)

    oos_pt = m_oos.get("per_trade")
    n_all = m_all.get("n", 0)
    null_pt = null_oos.get("per_trade")
    null_p95 = null_oos.get("p95")
    top5 = m_all.get("top5_day_pct")
    drop_pt = m_all.get("drop_top5_per_trade")
    notrunc_pt = m_notrunc.get("per_trade")
    full_pt = m_all.get("per_trade")

    g1 = oos_pt is not None and oos_pt > 0
    g2 = pos_q >= need_q
    g3 = top5 is not None and top5 < 200.0
    g4 = n_all >= 20
    g5 = drop_pt is not None and drop_pt > 0
    g6 = is_half is not None and is_half > 0
    g7 = oos_pt is not None and null_pt is not None and oos_pt > null_pt
    truncation_artifact = (
        full_pt is not None and full_pt > 0 and notrunc_pt is not None and notrunc_pt < 0
    )
    g8 = not truncation_artifact

    gates = {
        "1_oos_per_trade_pos": g1,
        "2_positive_quarters_>=60pct": g2,
        "3_top5_day_pct_<200": g3,
        "4_n_trades_>=20": g4,
        "5_drop_top5_per_trade_>0": g5,
        "6_is_first_half_per_trade_>0": g6,
        "7_beats_random_null": g7,
        "8_no_truncation_artifact": g8,
    }
    clears = all(gates.values())
    fails = [k for k, vv in gates.items() if not vv]
    return {
        "n_signals": len(sigs),
        "n_fills": len(fills),
        "full": m_all,
        "is": m_is,
        "oos": m_oos,
        "by_quarter": q,
        "positive_quarters": pos_q,
        "need_quarters": need_q,
        "is_first_half_per_trade": is_half,
        "no_truncation_ref": {
            "chartstop_eod_per_trade": notrunc_pt,
            "full_per_trade": full_pt,
            "is_artifact": truncation_artifact,
        },
        "random_null_oos": null_oos,
        "gates": gates,
        "clears_all_gates": clears,
        "failing_gates": fails,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    mes = load_futures("MES")
    mnq = load_futures("MNQ")
    common_days = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common_days)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common_days)].reset_index(drop=True)

    atr_mes = atr_series(mes["high"], mes["low"], mes["close"], ATR_LEN)
    atr_mnq = atr_series(mnq["high"], mnq["low"], mnq["close"], ATR_LEN)
    de_mes = {d: int(g.index[-1]) for d, g in mes.groupby("date")}
    de_mnq = {d: int(g.index[-1]) for d, g in mnq.groupby("date")}
    state_mes = _per_session_state(mes)
    state_mnq = _per_session_state(mnq)

    cut = int(len(common_days) * OOS_TRAIN_FRAC)
    is_days = set(common_days[:cut])
    oos_days = set(common_days[cut:])
    is_days_sorted = sorted(is_days)
    n_q = len(set(quarter(d) for d in common_days))

    # leader, laggard, lead_df, lag_df, lead_state, lag_state, lag_atr, lag_de
    configs = [
        ("MES", "MNQ", mes, mnq, state_mes, state_mnq, atr_mnq, de_mnq),  # primary
        ("MNQ", "MES", mnq, mes, state_mnq, state_mes, atr_mes, de_mes),  # reverse check
    ]

    results = {
        "meta": {
            "kind": "rescue-futures",
            "slug": "mesmnq_div_rescue",
            "lead_rescued": "b4-mes-mnq-divergence MES->MNQ thr=0.0015 (failed gate-5 only)",
            "hypothesis": (
                "RESCUE the B4 MES->MNQ divergence lead (OOS +$55/tr but FAILED gate-5: "
                "drop-top5 -$4.70) via a concentration fix. Sweep (a) vol-regime band, "
                "(b) 1-entry-per-day cap [structural no-op], (c) top-quartile divergence-"
                "magnitude day-filter, (d) min-divergence-persistence N bars. Winner must "
                "clear gate-5 AND all 7 other gates. Futures point-P&L, MNQ primary + MES "
                "reverse check."
            ),
            "generated": "2026-06-21",
            "base_threshold": BASE_THRESHOLD,
            "threshold_sweep": THRESHOLD_SWEEP,
            "qty_micros": b4.QTY,
            "commission_rt": b4.COMMISSION_RT,
            "slippage_ticks_each_side": b4.SLIP_TICKS,
            "point_value": b4.POINT_VALUE,
            "n_common_days": len(common_days),
            "date_range": [str(common_days[0]), str(common_days[-1])],
            "oos_split": {
                "is_days": len(is_days),
                "oos_days": len(oos_days),
                "oos_start": str(sorted(oos_days)[0]),
                "train_frac": OOS_TRAIN_FRAC,
            },
            "n_quarters": n_q,
            "entry_window": [str(RTH_OPEN), str(ENTRY_CUTOFF)],
            "fixes": {
                "a_vol_regime": ["low", "mid", "high", "drop_extreme_high"],
                "b_one_per_day": "structural no-op (base already 1/day) — verified",
                "c_top_mag": [0.5, 0.25, 0.1],
                "d_persistence": [1, 2, 3],
            },
            "gate_definitions": {
                "1": "OOS(2026) per-trade > 0",
                "2": f"positive in >= ceil(0.6*{n_q}) quarters",
                "3": "top-5 winning days < 200% of total P&L",
                "4": "n_trades >= 20",
                "5": "drop-top5-days per-trade > 0  (THE BLOCKER the rescue must clear)",
                "6": "IS(2025) first-half per-trade > 0",
                "7": "beats random-entry null mean (L172)",
                "8": "no-truncation: chart-stop+EOD doesn't flip a positive cell negative (L171)",
            },
            "leakage_controls": (
                "IS-derived fix thresholds (vol band, magnitude cut) FROZEN on in-sample "
                "days only; persistence is causal (walk-back over closed bars). Gate logic "
                "reused verbatim from B4 — no drift between lead and rescue."
            ),
        },
        "cells": [],
    }

    cleared: list[dict] = []
    best = None  # (oos_per_trade, tag, cell)  among gate-5-clearing or, if none, n>=20

    for lead_sym, lag_sym, lead_df, lag_df, lead_st, lag_st, lag_atr, lag_de in configs:
        for thr in THRESHOLD_SWEEP:
            enriched = enrich_signals(
                lead_df, lag_df, lead_st, lag_st, lag_sym, thr, lag_atr
            )
            base_n = len(enriched)

            # Build the fix variants for this (config, thr)
            variants: list[tuple[str, str, list[Sig], dict]] = []
            # (a) vol-regime
            for vv in results["meta"]["fixes"]["a_vol_regime"]:
                variants.append(
                    ("a_vol_regime", vv, fix_vol_regime(enriched, is_days, vv), {})
                )
            # (b) one-per-day (structural no-op)
            keep_b, info_b = fix_one_per_day(enriched)
            variants.append(("b_one_per_day", "cap1", keep_b, info_b))
            # (c) top-magnitude
            for tf in results["meta"]["fixes"]["c_top_mag"]:
                variants.append(
                    ("c_top_mag", f"top{int(tf*100)}", fix_top_quartile_mag(enriched, is_days, tf), {})
                )
            # (d) persistence
            for nb in results["meta"]["fixes"]["d_persistence"]:
                variants.append(
                    ("d_persistence", f"n{nb}", fix_min_persistence(enriched, nb), {})
                )

            for fix_name, knob, sigs, extra in variants:
                cell = eval_subset(
                    lag_df, lag_sym, sigs, lag_atr, lag_de,
                    is_days, oos_days, is_days_sorted, n_q,
                )
                cell.update(
                    {
                        "leader": lead_sym,
                        "laggard": lag_sym,
                        "threshold": thr,
                        "fix": fix_name,
                        "knob": knob,
                        "base_n_signals": base_n,
                        "fix_extra": extra,
                    }
                )
                results["cells"].append(cell)
                o = cell["oos"]
                tag = f"{lead_sym}->{lag_sym} thr={thr} {fix_name}/{knob}"
                drop_pt = cell["full"].get("drop_top5_per_trade")
                print(
                    f"[b5] {tag:42s} n={cell['n_signals']:3d} "
                    f"oos_pt={o.get('per_trade')} drop5={drop_pt} "
                    f"top5%={cell['full'].get('top5_day_pct')} posQ={cell['positive_quarters']}/{n_q} "
                    f"-> {'CLEARS' if cell['clears_all_gates'] else 'no('+';'.join(cell['failing_gates'])+')'}",
                    flush=True,
                )
                if cell["clears_all_gates"]:
                    cleared.append(cell)
                    key = o.get("per_trade") or -1e9
                    if best is None or key > best[0]:
                        best = (key, tag, cell)

    # Fallback "best" if nothing clears: highest OOS/tr among n>=20 cells (for disclosure)
    if best is None:
        for c in results["cells"]:
            if c["full"].get("n", 0) >= 20 and c["oos"].get("per_trade") is not None:
                key = c["oos"]["per_trade"]
                if best is None or key > best[0]:
                    best = (
                        key,
                        f"{c['leader']}->{c['laggard']} thr={c['threshold']} {c['fix']}/{c['knob']}",
                        c,
                    )

    results["n_clearing_cells"] = len(cleared)
    results["clearing_cells"] = [
        {
            "config": f"{c['leader']}->{c['laggard']}",
            "threshold": c["threshold"],
            "fix": c["fix"],
            "knob": c["knob"],
            "n": c["n_signals"],
            "oos_per_trade": c["oos"].get("per_trade"),
            "drop_top5_per_trade": c["full"].get("drop_top5_per_trade"),
        }
        for c in cleared
    ]
    if best is not None:
        b = best[2]
        results["best_cell"] = {
            "config": best[1],
            "oos_per_trade": best[0] if b["clears_all_gates"] else b["oos"].get("per_trade"),
            "n_signals": b["n_signals"],
            "drop_top5_per_trade": b["full"].get("drop_top5_per_trade"),
            "top5_day_pct": b["full"].get("top5_day_pct"),
            "clears_all_gates": b["clears_all_gates"],
            "failing_gates": b["failing_gates"],
            "fix": b["fix"],
            "knob": b["knob"],
        }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[b5] WROTE {OUT_JSON}")
    print(f"[b5] cells evaluated: {len(results['cells'])}")
    print(f"[b5] clearing cells (all 8 gates incl gate-5): {len(cleared)}")
    if best is not None:
        b = best[2]
        print(
            f"[b5] BEST: {best[1]}  oos_pt=${b['oos'].get('per_trade')}  "
            f"drop5=${b['full'].get('drop_top5_per_trade')}  n={b['n_signals']}  "
            f"clears={b['clears_all_gates']}  fails={b['failing_gates']}"
        )


if __name__ == "__main__":
    main()
