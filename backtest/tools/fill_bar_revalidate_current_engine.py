"""RE-VALIDATE require_bearish_fill_bar under the CURRENT engine (2026-06-26).

The original ratification (fill-bar-gate-sweep.json, 2026-06-17) ran the OLD AGG
profile: generic strike (default ATM-ish), bracket-only exits (TP1 + runner_target
+ premium_stop), NO chandelier. The CURRENT engine for Bold is:
  - ITM-2 strike (strike_offset_itm=2 -> strike_offset=-2 in sim convention)
  - tight -7% bear premium cap (premium_stop_pct_bear=-0.07)
  - MANAGED exits: chandelier profit-lock arms +5% favor, trails 15% off HWM
    (v15.3 chart-stop-primary; -50% catastrophe cap)
  - REAL fills (simulator_real, the only WR authority per C1)

This re-runs the A/B (gate=False baseline vs gate=True candidate) under that
CURRENT profile, on the SAME IS/OOS split as the original, plus the anchor
source-of-truth check (OP-16). A gate that correctly removed losing OTM/bracket
bear trades may now remove WINNERS once the managed ITM exit lets them run.

Read-only except the JSON output. No Alpaca calls.
"""
from __future__ import annotations
import sys, json, datetime as dt, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-06-18.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"  # vix only used as regime gate input

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 18)

IS_SUBWINDOWS = [
    ("W1 Jan-Jun 2025", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2 Jul-Dec 2025", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3 Jan-Mar 2026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4 Apr-May 2026", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

# OP-16 source-of-truth. The fill-bar gate fires ONLY on bear (P) entries, so the
# 5/07 CALL losers are irrelevant to it; what matters is it must not suppress the
# bear winners (4/29, 5/01, 5/04 are all puts) and must keep skipping/limiting the
# bear losers (5/05, 5/06 are puts).
J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6)}

# CURRENT Bold/AGG engine profile (real fills, ITM-2, tight stop, MANAGED chandelier).
AGG_CURRENT_KW = dict(
    use_real_fills=True,
    strike_offset=-2,                       # ITM-2 (strike_offset_itm=2 -> -2 sim convention)
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.07,            # tight cap
    premium_stop_pct_bull=-0.05,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    # MANAGED exit stack (v15.3 chart-stop-primary): chandelier arms +5%, trails 15% off HWM.
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.05,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.15,
)
AGG_OVR = {"vix_bear_threshold": 15.0, "vix_bull_max": 30.0}


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    return (et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et).date()


def _run(spy_df, vix_df, start, end, gate):
    kw = dict(AGG_CURRENT_KW)
    kw["require_bearish_fill_bar"] = gate
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end,
                        params_overrides=dict(AGG_OVR), **kw)


def _bear(trades):
    return [t for t in trades if t.side == "P"]


def _stats(trades):
    ts = list(trades)
    if not ts:
        return {"n": 0, "wr": 0.0, "total": 0.0, "avg": 0.0}
    pnls = [t.dollar_pnl for t in ts]
    return {
        "n": len(ts),
        "wr": round(sum(p > 0 for p in pnls) / len(ts), 3),
        "total": round(sum(pnls), 1),
        "avg": round(sum(pnls) / len(ts), 1),
    }


def _anchor_detail(base_trades, cand_trades):
    base_by, cand_by = {}, {}
    for t in base_trades:
        base_by.setdefault(_date(t), 0.0)
        base_by[_date(t)] += t.dollar_pnl
    for t in cand_trades:
        cand_by.setdefault(_date(t), 0.0)
        cand_by[_date(t)] += t.dollar_pnl
    rows, regressions = [], []
    for d in sorted(J_WINNERS | J_LOSERS):
        b, c = base_by.get(d, 0.0), cand_by.get(d, 0.0)
        kind = "WINNER" if d in J_WINNERS else "LOSER"
        # Winner regression = candidate captures meaningfully less. Loser regression =
        # candidate loses meaningfully more (gate should skip/limit losers, not worsen).
        regressed = (d in J_WINNERS and c < b - 50) or (d in J_LOSERS and c < b - 50)
        rows.append({"date": str(d), "kind": kind, "base": round(b, 1), "cand": round(c, 1),
                     "regressed": regressed})
        if regressed:
            regressions.append(rows[-1])
    return rows, (len(regressions) == 0)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running BASELINE (gate=False) IS...")
    b_is = _run(spy_df, vix_df, IS_START, IS_END, gate=False)
    print("Running BASELINE (gate=False) OOS...")
    b_oos = _run(spy_df, vix_df, OOS_START, OOS_END, gate=False)
    print("Running CANDIDATE (gate=True) IS...")
    c_is = _run(spy_df, vix_df, IS_START, IS_END, gate=True)
    print("Running CANDIDATE (gate=True) OOS...")
    c_oos = _run(spy_df, vix_df, OOS_START, OOS_END, gate=True)

    # Whole-population (all sides) and bear-only (the population the gate actually touches).
    b_is_all, c_is_all = _stats(b_is.trades), _stats(c_is.trades)
    b_oos_all, c_oos_all = _stats(b_oos.trades), _stats(c_oos.trades)
    b_is_bear, c_is_bear = _stats(_bear(b_is.trades)), _stats(_bear(c_is.trades))
    b_oos_bear, c_oos_bear = _stats(_bear(b_oos.trades)), _stats(_bear(c_oos.trades))

    is_delta = round(c_is_all["total"] - b_is_all["total"], 1)
    oos_delta = round(c_oos_all["total"] - b_oos_all["total"], 1)
    n_is, n_oos = b_is_all["n"], b_oos_all["n"]
    wf_norm = ((oos_delta / n_oos) / (is_delta / n_is)) if (is_delta != 0 and n_oos) else 0.0

    print("\nIS sub-window breakdown (gate ON vs OFF):")
    sw_hurt = 0
    sw_rows = []
    for lbl, s, e in IS_SUBWINDOWS:
        b = _pnl(_run(spy_df, vix_df, s, e, gate=False).trades)
        c = _pnl(_run(spy_df, vix_df, s, e, gate=True).trades)
        d = c - b
        hurt = d < -500
        if hurt:
            sw_hurt += 1
        sw_rows.append({"window": lbl, "base": round(b, 1), "cand": round(c, 1),
                        "delta": round(d, 1), "hurt": hurt})
        print(f"  {lbl}: base={b:+,.0f} cand={c:+,.0f} delta={d:+,.0f}{' <-- HURT' if hurt else ''}")

    # OP-16 anchor days (4/29-5/06) fall in the IS window (IS_END=5/07), NOT OOS.
    # Check them in the IS run where the engine actually trades them.
    anchor_rows, anchor_ok = _anchor_detail(b_is.trades, c_is.trades)

    # OP-22 gates: G1 IS_delta>=0, G2 OOS_delta>0, G3 WF>=0.70, G4 SW_hurt<=1, G5 anchor.
    g1 = is_delta >= 0
    g2 = oos_delta > 0
    g3 = wf_norm >= 0.70
    g4 = sw_hurt <= 1
    g5 = anchor_ok
    keep_justified = g1 and g2 and g3 and g4 and g5

    print("\n" + "=" * 72)
    print("CURRENT-ENGINE RE-VALIDATION (real fills, ITM-2, tight stop, chandelier)")
    print("=" * 72)
    print(f"ALL  IS  base n={b_is_all['n']:3} WR={b_is_all['wr']:.1%} ${b_is_all['total']:+,.0f}"
          f"  | cand n={c_is_all['n']:3} WR={c_is_all['wr']:.1%} ${c_is_all['total']:+,.0f}")
    print(f"ALL  OOS base n={b_oos_all['n']:3} WR={b_oos_all['wr']:.1%} ${b_oos_all['total']:+,.0f}"
          f"  | cand n={c_oos_all['n']:3} WR={c_oos_all['wr']:.1%} ${c_oos_all['total']:+,.0f}")
    print(f"BEAR IS  base n={b_is_bear['n']:3} WR={b_is_bear['wr']:.1%} ${b_is_bear['total']:+,.0f}"
          f"  | cand n={c_is_bear['n']:3} WR={c_is_bear['wr']:.1%} ${c_is_bear['total']:+,.0f}")
    print(f"BEAR OOS base n={b_oos_bear['n']:3} WR={b_oos_bear['wr']:.1%} ${b_oos_bear['total']:+,.0f}"
          f"  | cand n={c_oos_bear['n']:3} WR={c_oos_bear['wr']:.1%} ${c_oos_bear['total']:+,.0f}")
    print(f"\nIS_delta={is_delta:+,.0f}  OOS_delta={oos_delta:+,.0f}  WF={wf_norm:.3f}  SW_hurt={sw_hurt}")
    print(f"Gates: G1(IS>=0)={g1} G2(OOS>0)={g2} G3(WF>=.70)={g3} G4(SW<=1)={g4} G5(anchor)={g5}")
    print(f"\nAnchor source-of-truth (OOS, bear days):")
    for r in anchor_rows:
        print(f"  {r['date']} {r['kind']:6} base={r['base']:+.0f} cand={r['cand']:+.0f}"
              f"{'  REGRESSION' if r['regressed'] else ''}")
    print(f"\nKEEP still justified (all 5 gates): {keep_justified}")
    verdict = "KEEP" if keep_justified else "UNBLOCK"
    print(f"VERDICT: {verdict}")

    out = {
        "study": "require_bearish_fill_bar RE-VALIDATION under CURRENT engine",
        "date": "2026-06-26",
        "account": "bold/aggressive",
        "engine_profile": "real_fills + ITM-2 + premium_stop_bear=-0.07 + chandelier(arm+5%,trail15%) + managed exits",
        "window": {"IS": [str(IS_START), str(IS_END)], "OOS": [str(OOS_START), str(OOS_END)]},
        "baseline_gate_off": {
            "IS_all": b_is_all, "OOS_all": b_oos_all, "IS_bear": b_is_bear, "OOS_bear": b_oos_bear},
        "candidate_gate_on": {
            "IS_all": c_is_all, "OOS_all": c_oos_all, "IS_bear": c_is_bear, "OOS_bear": c_oos_bear},
        "IS_delta": is_delta, "OOS_delta": oos_delta, "WF_norm": round(wf_norm, 3),
        "SW_hurt": sw_hurt, "subwindows": sw_rows,
        "anchor_rows": anchor_rows, "anchor_ok": anchor_ok,
        "gates": {"G1_IS_delta_ge_0": g1, "G2_OOS_delta_gt_0": g2,
                  "G3_WF_ge_070": g3, "G4_SW_hurt_le_1": g4, "G5_anchor": g5},
        "keep_justified": keep_justified,
        "verdict": verdict,
        "note": ("Original ratification (2026-06-17) ran OLD bracket-only profile. This re-run "
                 "applies the CURRENT managed-exit ITM-2 profile. Gate fires only on bear (P) "
                 "entries; OP-16 anchor check confirms it does not suppress the bear winners."),
    }
    out_path = ROOT / "analysis" / "recommendations" / "fill-bar-gate-revalidate-current-engine.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return out


if __name__ == "__main__":
    main()
