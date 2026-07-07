"""OOS A/B SHIP-GATE for vwap_continuation exit params: candidate -0.06/0.40 vs the
CURRENT LIVE-armed -0.08/0.30, on the ACTUAL live cell (ATM Safe-2, strike_offset=0).

CONTEXT: the walk-forward study (analysis/recommendations/vwapcont-walkforward.json,
N=149 real OPRA) found the static exit -0.08/0.30 = $44.81/tr on the TEST region and a
best-FIXED cell -0.06/0.40 = $55.18/tr (+$10.37/tr) -- but that best-fixed was IN-SAMPLE.
This harness runs a PROPER OP-22 ship gate on the SAME trade set:
  (a) OOS (2026) expectancy positive AND candidate > current OOS
  (b) walk-forward per-trade WF = candidate OOS exp / candidate IS exp >= 0.70
  (c) sub-windows / quarters stable (no quarter where candidate << current)
  (d) anchor no-regression (J source-of-truth trades don't get worse)
  (e) drop-top3 still positive

PARITY GATE first: the current-static full/OOS numbers must reproduce the scorecard's
static (walk-forward static_aggregate_exp=44.81 on TEST region; sensitivity full-sample
stop-0.08_tp10.30 exp=47.27). If baseline doesn't reproduce, STOP (parity-fail).

Reuses simulate_cell_ext + metrics + edge_capture byte-for-byte (same detector pass, same
window, same real-OPRA fill path, ATM strike = the live cell). Exit shape is the ONLY lever.

C29: this validates the ATM Safe-2 cell = the LIVE armed cell (j_vwap_cont_strike_offset_safe
=0). ITM-2 is a DIFFERENT tier (unaffordable at Safe-2) and is NOT validated here.

RESEARCH ONLY. No params/heartbeat/order edits. Writes
analysis/recommendations/vwapcont-exit-ab-ship-gate.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/vwapcont_exit_ab_ship_gate.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix,
    _normalize_spy,
    detect_signals,
    metrics,
)
from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch.vwapcont_exit_parity import (  # noqa: E402
    WINDOW,
    edge_capture,
    simulate_cell_ext,
)
from lib.ribbon import compute_ribbon  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "vwapcont-exit-ab-ship-gate.json"

# Live exit shape held constant (ATM, tp1_qty 0.8, PL fixed arm+5%) -- SAME BASE as the
# walk-forward. Only (stop, tp1) differs between the two cells.
BASE_SHAPE = {
    "runner_target_premium_pct": 2.5,
    "tp1_qty_fraction": 0.8,
    "profit_lock_mode": "fixed",
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.0,
}
CURRENT = {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.30, **BASE_SHAPE}
CANDIDATE = {"premium_stop_pct": -0.06, "tp1_premium_pct": 0.40, **BASE_SHAPE}
STRIKE_OFFSET = 0  # ATM = the LIVE Safe-2 cell (C29)

WF_GATE = 0.70
# parity: full-sample stop-0.08/tp1-0.30 exp from the walk-forward sensitivity sweep.
PARITY_TARGET_FULL_EXP = 47.27
PARITY_TOL = 0.75  # $/tr tolerance on the reproduced baseline


def _pnls_by_key(rows):
    return {(r.date, r.side, r.strike): r.pnl for r in rows}


def drop_topk_positive(rows, k=3):
    """Total & exp with the top-k single trades removed (concentration robustness)."""
    pnls = sorted((r.pnl for r in rows), reverse=True)
    kept = pnls[k:]
    tot = round(sum(kept), 2)
    exp = round(sum(kept) / len(kept), 2) if kept else 0.0
    return {"n_dropped": k, "total_ex_topk": tot, "exp_ex_topk": exp,
            "positive": bool(tot > 0)}


def main() -> int:
    print(f"[ab] loading SPY+VIX {WINDOW[0]}..{WINDOW[1]} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(*WINDOW)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    print(f"[ab] {len(signals)} signals over {len(days)} trading days", flush=True)

    cur_rows, cur_cov = simulate_cell_ext(
        signals, spy, ribbon, vix, strike_offset=STRIKE_OFFSET, sim_kwargs=CURRENT)
    cand_rows, cand_cov = simulate_cell_ext(
        signals, spy, ribbon, vix, strike_offset=STRIKE_OFFSET, sim_kwargs=CANDIDATE)

    # intersect to the SAME trade set (fair A/B; entry/strike identical, exit is the lever)
    cur_map, cand_map = _pnls_by_key(cur_rows), _pnls_by_key(cand_rows)
    common_keys = [k for k in cur_map if k in cand_map]
    cur_common = [r for r in cur_rows if (r.date, r.side, r.strike) in set(common_keys)]
    cand_common = [r for r in cand_rows if (r.date, r.side, r.strike) in set(common_keys)]
    # sort both identically by (date, side, strike)
    cur_common.sort(key=lambda r: (r.date, r.side, r.strike))
    cand_common.sort(key=lambda r: (r.date, r.side, r.strike))
    n = len(common_keys)
    dropped = (len(cur_rows) - n, len(cand_rows) - n)
    print(f"[ab] common trade set n={n} (current dropped {dropped[0]}, "
          f"candidate dropped {dropped[1]})", flush=True)

    m_cur = metrics(cur_common)
    m_cand = metrics(cand_common)
    anc_cur = edge_capture(cur_common)
    anc_cand = edge_capture(cand_common)
    d3_cur = drop_topk_positive(cur_common, 3)
    d3_cand = drop_topk_positive(cand_common, 3)

    # ── PARITY GATE ──
    parity_diff = round(m_cur["exp_dollar"] - PARITY_TARGET_FULL_EXP, 2)
    parity_ok = abs(parity_diff) <= PARITY_TOL
    parity = {
        "reproduced_current_full_exp": m_cur["exp_dollar"],
        "scorecard_full_exp_target": PARITY_TARGET_FULL_EXP,
        "diff": parity_diff, "tolerance": PARITY_TOL, "PASS": bool(parity_ok),
        "note": ("reproduced within tolerance -> A/B numbers trustworthy" if parity_ok
                 else "PARITY FAIL -> baseline does not reproduce, STOP, do not trust A/B"),
    }

    # ── WALK-FORWARD per-trade (candidate) ──
    cand_is_exp = m_cand["is_exp"]
    cand_oos_exp = m_cand["oos_exp"]
    wf = round(cand_oos_exp / cand_is_exp, 3) if cand_is_exp and cand_is_exp > 0 else None

    # ── QUARTER-BY-QUARTER: no quarter where candidate << current ──
    q_cur = m_cur["quarters"]
    q_cand = m_cand["quarters"]
    q_rows = []
    worse_quarters = []
    for q in sorted(set(q_cur) | set(q_cand)):
        ce = q_cur.get(q, {}).get("exp")
        de = q_cand.get(q, {}).get("exp")
        delta = round((de or 0) - (ce or 0), 2) if (ce is not None and de is not None) else None
        q_rows.append({"quarter": q, "current_exp": ce, "candidate_exp": de,
                       "delta": delta, "n_cur": q_cur.get(q, {}).get("n"),
                       "n_cand": q_cand.get(q, {}).get("n")})
        # "<<" = candidate materially worse than current in that quarter (> $10/tr worse)
        if delta is not None and delta < -10.0:
            worse_quarters.append({"quarter": q, "delta": delta})

    # ── GATES (OP-22) ──
    g_a = bool(cand_oos_exp is not None and cand_oos_exp > 0
               and cand_oos_exp > m_cur["oos_exp"])
    g_b = bool(wf is not None and wf >= WF_GATE)
    g_c = bool(len(worse_quarters) == 0)
    # anchor: candidate edge_capture >= current (no regression); vacuous handled
    ec_cur, ec_cand = anc_cur.get("edge_capture"), anc_cand.get("edge_capture")
    if ec_cur is None and ec_cand is None:
        g_d, anchor_note = True, "vacuous (no anchor-date signals in family)"
    elif ec_cur is None or ec_cand is None:
        g_d, anchor_note = False, "anchor coverage differs between cells"
    else:
        g_d = bool(ec_cand >= ec_cur)
        anchor_note = f"candidate edge_capture {ec_cand} vs current {ec_cur}"
    g_e = bool(d3_cand["positive"])

    all_pass = bool(parity_ok and g_a and g_b and g_c and g_d and g_e)

    gates = {
        "parity": parity["PASS"],
        "a_oos_positive_and_beats_current": g_a,
        "b_walk_forward_ge_0.70": g_b,
        "c_quarters_stable_no_much_worse": g_c,
        "d_anchor_no_regression": g_d,
        "e_drop_top3_positive": g_e,
        "ALL_PASS": all_pass,
    }

    summary = {
        "family": "vwap_continuation",
        "analysis": "exit_param_OOS_ab_ship_gate",
        "run_date": dt.date.today().isoformat(),
        "window": f"{WINDOW[0]}..{WINDOW[1]}",
        "question": ("Does candidate exit -0.06/0.40 BEAT current live -0.08/0.30 OOS on the "
                     "ACTUAL live ATM Safe-2 cell, cleanly enough to ship?"),
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "strike_cell_validated": "ATM Safe-2 (strike_offset=0) = LIVE armed cell "
                                 "(j_vwap_cont_strike_offset_safe=0)",
        "c29_note": "ITM-2 tier is a DIFFERENT strike tier (unaffordable at Safe-2 $1.76K) "
                    "and is NOT validated here. Result does NOT transfer to ITM-2.",
        "n_common_trades": n,
        "coverage": {"current": cur_cov, "candidate": cand_cov,
                     "current_dropped": dropped[0], "candidate_dropped": dropped[1]},
        "current": {"cell": {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.30},
                    "metrics": m_cur, "anchor": anc_cur, "drop_top3": d3_cur},
        "candidate": {"cell": {"premium_stop_pct": -0.06, "tp1_premium_pct": 0.40},
                      "metrics": m_cand, "anchor": anc_cand, "drop_top3": d3_cand},
        "ab_table": {
            "full_exp": {"current": m_cur["exp_dollar"], "candidate": m_cand["exp_dollar"],
                         "delta": round(m_cand["exp_dollar"] - m_cur["exp_dollar"], 2)},
            "oos_exp": {"current": m_cur["oos_exp"], "candidate": cand_oos_exp,
                        "delta": round(cand_oos_exp - m_cur["oos_exp"], 2),
                        "current_oos_n": m_cur["oos_n"], "candidate_oos_n": m_cand["oos_n"]},
            "is_exp": {"current": m_cur["is_exp"], "candidate": cand_is_exp},
            "wf_candidate": wf,
            "quarters": q_rows,
            "worse_quarters": worse_quarters,
            "drop_top3_exp": {"current": d3_cur["exp_ex_topk"],
                              "candidate": d3_cand["exp_ex_topk"]},
            "anchor": {"current_ec": ec_cur, "candidate_ec": ec_cand, "note": anchor_note},
        },
        "parity_gate": parity,
        "gates": gates,
    }

    if not parity_ok:
        summary["verdict"] = (f"PARITY-FAIL: reproduced current-static full exp "
                              f"${m_cur['exp_dollar']} vs target ${PARITY_TARGET_FULL_EXP} "
                              f"(diff ${parity_diff} > tol ${PARITY_TOL}). STOP -- do not "
                              f"trust the A/B numbers.")
    elif all_pass:
        summary["verdict"] = (f"SHIP: candidate -0.06/0.40 clears ALL OP-22 gates on the live "
                              f"ATM Safe-2 cell. OOS ${cand_oos_exp} vs current "
                              f"${m_cur['oos_exp']} (+${round(cand_oos_exp - m_cur['oos_exp'],2)}"
                              f"/tr), WF={wf}, {len(worse_quarters)} much-worse quarters, "
                              f"anchor {ec_cand} vs {ec_cur}, drop3 ${d3_cand['exp_ex_topk']}. "
                              f"ATM only; ITM-2 unverified (C29).")
    else:
        fails = [k for k, v in gates.items() if k != "ALL_PASS" and not v]
        summary["verdict"] = (f"HOLD: candidate fails gate(s) {fails}. "
                              f"OOS cand ${cand_oos_exp} vs cur ${m_cur['oos_exp']}, WF={wf}, "
                              f"worse_quarters={worse_quarters}, drop3 "
                              f"${d3_cand['exp_ex_topk']}.")

    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[ab] wrote {OUT}", flush=True)

    print("\n=== PARITY GATE ===")
    print(f"  current full exp = ${m_cur['exp_dollar']}  target ${PARITY_TARGET_FULL_EXP}  "
          f"diff ${parity_diff}  PASS={parity_ok}")
    print("\n=== A/B TABLE (current -0.08/0.30  vs  candidate -0.06/0.40, ATM Safe-2) ===")
    print(f"  full exp:   current ${m_cur['exp_dollar']:>7}   candidate ${m_cand['exp_dollar']:>7}"
          f"   delta ${round(m_cand['exp_dollar']-m_cur['exp_dollar'],2)}")
    print(f"  OOS  exp:   current ${m_cur['oos_exp']:>7} (n={m_cur['oos_n']})   candidate "
          f"${cand_oos_exp:>7} (n={m_cand['oos_n']})   delta ${round(cand_oos_exp-m_cur['oos_exp'],2)}")
    print(f"  IS   exp:   current ${m_cur['is_exp']:>7}   candidate ${cand_is_exp:>7}")
    print(f"  WF (cand oos/is): {wf}")
    print(f"  drop-top3 exp: current ${d3_cur['exp_ex_topk']}   candidate ${d3_cand['exp_ex_topk']}")
    print(f"  anchor edge_capture: current {ec_cur}   candidate {ec_cand}  ({anchor_note})")
    print("  quarters (q: cur_exp -> cand_exp  delta):")
    for qr in q_rows:
        print(f"    {qr['quarter']}: {qr['current_exp']} -> {qr['candidate_exp']}  "
              f"delta {qr['delta']}  (n_cur={qr['n_cur']} n_cand={qr['n_cand']})")
    print(f"  much-worse quarters (< -$10/tr): {worse_quarters}")
    print("\n=== GATES ===")
    for k, v in gates.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"\nVERDICT: {summary['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
