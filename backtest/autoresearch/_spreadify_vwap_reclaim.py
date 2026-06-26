"""SPREAD-IFY edge #2 (vwap_reclaim_failed_break): debit-spread A/B vs long-single-leg.

THESIS (recency-drawdown rescue): the live edges bleed in the chop regime because a
-8% premium stop whipsaws a LONG single-leg call/put. A DIRECTIONAL DEBIT SPREAD
(buy near + sell further-OTM, same side, same SIGNAL) caps premium-at-risk, cuts
theta/vega, reduces the whipsaw -- at the cost of CAPPED upside (lower per-trade EV).
The hunted win is RISK-ADJUSTED (lower variance/maxDD) + reduced recency bleed while
staying expectancy-positive.

WHAT THIS DOES
  * Detector: BYTE-FOR-BYTE the validated #2 detector
    (_sub_struct_vwap_reclaim_failed_break.detect_signals) -- one causal entry/day.
  * Baseline (long_single_leg): each signal at strike_offset in {ATM=0, ITM-2=-2},
    -8% premium stop, v15 default exits, via lib.simulator_real.simulate_trade_real
    (the SAME real-fills path the live edge uses).
  * Debit spread: long-strike offset {ATM=0, ITM-1=-1, ITM-2=-2} x short-leg width
    {2,3,4 further OTM} (all fit the +/-$5 OPRA cache band, near-ATM), via
    lib.simulator_debit.simulate_debit_trade on real OPRA fills. The edge's stop/TP map
    to the SPREAD net debit: premium_stop -8% -> stop_frac=0.08 of debit; tp1=0.30 ->
    pt_frac=0.30 of debit. Same time stop (15:50 ET).
  * For the BEST cell + the whole grid: report FULL-OOS-2026 AND the recent ~25
    trading-day window (the chop/RED regime): expectancy/tr, n, WR, book maxDD,
    per-trade Sharpe, Sortino, and DELTAS vs the long-single-leg baseline.

GATE (debit-spread refinement of an existing edge):
  (1) expectancy/tr still > 0 (capped but positive)
  (2) L175 RISK-ADJUSTED bar: per-trade Sharpe holds/improves AND book Sortino holds
      AND maxDD MATERIALLY BETTER
  (3) RECENCY: reduces/flips the recent ~25-day RED bleed vs the long-single-leg baseline
  (4) no-regression (days it changes net-improve)
  (5) OOS-positive + posQ

Pure Python, $0. No live orders. Markets closed.
Writes analysis/recommendations/spreadify-vwap_reclaim.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_spreadify_vwap_reclaim.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
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
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    MAX_STRIKE_STEPS,
    QTY,
    OOS_YEAR,
)
# #2 detector — reused byte-for-byte (no edit to the watcher/detector).
from autoresearch._sub_struct_vwap_reclaim_failed_break import detect_signals  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.simulator_debit import build_debit_vertical, simulate_debit_trade  # noqa: E402

OUT = ROOT / "analysis" / "recommendations" / "spreadify-vwap_reclaim.json"

# ── Config ──────────────────────────────────────────────────────────────────
SURV_PREMIUM_STOP = -0.08      # the live edge's -8% premium stop (single-leg)
SPREAD_STOP_FRAC = 0.08        # -8% of the spread net debit (same rule, spread basis)
SPREAD_PT_FRAC = 0.30          # +30% of debit = the edge's tp1=0.30 mapped to the spread
RECENT_WINDOW_DAYS = 25        # the "chop/RED regime" recent trading-day window

# Baseline single-leg strike tiers (ATM = Safe-2; ITM-2 = Bold survivor structure)
BASELINE_OFFSETS = [(0, "ATM"), (-2, "ITM2")]
# Debit-spread geometry sweep
LONG_OFFSETS = [(0, "ATM"), (-1, "ITM1"), (-2, "ITM2")]   # near (long) leg offset
SHORT_WIDTHS = [2, 3, 4]                                   # short leg $ further OTM


@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    exit_reason: str


# ─────────────────────────────────────────────────────────────────────────────
# Sim a signal set — long-single-leg baseline (simulate_trade_real)
# ─────────────────────────────────────────────────────────────────────────────
def simulate_single_leg(signals, spy, ribbon, vix, *, strike_offset, premium_stop_pct
                        ) -> tuple[list[TradeRow], dict]:
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_cache_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="VWAP_RECLAIM_BASE", strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
        )
        if fill is None or fill.dollar_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(date=str(d), side=sg.side,
                             pnl=round(float(fill.dollar_pnl), 2),
                             exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE"))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# Sim a signal set — DEBIT SPREAD (simulate_debit_trade)
# ─────────────────────────────────────────────────────────────────────────────
def simulate_spread(signals, spy, *, long_offset, short_width) -> tuple[list[TradeRow], dict]:
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_cache_miss = n_sim_none = n_skip = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        legs = build_debit_vertical(spot, sg.side, near_offset=long_offset, width=short_width)
        # Band pre-check: snap each leg's strike to nearest cached; SKIP if either misses.
        ok = True
        snapped = []
        for leg in legs:
            sk = _nearest_cached_strike(d, leg.strike, leg.side, MAX_STRIKE_STEPS)
            if sk is None:
                ok = False
                break
            snapped.append((sk, leg.side, leg.qty_sign))
        if not ok:
            n_cache_miss += 1
            continue
        from lib.multileg_structures import Leg
        legs2 = [Leg(sk, side, qs) for sk, side, qs in snapped]
        # After snapping, the long+short could collapse to the same strike -> degenerate; skip.
        if legs2[0].strike == legs2[1].strike:
            n_skip += 1
            continue
        decision_ts = pd.Timestamp(bar["timestamp_et"]).to_pydatetime()
        fill = simulate_debit_trade(
            date=d, legs=legs2, entry_time_et=decision_ts, spot=spot,
            width=short_width, structure_name="VWAP_RECLAIM_DEBIT",
            contracts=QTY, pt_frac=SPREAD_PT_FRAC, stop_frac=SPREAD_STOP_FRAC,
        )
        if fill.skipped:
            n_skip += 1
            continue
        if fill.realized_pnl is None:
            n_sim_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(date=str(d), side=sg.side,
                             pnl=round(float(fill.realized_pnl), 2),
                             exit_reason=str(fill.exit_reason)))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_cache_miss,
           "sim_none": n_sim_none, "skip": n_skip,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS — book maxDD, per-trade Sharpe, Sortino, expectancy, WR
# ─────────────────────────────────────────────────────────────────────────────
def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _book_maxdd(rows: list[TradeRow]) -> float:
    """Max drawdown ($) of the cumulative-equity curve of per-trade P&L, time-ordered.

    Trades sorted by date then original sequence. Returns a POSITIVE drawdown magnitude
    (0 if the curve never draws down)."""
    if not rows:
        return 0.0
    ordered = sorted(rows, key=lambda r: r.date)
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for r in ordered:
        eq += r.pnl
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > maxdd:
            maxdd = dd
    return round(maxdd, 2)


def _sharpe(pnls: np.ndarray) -> Optional[float]:
    """Per-trade Sharpe = mean / std (not annualized — a per-trade risk-adjusted ratio)."""
    if len(pnls) < 2:
        return None
    sd = float(np.std(pnls, ddof=1))
    if sd == 0:
        return None
    return round(float(np.mean(pnls)) / sd, 4)


def _sortino(pnls: np.ndarray) -> Optional[float]:
    """Per-trade Sortino = mean / downside-deviation (std of negative returns only)."""
    if len(pnls) < 2:
        return None
    downside = pnls[pnls < 0]
    if len(downside) < 1:
        return None  # no losing trades -> undefined / infinite
    dd = float(np.sqrt(np.mean(downside ** 2)))
    if dd == 0:
        return None
    return round(float(np.mean(pnls)) / dd, 4)


def metrics(rows: list[TradeRow], recent_dates: set[str]) -> dict:
    if not rows:
        return {"n": 0}
    pnl = np.array([r.pnl for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())

    oos_rows = [r for r in rows if int(r.date[:4]) == OOS_YEAR]
    recent_rows = [r for r in rows if r.date in recent_dates]

    def _exp(rs):
        return round(float(np.mean([r.pnl for r in rs])), 2) if rs else None

    def _tot(rs):
        return round(float(np.sum([r.pnl for r in rs])), 2) if rs else 0.0

    def _wr(rs):
        return round(100 * float(np.mean([1 if r.pnl > 0 else 0 for r in rs])), 1) if rs else None

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(r.date)].append(r.pnl)
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["exp"] > 0)

    oos_pnl = np.array([r.pnl for r in oos_rows], float) if oos_rows else np.array([])
    rec_pnl = np.array([r.pnl for r in recent_rows], float) if recent_rows else np.array([])

    return {
        "n": n,
        "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2),
        "total_dollar": round(float(pnl.sum()), 2),
        "book_maxdd": _book_maxdd(rows),
        "sharpe": _sharpe(pnl),
        "sortino": _sortino(pnl),
        # FULL-OOS-2026
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "oos_wr": _wr(oos_rows), "oos_maxdd": _book_maxdd(oos_rows),
        "oos_sharpe": _sharpe(oos_pnl), "oos_sortino": _sortino(oos_pnl),
        # RECENT ~25-day window (the chop/RED regime)
        "recent_n": len(recent_rows), "recent_exp": _exp(recent_rows),
        "recent_total": _tot(recent_rows), "recent_wr": _wr(recent_rows),
        "recent_maxdd": _book_maxdd(recent_rows),
        "recent_sharpe": _sharpe(rec_pnl), "recent_sortino": _sortino(rec_pnl),
        "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "exit_hist": {k: int(v) for k, v in sorted(
            {r.exit_reason: sum(1 for x in rows if x.exit_reason == r.exit_reason)
             for r in rows}.items())},
    }


def _delta(a, b):
    """a - b, None-safe (returns None if either side is None)."""
    if a is None or b is None:
        return None
    return round(a - b, 2)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[spreadify-2] loading SPY+VIX (through 2026-06-15) ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 6, 15))
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_days = len(days)
    print(f"[spreadify-2] SPY bars={len(spy)} days={n_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    # #2 detector (byte-for-byte)
    signals = detect_signals(days)
    sig_dates = sorted({str(spy.iloc[s.bar_idx]['timestamp_et'].date()) for s in signals})
    side_ct = {"C": sum(1 for s in signals if s.side == "C"),
               "P": sum(1 for s in signals if s.side == "P")}
    # recent ~25-trading-day window = the last RECENT_WINDOW_DAYS distinct trading days
    # in the data that carry a signal (the chop/RED regime the thesis targets).
    all_trading_dates = sorted({str(dc.date) for dc in days})
    recent_trading_dates = set(all_trading_dates[-RECENT_WINDOW_DAYS:])
    recent_window = (all_trading_dates[-RECENT_WINDOW_DAYS], all_trading_dates[-1])
    print(f"[spreadify-2] #2 signals={len(signals)} on {len(sig_dates)} days side={side_ct}",
          flush=True)
    print(f"[spreadify-2] recent window = last {RECENT_WINDOW_DAYS} trading days "
          f"{recent_window[0]}..{recent_window[1]}", flush=True)

    # ── Baselines (long single leg) per tier ────────────────────────────────
    baselines = {}
    for off, lbl in BASELINE_OFFSETS:
        rows, cov = simulate_single_leg(signals, spy, ribbon, vix,
                                        strike_offset=off, premium_stop_pct=SURV_PREMIUM_STOP)
        m = metrics(rows, recent_trading_dates)
        baselines[lbl] = {"strike_offset": off, "tier": lbl, "coverage": cov, "metrics": m}
        print(f"\n[BASELINE {lbl} off={off:+d}] n={m.get('n')} exp=${m.get('exp_dollar')} "
              f"maxDD=${m.get('book_maxdd')} Sharpe={m.get('sharpe')} Sortino={m.get('sortino')} "
              f"| OOS exp=${m.get('oos_exp')} (n={m.get('oos_n')}) maxDD=${m.get('oos_maxdd')} "
              f"| RECENT exp=${m.get('recent_exp')} (n={m.get('recent_n')}) "
              f"total=${m.get('recent_total')} maxDD=${m.get('recent_maxdd')}", flush=True)

    # ── Debit-spread geometry grid ──────────────────────────────────────────
    grid = []
    for loff, llbl in LONG_OFFSETS:
        for w in SHORT_WIDTHS:
            rows, cov = simulate_spread(signals, spy, long_offset=loff, short_width=w)
            m = metrics(rows, recent_trading_dates)
            # baseline at the matching long-leg tier (ATM->ATM, ITM1->ITM2 fallback, ITM2->ITM2)
            base_lbl = "ATM" if loff == 0 else "ITM2"
            base_m = baselines[base_lbl]["metrics"]
            deltas = {
                "vs_baseline_tier": base_lbl,
                "exp_delta": _delta(m.get("exp_dollar"), base_m.get("exp_dollar")),
                "maxdd_delta": _delta(m.get("book_maxdd"), base_m.get("book_maxdd")),
                "sharpe_delta": _delta(m.get("sharpe"), base_m.get("sharpe")),
                "sortino_delta": _delta(m.get("sortino"), base_m.get("sortino")),
                "oos_exp_delta": _delta(m.get("oos_exp"), base_m.get("oos_exp")),
                "oos_maxdd_delta": _delta(m.get("oos_maxdd"), base_m.get("oos_maxdd")),
                "oos_sharpe_delta": _delta(m.get("oos_sharpe"), base_m.get("oos_sharpe")),
                "recent_exp_delta": _delta(m.get("recent_exp"), base_m.get("recent_exp")),
                "recent_total_delta": _delta(m.get("recent_total"), base_m.get("recent_total")),
                "recent_maxdd_delta": _delta(m.get("recent_maxdd"), base_m.get("recent_maxdd")),
                "recent_sharpe_delta": _delta(m.get("recent_sharpe"), base_m.get("recent_sharpe")),
            }
            cell = {
                "long_offset": loff, "long_tier": llbl, "short_width": w,
                "label": f"long{llbl}_w{w}",
                "coverage": cov, "metrics": m, "deltas": deltas,
            }
            grid.append(cell)
            print(f"  [SPREAD long{llbl}(off={loff:+d}) w={w}] n={m.get('n')} "
                  f"exp=${m.get('exp_dollar')} maxDD=${m.get('book_maxdd')} "
                  f"Sharpe={m.get('sharpe')} Sortino={m.get('sortino')} "
                  f"| OOS exp=${m.get('oos_exp')}(n={m.get('oos_n')}) "
                  f"| RECENT exp=${m.get('recent_exp')}(n={m.get('recent_n')}) "
                  f"tot=${m.get('recent_total')} maxDD=${m.get('recent_maxdd')} "
                  f"|| dE=${deltas['exp_delta']} dMaxDD=${deltas['maxdd_delta']} "
                  f"dSharpe={deltas['sharpe_delta']} dRecentTot=${deltas['recent_total_delta']}",
                  flush=True)

    # ── Pick the BEST cell ───────────────────────────────────────────────────
    # Selection per the GATE: prefer cells that are OOS-positive AND posQ>=4 AND
    # expectancy>0, then rank by the RISK-ADJUSTED + recency objective:
    #   score = (recent maxDD reduction) + (recent total improvement) + 1000*(sharpe delta)
    # i.e. reward smaller recent drawdown / less recent bleed / better per-trade Sharpe.
    def _eligible(c):
        m = c["metrics"]
        return (m.get("n", 0) >= 20 and (m.get("exp_dollar") or -1) > 0
                and (m.get("oos_exp") or -1) > 0 and m.get("positive_quarters_n", 0) >= 4)

    def _score(c):
        d = c["deltas"]
        mdd = d.get("recent_maxdd_delta") or 0.0      # negative = drawdown reduced (good)
        rtot = d.get("recent_total_delta") or 0.0     # positive = less recent bleed (good)
        sh = d.get("sharpe_delta") or 0.0
        return (-mdd) + rtot + 1000.0 * sh

    eligible = [c for c in grid if _eligible(c)]
    pool = eligible if eligible else grid
    best = max(pool, key=_score) if pool else None

    primary_baseline = baselines["ITM2"]  # the live Bold survivor tier = primary comparison

    summary = {
        "edge": "vwap_reclaim_failed_break (#2)",
        "experiment": "spread-ify: directional debit-spread A/B vs long-single-leg baseline",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "trading_days": n_days,
        "recent_window": {"days": RECENT_WINDOW_DAYS,
                          "start": recent_window[0], "end": recent_window[1]},
        "oos_split": f"IS=2025 / OOS={OOS_YEAR} (calendar-year)",
        "detector": ("BYTE-FOR-BYTE _sub_struct_vwap_reclaim_failed_break.detect_signals "
                     "(one causal entry/day: morning-trend VWAP-reclaim after a FAILED "
                     "counter-trend VWAP break)"),
        "fills_authority": ("real OPRA: long-leg via lib.simulator_real.simulate_trade_real; "
                            "debit spread via lib.simulator_debit.simulate_debit_trade "
                            "(both reuse the same OPRA loader; C1)"),
        "config": {
            "baseline_premium_stop_pct": SURV_PREMIUM_STOP,
            "spread_stop_frac_of_debit": SPREAD_STOP_FRAC,
            "spread_pt_frac_of_debit": SPREAD_PT_FRAC,
            "qty": QTY,
            "baseline_offsets": [o for o, _ in BASELINE_OFFSETS],
            "spread_long_offsets": [o for o, _ in LONG_OFFSETS],
            "spread_short_widths": SHORT_WIDTHS,
        },
        "n_signals": len(signals),
        "signal_side_count": side_ct,
        "baselines": baselines,
        "spread_grid": grid,
        "best_cell": best,
        "primary_baseline_tier": "ITM2",
        "GATE": {
            "1_expectancy_positive": "spread exp/tr still > 0 (capped but positive)",
            "2_risk_adjusted_L175": "per-trade Sharpe holds/improves AND Sortino holds AND maxDD materially better",
            "3_recency": "reduces/flips the recent ~25-day RED bleed vs long-single-leg baseline",
            "4_no_regression": "the days it changes net-improve",
            "5_oos_posq": "OOS-positive + positive_quarters >= 4",
        },
        "DISCLOSURE": {
            "capped_upside": ("the short leg CAPS upside, so per-trade EV is expected to FALL; "
                              "the hunted win is risk-adjusted (lower maxDD/variance) + recency."),
            "band_constraint": ("debit spreads are near-ATM/narrow -> fit the +/-$5 OPRA cache band; "
                                "any leg outside the band is a cache_miss (skipped+counted)."),
            "spy_vs_option": "real OPRA fills; SPY-direction != option edge (C3/L58).",
            "strike_tier_caveat": "C29 — gates do not transfer across strike tiers; reported per tier.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[spreadify-2] wrote {OUT}", flush=True)

    print("\n=== SPREAD-IFY #2 vwap_reclaim VERDICT ===")
    bm = primary_baseline["metrics"]
    print(f"BASELINE ITM2 long-single-leg: n={bm.get('n')} exp=${bm.get('exp_dollar')} "
          f"maxDD=${bm.get('book_maxdd')} Sharpe={bm.get('sharpe')} "
          f"OOS exp=${bm.get('oos_exp')} RECENT exp=${bm.get('recent_exp')} "
          f"RECENT total=${bm.get('recent_total')} RECENT maxDD=${bm.get('recent_maxdd')}")
    if best:
        m = best["metrics"]; d = best["deltas"]
        print(f"BEST SPREAD {best['label']}: n={m.get('n')} exp=${m.get('exp_dollar')} "
              f"maxDD=${m.get('book_maxdd')} Sharpe={m.get('sharpe')} Sortino={m.get('sortino')} "
              f"OOS exp=${m.get('oos_exp')} RECENT exp=${m.get('recent_exp')} "
              f"RECENT total=${m.get('recent_total')} RECENT maxDD=${m.get('recent_maxdd')}")
        print(f"DELTAS vs {d['vs_baseline_tier']} baseline: dExp=${d['exp_delta']} "
              f"dMaxDD=${d['maxdd_delta']} dSharpe={d['sharpe_delta']} dSortino={d['sortino_delta']} "
              f"dOOSexp=${d['oos_exp_delta']} dRecentExp=${d['recent_exp_delta']} "
              f"dRecentTotal=${d['recent_total_delta']} dRecentMaxDD=${d['recent_maxdd_delta']}")
    else:
        print("NO spread cell produced trades.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
