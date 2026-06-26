"""SELECTION test: vwap_continuation through the FULL mandatory gate stack + fraud gates.

THESIS UNDER TEST (the user's brief): mechanical daily signals are coin-flips (WR 30-38%,
no raw entry edge) -- ~32 strategies died on both 0DTE options AND futures. The ONE
survivor (vwap_continuation) is SELECTIVE. The thesis: SELECTION/CONFLUENCE is the edge --
requiring multiple independent confirmations before entry converts a coin-flip into an edge.

This script tests that honestly for the SELECTIVE survivor. It re-uses the VALIDATED
``_edgehunt_vwap_continuation.detect_signals`` detector (byte-for-byte the live
vwap_continuation_watcher port), re-simulates the SURVIVOR STRUCTURE on real OPRA fills
(strike_offset=-2 ITM-2, premium_stop_pct=-0.08, v15 exits), and applies EVERY mandatory
gate deterministically -- anti-pattern 2.10 (no cherry-picking), all gates in-script:

  GATE_OOS    : OOS(2026) per-trade > 0
  GATE_IS     : IN-SAMPLE(2025) per-trade > 0      (reject IS-neg/OOS-pos single-regime
                                                     artifacts -- the futures trap)
  GATE_Q      : positive_quarters >= 4/6
  GATE_CONC   : top5-day < 200%  AND  drop-top-5-days per-trade > 0
  GATE_N      : n >= 20
  GATE_NULL   : beats a RANDOM-entry null (same exit/stop/strike/side-mix, 20 seeds) --
                beat the null MAX AND drop-top5 beats the null MEAN  (null_baseline.py/L172)
  GATE_TRUNC  : sign does NOT invert at chart-stop-only (-0.99)  (truncation_guard.py/L171)

The last two are the GRADUATED fraud gates this campaign wired into the verify harness
(autoresearch.fraud_gates). A candidate is a SELECTION_EDGE only if ALL gates hold.

Real-fills authority (C1): lib.simulator_real.simulate_trade_real. Pure Python, $0. No
live orders. Markets closed.

Writes analysis/recommendations/sel-vwap-continuation.json.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sel_vwap_continuation.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # backtest/
ROOT = REPO.parent                            # repo root (42/)
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _align_vix,
    _normalize_spy,
    detect_signals,
)
from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike,
    _strike_from_spot,
    build_day_contexts,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402

SLUG = "vwap-continuation"
OUT = ROOT / "analysis" / "recommendations" / f"sel-{SLUG}.json"

# ── SURVIVOR STRUCTURE (the user's brief: use as primary) ──────────────────────
STRIKE_OFFSET = -2            # ITM-2
PREMIUM_STOP_PCT = -0.08      # v15 asymmetric tight stop
QTY = 3                       # 2 TP + 1 runner
MAX_STRIKE_STEPS = 4          # nearest-cached snap radius (matches the edge-hunt path)
SETUP = "SEL_VWAP_CONTINUATION"
OOS_YEAR = 2026
NULL_SEEDS = 20

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# ── Mandatory gate bars ────────────────────────────────────────────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0


def _quarter(day: str) -> str:
    y, m, _ = day.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _per_trade(rows):
    return round(float(np.mean([r["pnl"] for r in rows])), 2) if rows else None


def _drop_top5_per_trade(rows):
    """Per-trade after removing the 5 best P&L DAYS (concentration robustness)."""
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r["pnl"])
    if not by_day:
        return None
    day_tot = {d: sum(v) for d, v in by_day.items()}
    top5 = set(d for d, _ in sorted(day_tot.items(), key=lambda kv: kv[1], reverse=True)[:5])
    kept = [p for d, v in by_day.items() if d not in top5 for p in v]
    return round(float(np.mean(kept)), 2) if kept else None


def _top5_day_pct(rows):
    by_day = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    total = sum(by_day.values())
    if total <= 0:
        return None
    top5 = sum(sorted(by_day.values(), reverse=True)[:5])
    return round(100 * top5 / total, 1)


def main() -> int:
    print(f"[sel] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)

    # RTH-only reset-index frame for the fraud-gate re-sim (random null draws from it).
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] < dt.time(16, 0))].reset_index(drop=True)

    # ── SELECTION detector: the validated vwap-continuation signals (full pattern) ──
    signals = detect_signals(days, vix, breakout_only=False, put_needs_rising_vix=False)
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals})
    print(f"[sel] vwap_continuation signals={len(signals)} on {sig_days} days "
          f"({round(100*sig_days/n_days,1)}% of {n_days}) side={side_ct}", flush=True)

    # ── Re-simulate the SURVIVOR STRUCTURE on real OPRA fills ──────────────────
    rows = []
    n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - STRIKE_OFFSET if sg.side == "P" else atm + STRIKE_OFFSET
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=None,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "vwap_cont"],
            side=sg.side, qty=QTY, setup=SETUP, strike_override=strike,
            entry_vix=entry_vix, premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        rows.append({"date": str(d), "side": sg.side, "pnl": round(float(fill.dollar_pnl), 2),
                     "exit": fill.exit_reason.name if fill.exit_reason else "NONE"})

    n = len(rows)
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]
    by_q = defaultdict(list)
    for r in rows:
        by_q[_quarter(r["date"])].append(r["pnl"])
    quarters = {q: {"n": len(v), "per_trade": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    pos_q = sum(1 for v in quarters.values() if v["per_trade"] > 0)

    overall_pt = _per_trade(rows)
    is_pt = _per_trade(is_rows)
    oos_pt = _per_trade(oos_rows)
    drop_top5_pt = _drop_top5_per_trade(rows)
    top5 = _top5_day_pct(rows)

    # ── FRAUD GATES via the graduated harness (per-trade re-simulation) ────────
    cand_signals = [CandidateSignal(bar_idx=int(rth.index[rth["timestamp_et"] == spy.iloc[s.bar_idx]["timestamp_et"]][0]),
                                    side=s.side, rejection_level=float(s.stop_level),
                                    note=s.note or "vwap_cont")
                    for s in signals
                    if (rth["timestamp_et"] == spy.iloc[s.bar_idx]["timestamp_et"]).any()]
    print(f"[sel] running fraud gates (re-sim chosen + chart-stop-only + {NULL_SEEDS}-seed null) ...",
          flush=True)
    fraud = verify_candidate(
        cand_signals, rth, strike_offset=STRIKE_OFFSET, premium_stop_pct=PREMIUM_STOP_PCT,
        qty=QTY, setup=SETUP, seeds=NULL_SEEDS)

    # ── ALL MANDATORY GATES (deterministic, in-script) ─────────────────────────
    gates = {
        "GATE_OOS_pt_gt0": bool(oos_pt is not None and oos_pt > 0),
        "GATE_IS_pt_gt0": bool(is_pt is not None and is_pt > 0),
        "GATE_pos_quarters_ge4of6": bool(pos_q >= BAR_POS_Q and len(quarters) >= 6),
        "GATE_top5_day_lt200": bool(top5 is not None and top5 < BAR_TOP5),
        "GATE_drop_top5_pt_gt0": bool(drop_top5_pt is not None and drop_top5_pt > 0),
        "GATE_n_ge20": bool(n >= BAR_N),
        "GATE_beats_random_null": bool(fraud.null_pass),
        "GATE_no_truncation": bool(fraud.no_truncation_pass),
    }
    fails = [k for k, v in gates.items() if not v]
    selection_edge = len(fails) == 0

    summary = {
        "slug": SLUG,
        "thesis": ("SELECTION/CONFLUENCE is the edge -- a SELECTIVE detector (vwap_continuation, "
                   "the sole survivor of ~32 mechanical-daily-signal strategies) converts the "
                   "0DTE coin-flip into a per-trade option edge. Tested honestly; may also fail."),
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_days,
        "detector": ("VALIDATED _edgehunt_vwap_continuation.detect_signals (byte-for-byte the live "
                     "vwap_continuation_watcher port): first 3 RTH closes same-side of as-of VWAP "
                     "= day side; first in-trend continuation (breakout or shallow VWAP-ward dip) "
                     "= entry; one causal entry/day, next-bar-open fill, no look-ahead"),
        "structure": {"strike_offset": STRIKE_OFFSET, "strike_tier": "ITM-2",
                      "premium_stop_pct": PREMIUM_STOP_PCT, "qty": QTY, "exits": "v15"},
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "signals": {"n": len(signals), "on_days": sig_days,
                    "fire_day_pct": round(100 * sig_days / n_days, 1), "side": side_ct},
        "coverage": {"signals": len(signals), "filled": n,
                     "cache_miss": n_cache_miss, "sim_none": n_sim_none,
                     "fill_rate": round(n / len(signals), 3) if signals else 0.0},
        "metrics": {
            "n": n,
            "overall_per_trade": overall_pt,
            "is_n": len(is_rows), "is_per_trade": is_pt,
            "oos_n": len(oos_rows), "oos_per_trade": oos_pt,
            "drop_top5_per_trade": drop_top5_pt,
            "top5_day_pct": top5,
            "positive_quarters": f"{pos_q}/{len(quarters)}",
            "quarters": quarters,
            "wr_pct": round(100 * sum(1 for r in rows if r["pnl"] > 0) / n, 1) if n else None,
            "exit_hist": {k: sum(1 for r in rows if r["exit"] == k)
                          for k in sorted({r["exit"] for r in rows})},
        },
        "fraud_gates": fraud.as_dict(),
        "gates": gates,
        "fails": fails,
        "selection_edge": selection_edge,
        "verdict": ("SELECTION_EDGE: all mandatory gates hold (incl. both graduated fraud gates) "
                    "-> selection/confluence converts the coin-flip into a real per-trade option edge"
                    if selection_edge else
                    f"NOT A SELECTION_EDGE: fails {fails}"),
        "DISCLOSURE": {
            "per_trade": "expectancy reported, not WR alone (OP-14)",
            "is_oos": "IS=2025 AND OOS=2026 BOTH required positive (rejects single-regime artifacts)",
            "concentration": "top5_day_pct + drop-top-5-days per-trade (OP-20 #5)",
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58)",
            "fraud_gates": ("random-entry-null (L172) AND no-truncation (L171) -- the two "
                            "discriminators that caught RSI2/IBS/ema_adx after the naive 5-gate bar"),
            "no_cherry_pick": "single fixed structure (ITM-2/-8%/v15); no grid survivor-pick (2.10)",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[sel] wrote {OUT}", flush=True)

    print("\n=== SELECTION VERDICT (vwap_continuation) ===")
    print(f"signals={len(signals)} filled={n}  WR={summary['metrics']['wr_pct']}%")
    print(f"per-trade: overall=${overall_pt}  IS=${is_pt}  OOS=${oos_pt}  drop-top5=${drop_top5_pt}")
    print(f"posQ={pos_q}/{len(quarters)}  top5_day%={top5}")
    print(f"NULL: chosen=${fraud.chosen_per_trade}/tr  null_max=${fraud.null.get('per_trade_max')}  "
          f"null_mean=${fraud.null.get('per_trade_mean')}  -> null_pass={fraud.null_pass}")
    print(f"TRUNC: chart-stop-only=${fraud.chart_stop_only_per_trade}/tr  "
          f"-> no_truncation_pass={fraud.no_truncation_pass}")
    print(f"GATES: {gates}")
    print(f"VERDICT: {summary['verdict']}")
    return 0 if selection_edge else 1


if __name__ == "__main__":
    sys.exit(main())
