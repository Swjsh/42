"""PART C — validate J's better-ENTRY rules on OUR 2025-26 SPY real-fills data.

J's entry-quality analysis (webull_entry_quality.py, his 2021-23 Webull trades)
found the entry-read features that separate his GOOD-thesis entries from his
BAD-thesis ones. The #1 discriminator was CONFIRMED-CLOSE (enter only after a 5m
bar that closes in the thesis direction), #2 was VWAP-ALIGNMENT.

This module checks whether those rules transfer to OUR engine on OUR data
(SPY 0DTE, real OPRA fills, 2025-01..2026-06), through the SAME orchestrator gate
framework used for every ratified gate (entry_bar_direction_gate.py):
  OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1 AND anchor_no_regression.

The Safe BEAR-side confirmed-close gate (entry_bar_body_pct_min=0.20) is ALREADY
LIVE (analysis/recommendations/safe_entry_body_gate.json, ratified 2026-06-18,
WF=7.19). So this harness focuses on the NET-NEW contribution the J data implies:

  C1. BULL-side confirmed-close extension  (entry_bar_body_pct_min_bull=0.20)
      — J's data shows confirmed_close helps BOTH sides; the live gate is bear-only.
  C2. Confirmed-close on BOTH sides together (the full J timing rule).

Each candidate is run vs the production Safe baseline. Pure orchestrator A/B.
Propose-only — writes a scorecard; flips nothing live. py_compile clean.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/j_entry_quality_validate.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"
OUT = ROOT / "analysis" / "recommendations" / "j-entry-quality.json"

IS_START, IS_END = dt.date(2025, 1, 2), dt.date(2026, 5, 7)
OOS_START, OOS_END = dt.date(2026, 5, 8), dt.date(2026, 6, 16)

ANCHOR_WINNERS = {dt.date(2025, 4, 29), dt.date(2025, 5, 1), dt.date(2025, 5, 4)}
ANCHOR_LOSERS = {dt.date(2025, 5, 5), dt.date(2025, 5, 6), dt.date(2025, 5, 7)}
ANCHOR_DATES = sorted(ANCHOR_WINNERS | ANCHOR_LOSERS)

SUBWINDOWS = [
    ("SW1_2025H1", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
    ("SW2_2025H2", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
    ("SW3_early26", dt.date(2026, 1, 2), dt.date(2026, 5, 7)),
]

# Production Safe baseline (matches the live book used by the ratified bear gate).
SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

# The Safe baseline ALREADY runs with the live bear confirmed-close gate on.
LIVE_BEAR_GATE = dict(entry_bar_body_pct_min=0.20)


def _run(spy, vix, start, end, **overrides):
    res = run_backtest(spy, vix, start_date=start, end_date=end,
                       **{**SAFE_BASE, **overrides})
    trades = res.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    wr = sum(1 for t in trades if t.dollar_pnl > 0) / n if n else 0.0
    return {"n": n, "pnl": round(pnl, 0), "wr": round(wr, 4), "trades": trades}


def _wf(is_delta, n_is_removed, oos_delta, n_oos_removed):
    """Per-removed-trade walk-forward: (oos_delta/oos_removed)/(is_delta/is_removed)."""
    if not (n_is_removed and n_oos_removed and is_delta):
        return float("nan")
    return (oos_delta / n_oos_removed) / (is_delta / n_is_removed)


def _anchor(base_trades, cand_trades):
    def by_date(ts):
        d: dict[Any, float] = {}
        for t in ts:
            d[t.entry_time_et.date()] = d.get(t.entry_time_et.date(), 0.0) + t.dollar_pnl
        return d
    b, c = by_date(base_trades), by_date(cand_trades)
    rows = []
    regression = False
    for date in ANCHOR_DATES:
        bp, cp = b.get(date, 0.0), c.get(date, 0.0)
        delta = cp - bp
        kind = "W" if date in ANCHOR_WINNERS else "L"
        hurt = date in ANCHOR_WINNERS and cp < bp and abs(delta) > 50
        if hurt:
            regression = True
        rows.append({"date": str(date), "kind": kind,
                     "base": round(bp, 0), "cand": round(cp, 0),
                     "delta": round(delta, 0), "regression": hurt})
    return rows, (not regression)


def _evaluate(name, desc, spy, vix, cand_overrides) -> dict[str, Any]:
    """Full IS/OOS/SW/anchor A/B for one candidate vs the live-baseline."""
    base_is = _run(spy, vix, IS_START, IS_END, **LIVE_BEAR_GATE)
    cand_is = _run(spy, vix, IS_START, IS_END, **LIVE_BEAR_GATE, **cand_overrides)
    base_oos = _run(spy, vix, OOS_START, OOS_END, **LIVE_BEAR_GATE)
    cand_oos = _run(spy, vix, OOS_START, OOS_END, **LIVE_BEAR_GATE, **cand_overrides)

    is_delta = cand_is["pnl"] - base_is["pnl"]
    oos_delta = cand_oos["pnl"] - base_oos["pnl"]
    is_removed = base_is["n"] - cand_is["n"]
    oos_removed = base_oos["n"] - cand_oos["n"]
    wf = _wf(is_delta, is_removed, oos_delta, oos_removed)

    sw_rows = []
    sw_hurt = 0
    for wn, ws, we in SUBWINDOWS:
        b = _run(spy, vix, ws, we, **LIVE_BEAR_GATE)
        c = _run(spy, vix, ws, we, **LIVE_BEAR_GATE, **cand_overrides)
        d = c["pnl"] - b["pnl"]
        hurt = d < -50
        if hurt:
            sw_hurt += 1
        sw_rows.append({"window": wn, "base": b["pnl"], "cand": c["pnl"],
                        "delta": round(d, 0), "hurt": hurt})

    anchor_rows, anchor_ok = _anchor(base_is["trades"], cand_is["trades"])

    g1 = is_delta > 0
    g2 = oos_delta > 0
    g3 = (wf == wf) and wf >= 0.70
    g4 = sw_hurt <= 1
    g5 = anchor_ok
    all_pass = g1 and g2 and g3 and g4 and g5
    verdict = "SHIP" if all_pass else ("PROPOSE" if (g2 and g4 and g5) else "WATCH")

    return {
        "name": name,
        "description": desc,
        "overrides": {k: (str(v) if isinstance(v, dt.time) else v)
                      for k, v in cand_overrides.items()},
        "is_baseline": {"n": base_is["n"], "pnl": base_is["pnl"], "wr": base_is["wr"]},
        "is_candidate": {"n": cand_is["n"], "pnl": cand_is["pnl"], "wr": cand_is["wr"]},
        "is_n_removed": is_removed,
        "is_delta": round(is_delta, 0),
        "oos_baseline": {"n": base_oos["n"], "pnl": base_oos["pnl"], "wr": base_oos["wr"]},
        "oos_candidate": {"n": cand_oos["n"], "pnl": cand_oos["pnl"], "wr": cand_oos["wr"]},
        "oos_n_removed": oos_removed,
        "oos_delta": round(oos_delta, 0),
        "wf_per_removed_trade": round(wf, 3) if wf == wf else None,
        "sw_rows": sw_rows,
        "sw_hurt": sw_hurt,
        "anchor_rows": anchor_rows,
        "anchor_ok": anchor_ok,
        "gates": {"G1_is_pos": g1, "G2_oos_pos": g2, "G3_wf_ge_0.70": g3,
                  "G4_sw_hurt_le_1": g4, "G5_anchor_ok": g5, "all_pass": all_pass},
        "verdict": verdict,
    }


def main() -> int:
    print("Loading OUR 2025-26 SPY/VIX data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows  VIX {len(vix)} rows")

    candidates = [
        ("C1_bull_confirmed_close",
         "Extend J's confirmed-close timing rule to the BULL side "
         "(entry_bar_body_pct_min_bull=0.20). Bear side already live & ratified.",
         dict(entry_bar_body_pct_min_bull=0.20)),
        ("C2_both_sides_confirmed_close",
         "J's confirmed-close on BOTH sides at once (bear 0.20 already live + bull 0.20).",
         dict(entry_bar_body_pct_min_bull=0.20)),  # bear already in LIVE_BEAR_GATE
    ]

    results = []
    for name, desc, ov in candidates:
        print(f"\n=== {name} ===")
        r = _evaluate(name, desc, spy, vix, ov)
        results.append(r)
        print(f"  IS:  base n={r['is_baseline']['n']} ${r['is_baseline']['pnl']:+.0f}"
              f" -> cand n={r['is_candidate']['n']} ${r['is_candidate']['pnl']:+.0f}"
              f"  (delta ${r['is_delta']:+.0f}, removed {r['is_n_removed']})")
        print(f"  OOS: base n={r['oos_baseline']['n']} ${r['oos_baseline']['pnl']:+.0f}"
              f" -> cand n={r['oos_candidate']['n']} ${r['oos_candidate']['pnl']:+.0f}"
              f"  (delta ${r['oos_delta']:+.0f}, removed {r['oos_n_removed']})")
        print(f"  WF={r['wf_per_removed_trade']}  SW_hurt={r['sw_hurt']}/3  "
              f"anchor_ok={r['anchor_ok']}  -> {r['verdict']}")

    payload = {
        "_generated": dt.datetime.now().isoformat(timespec="seconds"),
        "_what": "PART C — J's better-ENTRY rules validated on OUR 2025-26 SPY real-fills",
        "_method": "Orchestrator IS/OOS/SW/anchor A/B vs production Safe baseline "
                   "(which already includes the live bear confirmed-close gate). "
                   "Gate: OOS+ AND WF>=0.70 AND SW_hurt<=1 AND anchor-no-regression.",
        "_data": {"spy": MASTER_SPY.name, "is": [str(IS_START), str(IS_END)],
                  "oos": [str(OOS_START), str(OOS_END)]},
        "_cross_reference": {
            "bear_confirmed_close_ALREADY_LIVE": "analysis/recommendations/safe_entry_body_gate.json "
            "(RATIFY 2026-06-18, WF=7.19) — J's #1 entry discriminator, already shipped on Safe.",
            "aggressive_entry_body_REJECTED": "analysis/recommendations/agg_entry_body_gate.json "
            "(REJECT, IS delta negative) — does NOT transfer to the Bold/ITM book (L29).",
            "j_source_analysis": "analysis/webull-j-trades/entry_quality.json",
        },
        "candidates": results,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
