"""B6 DE-CONCENTRATION STACK — the DECISIVE test of whether edge #3 is a real 3rd edge.

WHAT B5 FOUND (and why it is not yet shippable)
-----------------------------------------------
B5 (`_b5_mesmnq_div_rescue.py`) rescued the B4 MES->MNQ divergence lead by applying the
min-divergence-persistence fix at N=2. That cell cleared ALL 8 of B5's gates, headline:

    MES->MNQ thr=0.0015 d_persistence/n2 : OOS +$71.46/tr, n=118,
    FULL-sample drop-top5 = +$3.65 (gate-5 PASS), top5-day = 92.4%.

THE SHIP-REVIEW HOLE (the reason for B6)
----------------------------------------
B5's gate-5 (drop-top5 +$3.65) was computed on the **FULL IS+OOS sample**. On the
**OOS-ALONE window** (n=41) the same statistic is:

    drop-top5_OOS = -$16.36   AND   top5-day_OOS = 120.1%.

Translation: remove the 5 best *OOS* days and the OOS edge goes NEGATIVE. The
persistence>=2 fix de-concentrated the FULL sample but did NOT de-concentrate OOS-alone.
A FULL-sample drop-top5 is necessary but NOT sufficient — the live edge must survive
top-5-day removal on the out-of-sample window it will actually trade in (C4/C22:
disclose concentration, normalize OOS, beware 2026-bull-regime artifacts).

THE B6 EXPERIMENT — STACK (a)+(d) AND JUDGE ON OOS-ALONE DROP-TOP5
------------------------------------------------------------------
1. STACK fix (a) vol-regime ATR%-band gate AND fix (d) persistence>=N TOGETHER.
   Sweep the SAME ATR-band variants B5 used {low, mid, high, drop_extreme_high}
   x N in {2,3,4} x the same threshold sweep {0.0010, 0.0015, 0.0020}.
   The two fixes are independent SIGNAL-SET SUBSET filters; intersecting them should
   trim the right tail (vol-regime) AND the noise blips (persistence) at once.

2. For EVERY cell compute drop-top5 on BOTH
     (i)  the FULL sample      (B5's necessary-but-insufficient statistic), AND
     (ii) the OOS-ALONE window (the decisive de-concentration test).
   Both reported side-by-side.

3. STRICTER B6 WINNER BAR — a cell clears ONLY when:
     * drop-top5 on the OOS-ALONE window > 0   (the new decisive gate), AND
     * OOS-alone per-trade > 0,                 AND
     * all 7 OTHER B4/B5 gates pass.
   (B5's full-sample gate-5 stays in the suite as gate-5 but is no longer sufficient.)

4. MAP THE PERSISTENCE PLATEAU — is N=2 the center of a flat favorable region
   (N=3,4 also de-concentrate OOS) or a fragile single-value spike? We report
   drop-top5_OOS at EACH N (2,3,4) for the headline thr/band so the plateau is visible.

5. LEAKAGE CONTROL — every IS-derived threshold (ATR-band edges, top-Q) is FROZEN on
   IS-2025 days ONLY. Persistence is causal (walk-back over closed bars). No OOS leakage.

REUSED VERBATIM (no signal/sim/gate drift between B4 lead, B5 rescue, B6 stack):
  * data loaders + per-session state            (b4.load_futures / _per_session_state)
  * (a) vol-regime ATR%-band gate logic         (b5.fix_vol_regime)
  * (d) min-divergence-persistence logic         (b5.fix_min_persistence + enrich_signals)
  * the 8-gate point-P&L suite                    (b4.eval_cell math, via b5.eval_subset)
NOTE on fraud_gates.py: that module re-simulates the SPY *option* (OPRA) domain via
lib.simulator_real and is structurally INAPPLICABLE to futures point-P&L (no strike, no
premium stop). The B4/B5 8-gate suite IS the futures-domain graduated-fraud analog of
fraud_gates (gate-7 = random-entry null L172, gate-8 = no-truncation L171); B6 reuses
THAT suite verbatim, which is the correct fraud-gate stack for this domain.

HONEST VERDICT:
  * NO stacked cell clears OOS-alone drop-top5 > 0  -> edge #3 is a 2026-bull-regime
    artifact (C22). verdict ARCHIVE_REGIME_ARTIFACT, recommend NOT shipping.
  * A stacked cell DOES clear  -> SHIP_DECONCENTRATED (still gated on the futures
    order-builder). Negative results are NOT softened.

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_b6_div_stack.py
Pure Python, $0, no live orders, no option pricing. Markets CLOSED.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest" / "autoresearch"))

# Reuse the PROVEN B4 lead machinery + B5 rescue fixes VERBATIM — zero drift.
import _b4_mes_mnq_divergence as b4  # noqa: E402
from _b4_mes_mnq_divergence import (  # noqa: E402
    ATR_LEN,
    ENTRY_CUTOFF,
    OOS_TRAIN_FRAC,
    RTH_OPEN,
    atr_series,
    by_quarter,
    is_first_half_per_trade,
    load_futures,
    metrics,
    quarter,
    random_null,
    simulate,
    _per_session_state,
)
from _b5_mesmnq_div_rescue import (  # noqa: E402
    enrich_signals,
    fix_min_persistence,
    fix_vol_regime,
)

OUT_JSON = ROOT / "analysis" / "recommendations" / "b6-div-stack.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "B6-DIVERGENCE-STACK-SCORECARD.md"

# Same threshold sweep B5 used (sweep around the proven B4 lead so the fix isn't tied to one thr).
THRESHOLD_SWEEP = [0.0010, 0.0015, 0.0020]
# Same ATR-band variants B5's fix (a) used.
VOL_BANDS = ["low", "mid", "high", "drop_extreme_high"]
# Persistence plateau sweep — the task's N in {2,3,4}.
PERSISTENCE_N = [2, 3, 4]
HEADLINE_THR = 0.0015           # the B4/B5 lead threshold (for the plateau map)
HEADLINE_BAND = "drop_extreme_high"  # trims only the vol tail — the de-concentration intent


def _stack_signals(enriched, is_days, band, n_bars):
    """STACK fix (a) vol-regime AND fix (d) persistence: keep only signals in BOTH subsets.
    Both fixes return list[Sig] from the SAME enriched signal pool; the stack is the
    set-intersection by the (date, idx, side) identity of the Sig. IS-derived band edges
    are frozen inside fix_vol_regime on is_days only; persistence is causal."""
    keep_vol = fix_vol_regime(enriched, is_days, band)
    keep_per = fix_min_persistence(enriched, n_bars)
    ids_per = {(s.date, s.idx, s.side) for s in keep_per}
    # intersect; preserve vol-subset order (deterministic)
    return [s for s in keep_vol if (s.date, s.idx, s.side) in ids_per]


def eval_stack_cell(lag_df, symbol, sigs, atr, day_end, is_days, oos_days,
                    is_days_sorted, n_quarters):
    """Evaluate one stacked signal subset through the SAME 8-gate point-P&L suite B4/B5
    use, PLUS the new B6 decisive statistic: drop-top5 + top5-day on the OOS-ALONE window.

    The 8-gate math is byte-equivalent to b4.eval_cell / b5.eval_subset (we re-walk the
    same simulate() fills). The B6 addition: compute metrics() on the OOS fills ALONE so
    drop_top5_per_trade / top5_day_pct reflect the out-of-sample window the edge trades in."""
    fills = [f for s in sigs
             if (f := simulate(lag_df, s, symbol, atr=atr, day_end=day_end,
                               exit_mode="atr_trail"))]
    fills_notrunc = [f for s in sigs
                     if (f := simulate(lag_df, s, symbol, atr=atr, day_end=day_end,
                                       exit_mode="chartstop_eod"))]
    is_fills = [f for f in fills if f.date in is_days]
    oos_fills = [f for f in fills if f.date in oos_days]

    m_all = metrics(fills)
    m_is = metrics(is_fills)
    m_oos = metrics(oos_fills)            # <-- metrics() on OOS-alone gives drop-top5_OOS

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
    top5_full = m_all.get("top5_day_pct")
    drop_full = m_all.get("drop_top5_per_trade")        # FULL-sample (B5's gate-5)
    top5_oos = m_oos.get("top5_day_pct")
    drop_oos = m_oos.get("drop_top5_per_trade")          # OOS-ALONE (B6 decisive)
    notrunc_pt = m_notrunc.get("per_trade")
    full_pt = m_all.get("per_trade")

    # ── the original 8 gates (verbatim definitions from B4/B5) ──────────────────
    g1 = oos_pt is not None and oos_pt > 0
    g2 = pos_q >= need_q
    g3 = top5_full is not None and top5_full < 200.0
    g4 = n_all >= 20
    g5 = drop_full is not None and drop_full > 0          # FULL-sample drop-top5 (necessary)
    g6 = is_half is not None and is_half > 0
    g7 = oos_pt is not None and null_pt is not None and oos_pt > null_pt
    truncation_artifact = (full_pt is not None and full_pt > 0
                           and notrunc_pt is not None and notrunc_pt < 0)
    g8 = not truncation_artifact
    gates = {
        "1_oos_per_trade_pos": g1,
        "2_positive_quarters_>=60pct": g2,
        "3_top5_day_pct_<200": g3,
        "4_n_trades_>=20": g4,
        "5_drop_top5_FULL_per_trade_>0": g5,
        "6_is_first_half_per_trade_>0": g6,
        "7_beats_random_null": g7,
        "8_no_truncation_artifact": g8,
    }

    # ── B6 DECISIVE GATE: OOS-ALONE drop-top5 > 0 ──────────────────────────────
    g_oos_drop = drop_oos is not None and drop_oos > 0
    # The seven OTHER gates (everything except the FULL-sample drop-top5 g5, which B6
    # demotes to "necessary but not sufficient"). Per the task: clear only if OOS-alone
    # drop-top5 > 0 AND all 7 OTHER gates pass AND OOS/tr > 0.
    seven_others = [g1, g2, g3, g4, g6, g7, g8]
    b6_clears = bool(g_oos_drop and g1 and all(seven_others))
    b6_fails = []
    if not g_oos_drop:
        b6_fails.append("B6_oos_drop_top5_>0")
    for k, v in gates.items():
        if k == "5_drop_top5_FULL_per_trade_>0":
            continue  # demoted: tracked but not part of the B6 sufficiency set
        if not v:
            b6_fails.append(k)

    return {
        "n_signals": len(sigs),
        "n_fills": len(fills),
        "full": m_all,
        "is": m_is,
        "oos": m_oos,
        "drop_top5_FULL_per_trade": drop_full,
        "top5_day_pct_FULL": top5_full,
        "drop_top5_OOS_per_trade": drop_oos,
        "top5_day_pct_OOS": top5_oos,
        "by_quarter": q,
        "positive_quarters": pos_q,
        "need_quarters": need_q,
        "is_first_half_per_trade": is_half,
        "no_truncation_ref": {"chartstop_eod_per_trade": notrunc_pt,
                              "full_per_trade": full_pt,
                              "is_artifact": truncation_artifact},
        "random_null_oos": null_oos,
        "gates_original_8": gates,
        "b6_oos_drop_top5_pass": g_oos_drop,
        "b6_clears": b6_clears,
        "b6_failing_gates": b6_fails,
    }


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

    configs = [
        ("MES", "MNQ", mes, mnq, state_mes, state_mnq, atr_mnq, de_mnq),  # primary (edge #3)
        ("MNQ", "MES", mnq, mes, state_mnq, state_mes, atr_mes, de_mes),  # reverse check
    ]

    results = {
        "meta": {
            "kind": "deconcentration-stack-futures",
            "slug": "b6_div_stack",
            "edge_under_test": (
                "edge #3 = B5 MES->MNQ thr=0.0015 d_persistence/n2 (cleared B5's 8 gates "
                "on FULL-sample drop-top5 +$3.65, but OOS-ALONE drop-top5 = -$16.36, "
                "top5-day_OOS = 120.1% -> NOT de-concentrated out-of-sample)"
            ),
            "hypothesis": (
                "STACK fix (a) vol-regime ATR%-band + fix (d) persistence>=N together to "
                "de-concentrate the OOS-ALONE window. A cell is a B6 winner only if "
                "OOS-alone drop-top5 > 0 AND OOS/tr > 0 AND all 7 other B4/B5 gates pass. "
                "If none clears, edge #3 is a 2026-bull-regime artifact (C22) -> ARCHIVE."
            ),
            "generated": "2026-06-21",
            "reused_verbatim": [
                "b4.load_futures / _per_session_state (data loaders + session state)",
                "b5.fix_vol_regime (a) vol-regime ATR%-band gate",
                "b5.fix_min_persistence + b5.enrich_signals (d) persistence",
                "b4.eval_cell 8-gate point-P&L math (gate-7 null L172, gate-8 no-trunc L171)",
            ],
            "fraud_gates_note": (
                "fraud_gates.py re-simulates the SPY OPRA *option* domain (strike_offset + "
                "premium_stop via lib.simulator_real) and is structurally inapplicable to "
                "futures point-P&L. The B4/B5 8-gate suite is the futures-domain graduated-"
                "fraud analog (null + no-truncation) and is reused verbatim here."
            ),
            "threshold_sweep": THRESHOLD_SWEEP,
            "vol_bands": VOL_BANDS,
            "persistence_N_sweep": PERSISTENCE_N,
            "headline_thr": HEADLINE_THR,
            "headline_band": HEADLINE_BAND,
            "n_common_days": len(common_days),
            "date_range": [str(common_days[0]), str(common_days[-1])],
            "oos_split": {"is_days": len(is_days), "oos_days": len(oos_days),
                          "oos_start": str(sorted(oos_days)[0]),
                          "train_frac": OOS_TRAIN_FRAC},
            "n_quarters": n_q,
            "entry_window": [str(RTH_OPEN), str(ENTRY_CUTOFF)],
            "b6_winner_bar": (
                "drop-top5 on OOS-ALONE > 0 AND OOS/tr > 0 AND all 7 other gates pass "
                "(FULL-sample drop-top5 is necessary but NOT sufficient)"
            ),
            "leakage_controls": (
                "ATR-band edges + any top-Q frozen on IS-2025 days only (inside "
                "fix_vol_regime); persistence is causal walk-back over closed bars; gate "
                "logic verbatim from B4 -> no drift across B4/B5/B6."
            ),
        },
        "cells": [],
    }

    cleared = []
    best = None  # (oos_drop, tag, cell) among B6-clearing; else fallback for disclosure
    # plateau map: {config: {N: {thr,band: drop_oos}}} for the headline thr/band, all N
    plateau = {}

    for lead_sym, lag_sym, lead_df, lag_df, lead_st, lag_st, lag_atr, lag_de in configs:
        plateau[f"{lead_sym}->{lag_sym}"] = {}
        for thr in THRESHOLD_SWEEP:
            enriched = enrich_signals(lead_df, lag_df, lead_st, lag_st, lag_sym, thr, lag_atr)
            base_n = len(enriched)
            for band in VOL_BANDS:
                for n_bars in PERSISTENCE_N:
                    sigs = _stack_signals(enriched, is_days, band, n_bars)
                    cell = eval_stack_cell(
                        lag_df, lag_sym, sigs, lag_atr, lag_de,
                        is_days, oos_days, is_days_sorted, n_q)
                    cell.update({
                        "leader": lead_sym, "laggard": lag_sym, "threshold": thr,
                        "vol_band": band, "persistence_n": n_bars,
                        "base_n_signals": base_n,
                    })
                    results["cells"].append(cell)

                    drop_oos = cell["drop_top5_OOS_per_trade"]
                    drop_full = cell["drop_top5_FULL_per_trade"]
                    oos_pt = cell["oos"].get("per_trade")
                    tag = f"{lead_sym}->{lag_sym} thr={thr} {band}/n{n_bars}"
                    print(
                        f"[b6] {tag:40s} n={cell['n_signals']:3d} "
                        f"oos_pt={oos_pt} dropFULL={drop_full} dropOOS={drop_oos} "
                        f"top5OOS%={cell['top5_day_pct_OOS']} posQ={cell['positive_quarters']}/{n_q} "
                        f"-> {'B6-CLEARS' if cell['b6_clears'] else 'no('+';'.join(cell['b6_failing_gates'])+')'}",
                        flush=True)

                    # plateau map for the headline thr+band across all N
                    if thr == HEADLINE_THR and band == HEADLINE_BAND:
                        plateau[f"{lead_sym}->{lag_sym}"][f"n{n_bars}"] = {
                            "drop_top5_OOS_per_trade": drop_oos,
                            "drop_top5_FULL_per_trade": drop_full,
                            "oos_per_trade": oos_pt,
                            "top5_day_pct_OOS": cell["top5_day_pct_OOS"],
                            "n_signals": cell["n_signals"],
                            "b6_clears": cell["b6_clears"],
                        }

                    if cell["b6_clears"]:
                        cleared.append(cell)
                        key = drop_oos if drop_oos is not None else -1e9
                        if best is None or key > best[0]:
                            best = (key, tag, cell)

    # Fallback "best" for disclosure if nothing clears: the cell with the highest
    # OOS-alone drop-top5 among n>=20 cells (the closest-to-clearing, honestly reported).
    if best is None:
        for c in results["cells"]:
            if c["full"].get("n", 0) >= 20 and c["drop_top5_OOS_per_trade"] is not None:
                key = c["drop_top5_OOS_per_trade"]
                if best is None or key > best[0]:
                    best = (key,
                            f"{c['leader']}->{c['laggard']} thr={c['threshold']} "
                            f"{c['vol_band']}/n{c['persistence_n']}",
                            c)

    results["n_clearing_cells"] = len(cleared)
    results["clearing_cells"] = [
        {"config": f"{c['leader']}->{c['laggard']}", "threshold": c["threshold"],
         "vol_band": c["vol_band"], "persistence_n": c["persistence_n"],
         "n": c["n_signals"], "oos_per_trade": c["oos"].get("per_trade"),
         "drop_top5_OOS_per_trade": c["drop_top5_OOS_per_trade"],
         "drop_top5_FULL_per_trade": c["drop_top5_FULL_per_trade"]}
        for c in cleared
    ]
    results["persistence_plateau"] = plateau
    if best is not None:
        b = best[2]
        results["best_cell"] = {
            "config": best[1],
            "oos_per_trade": b["oos"].get("per_trade"),
            "n_signals": b["n_signals"],
            "drop_top5_OOS_per_trade": b["drop_top5_OOS_per_trade"],
            "drop_top5_FULL_per_trade": b["drop_top5_FULL_per_trade"],
            "top5_day_pct_OOS": b["top5_day_pct_OOS"],
            "b6_clears": b["b6_clears"],
            "b6_failing_gates": b["b6_failing_gates"],
            "vol_band": b["vol_band"],
            "persistence_n": b["persistence_n"],
        }

    verdict = "SHIP_DECONCENTRATED" if cleared else "ARCHIVE_REGIME_ARTIFACT"
    results["verdict"] = verdict

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    _write_scorecard(results)

    print(f"\n[b6] WROTE {OUT_JSON}")
    print(f"[b6] WROTE {OUT_MD}")
    print(f"[b6] cells evaluated: {len(results['cells'])}")
    print(f"[b6] B6-clearing cells (OOS-alone drop-top5>0 + OOS/tr>0 + 7 gates): {len(cleared)}")
    print(f"[b6] VERDICT: {verdict}")
    if best is not None:
        b = best[2]
        print(f"[b6] BEST (by OOS-drop-top5): {best[1]}  oos_pt=${b['oos'].get('per_trade')}  "
              f"dropOOS=${b['drop_top5_OOS_per_trade']}  dropFULL=${b['drop_top5_FULL_per_trade']}  "
              f"n={b['n_signals']}  b6_clears={b['b6_clears']}")


def _fmt(x):
    return "n/a" if x is None else f"{x}"


def _write_scorecard(results: dict) -> None:
    m = results["meta"]
    lines = []
    lines.append("# B6 — DE-CONCENTRATION STACK SCORECARD")
    lines.append("")
    lines.append("> The decisive test of whether **edge #3** (B5 MES->MNQ persistence/n2) is a real 3rd")
    lines.append("> futures edge, or a 2026-bull-regime concentration artifact. Generated "
                 f"{m['generated']}. Pure-Python, $0.")
    lines.append("")
    lines.append(f"**VERDICT: `{results['verdict']}`**")
    lines.append("")
    lines.append("## What B6 tests")
    lines.append("")
    lines.append(f"- {m['edge_under_test']}")
    lines.append(f"- **Stack:** fix (a) vol-regime ATR%-band {m['vol_bands']} x "
                 f"fix (d) persistence N {m['persistence_N_sweep']} x threshold "
                 f"{m['threshold_sweep']} (both fixes intersected as signal-set subsets).")
    lines.append(f"- **B6 winner bar:** {m['b6_winner_bar']}.")
    lines.append(f"- **Leakage controls:** {m['leakage_controls']}")
    lines.append(f"- **Data:** {m['n_common_days']} common MES/MNQ days "
                 f"{m['date_range'][0]} .. {m['date_range'][1]}; OOS split "
                 f"{m['oos_split']['is_days']} IS / {m['oos_split']['oos_days']} OOS "
                 f"(OOS starts {m['oos_split']['oos_start']}).")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    lines.append(f"- **Cells evaluated:** {len(results['cells'])}")
    lines.append(f"- **B6-clearing cells:** {results['n_clearing_cells']}")
    if results["n_clearing_cells"]:
        lines.append("")
        lines.append("| config | thr | band | N | n | OOS/tr | dropOOS | dropFULL |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in results["clearing_cells"]:
            lines.append(f"| {c['config']} | {c['threshold']} | {c['vol_band']} | "
                         f"{c['persistence_n']} | {c['n']} | {_fmt(c['oos_per_trade'])} | "
                         f"{_fmt(c['drop_top5_OOS_per_trade'])} | {_fmt(c['drop_top5_FULL_per_trade'])} |")
    else:
        lines.append("- **NO stacked cell cleared the OOS-alone drop-top5 > 0 bar.**")
    lines.append("")
    bc = results.get("best_cell")
    if bc:
        lines.append("## Best cell (by OOS-alone drop-top5)")
        lines.append("")
        lines.append(f"- **{bc['config']}** — band `{bc['vol_band']}`, persistence N={bc['persistence_n']}")
        lines.append(f"- n = {bc['n_signals']}, OOS/tr = ${_fmt(bc['oos_per_trade'])}")
        lines.append(f"- **drop-top5 OOS-alone = ${_fmt(bc['drop_top5_OOS_per_trade'])}** "
                     f"(top5-day OOS = {_fmt(bc['top5_day_pct_OOS'])}%)")
        lines.append(f"- drop-top5 FULL-sample = ${_fmt(bc['drop_top5_FULL_per_trade'])} "
                     "(B5's necessary-but-insufficient statistic)")
        lines.append(f"- B6 clears: **{bc['b6_clears']}**"
                     + ("" if bc["b6_clears"] else f" — fails: {bc['b6_failing_gates']}"))
        lines.append("")
    lines.append("## Persistence plateau map (headline thr="
                 f"{m['headline_thr']}, band `{m['headline_band']}`)")
    lines.append("")
    lines.append("Is N=2 the center of a flat favorable region, or a fragile single-value spike?")
    lines.append("drop-top5 on the **OOS-alone** window at each N:")
    lines.append("")
    for cfg, byN in results["persistence_plateau"].items():
        lines.append(f"### {cfg}")
        lines.append("")
        lines.append("| N | n | OOS/tr | dropOOS | dropFULL | top5-day OOS% | B6 clears |")
        lines.append("|---|---|---|---|---|---|---|")
        for nk in sorted(byN.keys()):
            r = byN[nk]
            lines.append(f"| {nk[1:]} | {r['n_signals']} | {_fmt(r['oos_per_trade'])} | "
                         f"{_fmt(r['drop_top5_OOS_per_trade'])} | {_fmt(r['drop_top5_FULL_per_trade'])} | "
                         f"{_fmt(r['top5_day_pct_OOS'])} | {r['b6_clears']} |")
        lines.append("")
    lines.append("## Honest read")
    lines.append("")
    if results["verdict"] == "ARCHIVE_REGIME_ARTIFACT":
        lines.append("**NO stacked (vol-regime x persistence) cell de-concentrates the OOS-alone "
                     "window** (drop-top5 OOS stays <= 0 everywhere it otherwise qualifies). "
                     "Per C22 (backward-looking gates anti-correlate with recovery / regime-"
                     "specific edges), **edge #3 is a 2026-bull-regime concentration artifact**: "
                     "its OOS profit lives in the 5 best OOS days and does not survive their "
                     "removal. **Recommendation: do NOT ship edge #3.** The B5 full-sample "
                     "drop-top5 +$3.65 was necessary but not sufficient; the decisive OOS-alone "
                     "test fails.")
    else:
        lines.append("At least one stacked cell de-concentrates the **OOS-alone** window "
                     "(drop-top5 OOS > 0) while clearing all 7 other gates and keeping OOS/tr > 0. "
                     "Edge #3 survives the decisive de-concentration test -> "
                     "**SHIP_DECONCENTRATED**, still gated on the futures order-builder before "
                     "any live placement.")
    lines.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
